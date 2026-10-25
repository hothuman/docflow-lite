"""Short per-thread connections and atomic, versioned SQLite migrations."""
from contextlib import contextmanager,closing
from pathlib import Path
import sqlite3
from uuid import uuid4
from .validation import ServiceError,now

SCHEMA_VERSION=4
MIGRATIONS={1:[
 '''CREATE TABLE clients(id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, legal_name TEXT NOT NULL DEFAULT '', contact TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN(0,1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
 '''CREATE TABLE equipment(id TEXT PRIMARY KEY, number TEXT NOT NULL COLLATE NOCASE UNIQUE, manufacturer TEXT NOT NULL DEFAULT '', model TEXT NOT NULL, kind TEXT NOT NULL DEFAULT '', serial TEXT NOT NULL DEFAULT '', owner_id TEXT NOT NULL REFERENCES clients(id), identifiers TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN(0,1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
 '''CREATE TABLE repair_orders(id TEXT PRIMARY KEY, number TEXT NOT NULL COLLATE NOCASE UNIQUE, equipment_id TEXT NOT NULL REFERENCES equipment(id), client_id TEXT NOT NULL REFERENCES clients(id), received_at TEXT NOT NULL, complaint TEXT NOT NULL DEFAULT '', accessories TEXT NOT NULL DEFAULT '', condition TEXT NOT NULL DEFAULT '', defects TEXT NOT NULL DEFAULT '', plan TEXT NOT NULL DEFAULT '', approval TEXT NOT NULL DEFAULT 'Не согласовано', approval_note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'accepted', started_at TEXT NOT NULL DEFAULT '', completed_at TEXT NOT NULL DEFAULT '', issued_at TEXT NOT NULL DEFAULT '', issued_accessories TEXT NOT NULL DEFAULT '', handover TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', discount_cents INTEGER NOT NULL DEFAULT 0 CHECK(discount_cents>=0), revision INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
 '''CREATE TABLE repair_items(id TEXT PRIMARY KEY, repair_id TEXT NOT NULL REFERENCES repair_orders(id), kind TEXT NOT NULL CHECK(kind IN('work','part')), name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', quantity TEXT NOT NULL, unit TEXT NOT NULL, price_cents INTEGER NOT NULL CHECK(price_cents>=0), total_cents INTEGER NOT NULL CHECK(total_cents>=0), position INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '')''',
 '''CREATE TABLE payments(id TEXT PRIMARY KEY, repair_id TEXT NOT NULL REFERENCES repair_orders(id), amount_cents INTEGER NOT NULL CHECK(amount_cents>0), occurred_at TEXT NOT NULL, method TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN('payment','refund')), comment TEXT NOT NULL DEFAULT '', voided INTEGER NOT NULL DEFAULT 0 CHECK(voided IN(0,1)), void_reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)''',
 '''CREATE TABLE repair_status_history(id INTEGER PRIMARY KEY, repair_id TEXT NOT NULL REFERENCES repair_orders(id), old_status TEXT NOT NULL, new_status TEXT NOT NULL, changed_at TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', source TEXT NOT NULL)''',
 '''CREATE TABLE attachments(id TEXT PRIMARY KEY, repair_id TEXT NOT NULL REFERENCES repair_orders(id), kind TEXT NOT NULL, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE, size INTEGER NOT NULL, mime TEXT NOT NULL, sha256 TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)''',
 '''CREATE TABLE generated_documents(id TEXT PRIMARY KEY, repair_id TEXT NOT NULL REFERENCES repair_orders(id), kind TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL, path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, template TEXT NOT NULL, UNIQUE(repair_id,kind,version))''',
 '''CREATE TABLE operations(id INTEGER PRIMARY KEY, entity TEXT NOT NULL, entity_id TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL)'''
],2:[
 'CREATE INDEX repairs_equipment ON repair_orders(equipment_id,received_at)',
 'CREATE INDEX repairs_state ON repair_orders(status,received_at)',
 'CREATE INDEX items_repair ON repair_items(repair_id,position)',
 'CREATE INDEX payments_repair ON payments(repair_id)',
 'CREATE INDEX attachments_repair ON attachments(repair_id)'
],3:[
 '''CREATE TABLE organization_profiles(id TEXT PRIMARY KEY, name TEXT NOT NULL, data_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
 '''CREATE TABLE service_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)''',
 '''CREATE TABLE managed_files(path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, size INTEGER NOT NULL, kind TEXT NOT NULL)''',
 'ALTER TABLE repair_orders ADD COLUMN profile_id TEXT REFERENCES organization_profiles(id)',
 'ALTER TABLE repair_items RENAME TO repair_items_v2',
 '''CREATE TABLE repair_items(id TEXT PRIMARY KEY, repair_id TEXT NOT NULL REFERENCES repair_orders(id), kind TEXT NOT NULL CHECK(kind IN('work','part','delivery','other')), name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', quantity TEXT NOT NULL, unit TEXT NOT NULL, price_cents INTEGER NOT NULL CHECK(price_cents>=0), total_cents INTEGER NOT NULL CHECK(total_cents>=0), position INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '')''',
 'INSERT INTO repair_items SELECT * FROM repair_items_v2',
 'DROP TABLE repair_items_v2',
 'CREATE INDEX items_repair ON repair_items(repair_id,position)',
 'CREATE INDEX items_repair_kind ON repair_items(repair_id,kind)',
 '''CREATE TABLE estimate_drafts(repair_id TEXT PRIMARY KEY REFERENCES repair_orders(id), lines_json TEXT NOT NULL, discount_cents INTEGER NOT NULL CHECK(discount_cents>=0), comment TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL)''',
 '''CREATE TABLE estimate_versions(id TEXT PRIMARY KEY, repair_id TEXT NOT NULL REFERENCES repair_orders(id), kind TEXT NOT NULL CHECK(kind IN('preliminary','final')), version INTEGER NOT NULL, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, prepared_by TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL, source_revision INTEGER NOT NULL, request_id TEXT UNIQUE, UNIQUE(repair_id,kind,version))''',
 '''CREATE TABLE estimate_events(id INTEGER PRIMARY KEY, estimate_id TEXT NOT NULL REFERENCES estimate_versions(id), action TEXT NOT NULL CHECK(action IN('prepared','sent','approved','rejected','withdrawn')), actor TEXT NOT NULL, comment TEXT NOT NULL, occurred_at TEXT NOT NULL)''',
 '''CREATE TRIGGER immutable_estimate_update BEFORE UPDATE ON estimate_versions BEGIN SELECT RAISE(ABORT,'Estimate snapshots are immutable'); END''',
 '''CREATE TRIGGER immutable_estimate_delete BEFORE DELETE ON estimate_versions BEGIN SELECT RAISE(ABORT,'Estimate snapshots are immutable'); END''',
 '''CREATE TRIGGER immutable_estimate_event_update BEFORE UPDATE ON estimate_events BEGIN SELECT RAISE(ABORT,'Estimate history is immutable'); END''',
 '''CREATE TRIGGER immutable_estimate_event_delete BEFORE DELETE ON estimate_events BEGIN SELECT RAISE(ABORT,'Estimate history is immutable'); END''',
 'CREATE INDEX estimates_repair ON estimate_versions(repair_id,kind,version)',
 '''CREATE TABLE import_sources(id TEXT PRIMARY KEY, name TEXT NOT NULL, file_sha256 TEXT NOT NULL, sheet TEXT NOT NULL, mapping_json TEXT NOT NULL, created_at TEXT NOT NULL)''',
 '''CREATE TABLE import_records(id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES import_sources(id), source_key TEXT NOT NULL, record_sha256 TEXT NOT NULL, repair_id TEXT NOT NULL REFERENCES repair_orders(id), rows_json TEXT NOT NULL, imported_at TEXT NOT NULL, UNIQUE(source_id,source_key))''',
 '''CREATE TABLE import_runs(id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES import_sources(id), report_json TEXT NOT NULL, created_at TEXT NOT NULL)''',
 'ALTER TABLE generated_documents ADD COLUMN metadata_json TEXT NOT NULL DEFAULT \'{}\'',
 'CREATE INDEX imports_repair ON import_records(repair_id)'
],4:[
 'CREATE INDEX estimate_events_version ON estimate_events(estimate_id,id)',
 'CREATE INDEX repairs_received ON repair_orders(received_at)',
]}

class Database:
    def __init__(self,path):
        self.path=Path(path)
        if self.path.is_symlink(): raise ServiceError('База не должна быть символической ссылкой')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        try:
            with self.connection() as c:
                if c.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise ServiceError('База повреждена; используйте проверенную копию')
                if c.execute('PRAGMA foreign_key_check').fetchall(): raise ServiceError('Нарушены связи базы; исходные данные не изменены')
                version=c.execute('PRAGMA user_version').fetchone()[0]
                if version>SCHEMA_VERSION: raise ServiceError('База создана более новой версией программы')
                if version and version<SCHEMA_VERSION:
                    backup=self.path.with_name(self.path.name+f'.before-v{version+1}-{uuid4().hex}.bak')
                    with backup.open('xb'): pass
                    try:
                        with closing(sqlite3.connect(backup)) as dest:c.backup(dest)
                    except Exception:
                        backup.unlink(missing_ok=True)
                        raise
                c.execute('BEGIN IMMEDIATE')
                try:
                    for v in range(version+1,SCHEMA_VERSION+1):
                        for statement in MIGRATIONS[v]:c.execute(statement)
                        c.execute(f'PRAGMA user_version={v}')
                    if c.execute('PRAGMA foreign_key_check').fetchall(): raise ServiceError('Миграция нарушает связи; выполнен откат')
                    c.commit()
                except Exception:c.rollback();raise
                c.execute('PRAGMA journal_mode=WAL')
        except sqlite3.Error as exc: raise ServiceError('Не удалось открыть или обновить SQLite. Исходную базу не заменяли: '+str(exc)) from exc

    @contextmanager
    def connection(self,write=False):
        c=None
        try:
            c=sqlite3.connect(self.path,timeout=10)
            c.row_factory=sqlite3.Row
            c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=10000')
            if write:c.execute('BEGIN IMMEDIATE')
            yield c
            if write:c.commit()
        except sqlite3.IntegrityError as exc:
            if c:c.rollback()
            raise ServiceError('Номер уже существует или нарушена связь записей') from exc
        except sqlite3.Error as exc:
            if c:c.rollback()
            raise ServiceError('Ошибка локальной базы: '+str(exc)) from exc
        except Exception:
            if c:c.rollback()
            raise
        finally:
            if c:c.close()
