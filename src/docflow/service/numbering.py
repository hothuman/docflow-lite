"""Business numbers independent of immutable repair IDs and frozen documents.

Counters live in existing settings; prior numbers stay reserved in the audit log.
Unknown historical sequences do not choose the operational starting point.
"""
import json
import re
from .profiles import profile


def aliases(connection):
    result = {}
    for row in connection.execute("SELECT entity_id,detail FROM operations WHERE entity='repair' AND action='renumber' ORDER BY id"):
        try:
            detail = json.loads(row['detail'])
            old = detail['before']
            if isinstance(old, str):
                result.setdefault(row['entity_id'], []).append(old)
        except (ValueError, TypeError, KeyError):
            continue
    return result


def used_numbers(connection):
    numbers = {row[0].casefold() for row in connection.execute('SELECT number FROM repair_orders')}
    for values in aliases(connection).values():
        numbers.update(n.casefold() for n in values)
    return numbers


def sequence(connection):
    p = profile(connection, active=True)
    key = 'repair_sequence/' + json.dumps([p['id'], p['number_prefix']], ensure_ascii=False)
    row = connection.execute('SELECT value FROM service_settings WHERE key=?', (key,)).fetchone()
    n = p['number_start']
    if row:
        try:
            n = max(n, int(row[0]))
        except (ValueError, TypeError):
            pass
    return p, key, n


def numeric_part(number, prefix):
    pattern = re.escape(prefix) + r'([0-9]+)'
    match = re.fullmatch(pattern, number, flags=re.IGNORECASE)
    return int(match[1]) if match else None


def suggest_number(connection):
    p, _, n = sequence(connection)
    # Explicit imported records never imply a confirmed numbering sequence.
    for row in connection.execute("SELECT number FROM repair_orders WHERE status!='historical' AND id NOT IN (SELECT repair_id FROM import_records)"):
        value = numeric_part(row[0], p['number_prefix'])
        if value is not None:
            n = max(n, value + 1)
    used = used_numbers(connection)
    while True:
        number = f"{p['number_prefix']}{n:06d}" if p['number_prefix'] else str(n)
        if number.casefold() not in used:
            return number, p['id']
        n += 1


def advance_sequence(connection, number):
    p, key, n = sequence(connection)
    value = numeric_part(number, p['number_prefix'])
    if value is not None:
        n = max(n, value + 1)
        connection.execute('INSERT INTO service_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(n)))
