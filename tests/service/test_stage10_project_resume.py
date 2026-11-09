"""Restart regression for a separately upgraded Service project."""
from docflow.ui.window import MainWindow
from test_stage1_upgrade_copy import app, hashes, idle, legacy_project


def test_restart_opens_last_successful_migrated_copy(app, tmp_path, monkeypatch):
    import docflow.ui.service.workspace as module

    original = legacy_project(tmp_path / 'original')
    before = hashes(original)
    copies = tmp_path / 'copies'
    copies.mkdir()
    prompts = []

    def confirm(*args):
        prompts.append(args)
        return False

    monkeypatch.setattr(module, 'default_root', lambda: original)
    monkeypatch.setattr(module, 'confirm', confirm)
    monkeypatch.setattr(module.QFileDialog, 'getExistingDirectory', lambda *args: str(copies))

    window = MainWindow()
    window.navigate(5)
    workspace = window.service_workspace
    idle(app, workspace)
    try:
        monkeypatch.setattr(module, 'confirm', lambda *args: True)
        workspace.open_project(original)
        idle(app, workspace)
        assert workspace.store is not None
        copy = workspace.store.root
        assert copy.parent == copies
        assert workspace.store.repairs()[0]['number'] == 'OLD-NUMBER'
    finally:
        window.close()

    prompts.clear()
    monkeypatch.setattr(module, 'confirm', confirm)
    restarted = MainWindow()
    restarted.navigate(5)
    workspace = restarted.service_workspace
    idle(app, workspace)
    try:
        assert not prompts, 'Ordinary restart offered to upgrade the original again'
        assert workspace.store is not None
        assert workspace.store.root == copy
        assert hashes(original) == before
    finally:
        restarted.close()

def test_first_run_and_disabled_resume_leave_database_and_remembered_path_alone(app, tmp_path, monkeypatch):
    import docflow.ui.service.workspace as module
    from docflow.ui.settings import LAST_PROJECT_KEY, preferences
    from test_stage1_upgrade_copy import dispose

    default = tmp_path / 'legacy-default'
    monkeypatch.setattr(module, 'default_root', lambda: default)
    first = module.ServiceWorkspace()
    try:
        assert first.store is None and first.project_state == 'not_open'
        assert first.open_project_button.isEnabled()
        assert not default.exists()
        assert not preferences().contains(LAST_PROJECT_KEY)
        first.open_project(tmp_path / 'workshop')
        idle(app, first)
        root = first.store.root
        first.settings_page.resume_project.setChecked(False)
        assert str(root) in first.settings_page.project_path.text()
    finally:
        dispose(app, first)

    second = module.ServiceWorkspace()
    try:
        idle(app, second)
        assert second.store is None
        assert not second.settings_page.resume_project.isChecked()
        assert preferences().value(LAST_PROJECT_KEY) == str(root)
        monkeypatch.setattr(module.QFileDialog, 'getExistingDirectory', lambda *args: str(root))
        second.choose_project()
        idle(app, second)
        assert second.store.root == root
    finally:
        dispose(app, second)


def test_compatible_project_reopens_with_repairs_and_document(app, tmp_path):
    from docflow.service.project_upgrade import copy_project_for_upgrade
    from docflow.ui.service.workspace import ServiceWorkspace
    from test_stage1_upgrade_copy import dispose

    root = copy_project_for_upgrade(legacy_project(tmp_path / 'legacy'), tmp_path / 'current')
    first = ServiceWorkspace(root=root)
    idle(app, first)
    assert first.store.root == root
    dispose(app, first)

    reopened = ServiceWorkspace()
    try:
        idle(app, reopened)
        assert reopened.store.root == root
        assert reopened.store.repairs()[0]['number'] == 'OLD-NUMBER'
        document, = reopened.store.documents()
        assert (root / document['path']).read_bytes() == b'synthetic original immutable document'
    finally:
        dispose(app, reopened)


def test_stale_legacy_preference_needs_explicit_copy_and_keeps_original(app, tmp_path, monkeypatch):
    import docflow.ui.service.workspace as module
    from docflow.ui.settings import LAST_PROJECT_KEY, preferences
    from test_stage1_upgrade_copy import dispose

    root = legacy_project(tmp_path / 'legacy')
    before = hashes(root)
    preferences().setValue(LAST_PROJECT_KEY, str(root))
    confirms = []
    monkeypatch.setattr(module, 'confirm', lambda *args: confirms.append(args) or False)
    workspace = module.ServiceWorkspace()
    try:
        idle(app, workspace)
        assert workspace.project_state == 'upgrade_available'
        assert not workspace.copy_project_button.isHidden()
        assert not workspace.retry_project_button.isHidden()
        assert not confirms
        workspace.copy_project_button.click()
        assert len(confirms) == 1
        assert workspace.project_state == 'cancelled'
        assert preferences().value(LAST_PROJECT_KEY) == str(root)
        assert hashes(root) == before
    finally:
        dispose(app, workspace)


def test_retry_and_manual_switch_after_missing_path_or_lock(app, tmp_path, monkeypatch):
    import docflow.ui.service.workspace as module
    from docflow.service.repository import ServiceStore
    from docflow.ui.settings import LAST_PROJECT_KEY, preferences
    from test_stage1_upgrade_copy import dispose

    root = tmp_path / 'missing'
    preferences().setValue(LAST_PROJECT_KEY, str(root))
    warnings = []
    monkeypatch.setattr(module.QMessageBox, 'warning', lambda *args: warnings.append(args))
    workspace = module.ServiceWorkspace()
    lock = module.QLockFile(str(root / '.docflow-service.lock'))
    try:
        idle(app, workspace)
        assert workspace.project_state == 'error'
        assert not root.exists()
        assert workspace.retry_project_button.isEnabled()
        assert workspace.open_project_button.isEnabled()
        ServiceStore(root)
        assert lock.tryLock(0)
        workspace.retry_project_button.click()
        idle(app, workspace)
        assert workspace.project_state == 'locked'
        lock.unlock()
        workspace.retry_project_button.click()
        idle(app, workspace)
        assert workspace.project_state == 'opened'
        assert workspace.store.root == root
        assert not warnings

        invalid = tmp_path / 'invalid'
        invalid.mkdir()
        (invalid / 'service.db').write_bytes(b'broken SQLite')
        monkeypatch.setattr(module.QFileDialog, 'getExistingDirectory', lambda *args: str(invalid))
        workspace.choose_project()
        idle(app, workspace)
        assert workspace.project_state == 'error'
        assert workspace.store.root == root
        assert workspace.project_lock.isLocked()
        assert preferences().value(LAST_PROJECT_KEY) == str(root)
        assert (invalid / 'service.db').read_bytes() == b'broken SQLite'
    finally:
        lock.unlock()
        dispose(app, workspace)


def test_disappearing_database_is_never_recreated_in_existing_store(tmp_path):
    import pytest
    from docflow.service.repository import ServiceStore
    from docflow.service.validation import ServiceError

    store = ServiceStore(tmp_path)
    existing = ServiceStore(tmp_path, require_existing=True)
    store.db.path.unlink()
    with pytest.raises(ServiceError):
        existing.repairs()
    assert not store.db.path.exists()
