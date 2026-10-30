"""Project opening must settle after cancellation, errors and switching."""
import pytest
import threading
from PySide6.QtCore import QTimer, QLockFile
from docflow.service.database import Database
from docflow.service.repository import ServiceStore
from PySide6.QtWidgets import QPushButton
from test_stage1_upgrade_copy import app, legacy_project, hashes, idle, dispose
import docflow.ui.service.workspace as module


@pytest.mark.parametrize('accept_copy', [False, True])
def test_first_legacy_cancel_has_terminal_status_and_safe_actions(app, tmp_path, monkeypatch, accept_copy):
    source = legacy_project(tmp_path/'legacy')
    before = hashes(source)
    monkeypatch.setattr(module, 'confirm', lambda *args: accept_copy)
    monkeypatch.setattr(module.QFileDialog, 'getExistingDirectory', lambda *args: '')
    workspace = module.ServiceWorkspace(root=source)
    idle(app, workspace)
    try:
        assert workspace.worker is None
        assert workspace.store is None
        assert hashes(source) == before
        assert 'Открываю проект' not in workspace.location.text()
        assert 'Проект не открыт' in workspace.location.text()
        for index in range(workspace.tabs.count()):
            workspace.tabs.setCurrentIndex(index)
            app.processEvents()
        add = next(b for b in workspace.toolbars['clients'].findChildren(QPushButton) if b.text() == 'Добавить')
        assert not add.isEnabled()
        assert workspace.open_project_button.isEnabled()
        assert workspace.new_project_button.isEnabled()
        assert workspace.restore_project_button.isEnabled()
    finally:
        dispose(app, workspace)


def test_clean_first_open_and_create_client_from_form(app, tmp_path):
    workspace=module.ServiceWorkspace(root=tmp_path/'new');idle(app,workspace)
    try:
        assert workspace.project_state=='opened'
        assert workspace.location.text()=='Проект: new'
        assert not workspace._project_busy
        def enter():
            dialog=app.activeModalWidget()
            dialog.fields['name'].setText('Synthetic new client');dialog.accept()
        QTimer.singleShot(20,enter);workspace.new_client();idle(app,workspace)
        assert workspace.store.clients()[0]['name']=='Synthetic new client'
        assert workspace.views['clients'].proxy.rowCount()==1
    finally:dispose(app,workspace)


@pytest.mark.parametrize('accept_copy',[False,True])
def test_cancel_switch_preserves_current_project_and_its_data(app,tmp_path,monkeypatch,accept_copy):
    legacy=legacy_project(tmp_path/'B');before=hashes(legacy)
    workspace=module.ServiceWorkspace(root=tmp_path/'A');idle(app,workspace)
    try:
        client=workspace.store.save_client({'name':'Synthetic A'})
        workspace.refresh();idle(app,workspace)
        current=workspace.store;lock=workspace.project_lock
        monkeypatch.setattr(module,'confirm',lambda *args:accept_copy)
        monkeypatch.setattr(module.QFileDialog,'getExistingDirectory',lambda *args:'')
        workspace.open_project(legacy);idle(app,workspace)
        assert workspace.store is current and workspace.project_lock is lock
        assert workspace.location.text().startswith('Проект: A')
        assert 'Открываю проект' not in workspace.location.text()
        assert workspace.cache['clients'][0]['id']==client
        assert workspace.views['clients'].proxy.rowCount()==1
        assert workspace.store.save_client({'name':'Still A'})
        assert hashes(legacy)==before
    finally:dispose(app,workspace)


def test_busy_project_retries_without_restart(app,tmp_path):
    root=tmp_path/'locked';ServiceStore(root)
    lock=QLockFile(str(root/'.docflow-service.lock'));assert lock.tryLock(0)
    before=hashes(root)
    workspace=module.ServiceWorkspace(root=root);idle(app,workspace)
    try:
        assert workspace.project_state=='locked' and workspace.store is None
        assert 'занят' in workspace.location.text().lower()
        assert hashes(root)==before
        lock.unlock();workspace.open_project(root);idle(app,workspace)
        assert workspace.project_state=='opened' and workspace.store.root==root
    finally:lock.unlock();dispose(app,workspace)


