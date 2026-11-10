"""Local advisory layout checks on an already validated, immutable DOCX snapshot.

No renderer claims: widths and text lengths are hints, never generation gates.
Container safety and supported-token validation remain Template.load's contract.
"""
import io
import re
import zipfile
from dataclasses import dataclass
from .templates import W, parse, STORY


@dataclass(frozen=True)
class Finding:
    code: str
    message: str


def layout_findings(raw):
    findings=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root=parse(z.read('word/document.xml'))
        areas=[]
        for sect in root.iter(W+'sectPr'):
            size=sect.find(W+'pgSz');margin=sect.find(W+'pgMar')
            if size is not None and margin is not None:
                try:areas.append(int(size.get(W+'w'))-int(margin.get(W+'left'))-int(margin.get(W+'right')))
                except (ValueError,TypeError):pass
        for index,table in enumerate(root.iter(W+'tbl'),1):
            widths=[]
            grid=table.find(W+'tblGrid')
            if grid is not None:
                try:widths.append(sum(int(c.get(W+'w','0')) for c in grid))
                except ValueError:pass
            width=table.find(W+'tblPr/'+W+'tblW')
            if width is not None and width.get(W+'type')=='dxa':
                try:widths.append(int(width.get(W+'w','0')))
                except ValueError:pass
            if areas and max(widths,default=0)>min(areas)+20:
                findings.append(Finding('table_width',f'Таблица {index} может выходить за печатную область. Проверьте ширину в Word; это предупреждение, а не запрет генерации.'))
            if len(table.findall(W+'tr'))>10:
                first=table.find(W+'tr')
                if first is not None and first.find(W+'trPr/'+W+'tblHeader') is None:
                    findings.append(Finding('table_header',f'У таблицы {index} не задан повтор заголовка. Для длинного документа проверьте следующие страницы.'))
        text=' '.join(t.text or '' for t in root.iter(W+'t'))
        if any(len(word)>160 for word in re.split(r'\s+',text)):
            findings.append(Finding('long_word','Есть очень длинный текст без пробелов. Проверьте переносы и границы ячеек в редакторе.'))
        for name in z.namelist():
            if STORY.fullmatch(name):
                part=parse(z.read(name))
                if any(next(part.iter(W+tag),None) is not None for tag in ('ins','del','sdt')):
                    findings.append(Finding('review_markup','В шаблоне есть правки или элементы управления Word. Проверьте отображаемый текст на копии в редакторе.'))
                    break
    return tuple(findings)


def configuration_messages(window):
    """Inspect current data without changing mappings, undo, files or worker state."""
    from .validation import values_for
    templates=window.active_templates()
    if not templates:return ['Добавьте Word-шаблон. При загрузке проверяются контейнер DOCX, переменные и небезопасные вложения.']
    mapping,rules=window.mapping();messages=[]
    fields=set().union(*(t.fields for t in templates))
    for field in sorted(fields-mapping.keys()):
        messages.append(f'Поле «{field}» не связано со столбцом таблицы. Выберите столбец перед созданием документов.')
    for template in templates:
        messages.append(f'{template.path.name}: загруженная копия DOCX проверена; полей: {len(template.fields)}.')
        if not template.path.is_file():messages.append('Исходный файл сейчас недоступен. Загруженная копия сохранена в памяти; перед следующим открытием восстановите доступ к файлу.')
        messages.extend(f'{template.path.name}: {finding.message}' for finding in template.diagnostics)
    if window.table and 0<=window.row_selector.currentIndex()<len(window.table.records):
        record=window.table.records[window.row_selector.currentIndex()]
        safe_mapping={k:v for k,v in mapping.items() if v in window.table.headers}
        _,issues=values_for(record,safe_mapping,rules)
        messages.extend(f'Строка {issue.row}, поле «{issue.field}»: {issue.message}.' for issue in issues)
        if any(len(v)>2500 for v in record.values.values()):messages.append('В выбранной записи есть длинный текст. Строка выше страницы может продолжаться на следующей; проверьте DOCX в Word.')
    messages.append('Проверена выбранная запись. Для всего файла нажмите «Проверить все строки». Предупреждения о вёрстке приблизительны и не блокируют корректный шаблон.')
    return messages
