"""Service previews are read-only and commit the exact reviewed DOCX."""
import hashlib
import json
from pathlib import Path
from threading import Event

from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QPushButton
import pytest

from docflow.service.attachments import attachment_path
from docflow.service.backup import create_backup, restore_backup
from docflow.service.documents import generate_document, prepare_document, save_prepared_document
from docflow.service.estimates import freeze_estimate, save_draft
from docflow.service.repository import ServiceStore
from docflow.service.validation import ServiceError
from docflow.ui.service.repair_editor import RepairPage
from docflow.ui.window import MainWindow

from test_stage1_document_actions import idle


@pytest.fixture
def workshop(tmp_path):
    store = ServiceStore(tmp_path / 'workshop')
    key = store.intake(client={'name': 'Учебный заказчик'},
                       equipment={'number': 'QA16-001', 'model': 'Учебный насос'})
    store.save_repair(key, {'complaint': 'Не держит давление', 'defects': 'Износ уплотнения'})
    store.save_item(key, {'kind': 'work', 'name': 'Диагностика', 'quantity': '1', 'price': '1500'})
    store.save_item(key, {'kind': 'part', 'name': 'Уплотнение', 'quantity': '1', 'price': '350'})
    store.add_payment(key, '1000')
    return store, key


def test_preparing_a_stock_act_changes_no_project_files_and_commits_exact_bytes(workshop):
    store, key = workshop
    before = store.snapshot(key)
    preview = prepare_document(store, key, 'completion')
    assert store.snapshot(key) == before
    assert not (store.root / 'generated').exists()
    assert not (store.root / 'templates').exists()

    saved = save_prepared_document(store, preview)
    row, = store.documents()
    meta = json.loads(row['metadata_json'])
    source = store.root / 'templates/default-v8/completion.docx'
    assert saved.read_bytes() == preview.rendered
    assert hashlib.sha256(source.read_bytes()).hexdigest() == meta['template_sha256']
    assert row['sha256'] == hashlib.sha256(preview.rendered).hexdigest()
    assert row['version'] == 1
    another = generate_document(store, key, 'completion')
    assert another != saved and saved.read_bytes() == preview.rendered
    assert [doc['version'] for doc in store.documents()] == [2, 1]
    assert store.snapshot(key)['repair_status_history'] == before['repair_status_history']


def test_stale_act_requires_a_fresh_preview_but_selected_saved_estimate_remains_valid(workshop):
    store, key = workshop
    stale = prepare_document(store, key, 'completion')
    save_draft(store, key, [{'kind': 'work', 'name': 'Утверждённая работа', 'quantity': '1', 'price': '1500'}])
    first = freeze_estimate(store, key, 'preliminary', 'Учебный мастер')
    immutable = prepare_document(store, key, 'estimate_preliminary', estimate_id=first)
    store.save_repair(key, {'complaint': 'Изменённая жалоба'})

    with pytest.raises(ServiceError, match='Обновите предпросмотр'):
        save_prepared_document(store, stale)
    assert not store.documents()
    saved = save_prepared_document(store, immutable)
    assert saved.read_bytes() == immutable.rendered
    row, = store.documents()
    assert json.loads(row['metadata_json'])['estimate_id'] == first


def click(widget, caption):
    control = next(button for button in widget.findChildren(QPushButton)
                   if button.text() == caption and button.isVisible())
    assert control.isEnabled()
    control.click()


def test_embedded_wizard_preview_commit_and_backup_restore(workshop, tmp_path, monkeypatch):
    store, key = workshop
    app = QApplication.instance()
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(Path(url.toLocalFile())) or True)
    window = MainWindow(service_root=store.root)
    window.resize(1366, 768)
    window.show()
    window.navigate(5)
    workspace = window.service_workspace
    try:
        idle(app, workspace)
        workspace.open_repair(key, 'Документы')
        idle(app, workspace)
        editor = workspace.current_page
        assert isinstance(editor, RepairPage) and not editor.isWindow()
        wizard = editor.document_wizard

        wizard.start('estimate_final')
        click(wizard, 'Проверить данные')
        assert wizard.profile_banner.objectName() == 'documentReadinessError'
        assert 'Сначала сохраните' in wizard.profile_banner.text()
        assert not wizard.preview_button.isEnabled()

        wizard.start('completion')
        click(wizard, 'Проверить данные')
        assert 'нейтральная форма' in wizard.profile_banner.text()
        release_preview = Event()

        def delayed(*args, **kwargs):
            assert release_preview.wait(10)
            return prepare_document(*args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr('docflow.ui.service.document_actions.prepare_document', delayed)
            click(wizard, 'Посмотреть документ')
            try:
                assert workspace.operation_cancel.isVisible()
                workspace.operation_cancel.click()
            finally:
                release_preview.set()
            idle(app, workspace)
        assert wizard.pages.currentIndex() == 1
        assert wizard.prepared is None
        assert 'отменён' in wizard.document_status.text()
        assert not workspace.store.documents()

        click(wizard, 'Посмотреть документ')
        idle(app, workspace)
        assert wizard.pages.currentIndex() == 2
        for expected in ('Диагностика', 'Уплотнение', '1 850,00', '850,00'):
            assert expected in wizard.preview_text.toPlainText()
        assert not workspace.store.documents()

        prepared = wizard.prepared.rendered
        click(wizard, 'Посмотреть разметку DOCX')
        idle(app, workspace)
        assert len(opened) == 1 and opened[0].read_bytes() == prepared
        opened[0].write_bytes(b'synthetic modification in external viewer')
        click(wizard, 'Продолжить к созданию')
        click(wizard, 'Создать DOCX')
        idle(app, workspace)
        assert wizard.pages.currentIndex() == 4
        assert wizard.result_name.text() == 'Акт выполненных работ'
        assert 'Версия 1' in wizard.result_info.text()
        saved = wizard._last_document
        assert saved.read_bytes() == prepared
        assert QApplication.activeModalWidget() is None
        assert workspace.current_page is editor
        assert workspace.store.snapshot(key)['repair']['status'] == 'accepted'

        click(wizard, 'Открыть')
        idle(app, workspace)
        assert opened[-1] == saved
        archive = create_backup(workspace.store, tmp_path / 'archive.zip')
        recovered = ServiceStore(restore_backup(archive, tmp_path / 'recovered'))
        row, = recovered.documents()
        assert attachment_path(recovered, row['id'], True).read_bytes() == prepared
        assert recovered.snapshot(key)['totals']['balance'] == 85_000
    finally:
        idle(app, workspace)
        workspace.back_page()
        idle(app, workspace)
        window.close()
