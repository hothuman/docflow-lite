"""Conservative local suggestions. Ambiguity is left for the operator."""
import unicodedata

ALIASES = (
    ('client', 'customer', 'клиент', 'заказчик'),
    ('amount', 'total', 'сумма', 'итого'),
    ('date', 'дата'), ('email', 'почта', 'электроннаяпочта'),
    ('phone', 'телефон'), ('invoice_no', 'номерсчета', 'номерсчёта'),
    ('equipment_number', 'номераппарата'), ('serial', 'серийныйномер'),
)


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold().replace('ё', 'е') if c.isalnum())


def suggestions(fields, headers):
    """Return (unique choices, candidates); no fuzzy, data-based or remote inference."""
    choices, candidates = {}, {}
    headers = tuple(headers)
    for field in sorted(fields):
        exact = [h for h in headers if h == field]
        key = normalized(field)
        matches = exact or [h for h in headers if key and normalized(h) == key]
        if not matches:
            aliases = next((set(map(normalized, group)) for group in ALIASES if key in set(map(normalized, group))), set())
            matches = [h for h in headers if normalized(h) in aliases]
        candidates[field] = tuple(matches)
        if len(matches) == 1:
            choices[field] = matches[0]
    return choices, candidates
