"""Business number transitions preserve IDs, issued documents and history."""
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from docflow.service.repository import ServiceStore
from docflow.service.validation import ServiceError
from docflow.service.documents import generate_document
from docflow.service.backup import create_backup,restore_backup
from docflow.service.profiles import save_profile


def project(tmp_path):
    s=ServiceStore(tmp_path/'project')
    client=s.save_client({'name':'Учебный клиент'})
    equipment=s.save_equipment({'number':'APP-1000','model':'Учебная модель','owner_id':client})
    return s,equipment


def test_default_sequence_preview_cancel_and_manual_jump(tmp_path):
    s,e=project(tmp_path)
    assert s.preview_repair_number()==s.preview_repair_number()=='1'
    first=s.create_repair(e,'1000')
    assert s.preview_repair_number()=='1001'
    second=s.create_repair(e)
    assert s.get('repair_orders',second)['number']=='1001'
    again=ServiceStore(s.root)
    assert again.preview_repair_number()=='1002'
    assert again.get('equipment',e)['number']=='APP-1000'
    assert first!=second


def test_rename_is_audited_old_search_reserved_and_docs_frozen(tmp_path):
    s,e=project(tmp_path);r=s.create_repair(e,'1000')
    path=generate_document(s,r,'intake');original=path.read_bytes()
    revision=s.rename_repair(r,'1005','Учебная корректировка',expected_revision=0)
    assert revision==1 and s.get('repair_orders',r)['id']==r
    assert s.repairs('1000')[0]['id']==s.repairs('1005')[0]['id']==r
    assert path.read_bytes()==original and s.documents()[0]['path']==path.relative_to(s.root).as_posix()
    assert s.preview_repair_number()=='1006'
    with s.db.connection() as c:
        record=c.execute("SELECT detail FROM operations WHERE action='renumber'").fetchone()
    assert json.loads(record[0])=={'before':'1000','after':'1005','reason':'Учебная корректировка'}
    with pytest.raises(ServiceError,match='уже использован'):s.create_repair(e,'1000')
    another=s.create_repair(e)
    with pytest.raises(ServiceError,match='уже использован'):s.rename_repair(another,'1005')
    with pytest.raises(ServiceError,match='уже изменена'):s.rename_repair(r,'2000',expected_revision=0)
    backup=create_backup(s,tmp_path/'backup.zip');copy=ServiceStore(restore_backup(backup,tmp_path/'restored'))
    # Equipment APP-1000 can also match: the renamed repair must remain present.
    assert r in {row['id'] for row in copy.repairs('1000')}
    assert copy.preview_repair_number()==s.preview_repair_number()
    assert (copy.root/path.relative_to(s.root)).read_bytes()==original


def test_two_stores_parallel_creates_no_collisions(tmp_path):
    s,e=project(tmp_path);other=ServiceStore(s.root)
    with ThreadPoolExecutor(max_workers=4) as pool:
        keys=list(pool.map(lambda i:(s if i%2 else other).create_repair(e),range(12)))
    assert len(set(keys))==12
    assert {r['number'] for r in s.repairs()}=={str(i) for i in range(1,13)}


def test_historical_sequence_not_inferred_and_prefix_preserved(tmp_path):
    s,e=project(tmp_path);r=s.create_repair(e,'1')
    # Simulate stored legacy observation; no sequence guessed from its number.
    with s.db.connection(True) as c:
        c.execute("UPDATE repair_orders SET number='999999',status='historical' WHERE id=?",(r,))
        c.execute('DELETE FROM service_settings')
    assert s.preview_repair_number()=='1'
    save_profile(s,{'name':'Учебный старый профиль','number_prefix':'R-','number_start':1000},activate=True)
    assert s.preview_repair_number()=='R-001000'
    created=s.create_repair(e);assert s.get('repair_orders',created)['number']=='R-001000'
    save_profile(s,{'name':'Учебные простые номера','number_prefix':'','number_start':1000},activate=True)
    assert s.preview_repair_number()=='1000'


def test_previous_number_is_searchable_in_visible_grid(tmp_path):
    from PySide6.QtWidgets import QApplication
    from docflow.ui.service.widgets import Grid
    app=QApplication.instance() or QApplication([])
    s,e=project(tmp_path);key=s.create_repair(e,'OLD-ALIAS')
    s.rename_repair(key,'1005')
    grid=Grid([('number','№ ремонта')]);grid.install(s.repairs())
    grid.proxy.setFilterFixedString('OLD-ALIAS')
    assert grid.proxy.rowCount()==1
    assert grid.proxy.index(0,0).data()=='1005'
    grid.deleteLater();app.processEvents()
