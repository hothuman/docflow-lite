import hashlib,json
import pytest
from docx import Document
from docflow.service.repository import ServiceStore
from docflow.service.profiles import save_profile,profile
from docflow.service.documents import generate_document
from docflow.service.estimates import save_draft,freeze_estimate,get_estimate
from docflow.service.validation import ServiceError


def setup(tmp_path,body):
 s=ServiceStore(tmp_path/'project');owner=s.save_client({'name':'QA OWNER','phone':'OWNER-PHONE'});customer=s.save_client({'name':'QA REQUESTER','contact':'QA Visit contact'})
 eq=s.save_equipment({'number':'QA-007','model':'QA Pump','serial':'','owner_id':owner});repair=s.create_repair(eq,'QA-R1','QA Complaint',client_id=customer)
 path=tmp_path/'form.docx';d=Document();d.add_paragraph('QA SAMPLE — fictional form, no customer approval');d.add_paragraph(body);d.save(path)
 return s,repair,eq,owner,customer,path


def data(**extra):return {'name':'QA SAMPLE','organization_name':'QA SAMPLE Workshop','contact':'QA only','details':'QA SAMPLE, no real requisites',**extra}


def body(path):
 d=Document(path);return '\n'.join([p.text for p in d.paragraphs]+[c.text for t in d.tables for r in t.rows for c in r.cells])


def test_stage8_document_owner_is_distinct_from_requester(tmp_path):
 s,r,eq,owner,customer,path=setup(tmp_path,'Owner {{owner_name}} / Requester {{client_name}} / Contact {{client_contact}}')
 before=hashlib.sha256(path.read_bytes()).hexdigest();save_profile(s,data(),assets={'templates':{'intake':path}},repair_id=r)
 out=generate_document(s,r,'intake');text=body(out);assert 'Owner QA OWNER' in text and 'Requester QA REQUESTER' in text and 'QA Visit contact' in text
 assert hashlib.sha256(path.read_bytes()).hexdigest()==before


def test_stage8_scalar_aliases_and_explicit_optional_blank(tmp_path):
 s,r,eq,owner,customer,path=setup(tmp_path,'Владелец {{Собственник}} / Заказчик {{Заказчик}} / Доп {{Дополнение}}')
 values=data(template_field_mapping={'intake':{'Собственник':'owner_name','Заказчик':'client_name','Дополнение':''}},template_required_fields={'intake':['Собственник','Заказчик']})
 key=save_profile(s,values,assets={'templates':{'intake':path}},repair_id=r);out=generate_document(s,r,'intake');text=body(out)
 assert 'QA OWNER' in text and 'QA REQUESTER' in text and '{{' not in text
 with s.db.connection() as c:assert profile(c,key)['template_field_mapping']['intake']['Дополнение']==''


def test_stage8_required_empty_blocks_without_docx_or_fake_value(tmp_path):
 s,r,eq,owner,customer,path=setup(tmp_path,'Serial {{equipment_serial}}')
 save_profile(s,data(template_required_fields={'warranty':['equipment_serial']}),assets={'templates':{'warranty':path}},repair_id=r)
 before=s.snapshot(r)['generated_documents']
 with pytest.raises(ServiceError,match='equipment_serial'):generate_document(s,r,'warranty')
 assert s.snapshot(r)['generated_documents']==before
 s.save_equipment({**s.get('equipment',eq),'serial':'QA-CONFIRMED-SERIAL'},eq)
 assert 'QA-CONFIRMED-SERIAL' in body(generate_document(s,r,'warranty'))


def test_stage8_new_estimate_owner_snapshot_and_old_document_immutable(tmp_path):
 s,r,eq,owner,customer,path=setup(tmp_path,'Owner {{owner_name}} / Customer {{client_name}}')
 save_profile(s,data(),assets={'templates':{'estimate_preliminary':path}},repair_id=r)
 save_draft(s,r,[{'kind':'work','name':'QA Work','quantity':'1','price':'10.01'}]);quote=freeze_estimate(s,r,'preliminary','QA')
 with s.db.connection() as c:assert get_estimate(c,quote)['payload']['owner']['id']==owner
 old=generate_document(s,r,'estimate_preliminary',estimate_id=quote);old_sha=hashlib.sha256(old.read_bytes()).hexdigest()
 other=s.save_client({'name':'QA NEW OWNER'});s.save_equipment({**s.get('equipment',eq),'owner_id':other},eq)
 again=generate_document(s,r,'estimate_preliminary',estimate_id=quote);assert 'QA OWNER' in body(again) and 'QA NEW OWNER' not in body(again)
 assert hashlib.sha256(old.read_bytes()).hexdigest()==old_sha


@pytest.mark.parametrize('bad',[
 {'template_field_mapping':{'intake':{'total':'client_name'}}},
 {'template_field_mapping':{'intake':{'X':'__import__'}}},
 {'template_required_fields':{'intake':[['unhashable']]}},
 {'template_required_fields':{'intake':['Unknown']}},
])
def test_stage8_invalid_field_configuration_does_not_commit(tmp_path,bad):
 s=ServiceStore(tmp_path/'p')
 with pytest.raises(ServiceError):save_profile(s,data(**bad))
 with s.db.connection() as c:assert c.execute('SELECT COUNT(*) FROM organization_profiles').fetchone()[0]==0


def test_stage8_legacy_quote_cannot_read_current_owner(tmp_path):
 from docflow.service.document_fields import readiness_context
 s,r,eq,owner,customer,path=setup(tmp_path,'QA {{client_name}}');save_draft(s,r,[]);quote=freeze_estimate(s,r,'preliminary','QA');snap=s.snapshot(r)
 legacy=json.loads(json.dumps(snap));legacy['estimates'][0]['payload'].pop('owner')
 _,_,values=readiness_context(legacy,'estimate_preliminary');assert values['owner_name']=='' and values['client_name']=='QA REQUESTER'


def test_stage8_template_field_dialog_keeps_unresolved_input(qt_application_lifetime):
 from docflow.ui.service.template_fields import TemplateFieldsDialog
 from PySide6.QtWidgets import QDialog
 d=TemplateFieldsDialog({'Владелец','client_name','Дополнение'}, {},'intake');d.show()
 try:
  assert d.mapping_widgets['Владелец'].currentData()=='owner_name'
  d.accept();assert d.isVisible() and 'Дополнение' in d.error.text()
  combo=d.mapping_widgets['Дополнение'];combo.setCurrentIndex(combo.findData(''));d.accept();assert d.result()==QDialog.DialogCode.Accepted
  assert d.values()[0]['Дополнение']==''
 finally:d.reject()

def test_stage8_preliminary_unknown_payment_is_not_fabricated_zero(tmp_path):
 s,r,eq,owner,customer,path=setup(tmp_path,'Paid {{paid}} / Balance {{balance}} / Total {{total}}')
 save_profile(s,data(),assets={'templates':{'estimate_preliminary':path}},repair_id=r)
 save_draft(s,r,[{'kind':'work','name':'QA','quantity':'1','price':'100.01'}]);quote=freeze_estimate(s,r,'preliminary','QA')
 with s.db.connection() as c:assert 'paid' not in get_estimate(c,quote)['payload']['totals']
 text=body(generate_document(s,r,'estimate_preliminary',estimate_id=quote))
 assert 'Paid Неизвестно / Balance Неизвестно / Total 100,01' in text
