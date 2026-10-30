import hashlib
import json
from threading import Event
import pytest
from docflow.service import catalog as api
from docflow.service.catalog_loader import parse_file,MAX_BYTES
from docflow.service.repository import ServiceStore
from docflow.service.validation import ServiceError
from docflow.service.estimates import save_draft,freeze_estimate,get_estimate
from docflow.service.backup import create_backup,restore_backup

@pytest.fixture
def store(tmp_path):return ServiceStore(tmp_path/'project')

def parsed(rows):
    return {'headers':list(api.FIELDS),'rows':[(i+2,r) for i,r in enumerate(rows)],'file_sha256':'0'*64,'file_name':'synthetic.csv','sheet':'','encoding':'auto'}

def item(code='001',**extra):return dict(external_id=code,sku='SKU-'+code,name='Учебная деталь '+code,kind='part',unit='шт.',group='Группа',subgroup='Подгруппа',shelf_raw='Полка 01',price='123.45',currency='RUB',**extra)

def plan(store,rows,**kwargs):return api.preview(store,parsed(rows),'Synthetic',{k:k for k in api.FIELDS},**kwargs)
def commit(store,rows,**kwargs):return api.apply(store,plan(store,rows,**kwargs),confirmed=True)

def test_exact_keys_leading_zeros_case_groups_replay_missing_rows(store):
    rows=[item(x) for x in ('001','1','ABC','abc')];commit(store,rows)
    assert len(api.search(store))==4
    assert plan(store,rows).counts=={'unchanged':4}
    commit(store,rows);commit(store,rows[:1]);assert len(api.search(store))==4
    row=api.search(store,'SKU-001')[0];assert row['external_id']=='001' and row['subgroup']=='Подгруппа' and row['shelf_raw']=='Полка 01'
    with store.db.connection() as c:assert c.execute('SELECT COUNT(*) FROM catalog_imports').fetchone()[0]==3

@pytest.mark.parametrize('field,value', [('external_id',' 001'),('sku','001 '),('price','1.001'),('price','NaN'),('price','-1'),('currency','rub'),('name','=SUM(1)'),('description','https://evil.invalid'),('name','bad\u202ename'),('kind','товар')])
def test_bad_rows_are_visible_and_no_implicit_apply(store,field,value):
    row=item();row[field]=value;p=plan(store,[row]);assert p.counts=={'error':1}
    with pytest.raises(ServiceError):api.apply(store,p,confirmed=True)
    assert not api.search(store)

def test_unknown_prices_and_zero_distinct_and_currency_required(store):
    a=item();a['price']='';a['currency']='';b=item('002');b['price']='0'
    commit(store,[a,b]);rows=api.search(store);assert rows[0]['price_cents'] is None and rows[1]['price_cents']==0
    a['price']='1';assert plan(store,[a]).counts=={'error':1}

def test_duplicate_file_and_existing_sku_conflicts(store):
    a=item();assert plan(store,[a,a]).counts=={'conflict':2};commit(store,[a])
    b=item('002');b['sku']=a['sku'];p=plan(store,[b,item('003')]);assert p.counts=={'conflict':1,'new':1}
    with pytest.raises(ServiceError):api.apply(store,p,confirmed=True)
    r=api.apply(store,p,confirmed=True,skip_problems=True);assert r['skipped']==1 and len(api.search(store))==2

def test_updates_price_policy_stale_plan_and_explicit_confirmation(store):
    row=item();p=plan(store,[row])
    with pytest.raises(ServiceError):api.apply(store,p)
    commit(store,[row]);row['price']='999';row['name']='Новое имя';p=plan(store,[row]);assert p.rows[0].item['price_cents']==12345
    api.apply(store,p,confirmed=True);p=plan(store,[row],update_prices=True);assert p.rows[0].item['price_cents']==99900
    row['name']='Конкурентное изменение';commit(store,[row])
    with pytest.raises(ServiceError,match='изменился'):api.apply(store,p,confirmed=True)

def test_atomic_cancel_rolls_back_rows_and_report(store):
    class CancelDuringWrite:
        calls=0
        def is_set(self):self.calls+=1;return self.calls==3
    with pytest.raises(ServiceError,match='отменён'):api.apply(store,plan(store,[item(str(i)) for i in range(10)]),confirmed=True,cancel=CancelDuringWrite())
    assert not api.search(store)
    with store.db.connection() as c:assert c.execute('SELECT COUNT(*) FROM catalog_imports').fetchone()[0]==0

