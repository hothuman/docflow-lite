"""Independent preliminary drafts, immutable quotes and explicit manual events."""
import csv
import hashlib
import io
import json
from pathlib import Path
from uuid import uuid4

from .finance import ITEM_KINDS, calculate, totals
from .profiles import profile
from .validation import ServiceError, line_total, money, now, quantity, text


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def normalize_lines(rows):
    if not isinstance(rows, (list, tuple)) or len(rows) > 2000:
        raise ServiceError('В расчёте допускается до 2000 позиций')
    result = []
    for position, row in enumerate(rows):
        kind = row.get('kind')
        if kind not in ITEM_KINDS:
            raise ServiceError('Выберите работу, запчасть, доставку или другой согласованный расход')
        q = quantity(row.get('quantity', '1'))
        if 'price' in row:
            price = money(row['price'])
        else:
            price = row.get('price_cents', 0)
            if type(price) is not int or price < 0 or price > 10**14:
                raise ServiceError('Неверная цена в копейках')
        result.append({'id':text(row.get('id') or uuid4().hex, limit=100), 'kind':kind,
                       'name':text(row.get('name'), 'Наименование', True, 500),
                       'description':text(row.get('description')), 'quantity':q,
                       'unit':text(row.get('unit', 'шт.'), 'Единица', True, 30),
                       'price_cents':price, 'total_cents':line_total(q, price),
                       'position':position, 'notes':text(row.get('notes'))})
        if 'price' not in row and row.get('price_known',True) in (False,0):
            result[-1]['price_known']=False
    calculate(result)
    return result


def draft(connection, repair_id):
    row = connection.execute('SELECT * FROM estimate_drafts WHERE repair_id=?', (repair_id,)).fetchone()
    if row is None:
        return {'repair_id':repair_id, 'lines':[], 'discount_cents':0, 'comment':'', 'revision':0, 'updated_at':''}
    return {**dict(row), 'lines':json.loads(row['lines_json'])}


def save_draft(store, repair_id, rows, discount='0', comment='', expected_revision=None):
    lines = normalize_lines(rows); cents = money(discount)
    calculate(lines, cents); comment = text(comment)
    with store.lock, store.db.connection(True) as c:
        store.require(c, 'repair_orders', repair_id)
        current = draft(c, repair_id)
        if expected_revision is not None and expected_revision != current['revision']:
            raise ServiceError('Черновик сметы изменился; откройте свежую версию')
        revision = current['revision'] + 1
        c.execute('INSERT INTO estimate_drafts(repair_id,lines_json,discount_cents,comment,revision,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(repair_id) DO UPDATE SET lines_json=excluded.lines_json,discount_cents=excluded.discount_cents,comment=excluded.comment,revision=excluded.revision,updated_at=excluded.updated_at',
                  (repair_id, canonical(lines), cents, comment, revision, now()))
        store._touch(c, repair_id); store.audit(c, 'estimate_draft', repair_id, 'save', str(revision))
    return revision


def get_estimate(connection, key):
    row = connection.execute('SELECT * FROM estimate_versions WHERE id=?', (key,)).fetchone()
    if row is None:
        raise ServiceError('Версия сметы не найдена')
    result = dict(row); result['payload'] = json.loads(row['payload_json'])
    result['events'] = [dict(x) for x in connection.execute('SELECT * FROM estimate_events WHERE estimate_id=? ORDER BY id', (key,))]
    result['state'] = result['events'][-1]['action'] if result['events'] else 'prepared'
    result['total'] = result['payload']['totals']['total']
    return result


def list_estimates(connection, repair_id=None):
    sql = 'SELECT id FROM estimate_versions'
    args = ()
    if repair_id:
        sql += ' WHERE repair_id=?'; args = (repair_id,)
    sql += ' ORDER BY created_at DESC,version DESC,rowid DESC'
    return [get_estimate(connection, row[0]) for row in connection.execute(sql, args)]


def approved_preliminary(connection, repair_id):
    row = connection.execute("SELECT v.id FROM estimate_versions v WHERE v.repair_id=? AND v.kind='preliminary' AND (SELECT action FROM estimate_events WHERE estimate_id=v.id ORDER BY id DESC LIMIT 1)='approved' ORDER BY v.version DESC LIMIT 1", (repair_id,)).fetchone()
    return get_estimate(connection, row[0]) if row else None


