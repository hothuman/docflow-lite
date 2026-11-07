
from pathlib import Path

from docflow.service.history_import import _load, import_history, preview_history
from docflow.service.import_mapping import propose_history
from docflow.service.repository import ServiceStore

SOURCE = Path(__file__).resolve().parents[2] / 'examples/stage8/journal-qa.xlsx'


def test_stage9_journal_preview_explains_wrong_money_mapping_and_preserves_original(tmp_path):
    store = ServiceStore(tmp_path / 'project')
    original = SOURCE.read_bytes()
    table, _ = _load(SOURCE, 'Журнал')
    mapping, _ = propose_history(table.headers)
    status_header = mapping['status']
    status_map = {r.values[status_header]: 'accepted' for r in table.records}
    options = dict(sheet='Журнал', status_map=status_map,
                   equipment_decisions={'0007': 'new', '0008': 'new'},
                   client_decisions={'0001': 'new', '0002': 'new'},
                   owner_decisions={'owner:qa-own1': 'new'})
    broken = preview_history(store, SOURCE, {**mapping, 'discount': mapping['payment_state']}, **options)
    assert broken['counts']['error'] == 3
    for group, row, value in zip(broken['groups'], (2, 3, 4), ('known', 'known', 'unknown')):
        error = '\n'.join(group['errors'])
        assert f'Строка {row}' in error and 'Скидка' in error and value in error
        assert mapping['payment_state'] in error and 'сопоставление' in error
    assert not store.repairs() and not store.equipment()

    correct = preview_history(store, SOURCE, mapping, **options)
    assert correct['counts']['ready'] == 3
    assert not store.repairs()
    result = import_history(store, correct, confirmed=True)
    assert result['imported'] == 3
    rows = {row['number']: row for row in store.repairs()}
    assert [(rows[k]['total'], rows[k]['paid'], rows[k]['balance']) for k in ('QA-R1','QA-R2','QA-R3')] == [
        (10001, 2001, 8000), (21012, 0, 21012), (None, None, None)]
    assert {row['number'] for row in store.equipment()} == {'0007', '0008'}
    assert rows['QA-R2']['equipment_id'] == rows['QA-R1']['equipment_id']
    repeated = preview_history(store, SOURCE, mapping, **options)
    assert repeated['counts']['already_imported'] == 3
    assert SOURCE.read_bytes() == original
