"""Stage 1: actual repair-card document actions, desktop failures and raw retention."""
import hashlib
import json
import time
from pathlib import Path

import pytest
from docx import Document
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from docflow.gui import MainWindow
from docflow.service.demo import seed_demo
from docflow.service.documents import KINDS
from docflow.ui.service.repair_editor import RepairDialog
from docflow.ui.service.document_actions import open_for_printing


def idle(app, workspace):
    until = time.monotonic() + 30
    while workspace.worker or workspace._pending_refresh:
        app.processEvents()
        time.sleep(.005)
        assert time.monotonic() < until
    app.processEvents()


@pytest.fixture
def card(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    messages = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda parent, title, message: messages.append(message))
    ids = seed_demo(tmp_path / 'Synthetic-stage1')
    window = MainWindow(service_root=tmp_path / 'Synthetic-stage1')
    window.navigate(5)
    workspace = window.service_workspace
    idle(app, workspace)
    editor = RepairDialog(workspace, workspace.store.snapshot(ids['repair']))
    workspace.dialogs.append(editor)
    editor.show()
    app.processEvents()
    yield app, workspace, editor, ids, messages
    idle(app, workspace)
    editor.dirty = False
    editor.accept()
    workspace.dialogs.remove(editor)
    window.close()
    app.processEvents()


def test_quick_act_uses_current_saved_repair_without_excel_and_versions_old_file(card, monkeypatch):
    app, workspace, editor, ids, messages = card
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(Path(url.toLocalFile())) or True)
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args: (KINDS['intake'], True))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: pytest.fail('Service act must not ask for Excel/CSV'))
    editor.fields['complaint'].setPlainText('Кириллица: не включается\nПовторная строка, цена 123,45 ₽')
    editor.quick_document_button.click()
    idle(app, workspace)
    assert len(opened) == 1 and opened[0].is_file()
    generated = workspace.store.snapshot(ids['repair'])['generated_documents']
    assert len(generated) == 1 and generated[0]['kind'] == 'intake'
    doc = Document(opened[0])
    paragraphs = '\n'.join(p.text for p in doc.paragraphs)
    assert 'Кириллица: не включается' in paragraphs
    assert 'Повторная строка, цена 123,45 ₽' in paragraphs
    assert workspace.store.get('equipment', ids['equipment'])['number'] in paragraphs
    assert 'Ctrl+P' in editor.document_status.text()
    assert editor.repair_number.isReadOnly()
    assert editor.repair_number.text() == editor.snapshot['repair']['number']
    old_digest = hashlib.sha256(opened[0].read_bytes()).hexdigest()
    editor.quick_document_button.click()
    idle(app, workspace)
    assert len(opened) == 2 and opened[0] != opened[1]
    assert hashlib.sha256(opened[0].read_bytes()).hexdigest() == old_digest
    assert sorted(r['version'] for r in editor.snapshot['generated_documents']) == [1, 2]
    assert not messages


def test_no_editor_keeps_docx_and_explains_folder_action(card, monkeypatch):
    app, workspace, editor, ids, messages = card
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: False)
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args: (KINDS['completion'], True))
    editor.quick_document_button.click()
    idle(app, workspace)
    assert editor._last_document.is_file()
    assert len(editor.snapshot['generated_documents']) == 1
    assert 'Показать папку документа' in messages[-1]
    assert 'Word или LibreOffice' in messages[-1]
    assert 'Не удалось открыть редактор' in editor.document_status.text()
    assert 'отправлено на принтер' not in editor.document_status.text().lower()
    folders = []
    monkeypatch.setattr(workspace, 'open_local', folders.append)
    editor.show_document_folder()
    idle(app, workspace)
    assert folders == [editor._last_document.parent]


def test_missing_template_is_actionable_and_keeps_existing_versions(card):
    app, workspace, editor, ids, messages = card
    editor.generate()
    idle(app, workspace)
    first = editor._last_document
    before = first.read_bytes()
    editor.template_path.setText(str(workspace.store.root / 'absent-template.docx'))
    editor.generate()
    idle(app, workspace)
    assert first.read_bytes() == before
    assert len(workspace.store.snapshot(ids['repair'])['generated_documents']) == 1
    assert 'Документ не создан' in editor.document_status.text()
    assert 'форму профиля' in editor.document_status.text()
    assert messages