@pytest.mark.parametrize('kind',['corrupt','permission','callback'])
def test_error_settles_and_can_retry(app,tmp_path,monkeypatch,kind):
    root=tmp_path/'problem';root.mkdir()
    warnings=[];monkeypatch.setattr(module.QMessageBox,'warning',lambda *args:warnings.append(args[-1]))
    original_preflight=Database.migration_required
    if kind=='corrupt':(root/'service.db').write_bytes(b'synthetic invalid database')
    elif kind=='permission':
        def no_access(path):raise PermissionError('PRIVATE_PATH_SENTINEL')
        monkeypatch.setattr(Database,'migration_required',no_access)
    else:
        original=module.ServiceWorkspace._install_project_data
        def fail_once(self,data):
            monkeypatch.setattr(module.ServiceWorkspace,'_install_project_data',original)
            raise RuntimeError('PRIVATE_CALLBACK_SENTINEL')
        monkeypatch.setattr(module.ServiceWorkspace,'_install_project_data',fail_once)
    before=hashes(root)
    workspace=module.ServiceWorkspace(root=root);idle(app,workspace)
    try:
        assert workspace.project_state=='error' and workspace.store is None
        assert workspace.worker is None and not workspace._project_busy
        assert 'Ошибка' in workspace.location.text() and 'Открываю проект' not in workspace.location.text()
        assert warnings and 'Операция выполнена' not in workspace.message.text()
        if kind!='callback':assert hashes(root)==before
        monkeypatch.setattr(Database,'migration_required',original_preflight)
        workspace.open_project(tmp_path/'retry');idle(app,workspace)
        assert workspace.project_state=='opened' and workspace.store.root.name=='retry'
    finally:dispose(app,workspace)


def test_failed_copy_or_install_keeps_A_and_unlocks_candidate(app,tmp_path,monkeypatch):
    import docflow.service.project_upgrade as upgrade
    legacy=legacy_project(tmp_path/'B');before=hashes(legacy)
    copies=tmp_path/'copies';copies.mkdir()
    monkeypatch.setattr(module.QMessageBox,'warning',lambda *args:None)
    monkeypatch.setattr(module,'confirm',lambda *args:True)
    monkeypatch.setattr(module.QFileDialog,'getExistingDirectory',lambda *args:str(copies))
    workspace=module.ServiceWorkspace(root=tmp_path/'A');idle(app,workspace)
    try:
        workspace.store.save_client({'name':'Synthetic A'});workspace.refresh();idle(app,workspace)
        current=workspace.store;cache=workspace.cache
        original=upgrade.copy_project_for_upgrade
        def fail(*args):raise OSError('Synthetic disk failure')
        monkeypatch.setattr(upgrade,'copy_project_for_upgrade',fail)
        workspace.open_project(legacy);idle(app,workspace)
        assert workspace.store is current and workspace.cache==cache
        assert workspace.location.text().startswith('Проект: A') and workspace.project_state=='error'
        assert hashes(legacy)==before
        monkeypatch.setattr(upgrade,'copy_project_for_upgrade',original)
        install=workspace._install_project_data
        def broken(data):
            workspace._install_project_data=install
            raise RuntimeError('Synthetic callback failure')
        monkeypatch.setattr(workspace,'_install_project_data',broken)
        workspace.open_project(tmp_path/'candidate');idle(app,workspace)
        assert workspace.store is current and workspace.cache==cache
        assert workspace.project_lock.isLocked()
        lock=QLockFile(str(tmp_path/'candidate/.docflow-service.lock'))
        assert lock.tryLock(0);lock.unlock()
        workspace.open_project(legacy);idle(app,workspace)
        assert workspace.store.root.parent==copies
        assert workspace.location.text()=='Проект: '+workspace.store.root.name
        assert workspace.store.documents()[0]['path']=='generated/OLD-NUMBER.docx'
        assert hashes(legacy)==before
    finally:dispose(app,workspace)


def test_every_business_entry_is_safe_without_store(app,tmp_path,monkeypatch):
    source=legacy_project(tmp_path/'legacy');before=hashes(source)
    monkeypatch.setattr(module,'confirm',lambda *args:False)
    monkeypatch.setattr(module.QFileDialog,'getOpenFileName',lambda *args:pytest.fail('Unexpected file picker'))
    monkeypatch.setattr(module.QFileDialog,'getSaveFileName',lambda *args:pytest.fail('Unexpected file picker'))
    workspace=module.ServiceWorkspace(root=source);idle(app,workspace)
    try:
        calls=[('start_intake',()),('search_all',()),('continue_repair',()),('new_client',()),('edit_client',()),('new_equipment',()),('edit_equipment',()),('new_repair',()),('new_repair_for',({},)),('archive',('clients',)),('equipment_card',()),('dashboard_history',()),('diagnostics',()),('diagnose_links',()),('organization_profiles',()),('import_history',()),('import_equipment',()),('review_docx',()),('backup',()),('open_folder',()),('open_repair',('missing',)),('open_selected',('finance',)),('open_selected',('estimates',)),('open_file',()),('export_document',())]
        for name,args in calls:
            getattr(workspace,name)(*args);app.processEvents()
            assert workspace.worker is None and workspace.store is None
        for index in range(workspace.tabs.count()):
            workspace.tabs.setCurrentIndex(index);app.processEvents()
            for button in workspace.tabs.currentWidget().findChildren(QPushButton):
                if button.isEnabled():assert button in workspace._safe_project_buttons
        assert hashes(source)==before
    finally:dispose(app,workspace)


