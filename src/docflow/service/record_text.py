"""Lossless display of legacy text envelopes; never rewrites stored source data.

JSON is decoded only when it is a complete value. Literal backslashes in normal
operator text are deliberately not treated as escape sequences. Source envelopes
have a narrow, labelled business projection and an independent raw-source view.
"""
from dataclasses import dataclass
import json
import re


BUSINESS_FIELDS = ('complaint', 'accessories', 'condition', 'defects', 'plan',
                   'approval_note', 'issued_accessories', 'handover', 'notes')
LABELS = {
    'complaint': 'Жалоба', 'complaints': 'Жалоба', 'problem': 'Описание проблемы',
    'defects': 'Диагностика', 'diagnostics': 'Диагностика', 'diagnosis': 'Диагностика',
    'plan': 'План работ', 'works': 'Работы', 'work': 'Работы', 'repair': 'Работы',
    'parts': 'Запчасти', 'cost': 'Стоимость из источника', 'total': 'Итог из источника',
    'final_total': 'Итог из источника', 'costs_cents': 'Суммы из источника, коп.',
    'notes': 'Примечания', 'user_notes': 'Примечания', 'comment': 'Примечания',
    'accessories': 'Комплектация', 'condition': 'Состояние', 'approval_note': 'Согласование',
    'issued_accessories': 'Комплектация при выдаче', 'handover': 'Выдача',
    'name': 'Название', 'amount': 'Сумма', 'description': 'Описание',
}
ALIASES = {
    'complaint': ('complaint', 'complaints', 'problem', 'жалоба', 'жалобы', 'неисправность'),
    'defects': ('defects', 'diagnostics', 'diagnosis', 'дефектовка', 'диагностика'),
    'plan': ('plan', 'план', 'план работ'),
    'source_works': ('source_works', 'works', 'work', 'repair', 'ремонт', 'работы'),
    'notes': ('user_notes', 'notes', 'comment', 'примечания', 'примечание'),
}
SOURCE_MARKERS = {'requires_identity_date_money_review', 'mapped_raw', 'source_key',
                  'source_rows', 'source_observation', 'raw_fields', 'docflow_text_format',
                  'source_fragment', 'source_sha256', 'source_document', 'file_sha256'}
_SOURCE_NEWLINE = re.compile(r'(?<!\\)\\{1,2}n(?=[^\x00-\x7f]|\s|$)')
_WINDOWS_PATH = re.compile(r'(?:[A-Za-z]:\\|(?:^|\s)\\\\[^\\\s]+\\)')


@dataclass(frozen=True)
class PresentedText:
    text: str
    raw: str
    warning: str = ''
    structured: bool = False


def _load(value):
    raw = '' if value is None else str(value)
    parsed = value
    structured = isinstance(parsed, (dict, list))
    if not isinstance(parsed, str):
        return raw, parsed, structured, False
    for _ in range(3):
        stripped = parsed.strip()
        if not stripped or stripped[0] not in '{["':
            return raw, parsed, structured, False
        # A JSON string can deliberately contain quoted speech. Do not strip
        # its quotes merely because the decoded value also resembles a string.
        if structured and stripped.startswith('"') and '\\' not in stripped:
            return raw, parsed, structured, False
        try:
            decoded = json.loads(stripped)
        except (ValueError, TypeError, RecursionError):
            return raw, parsed, structured, not structured
        structured = True
        parsed = decoded
        if not isinstance(parsed, str):
            break
    return raw, parsed, structured, False


def _envelope(value):
    return isinstance(value, dict) and bool(SOURCE_MARKERS.intersection(value))


def _source_lines(value):
    """Compatibility for known legacy source wrappers, not arbitrary plain text."""
    if not isinstance(value, str) or _WINDOWS_PATH.search(value):
        return value
    return _SOURCE_NEWLINE.sub('\n', value)


def _find(value, field, depth=0):
    if not isinstance(value, dict) or depth > 8:
        return None
    override = value.get('docflow_display_override')
    if isinstance(override, dict) and override.get('field') == field:
        return override.get('text', '')
    aliases = ALIASES.get(field, (field,))
    lowered = {str(k).strip().casefold(): v for k, v in value.items()}
    for key in aliases:
        if key.casefold() in lowered:
            return lowered[key.casefold()]
    for container in ('mapped_raw', 'raw_fields', 'business', 'proposed', 'original'):
        nested = value.get(container)
        if container == 'original' and value.get('docflow_text_format') == 1 and isinstance(nested,str):
            _, nested, _, _ = _load(nested)
        if isinstance(nested, dict):
            found = _find(nested, field, depth+1)
            if found is not None:
                return found
    return None


def _render(value, *, source=False, depth=0):
    if depth > 5:
        return 'Дополнительные сведения доступны в первоисточнике.'
    if value is None:
        return ''
    if isinstance(value, str):
        return _source_lines(value) if source else value
    if isinstance(value, bool):
        return 'Да' if value else 'Нет'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return '\n'.join(filter(None, (_render(x, source=source, depth=depth+1) for x in value)))
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if source and str(key).casefold() not in LABELS:
                continue
            rendered = _render(item, source=source, depth=depth+1)
            if rendered:
                lines.append(LABELS.get(str(key).casefold(), str(key)) + ': ' + rendered)
        return '\n'.join(lines)
    return 'Неподдерживаемое значение. Откройте первоисточник.'


def readable_field(value, field='notes'):
    raw, parsed, structured, malformed = _load(value)
    if malformed:
        return PresentedText('Исходная запись требует проверки. Откройте «Первоисточник».', raw,
                             'Не удалось прочитать структуру исходной записи.', False)
    source = _envelope(parsed)
    if isinstance(parsed, dict):
        selected = _find(parsed, field)
        if selected is not None:
            shown=_render(selected, source=source)
            warning='Сложная структура: проверьте первоисточник.' if 'Дополнительные сведения доступны в первоисточнике.' in shown else ''
            return PresentedText(shown, raw, warning, structured)
        if source:
            return PresentedText('', raw, 'Служебные сведения импорта сохранены в первоисточнике.', True)
    shown=_render(parsed, source=source)
    warning='Сложная структура: проверьте первоисточник.' if 'Дополнительные сведения доступны в первоисточнике.' in shown else ''
    return PresentedText(shown, raw, warning, structured)


def repair_display(repair):
    """Return a detached business projection. The supplied record is never mutated."""
    result = dict(repair)
    _, notes, _, _ = _load(repair.get('notes', ''))
    for field in BUSINESS_FIELDS:
        original = repair.get(field, '')
        display = readable_field(original, field)
        if not original and isinstance(notes, dict):
            found = _find(notes, field)
            if found is not None:
                display = PresentedText(_render(found, source=True), '', '', True)
        result[field] = display.text
    # Performed source work is evidence, not a proposed plan or newly confirmed
    # operational item. Keep this projection separate and read-only.
    works=_find(notes,'source_works') if _envelope(notes) else None
    result['source_works']=_render(works,source=True) if works is not None else ''
    return result


def preserve_field_edit(original, displayed_before, edited, field='notes'):
    """Keep exact raw bytes on unchanged saves; retain provenance on explicit edits."""
    if edited == displayed_before:
        return original
    raw, parsed, structured, malformed = _load(original)
    if not structured and not malformed:
        return edited
    if isinstance(parsed,dict) and parsed.get('docflow_text_format')==1:
        envelope=dict(parsed)
    else:
        envelope={'docflow_text_format':1,'original':raw}
    envelope['docflow_display_override'] = {'field': field, 'text': edited}
    return json.dumps(envelope, ensure_ascii=False, separators=(',', ':'))