def require_change_reason(connection, repair_id, reason):
    if approved_preliminary(connection, repair_id):
        return text(reason, 'Причина изменения согласованного объёма', True, 2000)
    return text(reason, limit=2000)


def comparison(connection, repair_id):
    approved = approved_preliminary(connection, repair_id)
    current = totals(connection, repair_id)
    latest = connection.execute("SELECT id FROM estimate_versions WHERE repair_id=? AND kind='preliminary' ORDER BY version DESC LIMIT 1", (repair_id,)).fetchone()
    selected = approved or (get_estimate(connection, latest[0]) if latest else None)
    if selected is None:
        return {'preliminary_total':None, 'final_total':current['total'], 'difference':None,
                'approved_estimate_id':None, 'changed_from_approved':False}
    lines = [dict(r) for r in connection.execute('SELECT * FROM repair_items WHERE repair_id=? ORDER BY position,rowid', (repair_id,))]
    def content(rows):
        return [{k:r.get(k,1 if k=='price_known' else '') for k in ('kind','name','description','quantity','unit','price_cents','total_cents','price_known')} for r in rows]
    changed = bool(approved) and (content(lines) != content(selected['payload']['lines']) or current['discount'] != selected['payload']['totals']['discount'])
    return {'preliminary_total':selected['total'], 'preliminary_id':selected['id'], 'preliminary_state':selected['state'],
            'final_total':current['total'], 'difference':current['total']-selected['total'] if current['total'] is not None else None,
            'approved_estimate_id':approved['id'] if approved else None, 'changed_from_approved':changed}


