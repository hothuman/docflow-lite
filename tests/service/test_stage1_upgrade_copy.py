"""Opening legacy projects in GUI requires an explicit, verified separate copy."""
import hashlib
import sqlite3
import time

import pytest

from docflow.service.database import MIGRATIONS, SCHEMA_VERSION, Database
from docflow.service.project_upgrade import copy_project_for_upgrade
from docflow.service.repository import ServiceStore
from docflow.service.validation import ServiceError


def hashes(folder):
    return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}


def legacy_project(root):
    root.mkdir()
    attachment=root/'generated/OLD-NUMBER.docx';attachment.parent.mkdir();attachment.write_bytes(b'synthetic original immutable document')
    with sqlite3.connect(root/'service.db') as c:
        for version in range(1,5):
            for statement in MIGRATIONS[version]:c.execute(statement)
        c.execute('PRAGMA user_version=4')
        c.execute("INSERT INTO clients(id,kind,name,created_at,updated_at) VALUES('client','organization','Synthetic original client','2020','2020')")
        c.execute("INSERT INTO equipment(id,number,model,owner_id,created_at,updated_at) VALUES('equipment','DEVICE-7','Synthetic original model','client','2020','2020')")
        c.execute("INSERT INTO repair_orders(id,number,equipment_id,client_id,received_at,created_at,updated_at) VALUES('repair','OLD-NUMBER','equipment','client','2020-01-02','2020','2020')")
        c.execute("INSERT INTO generated_documents(id,repair_id,kind,version,created_at,path,sha256,template) VALUES('document','repair','completion',1,'2020','generated/OLD-NUMBER.docx',?,'original-template')",(hashlib.sha256(attachment.read_bytes()).hexdigest(),))
    c.close()
    return root


def test_upgrade_copy_preserves_original_files_numbers_and_document(tmp_path):
    source=legacy_project(tmp_path/'original');before=hashes(source)
    assert Database.migration_required(source/'service.db')==4
    target=copy_project_for_upgrade(source,tmp_path/'updated')
    assert hashes(source)==before
    assert Database.migration_required(target/'service.db') is None
    assert (target/'generated/OLD-NUMBER.docx').read_bytes()==(source/'generated/OLD-NUMBER.docx').read_bytes()
    store=ServiceStore(target,allow_upgrade=False)
    assert store.repairs()[0]['number']=='OLD-NUMBER'
    assert store.snapshot('repair')['client']['name']=='Synthetic original client'
    assert list(target.glob('service.db.before-v5-*.bak'))


@pytest.mark.parametrize('target_kind',['existing','inside'])
def test_upgrade_refuses_overwriting_or_nesting_under_original(tmp_path,target_kind):
    source=legacy_project(tmp_path/'original');before=hashes(source)
    target=tmp_path/'existing' if target_kind=='existing' else source/'nested'
    if target_kind=='existing':target.mkdir()
    with pytest.raises(ServiceError):copy_project_for_upgrade(source,target)
    assert hashes(source)==before


@pytest.fixture(scope='module')
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def idle(app,workspace):
    until=time.monotonic()+20
    while workspace.worker or workspace._pending_refresh:
        app.processEvents();time.sleep(.005)
        assert time.monotonic()<until
    app.processEvents()


def dispose(app,workspace):
    workspace.close()
    if workspace.project_lock:workspace.project_lock.unlock()
    workspace.deleteLater();app.processEvents()


def test_gui_cancel_legacy_open_leaves_original_and_current_project_unchanged(app,tmp_path,monkeypatch):
    import docflow.ui.service.workspace as module
    source=legacy_project(tmp_path/'legacy');before=hashes(source)
    workspace=module.ServiceWorkspace(root=tmp_path/'current');idle(app,workspace)
    try:
        current=workspace.store.root
        monkeypatch.setattr(module,'confirm',lambda *args:False)
        workspace.open_project(source);idle(app,workspace)
        assert workspace.store.root==current
        assert hashes(source)==before
        assert 'Исходный проект не изменён' in workspace.message.text()
    finally:dispose(app,workspace)


def test_gui_confirm_opens_upgraded_copy_and_retains_original(app,tmp_path,monkeypatch):
    import docflow.ui.service.workspace as module
    source=legacy_project(tmp_path/'legacy');before=hashes(source)
    destination=tmp_path/'copies';destination.mkdir()
    workspace=module.ServiceWorkspace(root=tmp_path/'current');idle(app,workspace)
    try:
        monkeypatch.setattr(module,'confirm',lambda *args:True)
        monkeypatch.setattr(module.QFileDialog,'getExistingDirectory',lambda *args:str(destination))
        workspace.open_project(source);idle(app,workspace)
        assert workspace.store.root.parent==destination
        assert workspace.store.repairs()[0]['number']=='OLD-NUMBER'
        assert hashes(source)==before
        assert Database.migration_required(workspace.store.root/'service.db') is None
        assert len(workspace.store.documents())==1
    finally:dispose(app,workspace)
