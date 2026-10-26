"""Public limits are checked at the limit and one beyond, on synthetic data."""
from pathlib import Path
import pytest
from openpyxl import Workbook
from docx import Document
from docflow.data import load_table
from docflow.safety import read_bounded,MAX_FILE_BYTES
from docflow.profile import Profile
from docflow.batch import prepare,generate
from docflow.errors import DocFlowError


def test_csv_5000_rows_and_100_columns_and_reject_extra_row(tmp_path):
    p=tmp_path/'boundary.csv'
    p.write_text(';'.join('C'+str(i) for i in range(100))+'\n'+(';'.join(['value']*100)+'\n')*5000)
    table=load_table(p)
    assert len(table.headers)==100 and len(table.records)==5000
    with p.open('a') as f:f.write(';'.join(['extra']*100)+'\n')
    with pytest.raises(DocFlowError,match='5000'):load_table(p)


def test_xlsx_5000_rows_and_100_columns_are_supported_separately(tmp_path):
    p=tmp_path/'boundary.xlsx';w=Workbook();s=w.active;s.title='Лист'
    s.append(['C'+str(i) for i in range(100)])
    for i in range(5000):s.append([f'Строка {i}'])
    w.save(p);w.close()
    table=load_table(p,sheet='Лист')
    assert len(table.records)==5000 and len(table.headers)==100
    assert table.records[-1].values['C0']=='Строка 4999'


def test_20_templates_generate_one_complete_set_and_21_rejected(tmp_path):
    data=tmp_path/'data.csv';data.write_text('name\nSynthetic')
    templates=[]
    for i in range(20):
        p=tmp_path/f'{i}.docx';d=Document();d.add_paragraph('{{name}}');d.save(p);templates.append(p)
    profile=Profile(data,templates,{'name':'name'})
    result=generate(prepare(profile),tmp_path/'out')
    assert result.documents==20 and len(list(result.directory.rglob('*.docx')))==20
    profile.templates.append(templates[0])
    with pytest.raises(DocFlowError,match='20'):prepare(profile)


def test_input_byte_limit_is_exact_and_bounded(tmp_path):
    p=tmp_path/'bytes'
    with p.open('wb') as f:f.truncate(MAX_FILE_BYTES)
    assert len(read_bounded(p))==MAX_FILE_BYTES
    with p.open('ab') as f:f.write(b'x')
    with pytest.raises(DocFlowError,match='20'):read_bounded(p)
