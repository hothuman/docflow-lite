"""Explicit column mapping, preview and one atomic import. Never infer old IDs."""
from pathlib import Path
import json
from .validation import text,ServiceError
from ..data import load_table
from .history_import import HISTORY_FIELDS,workbook_sheets,preview_history,import_history

FIELDS=('number','model','manufacturer','serial','kind','identifiers','notes')
def preview_equipment(path,mapping):
    table=load_table(Path(path))
    if not {'number','model'}.issubset(mapping) or not set(mapping).issubset(FIELDS):raise ServiceError('Сопоставьте постоянный номер и модель')
    rows=[];seen=set()
    for record in table.records:
        # The existing table model supplies normalized strings by header name.
        values={field:text(record.values[header]) for field,header in mapping.items()}
        n=values['number'].casefold()
        if not n or not values['model'] or n in seen:raise ServiceError('Пустой или повторный постоянный номер; импорт не выполнен')
        seen.add(n);rows.append(values)
    return rows

def import_equipment(store,rows,owner_id):
    from uuid import uuid4
    from .validation import now
    # A single SQLite transaction: any conflict rolls back the whole batch.
    with store.lock,store.db.connection(True) as c:
        if store.require(c,'clients',owner_id)['archived']:raise ServiceError('Клиент архивирован')
        numbers={r[0].casefold() for r in c.execute('SELECT number FROM equipment')}
        keys=[]
        for row in rows:
            key=uuid4().hex;stamp=now();n=text(row.get('number'),'Номер',True,300);model=text(row.get('model'),'Модель',True,300)
            if n.casefold() in numbers:raise ServiceError('Повторяется постоянный номер; импорт отменён целиком')
            numbers.add(n.casefold())
            c.execute('INSERT INTO equipment(id,number,model,manufacturer,serial,kind,identifiers,notes,owner_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,n,model,text(row.get('manufacturer')),text(row.get('serial')),text(row.get('kind')),text(row.get('identifiers')),text(row.get('notes')),owner_id,stamp,stamp));keys.append(key)
        store.audit(c,'import',owner_id,'equipment',str(len(keys)))
        return keys
