"""Archived source identities stay discoverable without changing links/money."""
import csv
import json
import time
import pytest
from docflow.service.backup import create_backup, restore_backup
from docflow.service.history_import import preview_history, import_history
from docflow.service.link_audit import audit_links, audit_summary
from docflow.service.repository import ServiceStore


def archived_source_project(root):
    store = ServiceStore(root)
    client = store.save_client({'name': 'Synthetic source client'})
    equipment = store.save_equipment({'number': 'TEMP-1', 'model': 'Synthetic pump', 'serial': '', 'owner_id': client})
    repair = store.create_repair(equipment, 'ARCH-1', 'Synthetic source observation')
    store.save_repair(repair, {'status': 'historical'})
    store.set_financial_evidence(repair, False, False, 'Synthetic source payments and identity not reconciled')
    store.archive('equipment', equipment)
    store.archive('clients', client)
    return store, client, equipment, repair


def test_archived_source_links_exist_while_default_entity_lists_are_empty(tmp_path):
    store, client, equipment, repair = archived_source_project(tmp_path/'project')
    assert store.clients() == [] and store.equipment() == []
    assert store.repairs()[0]['id'] == repair
    assert store.repairs()[0]['client_id'] == client
    assert store.repairs()[0]['equipment_id'] == equipment
    assert store.equipment(archived=True, active=True) == []
    before = (store.root/'service.db').read_bytes()
    report = audit_links(store)
    assert (store.root/'service.db').read_bytes() == before
    assert report['status'] == 'passed' and not report['writes_performed']
    assert report['counts']['clients'] == {'current': 0, 'archived': 1}
    assert report['counts']['equipment'] == {'current': 0, 'archived': 1}
    assert report['counts']['repairs_with_archived_equipment'] == 1
    assert not any(report['problems'].values())
    text = json.dumps(report)
    assert all(secret not in text for secret in (client, equipment, repair, 'Synthetic source client', 'TEMP-1'))
    assert 'Это само по себе не означает потерю связей' in audit_summary(report)
    assert store.repairs()[0]['paid'] is None and store.repairs()[0]['balance'] is None


def test_explicit_same_name_clients_same_model_devices_and_replay_restore(tmp_path):
    store = ServiceStore(tmp_path/'project')
    path = tmp_path/'source.csv'
    headers = ['repair_number', 'equipment_number', 'model', 'client_key', 'client_name', 'received_at', 'payment_state', 'final_total']
    rows = [['101','DEVICE-A','Same model','client-a','Same client name','','unknown','100'],
            ['102','DEVICE-B','Same model','client-b','Same client name','','unknown','200']]
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        out = csv.writer(f,delimiter=';');out.writerow(headers);out.writerows(rows)
    plan = preview_history(store,path,{key:key for key in headers},default_status='historical',
                           equipment_decisions={'device-a':'new','device-b':'new'},
                           client_decisions={'client-a':'new','client-b':'new'})
    assert all(group['status'] == 'ready' for group in plan['groups'])
    assert import_history(store,plan,confirmed=True)['imported'] == 2
    assert import_history(store,plan,confirmed=True)['already_imported'] == 2
    assert len(store.clients()) == 2 and len(store.equipment()) == 2
    assert len({r['client_id'] for r in store.repairs()}) == 2
    assert len({r['equipment_id'] for r in store.repairs()}) == 2
    assert all(r['paid'] is None and r['balance'] is None for r in store.repairs())
    create_backup(store,tmp_path/'copy.zip');restore_backup(tmp_path/'copy.zip',tmp_path/'restored')
    restored = ServiceStore(tmp_path/'restored')
    assert audit_links(restored) == audit_links(store)
    assert {(r['id'], r['client_id'], r['equipment_id']) for r in restored.repairs()} == {(r['id'], r['client_id'], r['equipment_id']) for r in store.repairs()}


@pytest.fixture(scope='module')
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def idle(app, workspace):
    until = time.monotonic()+20
    while workspace.worker or workspace._pending_refresh:
        app.processEvents();time.sleep(.005)
        assert time.monotonic() < until
    app.processEvents()


def test_visible_archive_hint_action_and_unknown_money_in_actual_models(app, tmp_path):
    from PySide6.QtCore import Qt
    from docflow.ui.service.workspace import ServiceWorkspace
    store, client, equipment, repair = archived_source_project(tmp_path/'project')
    workspace = ServiceWorkspace(root=store.root);workspace.show();idle(app, workspace)
    try:
        assert workspace.views['clients'].proxy.rowCount() == 0
        assert workspace.views['equipment'].proxy.rowCount() == 0
        for key in ('clients','equipment'):
            assert 'В архиве: 1' in workspace.archive_hints[key].text()
            assert not workspace.archive_buttons[key].isHidden()
        workspace.archive_buttons['equipment'].click();idle(app,workspace)
        assert workspace.archived.isChecked() and workspace.views['equipment'].proxy.rowCount() == 1
        assert workspace.views['equipment'].records.rows[0]['id'] == equipment
        workspace.archive_buttons['clients'].click();idle(app,workspace)
        assert workspace.clients_archived.isChecked() and workspace.views['clients'].proxy.rowCount() == 1
        workspace.searches['equipment'].setText('does not exist')
        assert workspace.views['equipment'].proxy.rowCount() == 0
        assert 'По выбранным фильтрам' in workspace.empty_labels['equipment'].text()
        workspace.reset_filter_buttons['equipment'].click()
        assert workspace.views['equipment'].proxy.rowCount() == 1
        model = workspace.views['finance'].records
        balance_column = next(i for i, (key,_) in enumerate(model.columns) if key=='balance')
        index = model.index(0,balance_column)
        assert model.data(index,Qt.ItemDataRole.DisplayRole) == 'Неизвестно'
        assert model.data(index,Qt.ItemDataRole.ForegroundRole) is None
        assert store.snapshot(repair)['totals']['paid'] is None
        assert store.get('clients',client)['archived'] == 1 and store.get('equipment',equipment)['archived'] == 1
    finally:
        workspace.close()
        if workspace.project_lock:workspace.project_lock.unlock()
        workspace.deleteLater();app.processEvents()
