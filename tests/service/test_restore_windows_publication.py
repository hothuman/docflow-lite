import errno
from pathlib import Path
import pytest
from docflow.service import backup
from docflow.service.repository import ServiceStore
from docflow.service.validation import ServiceError


def denied():
    error=PermissionError(errno.EACCES,'QA temporary lock');error.winerror=5;return error


def test_transient_publication_lock_retries_the_same_atomic_rename(tmp_path,monkeypatch):
    stage=tmp_path/'stage';stage.mkdir();(stage/'data').write_bytes(b'QA preserve');dest=tmp_path/'restored';calls=[];waits=[]
    rename=backup.os.rename
    def blocked_once(a,b):
        calls.append((a,b))
        if len(calls)==1:raise denied()
        return rename(a,b)
    monkeypatch.setattr(backup.os,'rename',blocked_once);monkeypatch.setattr(backup.time,'sleep',waits.append)
    backup._publish_windows(stage,dest)
    assert calls==[(stage,dest)]*2 and waits==[.05] and (dest/'data').read_bytes()==b'QA preserve'


def test_publication_retry_never_replaces_concurrent_target(tmp_path,monkeypatch):
    stage=tmp_path/'stage';stage.mkdir();dest=tmp_path/'target';calls=[]
    def race(a,b):
        calls.append(1);dest.mkdir();(dest/'marker').write_bytes(b'other project');raise denied()
    monkeypatch.setattr(backup.os,'rename',race);monkeypatch.setattr(backup.time,'sleep',lambda _:None)
    with pytest.raises(FileExistsError):backup._publish_windows(stage,dest)
    assert len(calls)==1 and stage.is_dir() and (dest/'marker').read_bytes()==b'other project'


def test_permanent_publication_denial_is_bounded(tmp_path,monkeypatch):
    stage=tmp_path/'stage';stage.mkdir();dest=tmp_path/'target';calls=[];waits=[]
    def blocked(*a):calls.append(1);raise denied()
    monkeypatch.setattr(backup.os,'rename',blocked);monkeypatch.setattr(backup.time,'sleep',waits.append)
    with pytest.raises(PermissionError):backup._publish_windows(stage,dest)
    assert len(calls)==4 and waits==[.05,.1,.2] and stage.is_dir() and not dest.exists()


def test_restore_denial_explains_access_without_calling_valid_archive_corrupt(tmp_path,monkeypatch):
    s=ServiceStore(tmp_path/'p');s.intake(client={'name':'QA'},equipment={'number':'QA-1','model':'QA'})
    archive=backup.create_backup(s,tmp_path/'backup.zip');before=archive.read_bytes();target=tmp_path/'Restored'
    def blocked(*a):raise denied()
    monkeypatch.setattr(backup,'_publish_new_tree',blocked)
    with pytest.raises(ServiceError,match='доступ|занят') as exc:backup.restore_backup(archive,target)
    assert 'поврежд' not in str(exc.value) and archive.read_bytes()==before and not target.exists()