def test_permission_error_stays_inside_gui_and_retains_fields(card, monkeypatch):
    app, workspace, editor, ids, messages = card
    def denied(*args, **kwargs):
        raise PermissionError('Synthetic denied output')
    monkeypatch.setattr('docflow.ui.service.repair_editor.generate_document', denied)
    editor.generate()
    idle(app, workspace)
    assert not workspace.store.snapshot(ids['repair'])['generated_documents']
    assert 'Документ не создан' in editor.document_status.text()
    assert messages


def test_display_projection_does_not_rewrite_raw_notes_or_json_string_on_unrelated_save(card):
    app, workspace, editor, ids, messages = card
    raw = json.dumps({'requires_identity_date_money_review': True,
                      'mapped_raw': {'complaint': 'Течёт\\nПосле включения', 'notes': 'Сверить журнал'},
                      'source_key': 'synthetic:sheet:17'}, ensure_ascii=False)
    condition = json.dumps('Корпус целый\nЕсть царапины', ensure_ascii=False)
    workspace.store.save_repair(ids['repair'], {'notes': raw, 'condition': condition})
    editor.install(workspace.store.snapshot(ids['repair']))
    assert 'requires_identity_date_money_review' not in editor.fields['notes'].toPlainText()
    assert editor.fields['notes'].toPlainText() == 'Сверить журнал'
    assert editor.fields['condition'].toPlainText() == 'Корпус целый\nЕсть царапины'
    editor.fields['defects'].setPlainText('Новая осмысленная диагностика')
    editor.save()
    idle(app, workspace)
    saved = workspace.store.get('repair_orders', ids['repair'])
    assert saved['notes'] == raw and saved['condition'] == condition
    assert saved['defects'] == 'Новая осмысленная диагностика'
    assert not messages


def test_missing_generated_file_explains_restore_without_throwing(tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda parent, title, message: messages.append(message))
    assert open_for_printing(None, tmp_path / 'missing.docx') is False
    assert 'резервной копии' in messages[-1]


def test_long_import_source_is_not_revalidated_on_unrelated_card_edit(card):
    app, workspace, editor, ids, messages = card
    raw = json.dumps({'requires_identity_date_money_review': True,
                      'mapped_raw': {'notes': 'Проверить источник'},
                      'source_fragment': 'Источник ' * 4000}, ensure_ascii=False)
    with workspace.store.db.connection(True) as connection:
        connection.execute('UPDATE repair_orders SET notes=? WHERE id=?', (raw, ids['repair']))
    editor.install(workspace.store.snapshot(ids['repair']))
    editor.fields['defects'].setPlainText('Содержательная диагностика без изменения источника')
    editor.save()
    idle(app, workspace)
    saved = workspace.store.get('repair_orders', ids['repair'])
    assert saved['notes'] == raw
    assert saved['defects'] == 'Содержательная диагностика без изменения источника'
    assert not messages


def test_number_action_explicitly_confirms_and_keeps_issued_file(card, monkeypatch):
    app, workspace, editor, ids, messages = card
    editor.generate()
    idle(app, workspace)
    path = editor._last_document
    issued = path.read_bytes()
    old_number = editor.repair_number.text()
    captured = []
    monkeypatch.setattr(QInputDialog, 'getText', lambda *args, **kwargs: ('1000', True))
    monkeypatch.setattr('docflow.ui.service.repair_editor.confirm', lambda parent, message: captured.append(message) or True)
    editor.change_number()
    idle(app, workspace)
    assert old_number in captured[0] and '1000' in captured[0]
    assert editor.repair_number.text() == '1000'
    assert editor.key == ids['repair']
    assert path.read_bytes() == issued
    assert workspace.store.repairs(query=old_number)[0]['id'] == editor.key
    assert not messages


def test_completed_source_works_are_readonly_not_a_fabricated_plan(card):
    app, workspace, editor, ids, messages = card
    raw = json.dumps({'requires_identity_date_money_review': True,
                      'mapped_raw': {'works': 'Историческая замена узла'}}, ensure_ascii=False)
    workspace.store.save_repair(ids['repair'], {'notes': raw, 'plan': ''})
    editor.install(workspace.store.snapshot(ids['repair']))
    editor.tabs.show_section('Дефектовка')
    app.processEvents()
    assert editor.source_works.isReadOnly() and editor.source_works.isVisible()
    assert editor.source_works.toPlainText() == 'Историческая замена узла'
    assert editor.fields['plan'].toPlainText() == ''
    assert 'source_works' not in editor.values()
    assert workspace.store.get('repair_orders', ids['repair'])['notes'] == raw