def test_slow_worker_and_fast_navigation_then_repeat_open(app,tmp_path,monkeypatch):
    release=threading.Event();started=threading.Event();original=Database.migration_required
    def held(path):started.set();assert release.wait(10);return original(path)
    monkeypatch.setattr(Database,'migration_required',held)
    workspace=module.ServiceWorkspace(root=tmp_path/'A')
    try:
        assert started.wait(5)
        for _ in range(3):
            for i in range(workspace.tabs.count()):workspace.tabs.setCurrentIndex(i);app.processEvents()
        assert workspace.project_state=='opening' and workspace.worker.isRunning()
        assert workspace.open_project(tmp_path/'ignored') is False
        assert not (tmp_path/'ignored').exists()
        release.set();idle(app,workspace)
        monkeypatch.setattr(Database,'migration_required',original)
        for name in ('B','A','B'):
            workspace.open_project(tmp_path/name)
            for i in range(workspace.tabs.count()):workspace.tabs.setCurrentIndex(i);app.processEvents()
            idle(app,workspace)
            assert workspace.project_state=='opened' and workspace.store.root.name==name
            assert workspace.location.text()=='Проект: '+name
    finally:release.set();idle(app,workspace);dispose(app,workspace)


def test_project_log_excludes_paths_and_exception_text(tmp_path,monkeypatch):
    import logging
    import docflow.ui.diagnostics as diagnostics
    logger=logging.getLogger('docflow.project');old=logger.handlers[:];logger.handlers=[]
    monkeypatch.setattr(diagnostics,'diagnostic_path',lambda:tmp_path/'technical.log')
    try:
        diagnostics.record_project_event('worker_error',PermissionError('PRIVATE_CUSTOMER_PATH'))
        for handler in logger.handlers:handler.flush()
        text=(tmp_path/'technical.log').read_text(encoding='utf-8')
        assert 'PermissionError' in text and 'worker_error' in text
        assert 'PRIVATE_CUSTOMER_PATH' not in text and 'Traceback' not in text
    finally:
        for handler in logger.handlers:handler.close()
        logger.handlers=old


@pytest.mark.parametrize('problem',['lock','wal'])
def test_legacy_source_lock_or_wal_never_changes_original(app,tmp_path,monkeypatch,problem):
    source=legacy_project(tmp_path/'source');copies=tmp_path/'copies';copies.mkdir()
    lock=None
    if problem=='lock':
        lock=QLockFile(str(source/'.docflow-service.lock'));assert lock.tryLock(0)
    else:(source/'service.db-wal').write_bytes(b'synthetic nonempty uncheckpointed WAL')
    before=hashes(source)
    monkeypatch.setattr(module,'confirm',lambda *args:True)
    monkeypatch.setattr(module.QFileDialog,'getExistingDirectory',lambda *args:str(copies))
    monkeypatch.setattr(module.QMessageBox,'warning',lambda *args:None)
    workspace=module.ServiceWorkspace(root=source);idle(app,workspace)
    try:
        assert workspace.project_state==('locked' if problem=='lock' else 'error')
        assert workspace.store is None and hashes(source)==before
        assert not list(copies.iterdir())
    finally:
        if lock:lock.unlock()
        dispose(app,workspace)


@pytest.mark.parametrize('action',['new','restore'])
def test_recovery_buttons_work_with_no_store(app,tmp_path,monkeypatch,action):
    source=legacy_project(tmp_path/'source');before=hashes(source)
    monkeypatch.setattr(module,'confirm',lambda *args:False)
    workspace=module.ServiceWorkspace(root=source);idle(app,workspace)
    try:
        parent=tmp_path/'recovery';parent.mkdir()
        monkeypatch.setattr(module.QFileDialog,'getExistingDirectory',lambda *args:str(parent))
        if action=='new':workspace.new_project_button.click()
        else:
            from docflow.service.backup import create_backup
            store=ServiceStore(tmp_path/'backup-source');store.save_client({'name':'Synthetic restored'})
            archive=create_backup(store,tmp_path/'synthetic.zip')
            monkeypatch.setattr(module.QFileDialog,'getOpenFileName',lambda *args:(str(archive),''))
            monkeypatch.setattr(module,'confirm',lambda *args:True)
            workspace.restore_project_button.click()
        idle(app,workspace)
        assert workspace.project_state=='opened' and workspace.store.root.parent==parent
        if action=='restore':assert workspace.store.clients()[0]['name']=='Synthetic restored'
        assert hashes(source)==before
    finally:dispose(app,workspace)


def test_project_result_stays_visible_in_compact_main_window(app,tmp_path,monkeypatch):
    from docflow.gui import MainWindow
    source=legacy_project(tmp_path/'legacy')
    monkeypatch.setattr(module,'confirm',lambda *args:False)
    window=MainWindow(service_root=source);window.show();window.navigate(5)
    workspace=window.service_workspace;idle(app,workspace)
    try:
        for size in ((1060,740),(820,620),(640,360)):
            window.resize(*size);app.processEvents()
            assert workspace.location.isVisible()
            assert 'Проект не открыт' in workspace.location.text()
        workspace.open_project(tmp_path/'new');idle(app,workspace)
        assert workspace.location.isVisible() and workspace.location.text()=='Проект: new'
    finally:window.close();app.processEvents()
