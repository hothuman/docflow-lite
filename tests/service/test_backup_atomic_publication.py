import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from docflow.service import backup
from docflow.service.repository import ServiceStore
from docflow.service.validation import ServiceError


_CRASH_CHILD = """
import os
from pathlib import Path
import sys
import time

from docflow.service import backup
from docflow.service.repository import ServiceStore

root, destination, ready = (Path(value) for value in sys.argv[1:4])
phase = sys.argv[4]

def pause():
    ready.touch()
    time.sleep(60)

if phase == 'zip':
    original_write = backup.zipfile.ZipFile.write

    def write_member(archive, *args, **kwargs):
        original_write(archive, *args, **kwargs)
        archive.fp.flush()
        pause()

    backup.zipfile.ZipFile.write = write_member
else:
    # The previous code copied to an open final path. Stop it after 32 bytes.
    import shutil
    original_copy = shutil.copyfileobj

    def copy_file(source, target, *args):
        if getattr(target, 'name', None) == str(destination):
            target.write(source.read(32))
            target.flush()
            pause()
        return original_copy(source, target, *args)

    shutil.copyfileobj = copy_file

    # The atomic implementation has a single publication point.
    operation = 'rename' if os.name == 'nt' else 'link'
    original_publish = getattr(backup.os, operation)

    def publish(source, target, *args, **kwargs):
        if Path(target) == destination:
            pause()
        return original_publish(source, target, *args, **kwargs)

    setattr(backup.os, operation, publish)

backup.create_backup(ServiceStore(root), destination)
"""


def synthetic_project(path):
    store = ServiceStore(path)
    repair = store.intake(client={'name': 'QA'}, equipment={'number': 'QA-1', 'model': 'QA'})
    (store.root / 'templates').mkdir()
    (store.root / 'templates' / 'qa.txt').write_bytes(b'Synthetic project file')
    return store, repair


def project_hashes(root):
    return {
        path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob('*') if path.is_file()
    }


@pytest.mark.parametrize('phase', ['zip', 'publication'])
def test_killed_writer_never_leaves_final_zip(tmp_path, phase):
    store, repair = synthetic_project(tmp_path / 'project')
    previous = backup.create_backup(store, tmp_path / 'previous.zip')
    previous_bytes = previous.read_bytes()
    before = project_hashes(store.root)
    destination = tmp_path / 'interrupted.zip'
    ready = tmp_path / 'barrier'
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[2] / 'src')}
    child = subprocess.Popen(
        [sys.executable, '-c', _CRASH_CHILD, str(store.root), str(destination), str(ready), phase],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 20
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
    finally:
        if child.poll() is None:
            child.kill()
        _, stderr = child.communicate(timeout=10)
    assert ready.exists(), stderr.decode(errors='replace')
    assert child.returncode != 0
    assert list(tmp_path.glob('.interrupted.zip.*.tmp'))
    assert previous.read_bytes() == previous_bytes and project_hashes(store.root) == before
    remaining_size = destination.stat().st_size if destination.exists() else None
    assert remaining_size is None, f'Interrupted {phase} left {remaining_size} bytes at the final path'

    # Interrupted attempts do not reserve the name or make the project unusable.
    archive = backup.create_backup(store, destination)
    proof = backup.inspect_backup(archive)
    restored = ServiceStore(backup.restore_backup(archive, tmp_path / 'restored', expected_sha256=proof['sha256']))
    assert restored.snapshot(repair) == store.snapshot(repair)
    assert project_hashes(store.root) == before and previous.read_bytes() == previous_bytes


def test_backup_publish_is_verified_and_never_overwrites_existing_zip(tmp_path):
    store, repair = synthetic_project(tmp_path / 'project')
    before = project_hashes(store.root)
    archive = backup.create_backup(store, tmp_path / 'ready.zip')
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert backup.inspect_backup(archive)['sha256'] == sha
    with pytest.raises(ServiceError, match='перезаписать'):
        backup.create_backup(store, archive)
    with pytest.raises(ServiceError, match='изменился'):
        backup.restore_backup(archive, tmp_path / 'bad-hash', expected_sha256='0' * 64)
    assert not (tmp_path / 'bad-hash').exists()
    restored = ServiceStore(backup.restore_backup(archive, tmp_path / 'restored', expected_sha256=sha))
    assert restored.snapshot(repair) == store.snapshot(repair)
    assert (restored.root / 'templates' / 'qa.txt').read_bytes() == b'Synthetic project file'
    assert not list(tmp_path.glob('.ready.zip.*.tmp'))
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == sha and project_hashes(store.root) == before


def test_backup_publish_preserves_target_created_after_verification(tmp_path, monkeypatch):
    store, _ = synthetic_project(tmp_path / 'project')
    destination = tmp_path / 'raced.zip'
    operation = 'rename' if os.name == 'nt' else 'link'
    publish = getattr(backup.os, operation)

    def publish_after_other_writer(source, target, *args, **kwargs):
        assert target == destination
        destination.write_bytes(b'Existing copy from another writer')
        return publish(source, target, *args, **kwargs)

    monkeypatch.setattr(backup.os, operation, publish_after_other_writer)
    with pytest.raises(ServiceError, match='перезаписать'):
        backup.create_backup(store, destination)
    assert destination.read_bytes() == b'Existing copy from another writer'
    assert not list(tmp_path.glob('.raced.zip.*.tmp'))

def test_backup_rejects_bad_member_before_publication(tmp_path, monkeypatch):
    store, _ = synthetic_project(tmp_path / 'project')
    before = project_hashes(store.root)
    destination = tmp_path / 'bad-member.zip'
    write = backup.zipfile.ZipFile.write

    def corrupt_member(archive, source, name):
        if name == 'templates/qa.txt':
            return archive.writestr(name, b'X' * source.stat().st_size)
        return write(archive, source, name)

    monkeypatch.setattr(backup.zipfile.ZipFile, 'write', corrupt_member)
    with pytest.raises(ServiceError, match='изменился'):
        backup.create_backup(store, destination)
    assert not destination.exists()
    assert not list(tmp_path.glob('.bad-member.zip.*.tmp'))
    assert project_hashes(store.root) == before
