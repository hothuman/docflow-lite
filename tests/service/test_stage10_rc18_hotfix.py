"""Stage 10 hotfix reproductions on isolated workshop data."""
import os
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QLabel
import pytest

from docflow.gui import configure_app
from docflow.service.documents import generate_document
from docflow.service.repository import ServiceStore
from docflow.ui.window import MainWindow
from test_stage1_document_actions import idle


def capture(window, name):
    if directory := os.environ.get('DOCFLOW_RC19_SHOTS'):
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(target / f'{name}.png'))


@pytest.fixture
def journal(tmp_path):
    app = QApplication.instance()
    configure_app(app)
    store = ServiceStore(tmp_path / 'synthetic')
    first = store.intake(client={'name': 'Учебный заказчик'},
                         equipment={'number': 'QA-HOTFIX', 'model': 'Учебный насос'})
    window = MainWindow(service_root=store.root)
    window.resize(1366, 768)
    window.show()
    window.navigate(5)
    workspace = window.service_workspace
    idle(app, workspace)
    workspace.go_to_section(2)
    app.processEvents()
    try:
        yield app, window, workspace, first
    finally:
        idle(app, workspace)
        window.close()
        app.processEvents()


@pytest.mark.parametrize('size', [0, 1, 2, 10, 100])
def test_short_journal_starts_just_below_filters(journal, size):
    app, window, workspace, _ = journal
    page = workspace.journal
    source = dict(page.grid.records.rows[0])
    rows = [{**source, 'id': str(number), 'number': str(number)} for number in range(1,size+1)]
    page.install(rows, page.equipment)
    app.processEvents()
    grid_top = (page.grid if size else page.empty).mapTo(window, QPoint()).y()
    filters = page.status_filter.parentWidget()
    filter_bottom = filters.mapTo(window, filters.rect().bottomLeft()).y()
    capture(window, f'journal-{size}')
    assert page.grid.isVisible() == bool(size)
    if size == 100:
        assert page.grid.verticalScrollBar().maximum() > 0
        assert page.grid.proxy.rowCount() == 100
    assert 0 <= grid_top - filter_bottom <= 16


@pytest.mark.parametrize('route,expected', [('tab','handover'), ('continue','handover'), ('intake','intake')])
def test_context_selects_document_without_changing_saved_versions(journal, route, expected):
    app, window, workspace, first = journal
    existing = generate_document(workspace.store, first, 'handover')
    original = existing.read_bytes()
    workspace.open_repair(first, 'Приёмка')
    idle(app, workspace)
    editor = workspace.current_page
    wizard = editor.document_wizard
    if route == 'intake':
        editor.tabs.show_section('Документы')
    else:
        editor.tabs.stage_bar.setCurrentIndex(4)
        assert editor.tabs.is_section('Статус и история')
        if route == 'tab':
            editor.tabs.section_tabs[4].setCurrentIndex(1)
        else:
            editor.next_button.click()
    app.processEvents()
    capture(window, 'wizard-'+route)
    assert wizard.pages.currentIndex() == 0
    assert wizard.doc_kind.currentData() == expected
    assert wizard.doc_kind.count() == 8
    assert len(workspace.store.documents()) == 1
    assert existing.read_bytes() == original

    wizard.doc_kind.setCurrentIndex(wizard.doc_kind.findData('completion'))
    wizard.check_document()
    wizard.preview()
    idle(app, workspace)
    assert wizard.pages.currentIndex() == 2
    wizard._show(1)
    wizard._show(0)
    wizard._show(5)
    wizard._show(0)
    editor.tabs.section_tabs[4].setCurrentIndex(0)
    editor.tabs.section_tabs[4].setCurrentIndex(1)
    assert wizard.doc_kind.currentData() == 'completion'
    assert len(workspace.store.documents()) == 1
    assert existing.read_bytes() == original


def test_first_wizard_step_keeps_explanation_and_action_near_the_type(journal):
    app, window, workspace, first = journal
    workspace.open_repair(first, 'Документы')
    idle(app, workspace)
    wizard = workspace.current_page.document_wizard
    layout = wizard.pages.currentWidget().layout()
    action = layout.itemAt(2).widget()
    app.processEvents()
    capture(window, 'wizard-spacing')
    assert wizard.purpose.height() <= wizard.purpose.sizeHint().height() + 10
    assert wizard.purpose.y() - wizard.doc_kind.geometry().bottom() <= 16
    assert action.y() - wizard.purpose.geometry().bottom() <= 16
    wizard.check_document()
    app.processEvents()
    capture(window, 'wizard-check')
    assert wizard.template_name.height() <= wizard.template_name.sizeHint().height()+10
    assert wizard.preview_button.isVisible()

@pytest.mark.parametrize('key,section', [('equipment',1),('clients',3),('documents',5)])
def test_short_workshop_lists_keep_only_the_space_needed(journal, key, section):
    app, window, workspace, first = journal
    if key == 'documents':
        generate_document(workspace.store, first, 'handover')
        workspace.refresh()
        idle(app, workspace)
    workspace.go_to_section(section)
    app.processEvents()
    grid = workspace.views[key]
    source = dict(grid.records.rows[0])
    capture(window, key+'-one')
    for size in (0,1,3,50):
        grid.install([{**source,'id':str(index)} for index in range(size)])
        workspace.update_list_state(key)
        app.processEvents()
        assert grid.isVisible() == bool(size)
        if 0 < size <= 3:
            assert grid.height() <= grid.horizontalHeader().height() + size*grid.rowHeight(0) + 24
        elif size == 50:
            assert grid.verticalScrollBar().maximum() > 0


def test_short_equipment_history_stays_near_filters(journal):
    app, window, workspace, first = journal
    repair = workspace.store.snapshot(first)
    workspace.show_history({**repair['equipment'], 'owner': repair['client']['name']})
    idle(app, workspace)
    history = workspace.current_page
    capture(window, 'history-one')
    assert not any(label.text() == 'История аппарата' for label in history.findChildren(QLabel))
    assert 'минимум два обращения' in history.compare_hint.text()
    assert not history.compare_button.isEnabled()
    assert history.grid.height() <= 130