def test_bounded_large_catalog_replay(store):
    rows=[item(f'{i:05}') for i in range(2000)];commit(store,rows);assert plan(store,rows).counts=={'unchanged':2000}
    with store.db.connection() as c:assert c.execute('SELECT COUNT(*) FROM catalog_items').fetchone()[0]==2000
    with pytest.raises(ServiceError):plan(store,[item()]*5001)

def test_quote_snapshot_documents_backup_profiles_and_history_survive_updates(store,tmp_path):
    from docflow.ui.service.catalog import quote_line
    from docflow.service.documents import generate_document
    commit(store,[item()]);entry=api.search(store)[0];line=quote_line(entry,dict(kind='part',name=entry['name'],unit='шт.',quantity='2',price='123.45'))
    repair=store.intake(client={'name':'Учебный'},equipment={'number':'D-1','model':'Учебная модель'})
    save_draft(store,repair,[line]);estimate=freeze_estimate(store,repair,'preliminary','Учебный мастер')
    document=generate_document(store,repair,'estimate_preliminary',estimate_id=estimate);before_hash=hashlib.sha256(document.read_bytes()).hexdigest()
    with store.db.connection() as c:before=get_estimate(c,estimate)
    profile=json.loads(plan(store,[item()]).config_json);api.save_profile(store,'Synthetic',profile)
    updated=item();updated['price']='999.99';commit(store,[updated],update_prices=True)
    assert api.search(store)[0]['price_cents']==99999 and store.snapshot(repair)['totals']['total']==0
    with store.db.connection() as c:assert get_estimate(c,estimate)==before
    assert hashlib.sha256(document.read_bytes()).hexdigest()==before_hash
    recovered=ServiceStore(restore_backup(create_backup(store,tmp_path/'backup.zip'),tmp_path/'restored'))
    assert api.search(recovered)==api.search(store) and api.profiles(recovered)==api.profiles(store)
    with recovered.db.connection() as c:assert get_estimate(c,estimate)==before and c.execute('SELECT COUNT(*) FROM catalog_imports').fetchone()[0]==2

@pytest.mark.parametrize('encoding',['utf-8-sig','cp1251'])
def test_process_csv_encoding_exact_codes(tmp_path,encoding):
    path=tmp_path/'synthetic.csv';path.write_text('external_id;name\n001;Учебная деталь\n',encoding=encoding);before=path.read_bytes()
    value=parse_file(path,encoding=encoding);assert value['rows'][0][1]['external_id']=='001' and value['rows'][0][1]['name']=='Учебная деталь'
    assert path.read_bytes()==before and value['file_sha256']==hashlib.sha256(before).hexdigest()

def test_process_xlsx_sheets_and_formula_preview(store,tmp_path):
    from openpyxl import Workbook
    path=tmp_path/'synthetic.xlsx';wb=Workbook();ws=wb.active;ws.title='Первый';ws.append(['external_id','name']);ws.append(['001','Учебная деталь']);ws=wb.create_sheet('Второй');ws.append(['external_id','name']);ws.append(['002','=1+1']);wb.save(path)
    value=parse_file(path);assert value['sheet']=='Первый' and value['sheets']==['Первый','Второй']
    assert value['rows'][0][1]['external_id']=='001'
    with pytest.raises(ServiceError):parse_file(path,sheet='Второй')

def test_process_cancellation_timeout_size_and_bad_encoding(tmp_path):
    path=tmp_path/'test.csv';path.write_text('a,b\n1,2\n');event=Event();event.set()
    with pytest.raises(ServiceError,match='отменён'):parse_file(path,cancel=event)
    with pytest.raises(ServiceError,match='времени'):parse_file(path,timeout=0)
    with pytest.raises(ServiceError):parse_file(path,encoding='made-up')
    path.write_bytes(b'x'*(MAX_BYTES+1))
    with pytest.raises(Exception):parse_file(path)

def test_stage2_schema5_copy_preserves_all_original_rows_and_files(tmp_path):
    import sqlite3
    from test_stage1_upgrade_copy import legacy_project,hashes
    from docflow.service.database import MIGRATIONS
    from docflow.service.project_upgrade import copy_project_for_upgrade
    from docflow.service.compatibility_check import assert_upgrade_preserved
    original=legacy_project(tmp_path/'stage2')
    with sqlite3.connect(original/'service.db') as c:
        for statement in MIGRATIONS[5]:c.execute(statement)
        c.execute('PRAGMA user_version=5')
    before=hashes(original);target=copy_project_for_upgrade(original,tmp_path/'stage3');assert hashes(original)==before
    assert_upgrade_preserved(original/'service.db',target/'service.db');assert list(target.glob('service.db.before-v6-*.bak'))
