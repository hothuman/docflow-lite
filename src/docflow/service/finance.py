"""Exact management-accounting totals, not a fiscal receipt or bank connection."""
from .validation import ServiceError

ITEM_KINDS={'work':'Работа','part':'Запчасть','delivery':'Доставка','other':'Другой согласованный расход'}

def financial_status(total,paid):
    if paid>total:return 'Переплата / корректировка'
    if paid==0:return 'Нет учтённой оплаты'
    if paid<total:return 'Частично оплачено'
    return 'Оплачено'

def calculate(lines,discount=0,paid=0):
    sums={kind:0 for kind in ITEM_KINDS}
    for row in lines:
        if row['kind'] not in sums:raise ServiceError('Неизвестный тип позиции')
        sums[row['kind']]+=row['total_cents']
    gross=sum(sums.values())
    if not 0<=discount<=gross:raise ServiceError('Скидка не может превышать стоимость позиций')
    if gross>9000000000000000:raise ServiceError('Превышен предел суммы расчёта')
    total=gross-discount
    return {'work':sums['work'],'parts':sums['part'],'delivery':sums['delivery'],'other':sums['other'],
            'discount':discount,'total':total,'paid':paid,'balance':total-paid,'overpaid':max(0,paid-total),
            'financial_status':financial_status(total,paid)}

def totals(connection,repair_id):
    r=connection.execute('SELECT discount_cents FROM repair_orders WHERE id=?',(repair_id,)).fetchone()
    if not r:raise ServiceError('Ремонт не найден')
    sums={x['kind']:x['total'] for x in connection.execute('SELECT kind,SUM(total_cents) AS total FROM repair_items WHERE repair_id=? GROUP BY kind',(repair_id,))}
    paid=connection.execute("SELECT COALESCE(SUM(CASE kind WHEN 'payment' THEN amount_cents ELSE -amount_cents END),0) FROM payments WHERE repair_id=? AND voided=0",(repair_id,)).fetchone()[0]
    return calculate([{'kind':k,'total_cents':v} for k,v in sums.items()],r['discount_cents'],paid)
