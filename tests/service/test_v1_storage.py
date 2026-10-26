"""Stable gate: malformed copies must not be repaired into apparent success."""
import hashlib
import json
import sqlite3
import zipfile

import pytest

from docflow.service.backup import restore_backup
from docflow.service.database import Database, SCHEMA_VERSION
from docflow.service.validation import ServiceError
from docflow.service.attachments import safe_path


def archive_for(tmp_path, database):
    raw = database.read_bytes()
    archive = tmp_path / 'malformed.zip'
    manifest = {'format': 'docflow-service-backup-1', 'schema': SCHEMA_VERSION,
                'files': {'service.db': {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}}
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('service.db', raw)
        z.writestr('manifest.json', json.dumps(manifest))
    return archive


@pytest.mark.parametrize('damage', ['empty', 'missing_table', 'missing_trigger', 'version_mismatch'])
def test_restore_rejects_structurally_invalid_database_without_publishing(tmp_path, damage):
    path = tmp_path / 'source.db'
    if damage == 'empty':
        path.touch()
    else:
        Database(path)
        with sqlite3.connect(path) as c:
            if damage == 'missing_table':
                c.execute('DROP TABLE operations')
            elif damage == 'missing_trigger':
                c.execute('DROP TRIGGER immutable_estimate_update')
            else:
                c.execute('PRAGMA user_version=3')
        c.close()  # Commit and checkpoint WAL before taking bytes of this deliberately damaged fixture.
    archive = archive_for(tmp_path, path)
    before = archive.read_bytes()
    target = tmp_path / 'new'
    with pytest.raises(ServiceError):
        restore_backup(archive, target)
    assert not target.exists()
    assert archive.read_bytes() == before
    assert not list(tmp_path.glob('.docflow-restore-*'))


def test_open_existing_empty_database_never_initializes_over_it(tmp_path):
    path = tmp_path / 'service.db'
    path.touch()
    with pytest.raises(ServiceError):
        Database(path)
    assert path.read_bytes() == b''


@pytest.mark.parametrize('relative', ['attachments/NUL.docx', 'templates/foo./x',
                                    'attachments/a//b', 'attachments/./b', 'profiles/CON'])
def test_project_paths_reject_windows_aliases_on_every_platform(tmp_path, relative):
    with pytest.raises(ServiceError):
        safe_path(tmp_path, relative)


def test_valid_legacy_backup_is_checked_then_migrated_without_changing_original(tmp_path):
    from docflow.service.database import MIGRATIONS
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as c:
        for statement in MIGRATIONS[1]:c.execute(statement)
        c.execute("INSERT INTO clients(id,kind,name,created_at,updated_at) VALUES('legacy','organization','Synthetic legacy','x','x')")
        c.execute('PRAGMA user_version=1')
    c.close()
    archive=archive_for(tmp_path,path)
    with zipfile.ZipFile(archive) as z:
        contents={name:z.read(name) for name in z.namelist()}
    manifest=json.loads(contents['manifest.json']);manifest['schema']=1
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('service.db',contents['service.db']);z.writestr('manifest.json',json.dumps(manifest))
    before=archive.read_bytes()
    target=restore_backup(archive,tmp_path/'restored')
    with sqlite3.connect(target/'service.db') as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==SCHEMA_VERSION
        assert c.execute('SELECT name FROM clients').fetchone()[0]=='Synthetic legacy'
    c.close()
    assert archive.read_bytes()==before
    assert list(target.glob('service.db.before-*.bak'))
