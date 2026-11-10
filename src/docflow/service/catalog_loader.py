"""Bounded file-only parsing in a disposable process; never owns a database."""
import hashlib
import io
import multiprocessing as mp
from pathlib import Path
import tempfile
import time
import zipfile
from ..data import load_table
from .history_import import workbook_sheets
from ..safety import read_bounded
from .validation import ServiceError

MAX_BYTES=5*1024*1024
MAX_TEXT=8*1024*1024

def _parse_worker(path,sheet,encoding,connection):
    try:
        path=Path(path)
        if path.suffix.lower()=='.xlsx':
            with zipfile.ZipFile(path) as z:
                if sum(i.file_size for i in z.infolist())>20*1024*1024:raise ValueError('Expanded catalog exceeds limit')
        sheets=workbook_sheets(path) if path.suffix.lower()=='.xlsx' else []
        table=load_table(path,sheet=sheet or (sheets[0] if sheets else None),encoding=encoding)
        if len(table.headers)>32 or sum(len(v) for r in table.records for v in r.values.values())>MAX_TEXT:raise ValueError('Catalog exceeds limit')
        if any(len(v)>2000 for r in table.records for v in r.values.values()):raise ValueError('Cell exceeds limit')
        connection.send({'headers':table.headers,'rows':[(r.row_number,r.values) for r in table.records],
                         'sheets':sheets})
    except Exception as exc:
        connection.send({'error':'Не удалось разобрать каталог ('+type(exc).__name__+'). Проверьте лист, кодировку, лимиты, формулы и внешние ссылки.'})
    finally:connection.close()

def parse_file(path,*,sheet=None,encoding='auto',cancel=None,timeout=30):
    path=Path(path)
    if path.suffix.lower() not in ('.xlsx','.csv') or path.is_symlink():raise ServiceError('Выберите обычный локальный XLSX или CSV')
    if str(path).startswith(('\\\\','http:','https:')):raise ServiceError('Нужен локальный файл выгрузки')
    if encoding not in ('auto','utf-8-sig','cp1251'):raise ServiceError('Выберите поддерживаемую кодировку')
    raw=read_bounded(path,MAX_BYTES);digest=hashlib.sha256(raw).hexdigest()
    if cancel and cancel.is_set():raise ServiceError('Разбор отменён; проект не изменён')
    context=mp.get_context('spawn')
    with tempfile.TemporaryDirectory(prefix='docflow-catalog-') as folder:
        staged=Path(folder)/('input'+path.suffix.lower());staged.write_bytes(raw)
        parent,child=context.Pipe(duplex=False);process=context.Process(target=_parse_worker,args=(str(staged),sheet,encoding,child),daemon=True)
        process.start();child.close();started=time.monotonic()
        try:
            while not parent.poll(.05):
                if cancel and cancel.is_set():raise ServiceError('Разбор отменён; проект не изменён')
                if time.monotonic()-started>timeout:raise ServiceError('Разбор превысил лимит времени; проект не изменён')
                if not process.is_alive():raise ServiceError('Разбор прерван; проект не изменён')
            try:result=parent.recv()
            except EOFError as exc:raise ServiceError('Разбор прерван; проект не изменён') from exc
            if 'error' in result:raise ServiceError(result['error'])
            result.update(file_sha256=digest,file_name=path.name,sheet=sheet or (result['sheets'][0] if result['sheets'] else ''),encoding=encoding)
            return result
        finally:
            parent.close()
            if process.is_alive():process.terminate()
            process.join(timeout=5);process.close()
