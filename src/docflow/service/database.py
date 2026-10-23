"""Short per-thread connections and atomic, versioned SQLite migrations."""
from contextlib import contextmanager,closing
from pathlib import Path
import sqlite3
from .validation import ServiceError,now

SCHEMA_VERSION=2
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
]}

class Database:
    def __init__(self,path):
        self.path=Path(path)
        if self.path.is_symlink(): raise ServiceError('База не должна быть символической ссылкой')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        try:
            with self.connection() as c:
                if c.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise ServiceError('База повреждена; используйте проверенную копию')
                version=c.execute('PRAGMA user_version').fetchone()[0]
                if version>SCHEMA_VERSION: raise ServiceError('База создана более новой версией программы')
                if version and version<SCHEMA_VERSION:
                    backup=self.path.with_name(self.path.name+f'.before-v{SCHEMA_VERSION}-{now().replace(":","-")}.bak')
                    with closing(sqlite3.connect(backup)) as dest:c.backup(dest)
                c.execute('BEGIN IMMEDIATE')
                try:
                    for v in range(version+1,SCHEMA_VERSION+1):
                        for statement in MIGRATIONS[v]:c.execute(statement)
                        c.execute(f'PRAGMA user_version={v}')
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
