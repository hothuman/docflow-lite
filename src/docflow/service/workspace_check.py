"""Exercise the single-window routes on an isolated synthetic project."""
import hashlib
from pathlib import Path
import time

from docx import Document
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from ..ui.service.forms import FieldsDialog
from ..ui.service.history import HistoryComparison, HistoryPage
from ..ui.service.repair_editor import RepairPage
from ..ui.window import MainWindow
from .backup import create_backup, inspect_backup, restore_backup
from .repository import ServiceStore


def exercise(app, output, *, stage10=True):
    output = Path(output)
    output.mkdir(parents=True)
    window = MainWindow(service_root=output/'Учебная мастерская')
    window.resize(1366, 768)
    window.show()
    window.navigate(5)
    workspace = window.service_workspace
    work, part, paid = (2000, 450, 1600) if stage10 else (1500, 350, 1000)
    total = work+part
    checks = []
    layout_samples = {}

    def idle():
        deadline = time.monotonic()+40
        while workspace.worker or workspace._pending_refresh:
            app.processEvents()
            time.sleep(.005)
            if time.monotonic()>deadline:
                raise AssertionError(workspace.message.text())
        app.processEvents()

    def inside(cls):
        page = workspace.current_page
        assert isinstance(page, cls), type(page)
        assert page.window() is window and not page.isWindow() and page.isVisible()
        assert QApplication.activeModalWidget() is None
        active = [widget for widget in QApplication.topLevelWidgets()
                  if widget is not window and widget.isVisible() and window.isAncestorOf(widget)]
        assert not active, [widget.windowTitle() for widget in active]
        return page

    def shot(name):
        app.processEvents()
        assert window.grab().save(str(output/(name+'.png')))

    def form(values):
        active = inside(FieldsDialog)
        for key, value in values.items():
            field = active.fields[key]
            if hasattr(field, 'setPlainText'):
                field.setPlainText(value)
            else:
                field.setText(value)
        active.save_button.click()
        idle()

    def issue(page, approve):
        observed = []
        timer = QTimer(window)
        def respond():
            modal = app.activeModalWidget()
            if isinstance(modal, QMessageBox):
                observed.append(modal.text())
                choice = QMessageBox.StandardButton.Yes if approve else QMessageBox.StandardButton.No
                modal.button(choice).click()
        timer.timeout.connect(respond)
        timer.start(8)
        try:
            page.issue_button.click()
        finally:
            timer.stop()
        idle()
        assert observed and '850,00 ₽' in observed[0] and 'не подтверждает оплату' in observed[0]

    try:
        idle()
        store = workspace.store
        workspace.go_to_section(2)
        journal = workspace.journal
        journal.new_button.click()
        from ..ui.service.intake import IntakeDialog
        intake = inside(IntakeDialog)
        intake.name.setText('Тестовый заказчик')
        intake.number.setText('QA16-001')
        intake.model.setText('Учебный насос')
        intake.complaint.setPlainText('Не подаёт давление')
        intake.submit.click()
        idle()
        page = inside(RepairPage)
        first = page.key
        equipment = store.equipment()[0]
        page.tabs.show_section('Дефектовка')
        page.fields['defects'].setPlainText('Изношено уплотнение')
        page.fields['plan'].setPlainText('Проверить насос и заменить уплотнение')
        page.save_button.click()
        idle()
        for width,height in ((1920,1080),(1366,768),(820,620),(560,320)):
            window.resize(width,height)
            app.processEvents()
            viewport=page.body_scroll.viewport().height()
            assert viewport>=60 and page.next_button.isVisible(), (width,height,viewport)
            target=page.next_button.mapTo(window,page.next_button.rect().bottomLeft())
            assert target.y()<window.height(),(width,height,target.y())
            name=f'02-repair-{width}x{height}'
            layout_samples[name]={'actual':[window.width(),window.height()],
                                  'qt_dpr':window.devicePixelRatio(),'body_height':viewport}
            shot(name)
        window.resize(1366,768)
        app.processEvents()
        checks.append('embedded_intake_and_diagnosis')

        page.tabs.show_section('Работы')
        page.add_item_button.menu().actions()[0].trigger()
        form({'name':'Работа мастера','price':str(work)})
        assert inside(RepairPage) is page
        page.add_item_button.menu().actions()[1].trigger()
        form({'name':'Уплотнение','price':str(part)})
        page.tabs.show_section('Сметы')
        if stage10:
            from .estimates import save_draft
            save_draft(store, first, [
                {'name':'Работа мастера','kind':'work','quantity':'1','price':str(work)},
                {'name':'Уплотнение','kind':'part','quantity':'1','price':str(part)},
            ])
            page.install(store.snapshot(first))
            page.estimates.freeze('preliminary')
            form({'actor':'Учебный сотрудник','reason':'Проверочный предварительный расчёт'})
        page.estimates.freeze('final')
        form({'actor':'Учебный сотрудник','reason':'Проверочный финальный расчёт'})
        quotes = page.snapshot['estimates']
        assert len(quotes)==(2 if stage10 else 1) and all(q['total']==total*100 for q in quotes)
        if stage10:assert any(q['kind']=='preliminary' and q['version']==1 for q in quotes)
        app.processEvents()
        viewport=page.body_scroll.viewport()
        estimate_y=page.estimates.summary.mapTo(viewport,page.estimates.summary.rect().bottomLeft()).y()
        assert 0<estimate_y<viewport.height(),(estimate_y,viewport.height())
        versions=page.estimates.grid
        first_row=versions.visualRect(versions.proxy.index(0,0))
        row_center=versions.viewport().mapTo(viewport,first_row.center())
        assert viewport.rect().contains(row_center),(row_center,viewport.size())
        shot('03-estimate')
        page.tabs.show_section('Финансы')
        page.payment('payment')
        invalid = inside(FieldsDialog)
        invalid.fields['amount'].setText('ошибка')
        invalid.save_button.click()
        idle()
        assert inside(FieldsDialog) is invalid and invalid.error.isVisible()
        form({'amount':str(paid),'comment':'Учебный частичный расчёт'})
        totals = page.snapshot['totals']
        assert tuple(totals[k] for k in ('total','paid','balance'))==(total*100,paid*100,85000)
        assert 'Долг' in page.finance_values['balance'].text()
        shot('04-finance')
        checks.append('immutable_estimate_and_exact_internal_finance')

        page.tabs.show_section('Документы')
        wizard = page.document_wizard
        wizard.start('completion')
        wizard.check_document()
        wizard.preview()
        idle()
        assert wizard.prepared and '850,00' in wizard.preview_text.toPlainText()
        assert not page.next_button.isVisible()
        viewport=page.body_scroll.viewport()
        forward=wizard.preview_continue.mapTo(viewport,wizard.preview_continue.rect().center())
        assert viewport.rect().contains(forward),(forward,viewport.size())
        preview = wizard.prepared.rendered
        shot('05-document-preview')
        wizard.preview_continue.click()
        wizard.generate_button.click()
        idle()
        [document] = store.documents()
        path = store.root/document['path']
        assert path.read_bytes()==preview
        doc = Document(path)
        payload = '\n'.join([p.text for p in doc.paragraphs]+[cell.text for table in doc.tables
                            for row in table.rows for cell in row.cells])
        assert 'Уплотнение' in payload and '850,00' in payload
        shot('06-document-result')
        checks.append('preview_bytes_equal_saved_docx')

        page.tabs.show_section('Статус и история')
        original = page.snapshot['repair']['status']
        page.fields['status'].setCurrentIndex(page.fields['status'].findData('ready'))
        page.fields['handover'].setPlainText('Получатель: учебный заказчик')
        page.save_button.click()
        idle()
        assert page.snapshot['repair']['status']==original
        handover_proof = None
        if stage10:
            page.next_button.click()
            assert wizard.doc_kind.currentData()=='handover' and wizard.doc_kind.count()==8
            assert len(store.documents())==1
            wizard.check_document()
            wizard.preview()
            idle()
            assert wizard.prepared and 'Принято' in wizard.preview_text.toPlainText()
            assert 'полностью оплачено' not in wizard.preview_text.toPlainText().lower()
            bytes_at_preview = wizard.prepared.rendered
            wizard.preview_continue.click()
            wizard.generate_button.click()
            idle()
            handover_doc = next(doc for doc in store.documents() if doc['kind']=='handover')
            handover_proof = handover_doc['path'], bytes_at_preview
            assert (store.root/handover_doc['path']).read_bytes()==bytes_at_preview
            page.tabs.show_section('Статус и история')
        issue(page,False)
        assert store.snapshot(first)['repair']['status']==original
        issue(page,True)
        issued = store.snapshot(first)
        assert issued['repair']['status']=='issued' and issued['totals']['balance']==85000
        assert issued['repair_status_history'][-1]['new_status']=='issued'
        assert issued['repair_status_history'][-1]['note']
        page.open_status()
        status_form=inside(FieldsDialog)
        combo=status_form.fields['status']
        combo.setCurrentIndex(combo.findData('approval'))
        status_form.save_button.click()
        assert inside(FieldsDialog) is status_form and status_form.errors['reason'].isVisible()
        assert store.snapshot(first)['repair_status_history']==issued['repair_status_history']
        combo.setCurrentIndex(combo.findData('issued'))
        workspace.back_page()
        assert inside(RepairPage) is page
        shot('07-issued')
        checks.append('status_changes_only_on_explicit_confirmed_action')

        workspace.back_page()
        idle()
        journal.search.setText('QA16-001')
        journal.grid.selectRow(0)
        selected = journal.grid.selected()['id']
        workspace.open_journal_history()
        idle()
        history = inside(HistoryPage)
        assert 'минимум два обращения' in history.compare_hint.text()
        assert not history.compare_button.isEnabled()
        history.new()
        repeated = inside(IntakeDialog)
        repeated.complaint.setPlainText('Повторная проверка')
        repeated.submit.click()
        idle()
        second_page = inside(RepairPage)
        second = second_page.key
        assert first!=second and second_page.snapshot['totals']['balance']==0
        workspace.back_page()
        idle()
        if history.grid.proxy.rowCount()!=2:
            history.refresh()
            idle()
        assert inside(HistoryPage) is history and history.grid.proxy.rowCount()==2
        for row in range(2):
            history.grid.setCurrentIndex(history.grid.proxy.index(row,0))
            history.grid.setFocus()
            QTest.keyClick(history.grid,Qt.Key.Key_Space)
        assert history.compare_button.isEnabled()
        history.compare_button.click()
        idle()
        inside(HistoryComparison)
        shot('08-comparison')
        workspace.back_page()
        assert inside(HistoryPage) is history
        workspace.back_page()
        assert workspace.current_page is None
        assert journal.search.text()=='QA16-001' and journal.grid.selected()['id']==selected
        assert store.snapshot(first)['estimates']==quotes and store.snapshot(first)['totals']==issued['totals']
        checks.append('repeat_checkboxes_and_return_keep_context')

        archive = create_backup(store,output/'QA-Workspace.zip')
        info = inspect_backup(archive)
        restored = ServiceStore(restore_backup(archive,output/'Восстановленная копия',expected_sha256=info['sha256']))
        assert restored.snapshot(first)['totals']==issued['totals']
        assert restored.snapshot(second)['totals']['balance']==0
        assert restored.snapshot(first)['repair_status_history']==issued['repair_status_history']
        assert (restored.root/document['path']).read_bytes()==preview
        if handover_proof:
            handover_path, handover_bytes = handover_proof
            assert (store.root/handover_path).read_bytes()==handover_bytes
            assert (restored.root/handover_path).read_bytes()==handover_bytes
        assert hashlib.sha256(archive.read_bytes()).hexdigest()==info['sha256']
        checks.append('backup_restores_two_repairs_statuses_and_exact_document')
        return {'status':'passed','checks':checks,'qt_platform':app.platformName(),
                'operational_top_level_windows':1,'synthetic_only':True,'layout_samples':layout_samples}
    finally:
        idle()
        window.close()
        app.processEvents()
