"""Self-service helpers around the existing Core mapping and profile engine."""
import copy
from ..matching import suggestions


def checkpoint(w, internal=False):
    if (w._busy and not internal) or not w.table:
        return
    w._configuration_undo = {
        'table': w.table, 'templates': list(w.templates), 'active': set(w._active_paths),
        'mapping': dict(w._mapping_cache), 'rules': copy.deepcopy(w._rules_cache),
        'encoding': w.encoding, 'sheet': w.sheet, 'name': w.name_selector.currentText(),
    }
    w.restore_config_btn.setEnabled(True)


def edited(w, *_):
    checkpoint(w)
    w.update_preview()


def restore(w):
    if w._busy or not getattr(w, '_configuration_undo', None):
        return
    previous = w._configuration_undo
    checkpoint(w)  # A second press can return to the configuration just replaced.
    w.table = previous['table'];w.templates = previous['templates'];w._active_paths = previous['active']
    w.encoding = previous['encoding'];w.sheet = previous['sheet']
    w.encoding_selector.setCurrentText(w.encoding);w.sheet_input.setText(w.sheet or '')
    w._mapping_cache = {};w._rules_cache = {}
    w.refresh(previous['mapping'], previous['rules'], previous['name'])
    w.status.setText('Прежние настройки возвращены. Проверьте строки перед созданием документов.')


def propose(w):
    if w._busy or not w.table or not w.active_templates():
        return
    fields = set().union(*(t.fields for t in w.active_templates()))
    choices, candidates = suggestions(fields, w.table.headers)
    mapping, rules = w.mapping()
    added = {field: column for field, column in choices.items() if field not in mapping}
    if added:
        checkpoint(w)
        mapping = {**w._mapping_cache, **added}
        w.refresh(mapping, rules)
    ambiguous = [field for field in fields if field not in mapping and len(candidates[field]) > 1]
    w.config_message.setText(
        f'Предложено связей: {len(added)}. Прежние связи сохранены. '
        + ('Выберите вручную: ' + ', '.join(sorted(ambiguous)) + ' — несколько совпадений.' if ambiguous else 'Проверьте выбранные столбцы и пример документа.'))


def explain(w):
    if not w.table:
        w.config_message.setText('Загрузите таблицу и Word-шаблон. Затем свяжите каждое поле со столбцом.')
        return
    fields = set().union(*(t.fields for t in w.active_templates()))
    mapping, _ = w.mapping()
    _, candidates = suggestions(fields, w.table.headers)
    missing = sorted(fields - mapping.keys())
    ambiguous = [f for f in missing if len(candidates[f]) > 1]
    w.config_message.setText(
        f'Связано {len(mapping)} из {len(fields)} полей. '
        + ('Не выбраны: ' + ', '.join(missing) + '. ' if missing else 'Теперь проверьте все строки и пример документа. ')
        + ('Несколько совпадений: ' + ', '.join(ambiguous) + '; выберите нужный столбец вручную.' if ambiguous else ''))
    w.restore_config_btn.setEnabled(not w._busy and bool(getattr(w, '_configuration_undo', None)))
    w.suggest_config_btn.setEnabled(not w._busy and bool(fields))


def exercise(w, app, output, idle):
    """Opt-in synthetic configuration route, executed inside the delivered EXE."""
    from ..release_check import wait_idle
    import hashlib,json
    w.navigate(0);w.load_demo();wait_idle(w)
    source=output/'self-service.csv'
    source.write_text('Customer;Amount;Date;Email;Invoice No;Service\nQA One;12.34;2026-11-05;qa@example.invalid;00001;QA Work One\nQA Two;56.78;2026-11-05;qb@example.invalid;00002;QA Work Two\n',encoding='utf-8')
    w._load_data(source);wait_idle(w);w.navigate(2);w.suggest_config_btn.click();wait_idle(w)
    assert set(w.mapping()[0])=={'client','amount','date','email','invoice_no','service'}
    w.snapshot()  # Every template field must actually be configured.
    before=w.mapping();index=next(i for i in range(w.mapping_table.rowCount()) if w.mapping_table.item(i,0).text()=='client')
    w.mapping_table.cellWidget(index,1).setCurrentIndex(0);wait_idle(w)
    assert 'client' not in w.mapping()[0]
    w.restore_config_btn.click();wait_idle(w);assert w.mapping()==before
    w.config_row.setCurrentIndex(1);w.config_template.setCurrentIndex(1);wait_idle(w)
    w.refresh(*w.mapping());wait_idle(w)
    assert w.config_row.currentIndex()==w.row_selector.currentIndex()==1
    assert w.config_template.currentIndex()==w.template_selector.currentIndex()==1
    assert 'QA Two' in w.config_preview.toPlainText()
    profile=w.profile();path=output/'self-service-v1.json';profile.save(path)
    from ..profile import Profile
    assert Profile.load(path)==profile
    w.check_all();wait_idle(w)
    assert w._full_check==(w.validation_signature(),0,2)
    assert w.config_preview.toPlainText()==w.preview_text.toPlainText()
    previous=w.last_result
    destination=output/'Self-service DOCX'
    w.navigate(3);w.output_path.setText(str(destination));w.start_generation();wait_idle(w)
    assert w.last_result is not previous and w.last_result.directory.parent==destination
    assert (w.last_result.documents,w.last_result.accepted,w.last_result.rejected)==(4,2,0)
    generated=list(w.last_result.directory.rglob('*.docx'));assert len(generated)==4
    from docx import Document
    texts=['\n'.join([p.text for p in Document(path).paragraphs]+[c.text for t in Document(path).tables for r in t.rows for c in r.cells]) for path in generated]
    assert sum('QA One' in text for text in texts)==2 and sum('QA Two' in text for text in texts)==2
    assert all(not ('QA One' in text and 'QA Two' in text) and '{{' not in text for text in texts)
    report=json.loads((w.last_result.directory/'report.json').read_text(encoding='utf-8'))
    assert (report['documents'],report['accepted'],report['rejected'])==(4,2,0)
    assert w.grab().save(str(output/'stage5-result.png'))
    w.navigate(2);assert w.grab().save(str(output/'stage5-settings.png'))
    (output/'STAGE5-CONFIGURATION.json').write_text(json.dumps({'status':'passed','mapping':before[0],'generated':4,'v1_profile_roundtrip':True,'undo_preserved_values':True,'text_preview':True,'preview_selection_retained':True,'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
