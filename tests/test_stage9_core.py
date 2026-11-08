
from dataclasses import replace

from openpyxl import Workbook
from docx import Document
from PySide6.QtCore import QUrl, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from docflow.cli import demo_profile
from docflow.profile import Profile
from docflow.release_check import wait_idle
from docflow.ui.settings import preferences
from docflow.ui.theme import COLORS
from docflow.ui.window import MainWindow


def test_restart_returns_to_table_when_remembered_create_has_no_inputs(tmp_path):
    settings = preferences()
    settings.setValue('workspace/v2/documents', 3)
    settings.sync()
    window = MainWindow(service_root=tmp_path / 'project')
    assert window.pages.currentIndex() == 0
    assert window.core_next.text() == 'Выбрать таблицу'
    window.close()


def write_workbook(source, last_service='Проверка'):
    book = Workbook()
    book.active.title = 'Clients'
    book.active.append(['Номер','Клиент','Услуга','Сумма','Дата','Email'])
    book.active.append(['0001','QA <Первый> & Co','Диагностика',12500,'2026-11-07','a@example.invalid'])
    book.active.append(['0002','QA Второй','Ремонт',8400,'2026-11-08','b@example.invalid'])
    book.active.append(['0003','QA Ошибка',last_service,-150,'2026-11-08','c@example.invalid'])
    book.save(source)


def test_core_qt_generates_four_ooxml_files_and_skips_negative_amount(tmp_path):
    source = tmp_path / 'clients.xlsx'
    write_workbook(source)
    original = Profile.load(demo_profile())
    inputs = {p:p.read_bytes() for p in (source,*original.templates)}
    window = MainWindow(service_root=tmp_path / 'project')
    window.show()
    try:
        window.apply_profile(replace(original,data_file=source,sheet='Clients'))
        wait_idle(window)
        assert window.mapping()[0]['email'] == 'Email'
        assert window.data_path.text() == 'clients.xlsx'
        assert window.data_path.toolTip() == str(source)
        window.name_selector.setCurrentText('Клиент')
        assert 'row_0002_' in window.folder_preview.text()
        window.navigate(3)
        window.output_path.setText(str(tmp_path / 'output'))
        window.start_generation()
        wait_idle(window)
        result = window.last_result
        assert (result.documents,result.accepted,result.rejected) == (4,2,1)
        assert window.title.text() == 'Результаты создания'
        assert window.result_files_model.rowCount() == 4
        assert window.result_file_btn.isEnabled()
        first = window.result_files_model.index(0, 0)
        assert first.data().startswith(result.files[0].rsplit('/', 1)[1])
        assert first.data(Qt.ItemDataRole.UserRole) == result.files[0]
        assert 'Строка 4' in window.result_report.toPlainText()
        for file in result.files:
            document = Document(result.directory / file)
            contents = '\n'.join([p.text for p in document.paragraphs]+[
                c.text for t in document.tables for r in t.rows for c in r.cells])
            assert 'QA Ошибка' not in contents
            assert ('QA <Первый> & Co' in contents and '12500' in contents
                    and '2026-11-07' in contents and 'a@example.invalid' in contents) or (
                    'QA Второй' in contents and '8400' in contents
                    and '2026-11-08' in contents and 'b@example.invalid' in contents)
        assert all(path.read_bytes() == content for path,content in inputs.items())
    finally:
        wait_idle(window)
        window.close()


def test_core_validation_opens_each_error_in_its_source_cell(tmp_path):
    source = tmp_path / 'clients.xlsx'
    write_workbook(source, last_service=None)
    original = Profile.load(demo_profile())
    window = MainWindow(service_root=tmp_path / 'project')
    window.show()
    try:
        window.apply_profile(replace(original, data_file=source, sheet='Clients'))
        wait_idle(window)
        window.navigate(2)
        window.check_all()
        wait_idle(window)
        panel = window.validation_panel
        assert panel.isVisible() and panel.property('severity') == 'error'
        assert 'готовых строк: 2 из 3' in panel.heading.text()
        details = panel.report.toPlainText()
        assert 'Строка 4 · Сумма (amount): Нужно конечное число не меньше нуля' in details
        assert 'Строка 4 · Услуга (service): Обязательное поле пусто' in details
        QTest.keyClick(panel.first, Qt.Key.Key_Space)
        selected = window.source_table.currentIndex()
        assert (window.pages.currentIndex(), window.tabs.currentIndex()) == (0, 0)
        assert (selected.row(), selected.column()) == (2, 3)
        assert window.source_table.hasFocus()
        assert selected.data(Qt.ItemDataRole.ForegroundRole).name().upper() == COLORS['error']
        assert 'не меньше нуля' in selected.data(Qt.ItemDataRole.AccessibleDescriptionRole)
        assert 'Обязательное поле пусто' in window.source_issue.text()

        window.navigate(2)
        panel.report.anchorClicked.emit(QUrl('issue:1'))
        selected = window.source_table.currentIndex()
        assert (selected.row(), selected.column()) == (2, 2)
        assert 'пусто' in selected.data(Qt.ItemDataRole.AccessibleDescriptionRole)

        # Changing the mapping invalidates the previous check and its cell highlights.
        window.navigate(2)
        amount = window.mapping_table.cellWidget(0, 1)
        amount.setCurrentIndex(0)
        QApplication.processEvents()
        assert panel.mode == 'mapping' and not window.route_buttons[2].property('complete')
        assert selected.data(Qt.ItemDataRole.ForegroundRole) is None
        panel.first.click()
        assert amount.hasFocus() and amount.property('validationIssue') is True
        assert panel.first.accessibleName() == 'К первому полю без столбца'
    finally:
        wait_idle(window)
        window.close()
