"""Acceptance routes for the redesigned workshop using isolated synthetic projects."""
from pathlib import Path
from time import monotonic

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from docflow.gui import MainWindow
from docflow.service.demo import seed_demo
from docflow.service.documents import generate_document
from docflow.service.repository import ServiceStore
from docflow.ui.service import repair_editor


def settle(ui):
    until = monotonic() + 35
    while ui.worker or ui._pending_refresh:
        assert monotonic() < until, ui.message.text()
        QTest.qWait(10)
    QApplication.processEvents()


@pytest.fixture
def desk(tmp_path):
    root = tmp_path / 'Учебный проект'
    keys = seed_demo(root)
    window = MainWindow()
    window.show()
    window.activateWindow()
    window.navigate(5)
    ui = window.service_workspace
    try:
        yield window, ui, root, keys
    finally:
        settle(ui)
        if getattr(ui.current_page, 'dirty', False) and hasattr(ui.current_page, 'snapshot'):
            ui.current_page.install(ui.current_page.snapshot)
        window.close()


def open_demo(desk):
    _, ui, root, keys = desk
    ui.open_project(root, require_existing=True)
    settle(ui)
    assert ui.store.root == root
    return ui, keys


def test_project_landing_and_switch_respects_unsaved_repair(desk, tmp_path, monkeypatch):
    window, ui, root, _ = desk
    assert ui.open_project_button.isVisible() and ui.restore_project_button.isVisible()
    assert not ui.dashboard.metrics.isVisible() and not ui.dashboard.new_button.isVisible()
    assert 'Откройте проект' in window.title.text()
    _, keys = open_demo(desk)
    assert ui.dashboard.metrics.isVisible() and ui.project_menu.isVisible()
    assert str(root) == ui.location.toolTip()
    ui.open_repair(keys['repair'], 'Дефектовка')
    settle(ui)
    editor = ui.current_page
    editor.fields['defects'].setPlainText('Несохранённая учебная диагностика')
    second = tmp_path / 'Другой проект'
    seed_demo(second)
    monkeypatch.setattr(QMessageBox, 'exec', lambda _: QMessageBox.StandardButton.Cancel)
    ui.open_project(second, require_existing=True)
    settle(ui)
    assert ui.current_page is editor and ui.store.root == root
    assert editor.fields['defects'].toPlainText() == 'Несохранённая учебная диагностика'
    assert ui.store.snapshot(keys['repair'])['repair']['defects'] != 'Несохранённая учебная диагностика'


def test_customer_card_uses_exact_ids_and_keeps_ownership_distinct(desk):
    _, ui, root, keys = desk
    store = ServiceStore(root)
    customer = store.save_client({'kind': 'organization', 'name': 'Отдельный заказчик'})
    visit = store.create_repair(keys['equipment'], 'QA-KLINK', 'Синтетический повторный ремонт',
                                client_id=customer)
    open_demo(desk)
    ui.go_to_section(3)
    clients = ui.views['clients']
    row = next(i for i in range(clients.proxy.rowCount()) if
               clients.records.rows[clients.proxy.mapToSource(clients.proxy.index(i,0)).row()]['id'] == customer)
    clients.selectRow(row)
    clients.setFocus()
    QTest.keyClick(clients, Qt.Key.Key_Return)
    page = ui.current_page
    assert page.equipment.proxy.rowCount() == 0
    assert page.repairs.proxy.rowCount() == 1
    assert page.repairs.selected()['id'] == visit
    QTest.keyClick(page.repairs, Qt.Key.Key_Return)
    settle(ui)
    assert ui.current_page.key == visit
    assert 'Отдельный заказчик' in ui.current_page.identity.text()
    assert 'Демонстрационная мастерская' in ui.current_page.identity.text()


@pytest.mark.parametrize('kind,direction', [('payment', -1), ('refund', 1)])
def test_payment_or_refund_has_safe_default_and_writes_only_after_confirmation(desk, monkeypatch, kind, direction):
    ui, keys = open_demo(desk)
    chosen = keys['repair']
    ui.open_repair(chosen, 'Финансы')
    settle(ui)
    editor = ui.current_page
    start = ui.store.snapshot(chosen)
    editor.payment(kind)
    form = ui.current_page
    form.fields['amount'].setText('50.25')
    prompts = []
    monkeypatch.setattr(repair_editor, 'confirm', lambda _,message,*a,**kw: prompts.append((message,kw)) or False)
    form.save_button.click()
    assert ui.current_page is form and form.fields['amount'].text() == '50.25'
    assert ui.store.snapshot(chosen) == start
    message, options = prompts[0]
    assert '50,25 ₽' in message and start['repair']['number'] in message and options['cancel'] == 'Вернуться'
    monkeypatch.setattr(repair_editor, 'confirm', lambda *a,**kw: True)
    form.save_button.click()
    settle(ui)
    after = ui.store.snapshot(chosen)
    assert after['totals']['balance'] == start['totals']['balance'] + direction * 5025
    assert after['repair_status_history'] == start['repair_status_history']
    assert after['estimates'] == start['estimates']


def test_selected_saved_estimate_opens_same_version_from_workshop(desk):
    ui, _ = open_demo(desk)
    ui.go_to_section(6)
    table = ui.views['estimates']
    table.selectRow(table.proxy.rowCount() - 1)
    source = table.selected()
    QTest.keyClick(table, Qt.Key.Key_Return)
    settle(ui)
    assert ui.current_page.tabs.is_section('Сметы')
    panel = ui.current_page.estimates
    assert panel.mode.currentIndex() == 2 and panel.grid.selected()['id'] == source['id']
    assert str(source['version']) in ui.list_contexts['estimates'].text()


def test_documents_open_verified_parent_and_share_core_preview(desk, monkeypatch):
    _, _, root, keys = desk
    generated = generate_document(ServiceStore(root), keys['repair'],'intake')
    ui, _ = open_demo(desk)
    ui.go_to_section(5)
    ui.views['documents'].selectRow(0)
    opened = []
    monkeypatch.setattr(ui, 'open_local', lambda path: opened.append(Path(path)))
    ui.show_document_directory()
    settle(ui)
    assert opened == [generated.parent]
    ui.open_repair(keys['repair'],'Документы')
    settle(ui)
    wizard = ui.current_page.document_wizard
    wizard.start('intake')
    wizard.check_document()
    wizard.preview()
    settle(ui)
    assert wizard.preview_text.isReadOnly() and wizard.preview_text.objectName() == 'corePreviewPaper'
    assert 'Тестовая мойка' in wizard.preview_text.toPlainText()


def test_import_displays_only_source_specific_controls_without_writing(desk, tmp_path):
    ui, keys = open_demo(desk)
    before = ui.store.snapshot(keys['repair'])
    wizard = ui.import_history()
    QApplication.processEvents()
    assert not wizard.sheet.isVisible() and not wizard.encoding.isVisible()
    wizard.path.setText(str(tmp_path / 'journal.csv'))
    assert wizard.encoding.isVisible() and not wizard.sheet.isVisible()
    wizard.path.setText(str(tmp_path / 'journal.xlsx'))
    assert wizard.sheet.isVisible() and not wizard.encoding.isVisible()
    assert ui.store.snapshot(keys['repair']) == before
