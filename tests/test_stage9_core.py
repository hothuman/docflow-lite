
from dataclasses import replace

from openpyxl import Workbook
from docx import Document

from docflow.cli import demo_profile
from docflow.profile import Profile
from docflow.release_check import wait_idle
from docflow.ui.settings import preferences
from docflow.ui.window import MainWindow


def test_restart_returns_to_table_when_remembered_create_has_no_inputs(tmp_path):
    settings = preferences()
    settings.setValue('workspace/v2/documents', 3)
    settings.sync()
    window = MainWindow(service_root=tmp_path / 'project')
    assert window.pages.currentIndex() == 0
    assert window.core_next.text() == 'Выбрать таблицу'
    window.close()


def test_core_qt_generates_four_ooxml_files_and_skips_negative_amount(tmp_path):
    source = tmp_path / 'clients.xlsx'
    book = Workbook()
    book.active.title = 'Clients'
    book.active.append(['Номер','Клиент','Услуга','Сумма','Дата','Email'])
    book.active.append(['0001','QA <Первый> & Co','Диагностика',12500,'2026-11-07','a@example.invalid'])
    book.active.append(['0002','QA Второй','Ремонт',8400,'2026-11-08','b@example.invalid'])
    book.active.append(['0003','QA Ошибка','Проверка',-150,'2026-11-08','c@example.invalid'])
    book.save(source)
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
