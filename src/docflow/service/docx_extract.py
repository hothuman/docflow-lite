"""Controlled DOCX-to-review-CSV extraction, never a guessed repair import."""
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

from ..safety import check_archive,read_bounded,csv_safe
from ..templates import parse,W,paragraph_nodes
from .validation import ServiceError


def extract_tables(path):
    path=Path(path)
    if path.is_symlink() or path.suffix.lower()!='.docx':raise ServiceError('Выберите обычный DOCX')
    raw=read_bounded(path);check_archive(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if 'word/document.xml' not in z.namelist():raise ServiceError('Нет основного документа Word')
        root=parse(z.read('word/document.xml'))
    records=[];sha=hashlib.sha256(raw).hexdigest();maximum=0
    for table_index,table in enumerate(root.iter(W+'tbl'),1):
        for row_index,row in enumerate(table.findall(W+'tr'),1):
            values={};spans=[];column=0
            for cell in row.findall(W+'tc'):
                span=cell.find(W+'tcPr/'+W+'gridSpan');width=int(span.get(W+'val','1')) if span is not None else 1
                if not 1<=width<=100 or column+width>100:raise ServiceError('Таблица Word превышает 100 колонок')
                paragraphs=[p for p in cell.iter(W+'p') if next(p.iterancestors(W+'tc'),None) is cell]
                content='\n'.join(''.join(t.text for t in paragraph_nodes(p)) for p in paragraphs)
                if len(content)>10000:raise ServiceError('Ячейка Word длиннее 10000 символов')
                values[column]=content;spans.append({'column':column+1,'span':width});column+=width
            maximum=max(maximum,column)
            records.append({'source_sha256':sha,'source_fragment':f'word/document.xml/table[{table_index}]/row[{row_index}]',
                            'source_table':table_index,'source_row':row_index,'source_spans':json.dumps(spans,separators=(',',':')),'cells':values})
            if len(records)>5000:raise ServiceError('В одном контролируемом извлечении допускается до 5000 строк')
    if not records:raise ServiceError('В DOCX нет табличных строк; автоматическое распознавание свободного текста не выполняется')
    return {'source_name':path.name,'source_sha256':sha,'columns':maximum,'records':records,'database_writes':False,
            'warning':'Это извлечение для ручной проверки. Номера, даты, заголовки и объединение аппаратов не угадываются.'}


def export_review_csv(path,destination):
    extracted=extract_tables(path);destination=Path(destination);created=False
    try:
        with destination.open('x',encoding='utf-8-sig',newline='') as f:
            created=True;writer=csv.writer(f,delimiter=';')
            writer.writerow(['source_sha256','source_fragment','source_table','source_row','source_spans']+[f'cell_{i+1:02d}' for i in range(extracted['columns'])])
            for row in extracted['records']:
                writer.writerow([row[k] for k in ('source_sha256','source_fragment','source_table','source_row','source_spans')]
                                +[csv_safe(row['cells'].get(i,'')) for i in range(extracted['columns'])])
    except Exception:
        if created:destination.unlink(missing_ok=True)
        raise
    return {**extracted,'output':str(destination)}
