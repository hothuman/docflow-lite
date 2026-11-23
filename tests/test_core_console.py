"""The Core workspace keeps the completed run and its next action coherent."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
from shiboken6 import isValid

from docflow.gui import MainWindow
from docflow.release_check import wait_idle


def test_completed_run_opens_selected_document_and_new_run_is_explicit(tmp_path, monkeypatch):
    window = MainWindow(service_root=tmp_path / 'service')
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    try:
        assert window.select_first_table.isVisible()
        assert not window.core_next.isVisible()
        assert window.pages.currentWidget().accessibleName() == window.title.text()

        window.load_demo()
        wait_idle(window)
        window.core_next.click()
        assert window.pages.currentIndex() == 1
        window.core_next.click()
        assert window.pages.currentIndex() == 2
        original_table = window.table
        window.core_back.click()
        assert window.pages.currentIndex() == 1 and window.table is original_table

        window.navigate(3)
        window.output_path.setText(str(tmp_path / 'output'))
        window.generate_btn.click()
        wait_idle(window)
        assert window.last_result.documents == 4
        assert window.last_result.rejected == 1
        assert not window.options_card.isVisible() and not window.generate_btn.isVisible()
        assert window.result_file_btn.isVisible() and window.result_file_btn.isEnabled()
        assert window.result_file_btn.accessibleName() == 'Открыть документ'

        from docflow.ui import window as window_module
        opened = []
        monkeypatch.setattr(window_module.QDesktopServices, 'openUrl',
                            lambda url: opened.append(Path(url.toLocalFile())) or True)
        window.result_files.setCurrentIndex(window.result_files_model.index(1, 0))
        selected = window.result_files.currentIndex().data(Qt.ItemDataRole.UserRole)
        window.result_file_btn.setFocus()
        QTest.keyClick(window.result_file_btn, Qt.Key.Key_Space)
        assert opened == [window.last_result.directory / selected]

        previous_files = {path: path.read_bytes() for path in window.last_result.directory.rglob('*.docx')}
        window.new_run_btn.setFocus()
        QTest.keyClick(window.new_run_btn, Qt.Key.Key_Space)
        assert window.options_card.isVisible() and window.generate_btn.isVisible()
        assert window.generate_btn.text() == 'Создать новый комплект'
        assert window.generate_btn.objectName() != 'primary'

        blocked = tmp_path / 'not-a-directory'
        blocked.write_text('untouched', encoding='utf-8')
        window.output_path.setText(str(blocked))
        window.generate_btn.click()
        wait_idle(window)
        assert window.last_result is None
        assert not window.result_file_btn.isVisible()
        assert window.options_card.isVisible() and window.generate_btn.isEnabled()
        assert window.operation_notice.property('isError') is True
        assert all(path.read_bytes() == content for path, content in previous_files.items())
        assert blocked.read_text(encoding='utf-8') == 'untouched'
    finally:
        wait_idle(window)
        window.close()


def test_all_rejected_rows_offer_report_and_about_has_one_release_stage(tmp_path):
    window = MainWindow(service_root=tmp_path / 'service')
    window.show()
    try:
        window.load_demo()
        wait_idle(window)
        empty_values = tmp_path / 'incomplete.csv'
        empty_values.write_text('Номер;Клиент;Услуга;Сумма;Дата;Email\n01;Тест;Ремонт;-5;2026-11-23;missing\n', encoding='utf-8')
        window._load_data(empty_values)
        wait_idle(window)
        window.navigate(3)
        window.output_path.setText(str(tmp_path / 'results'))
        window.generate_btn.click()
        wait_idle(window)
        assert (window.last_result.documents, window.last_result.rejected) == (0, 1)
        assert window.result_file_btn.isVisible()
        assert window.result_file_btn.text() == window.result_file_btn.accessibleName() == 'Открыть отчёт'
        assert window.report_btn.isEnabled()

        window.navigate(4)
        labels = [label.text() for label in window.pages.currentWidget().findChildren(QLabel)]
        assert any('Стабильный выпуск' in label for label in labels)
        assert all('Предварительная версия' not in label for label in labels)
        assert not window.result_file_btn.isVisible()
    finally:
        wait_idle(window)
        window.close()


def test_async_table_reload_moves_focus_from_replaced_mapping_control(tmp_path):
    window = MainWindow(service_root=tmp_path / 'service')
    window.show()
    window.activateWindow()
    try:
        window.load_demo()
        wait_idle(window)
        window.navigate(2)
        previous = window.mapping_table.cellWidget(0, 1)
        previous.setFocus()
        assert previous.hasFocus()
        window._load_data(window.table.source)
        wait_idle(window)
        QApplication.processEvents()
        assert not isValid(previous)
        assert window.core_next.hasFocus()
        assert window.mapping_table.cellWidget(0, 1).accessibleName()
    finally:
        wait_idle(window)
        window.close()
