import csv
from threading import Event
import pytest
from docflow.service.repository import ServiceStore
from docflow.service.history_import import preview_history,import_history
from docflow.service.validation import ServiceError
H=['repair_number','received_at','equipment_number','model','client_key','client_name','works','final_total']
def source(tmp_path,rows,headers=H,encoding='utf-8-sig'):
 p=tmp_path/'journal.csv'
 with p.open('w',encoding=encoding,newline='') as f:w=csv.writer(f,delimiter=';');w.writerow(headers);w.writerows(rows)
 return p

def options():return dict(equipment_decisions={'0007':'new'},client_decisions={'c1':'new'},default_status='accepted',source_label='QA stable journal')

def test_stage8_explicit_csv_encoding(tmp_path):
 s=ServiceStore(tmp_path/'p');p=source(tmp_path,[['R1','2026-11-06','0007','Насос','C1','QA Клиент','Осмотр','100.01']],encoding='cp1251')
 plan=preview_history(s,p,dict(zip(H,H)),encoding='cp1251',**options());assert plan['groups'][0]['status']=='ready';import_history(s,plan,confirmed=True);assert s.equipment()[0]['number']=='0007'

def test_stage8_conflicting_person_key_is_not_last_row_wins(tmp_path):
 s=ServiceStore(tmp_path/'p');p=source(tmp_path,[['R1','2026-11-06','0007','QA','C1','QA Alpha','','0'],['R2','2026-11-07','0007','QA','C1','QA Beta','','0']])
 plan=preview_history(s,p,dict(zip(H,H)),**options());assert all(g['errors'] for g in plan['groups'])
 with pytest.raises(ServiceError):import_history(s,plan,confirmed=True)
 assert not s.clients() and not s.repairs()

def test_stage8_unkeyed_names_remain_separate(tmp_path):
 s=ServiceStore(tmp_path/'p');p=source(tmp_path,[['R1','2026-11-06','0007','QA','','QA Same','','0'],['R2','2026-11-07','0007','QA','','QA Same','','0']])
 plan=preview_history(s,p,dict(zip(H,H)),separate_clients=True,default_status='accepted');keys=[g['data']['client_key'] for g in plan['groups']];assert len(set(keys))==2
 assert all(g['status']=='needs_confirmation' for g in plan['groups'])

def test_stage8_distinct_owner_and_requester(tmp_path):
 s=ServiceStore(tmp_path/'p');headers=H+['owner_key','owner_name','owner_phone'];p=source(tmp_path,[['R1','2026-11-06','0007','QA','C1','QA Requester','','0','O1','QA Owner','QA-OWNER-PHONE']],headers)
 plan=preview_history(s,p,dict(zip(headers,headers)),owner_decisions={'owner:o1':'new'},**options());assert plan['groups'][0]['status']=='ready';import_history(s,plan,confirmed=True)
 snap=s.snapshot(s.repairs()[0]['id']);assert snap['client']['name']=='QA Requester' and snap['owner']['name']=='QA Owner';assert snap['owner']['phone']=='QA-OWNER-PHONE'

def test_stage8_cancel_rolls_back_selected_batch(tmp_path):
 s=ServiceStore(tmp_path/'p');p=source(tmp_path,[['R1','2026-11-06','0007','QA','C1','QA','','0']]);plan=preview_history(s,p,dict(zip(H,H)),**options());cancel=Event();cancel.set()
 with pytest.raises(ServiceError,match='отмен'):import_history(s,plan,confirmed=True,cancel=cancel)
 assert not s.clients() and not s.repairs()

