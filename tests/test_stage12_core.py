"""Acceptance regressions for the Stage 12 Core workflow."""
from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog, QApplication

from docflow.cli import demo_profile
from docflow.gui import MainWindow
from docflow.profile import Profile
from docflow.release_check import wait_idle
from docflow.validation import Rule


@pytest.fixture
def core():
    window = MainWindow()
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    yield window
    wait_idle(window)
    window.close()


def viewport_contains(widget, scroll):
    viewport = scroll.viewport()
    bounds = widget.rect().translated(widget.mapTo(viewport, widget.rect().topLeft()))
    return viewport.rect().contains(bounds)


def test_first_launch_imports_csv_and_goes_to_template_library_without_opening_a_dialog(core, tmp_path, monkeypatch):
    csv = tmp_path / 'Заявки.csv'
    csv.write_text('Клиент;Сумма\nУчебная организация;125\n', encoding='cp1251')
    original = csv.read_bytes()
    assert not core.core_route.isVisible()
    assert not core.source_settings.isVisible()

    calls = []

    def choose_table(*args):
        calls.append('table')
        return str(csv), ''

    monkeypatch.setattr(QFileDialog, 'getOpenFileName', choose_table)
    monkeypatch.setattr(QFileDialog, 'getOpenFileNames', lambda *_: calls.append('templates') or ([], ''))
    core.encoding_selector.setCurrentIndex(core.encoding_selector.findData('cp1251'))
    QTest.keyClick(core.select_first_table, Qt.Key.Key_Space)
    wait_idle(core)
    assert calls == ['table']
    assert core.encoding == 'cp1251'
    assert core.data_model.index(0, 0).data() == 'Учебная организация'
    assert 'Строк: 1 · Столбцов: 2' in core.stats.text()
    assert core.core_route.isVisible()
    core.core_next.click()
    assert core.pages.currentIndex() == 1 and core.templates_empty.isVisible()
    assert calls == ['table']
    core.core_next.click()
    assert calls == ['table', 'templates']
    core.core_back.click()
    assert core.pages.currentIndex() == 0 and core.table.source == csv
    assert csv.read_bytes() == original


def test_check_marks_source_rows_can_open_error_and_invalidates_on_mapping_changes(core, tmp_path):
    QTest.keyClick(core.demo_btn, Qt.Key.Key_Space)
    wait_idle(core)
    core.navigate(1)
    assert core.template_name.text() == core.templates[0].path.name
    core.template_list.setCurrentRow(1)
    assert core.template_name.text() == core.templates[1].path.name
    assert '{{client}}' in core.template_fields.toPlainText()
    core.navigate(2)
    core.output_path.setText(str(tmp_path / 'dry-run'))
    core.config_row.setCurrentIndex(1)
    core.config_template.setCurrentIndex(1)
    wait_idle(core)
    selected_name = core.table.records[1].values['Клиент']
    assert selected_name in core.config_preview.toPlainText()
    core.check_all()
    wait_idle(core)
    assert [item.text() for item in core.validation_panel.counts.values] == ['2', '1']
    assert not (tmp_path / 'dry-run').exists()
    assert core.data_model.headerData(0, Qt.Orientation.Vertical) == '✓ 2'
    assert core.data_model.headerData(2, Qt.Orientation.Vertical) == '! 4'
    core.validation_panel.first.click()
    assert core.pages.currentIndex() == 0 and core.source_table.currentIndex().row() == 2
    core.navigate(2)
    core.mapping_table.cellWidget(0, 1).setCurrentIndex(0)
    assert not core.validation_panel.counts.isVisible()
    assert core.data_model.headerData(2, Qt.Orientation.Vertical) == '4'


def test_compact_preview_has_keyboard_shortcut_button_and_result_actions_stay_visible(core, tmp_path):
    core.resize(560, 320)
    core.load_demo()
    wait_idle(core)
    core.navigate(2)
    QApplication.processEvents()
    assert core.preview_jump.isVisible()
    assert core.pages.currentWidget().horizontalScrollBar().maximum() == 0
    QTest.keyClick(core.preview_jump, Qt.Key.Key_Space)
    QApplication.processEvents()
    assert core.config_row.hasFocus() and viewport_contains(core.config_row, core.pages.currentWidget())

    core.navigate(3)
    core.output_path.setText(str(tmp_path / 'outputs'))
    core.generate_btn.click()
    wait_idle(core)
    QApplication.processEvents()
    assert core.result_file_btn.isVisible()
    assert viewport_contains(core.result_open_btn, core.pages.currentWidget())
    assert viewport_contains(core.new_run_btn, core.pages.currentWidget())


def test_replacement_resets_source_view_and_round_trips_original_json_format(core, tmp_path):
    base = Profile.load(demo_profile())
    source = tmp_path / 'таблица.csv'
    source.write_bytes(base.data_file.with_suffix('.csv').read_bytes())
    profile = replace(base, data_file=source, encoding='utf-8-sig', sheet=None)
    path = tmp_path / 'profile.json'
    profile.save(path)
    core.load_demo()
    wait_idle(core)
    core.tabs.setCurrentIndex(2)
    core.apply_profile(Profile.load(path))
    wait_idle(core)
    assert core.tabs.currentIndex() == 0
    assert core.encoding_selector.currentData() == 'utf-8-sig'
    restored = Profile.load(path)
    assert core.profile() == replace(restored, rules={field: restored.rules.get(field, Rule())
                                                    for field in restored.mapping})
