"""Read-only, aggregate relationship diagnostics without customer identifiers.

An archived identity is not a broken relationship. This report deliberately
does not infer physical identity or alter existing imports.
"""


def audit_links(store):
    with store.db.connection() as c:
        counts = {}
        for table in ('clients', 'equipment'):
            rows = c.execute(f'SELECT archived,COUNT(*) FROM {table} GROUP BY archived').fetchall()
            values = {int(row[0]): row[1] for row in rows}
            counts[table] = {'current': values.get(0, 0), 'archived': values.get(1, 0)}
        counts['repairs'] = c.execute('SELECT COUNT(*) FROM repair_orders').fetchone()[0]
        counts['historical_repairs'] = c.execute("SELECT COUNT(*) FROM repair_orders WHERE status='historical'").fetchone()[0]
        problems = {
            'repair_without_equipment': c.execute('SELECT COUNT(*) FROM repair_orders r LEFT JOIN equipment e ON e.id=r.equipment_id WHERE e.id IS NULL').fetchone()[0],
            'repair_without_client': c.execute('SELECT COUNT(*) FROM repair_orders r LEFT JOIN clients c ON c.id=r.client_id WHERE c.id IS NULL').fetchone()[0],
            'equipment_without_owner': c.execute('SELECT COUNT(*) FROM equipment e LEFT JOIN clients c ON c.id=e.owner_id WHERE c.id IS NULL').fetchone()[0],
            'foreign_key_violations': len(c.execute('PRAGMA foreign_key_check').fetchall()),
        }
        counts['repairs_with_archived_equipment'] = c.execute('SELECT COUNT(*) FROM repair_orders r JOIN equipment e ON e.id=r.equipment_id WHERE e.archived=1').fetchone()[0]
        counts['repairs_with_archived_client'] = c.execute('SELECT COUNT(*) FROM repair_orders r JOIN clients c ON c.id=r.client_id WHERE c.archived=1').fetchone()[0]
    return {'status': 'needs_review' if any(problems.values()) else 'passed',
            'counts': counts, 'problems': problems, 'writes_performed': False,
            'scope': 'Aggregate relationships only. No personal data, identity inference or corrections.'}


def audit_summary(report):
    counts, problems = report['counts'], report['problems']
    lines = ['Проверка связей без изменения данных', '',
             f"Клиенты: действующих {counts['clients']['current']}, архивных {counts['clients']['archived']}.",
             f"Оборудование: действующего {counts['equipment']['current']}, архивного {counts['equipment']['archived']}.",
             f"Обращений: {counts['repairs']}; исторических: {counts['historical_repairs']}.",
             f"Обращений с архивным аппаратом: {counts['repairs_with_archived_equipment']}.",
             f"Обращений с архивным клиентом: {counts['repairs_with_archived_client']}.", '',
             'Архивные клиенты и аппараты скрыты в обычных списках. Это само по себе не означает потерю связей.', '']
    labels = {'repair_without_equipment': 'Обращения без аппарата',
              'repair_without_client': 'Обращения без клиента',
              'equipment_without_owner': 'Аппараты без текущего владельца',
              'foreign_key_violations': 'Нарушения внешних ключей SQLite'}
    lines.extend(f'{labels[key]}: {value}.' for key, value in problems.items())
    lines.extend(['', 'Требует проверки: исправлять неоднозначные соответствия можно только на копии, после проверки источников и подтверждения предпросмотра изменений.' if any(problems.values()) else 'Структурные связи сохранены. Тождество физических аппаратов и старые суммы этим отчётом не подтверждаются.',
                  'Изменений и автоматического объединения записей не выполнено.'])
    return '\n'.join(lines)
