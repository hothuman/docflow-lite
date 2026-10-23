"""Exact management-accounting totals, not a fiscal receipt or bank connection."""
from .validation import ServiceError

def totals(connection,repair_id):
    r=connection.execute('SELECT discount_cents FROM repair_orders WHERE id=?',(repair_id,)).fetchone()
    if not r:raise ServiceError('Ремонт не найден')
    sums={x['kind']:x['total'] for x in connection.execute('SELECT kind,SUM(total_cents) AS total FROM repair_items WHERE repair_id=? GROUP BY kind',(repair_id,))}
    work=sums.get('work',0);parts=sums.get('part',0)
    paid=connection.execute("SELECT COALESCE(SUM(CASE kind WHEN 'payment' THEN amount_cents ELSE -amount_cents END),0) FROM payments WHERE repair_id=? AND voided=0",(repair_id,)).fetchone()[0]
    total=max(0,work+parts-r['discount_cents'])
    return {'work':work,'parts':parts,'discount':r['discount_cents'],'total':total,'paid':paid,'balance':total-paid,'overpaid':max(0,paid-total)}
