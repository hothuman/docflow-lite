from threading import Event

from docx import Document
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QWizard

from docflow.service.documents import generate_document
from docflow.service.repository import ServiceStore
from docflow.service.validation import ServiceError
from docflow.ui.service import backup_pages
from docflow.ui.theme import COLORS
from docflow.ui.window import MainWindow
from test_stage9_cp3_journal import wait_idle
from test_stage9_import_diagnostics import SOURCE


def test_import_marks_wrong_money_mapping_before_preview_and_opens_source_cell(tmp_path):
    window=MainWindow(service_root=tmp_path/'workshop')
    window.show();window.navigate(5)
    try:
        wait_idle(window)
        workspace=window.service_workspace
        wizard=workspace.import_history()
        assert wizard.window() is window and not wizard.isWindow()
        wizard.path.setText(str(SOURCE))
        wizard.inspect();wait_idle(window)
        wizard.next();wait_idle(window)
        assert wizard.currentId()==1
        discount=wizard.mappings['discount']
        correct=discount.currentData()
        flag_column=wizard.mapping()['payment_state']
        discount.setCurrentIndex(discount.findData(flag_column))
        assert wizard.mapping_warning.isVisible()
        assert 'Скидка' in wizard.mapping_warning.text() and flag_column in wizard.mapping_warning.text()
        assert COLORS['error'] in discount.styleSheet()
        wizard.build_statuses()
        for combo in wizard.statuses.values():combo.setCurrentIndex(combo.findData('accepted'))
        wizard.next();wait_idle(window)
        assert wizard.currentId()==2
        assert wizard.plan['counts']['error']==3 and not workspace.store.repairs()
        assert wizard.source_issue_button.isEnabled()
        wizard.source_issue_button.click()
        index=wizard.preview.currentIndex()
        assert wizard.currentId()==1
        assert wizard.source_model.headerData(index.row(),Qt.Orientation.Vertical)=='2'
        assert wizard.source_model.headerData(index.column(),Qt.Orientation.Horizontal)==flag_column
        assert index.data(Qt.ItemDataRole.ForegroundRole).name()==COLORS['error'].lower()
        assert 'known' in index.data(Qt.ItemDataRole.AccessibleDescriptionRole)
        discount.setCurrentIndex(discount.findData(correct))
        assert not wizard.mapping_warning.isVisible()
        assert index.data(Qt.ItemDataRole.AccessibleDescriptionRole) is None
    finally:
        window.close()


def test_embedded_import_cancel_remains_enabled(tmp_path):
    window=MainWindow(service_root=tmp_path/'workshop')
    window.show();window.navigate(5)
    try:
        wait_idle(window)
        wizard=window.service_workspace.import_history()
        release=Event()

        def task():
            release.wait(5)
            if wizard.cancel_event.is_set():raise ServiceError('Импорт отменён')
            raise AssertionError('Отмена не дошла до фоновой операции')

        assert wizard.run_operation(task)
        cancel=wizard.button(QWizard.WizardButton.CancelButton)
        assert cancel.isEnabled() and not wizard.currentPage().isEnabled()
        cancel.click()
        assert wizard.cancel_event.is_set()
        release.set();wait_idle(window)
        assert wizard.isVisible() and 'Импорт отменён' in wizard._errors[0].text()
    finally:
        if 'release' in locals():release.set()
        window.close()


def test_embedded_backup_names_zip_checks_integrity_and_restores_distinct_project(tmp_path, monkeypatch):
    root=tmp_path/'original'
    store=ServiceStore(root)
    first=store.intake(client={'name':'Учебный клиент'}, equipment={'number':'QA-0007','model':'Насос'})
    equipment=store.snapshot(first)['equipment']['id']
    second=store.create_repair(equipment,'QA-REPEAT','Повторное обращение')
    store.save_item(first,{'kind':'work','name':'Диагностика','quantity':'1','price':'1500'})
    store.save_item(first,{'kind':'part','name':'Уплотнение','quantity':'1','price':'350'})
    store.add_payment(first,'1000')
    document=generate_document(store,first,'completion')
    original_document=document.read_bytes()
    original_snapshot=store.snapshot(first)
    target_parent=tmp_path/'Копии'
    target_parent.mkdir()
    blocked_folder=target_parent/'Папка вместо файла.zip'
    blocked_folder.mkdir()
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *_:str(target_parent))
    window=MainWindow(service_root=root)
    window.show();window.navigate(5)
    try:
        wait_idle(window)
        workspace=window.service_workspace
        creation=workspace.backup()
        assert creation.window() is window
        creation.choose_folder()
        creation.filename.setText('../другое место.zip')
        creation.create()
        assert 'без пути' in creation.error.text()
        creation.filename.setText(blocked_folder.name)
        creation.create();wait_idle(window)
        assert 'существует папка' in creation.error.text()
        assert list(blocked_folder.iterdir())==[]
        creation.filename.setText('Резерв ремонта')
        assert 'Резерв ремонта.zip' in creation.target_label.text()
        creation.create();wait_idle(window)
        archive=target_parent/'Резерв ремонта.zip'
        assert archive.is_file() and creation.result.isVisible()
        assert archive.name==creation.result_name.text()
        assert str(target_parent) in creation.result_details.text()
        opened=[]
        monkeypatch.setattr(workspace,'open_local',opened.append)
        creation.open_location()
        assert opened==[target_parent]
        workspace.back_page()

        original_archive=archive.read_bytes()
        monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *_:(str(archive),'ZIP'))
        restore=workspace.restore()
        restore.choose_archive()
        restore.choose_folder()
        assert restore.target is None
        restore.check();wait_idle(window)
        assert 'SHA-256' in restore.verification.text()
        restore.choose_folder()
        target=restore.target
        confirmations=[]
        monkeypatch.setattr(backup_pages,'confirm',lambda *args,**kwargs:confirmations.append(args[1]) or False)
        restore.restore()
        assert str(target) in confirmations[0] and not target.exists()
        monkeypatch.setattr(backup_pages,'confirm',lambda *args,**kwargs:True)
        archive.write_bytes(original_archive+b'changed after verification')
        restore.restore();wait_idle(window)
        assert 'Архив изменился' in restore.error.text() and not target.exists()
        assert not restore.restore_button.isEnabled()
        assert workspace.store.root==root
        archive.write_bytes(original_archive)
        restore.check();wait_idle(window)
        restore.choose_folder()
        restore.restore();wait_idle(window)
        copied=workspace.store
        assert workspace.backup_result_panel.isVisible() and copied.root.name in workspace.backup_result_folder.text()
        assert copied.root!=root and copied.root.parent==target_parent
        assert copied.snapshot(first)['totals']==original_snapshot['totals']
        assert copied.snapshot(first)['totals']['balance']==85000
        assert copied.snapshot(second)['totals']['balance']==0
        recovered=copied.root/document.relative_to(root)
        assert recovered.read_bytes()==original_document
        assert Document(recovered).paragraphs
        assert store.snapshot(first)['totals']==original_snapshot['totals']
        assert document.read_bytes()==original_document and archive.read_bytes()==original_archive
    finally:
        window.close()