@pytest.mark.parametrize('encoding',['utf-8','utf-8-sig','cp1251','auto'])
def test_stage8_codepages_bom_and_strict_error(tmp_path,encoding):
 s=ServiceStore(tmp_path/'p');p=source(tmp_path,[['R1','2026-11-06','0007','Насос','C1','QA Клиент','','0']],encoding='cp1251' if encoding=='cp1251' else 'utf-8-sig')
 plan=preview_history(s,p,dict(zip(H,H)),encoding=encoding,**options());assert plan['groups'][0]['data']['model']=='Насос'
 if encoding=='cp1251':
  with pytest.raises(ServiceError):preview_history(s,p,dict(zip(H,H)),encoding='utf-8',**options())
 with pytest.raises(ServiceError):preview_history(s,p,dict(zip(H,H)),encoding='bogus',**options())
 assert not s.clients()

def test_stage8_appended_rows_reuse_confirmed_source_identity(tmp_path):
 s=ServiceStore(tmp_path/'p');rows=[['R1','2026-11-06','0007','QA','C1','QA Customer','','0']];p=source(tmp_path,rows)
 plan=preview_history(s,p,dict(zip(H,H)),**options());import_history(s,plan,confirmed=True)
 eq=s.equipment()[0]['id'];person=s.clients()[0]['id'];rows.append(['R2','2026-11-07','0007','QA','C1','QA Customer','','0']);source(tmp_path,rows)
 opt=options();opt['equipment_decisions']={'0007':eq}
 bad=preview_history(s,p,dict(zip(H,H)),**opt);assert bad['groups'][1]['status']=='error' and bad['groups'][1]['source_client_ids']==[person]
 opt['client_decisions']={'c1':person};plan=preview_history(s,p,dict(zip(H,H)),**opt);result=import_history(s,plan,confirmed=True)
 assert (result['imported'],result['already_imported'])==(1,1) and len(s.clients())==1 and len(s.repairs())==2
 again=preview_history(s,p,dict(zip(H,H)),**opt);assert import_history(s,again,confirmed=True)['already_imported']==2

def test_stage8_mid_transaction_cancel_is_atomic(tmp_path,monkeypatch):
 s=ServiceStore(tmp_path/'p');p=source(tmp_path,[['R1','2026-11-06','0007','QA','C1','QA','','0']]);plan=preview_history(s,p,dict(zip(H,H)),**options());cancel=Event();audit=s.audit
 def stop(*a,**kw):
  result=audit(*a,**kw);cancel.set();return result
 monkeypatch.setattr(s,'audit',stop)
 with pytest.raises(ServiceError,match='отмен'):import_history(s,plan,confirmed=True,cancel=cancel)
 assert not s.clients() and not s.repairs()
 with s.db.connection() as c:assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert not c.execute('PRAGMA foreign_key_check').fetchall();assert c.execute('SELECT COUNT(*) FROM import_records').fetchone()[0]==0

def test_stage8_legacy_replay_in_new_gui_mode_preserves_hashes(tmp_path):
 s=ServiceStore(tmp_path/'p');p=source(tmp_path,[['R1','2026-11-06','0007','QA','','QA Same','','0']]);mapping=dict(zip(H,H));opt=options();opt['client_decisions']={'qa same':'new'}
 plan=preview_history(s,p,mapping,**opt);import_history(s,plan,confirmed=True)
 modern=preview_history(s,p,mapping,separate_clients=True,**opt);assert modern['groups'][0]['record_sha256']==plan['groups'][0]['record_sha256'];assert import_history(s,modern,confirmed=True)['already_imported']==1

def test_stage8_russian_english_proposals_preserve_ambiguity():
 from docflow.service.import_mapping import propose_history
 choices,candidates=propose_history(['Номер обращения','Дата приема','Постоянный номер','Клиент','Owner','Owner phone','Сумма','Стоимость услуг','Телефон','Телефон заказчика'])
 assert choices['repair_number']=='Номер обращения' and choices['received_at']=='Дата приема' and choices['equipment_number']=='Постоянный номер'
 assert choices['owner_name']=='Owner' and choices['work_cost']=='Стоимость услуг'
 assert 'client_phone' not in choices and len(candidates['client_phone'])==2
 assert 'final_total' not in choices  # A generic "Сумма" is not a confirmed final total.