def freeze_estimate(store, repair_id, kind, prepared_by, reason='', request_id=None, expected_revision=None):
    if kind not in ('preliminary', 'final'):
        raise ServiceError('Выберите предварительную или окончательную смету')
    actor = text(prepared_by, 'Кто подготовил смету', True, 200)
    reason = text(reason, limit=2000)
    with store.lock, store.db.connection(True) as c:
        r = store.require(c, 'repair_orders', repair_id)
        if expected_revision is not None and r['revision'] != expected_revision:
            raise ServiceError('Ремонт изменился; обновите карточку перед сохранением сметы')
        if kind == 'preliminary':
            source = draft(c, repair_id)
            lines = normalize_lines(source['lines'])
            quote_totals = {k:v for k,v in calculate(lines, source['discount_cents']).items() if k not in ('paid','balance','overpaid','financial_status')}
            comment = source['comment']
        else:
            lines = normalize_lines([dict(x) for x in c.execute('SELECT * FROM repair_items WHERE repair_id=? ORDER BY position,rowid', (repair_id,))])
            quote_totals = totals(c, repair_id); comment = r['notes']
            if quote_totals['total'] is None:
                raise ServiceError('Уточните и подтвердите историческую стоимость перед окончательной сметой')
            if comparison(c, repair_id)['changed_from_approved'] and not reason:
                raise ServiceError('Укажите причину отличия окончательной сметы от согласованной')
        payload = {'repair':r, 'equipment':store.require(c, 'equipment', r['equipment_id']),
                   'client':store.require(c, 'clients', r['client_id']), 'profile':profile(c, r['profile_id']),
                   'lines':lines, 'totals':quote_totals, 'comment':comment, 'kind':kind, 'comparison':comparison(c,repair_id) if kind=='final' else None}
        content = canonical(payload); sha = hashlib.sha256(content.encode()).hexdigest()
        if request_id:
            prior = c.execute('SELECT * FROM estimate_versions WHERE request_id=?', (request_id,)).fetchone()
            if prior:
                if prior['repair_id'] != repair_id or prior['kind'] != kind or prior['payload_sha256'] != sha or prior['prepared_by'] != actor or prior['reason'] != reason:
                    raise ServiceError('Идентификатор относится к другой операции сохранения сметы')
                return prior['id']
        version = c.execute('SELECT COALESCE(MAX(version),0)+1 FROM estimate_versions WHERE repair_id=? AND kind=?', (repair_id,kind)).fetchone()[0]
        if version > 1 and not reason:
            raise ServiceError('Для новой версии укажите причину изменения')
        key = uuid4().hex; stamp = now()
        c.execute('INSERT INTO estimate_versions(id,repair_id,kind,version,payload_json,payload_sha256,prepared_by,reason,created_at,source_revision,request_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                  (key, repair_id, kind, version, content, sha, actor, reason, stamp, r['revision'], request_id))
        c.execute('INSERT INTO estimate_events(estimate_id,action,actor,comment,occurred_at) VALUES(?,?,?,?,?)', (key,'prepared',actor,reason,stamp))
        store.audit(c, 'estimate', key, 'freeze', kind+':'+str(version))
    return key


def estimate_summaries(store):
    """One indexed query for the global journal; no per-row JSON or event reads."""
    with store.db.connection() as c:
        return [dict(r) for r in c.execute("""SELECT v.id,v.repair_id,r.number,cl.name AS client,
          v.kind,v.version,v.created_at,v.prepared_by,
          CAST(json_extract(v.payload_json,'$.totals.total') AS INTEGER) AS total,
          COALESCE((SELECT action FROM estimate_events e WHERE e.estimate_id=v.id ORDER BY e.id DESC LIMIT 1),'prepared') AS state
          FROM estimate_versions v JOIN repair_orders r ON r.id=v.repair_id
          JOIN clients cl ON cl.id=r.client_id ORDER BY v.created_at DESC,v.rowid DESC""")]


def record_event(store, estimate_id, action, actor, comment):
    actor = text(actor, 'Кто внёс ручную отметку', True, 200)
    comment = text(comment, 'Основание ручной отметки', True, 2000)
    with store.lock, store.db.connection(True) as c:
        estimate = get_estimate(c, estimate_id)
        allowed = {'prepared':{'sent','approved','rejected','withdrawn'}, 'sent':{'approved','rejected','withdrawn'},
                   'approved':{'withdrawn'}, 'rejected':set(), 'withdrawn':set()}
        if estimate['state'] == action and estimate['events'][-1]['actor'] == actor and estimate['events'][-1]['comment'] == comment:
            return estimate['events'][-1]['id']
        if action not in allowed.get(estimate['state'], set()):
            raise ServiceError('Эта отметка недопустима для текущего состояния версии; создайте новую версию')
        cursor = c.execute('INSERT INTO estimate_events(estimate_id,action,actor,comment,occurred_at) VALUES(?,?,?,?,?)',
                           (estimate_id, action, actor, comment, now()))
        store.audit(c, 'estimate', estimate_id, 'manual_'+action, actor+': '+comment)
        return cursor.lastrowid


def csv_text(value):
    value = str(value)
    return "'"+value if value.lstrip().startswith(('=', '+', '-', '@')) else value


def export_specification(store, estimate_id, destination):
    with store.db.connection() as c:
        estimate = get_estimate(c, estimate_id)
    p = estimate['payload']; output = io.StringIO(newline=''); writer = csv.writer(output, delimiter=';')
    writer.writerow(['Номер ремонта','Клиент','Смета','Версия','Тип','Наименование','Количество','Единица','Цена ₽','Сумма ₽'])
    def amount(cents): return f'{cents//100}.{cents%100:02d}'
    for row in p['lines']:
        writer.writerow([csv_text(p['repair']['number']),csv_text(p['client']['name']),estimate['kind'],estimate['version'],
                         ITEM_KINDS[row['kind']],csv_text(row['name']),row['quantity'],csv_text(row['unit']),amount(row['price_cents']),amount(row['total_cents'])])
    writer.writerow(['','','','','Скидка','','','','',amount(p['totals']['discount'])])
    writer.writerow(['','','','','Итого','','','','',amount(p['totals']['total'])])
    destination = Path(destination); created = False
    try:
        with destination.open('x', encoding='utf-8-sig', newline='') as f:
            created = True; f.write(output.getvalue())
    except Exception:
        if created: destination.unlink(missing_ok=True)
        raise
    return destination
