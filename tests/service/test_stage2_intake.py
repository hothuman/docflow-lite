import pytest
from docflow.service.repository import ServiceStore
from docflow.service.validation import ServiceError

def payload():return {'client':{'name':'Synthetic client'},'equipment':{'number':'DEVICE-2','model':'Synthetic model'},'complaint':'Synthetic complaint'}

def test_atomic_intake_repeat_and_exact_replay(tmp_path):
    store=ServiceStore(tmp_path);p=payload();first=store.intake(**p,request_id='one')
    assert store.intake(**p,request_id='one')==first
    eq=store.snapshot(first)['equipment'];second=store.intake(equipment_id=eq['id'])
    assert first!=second and len(store.clients())==len(store.equipment())==1
    assert len(store.repairs(equipment_id=eq['id']))==2
    with pytest.raises(ServiceError):store.intake(**{**p,'complaint':'Changed'},request_id='one')

@pytest.mark.parametrize('failure',['duplicate_number','invalid_client','invalid_equipment','invalid_repair'])
def test_failed_intake_rolls_back_every_record_and_sequence(tmp_path,failure):
    store=ServiceStore(tmp_path);p=payload()
    if failure=='duplicate_number':store.intake(**p,number='1000');p['equipment']['number']='NEW-DEVICE';p['number']='1000'
    elif failure=='invalid_client':p['client']['email']='bad'
    elif failure=='invalid_equipment':p['equipment']['model']=''
    else:p['number']='x'*101
    before=(store.clients(),store.equipment(),store.repairs(),store.preview_repair_number())
    with pytest.raises(ServiceError):store.intake(**p)
    assert (store.clients(),store.equipment(),store.repairs(),store.preview_repair_number())==before

def test_same_model_never_merges_devices_or_clients(tmp_path):
    store=ServiceStore(tmp_path);store.intake(**payload());p=payload();p['equipment']['number']='OTHER';store.intake(**p)
    assert len(store.clients())==len(store.equipment())==2

def test_other_requester_does_not_change_equipment_owner(tmp_path):
    store=ServiceStore(tmp_path);first=store.intake(**payload());eq=store.snapshot(first)['equipment'];other=store.save_client({'name':'Other requester'})
    second=store.intake(equipment_id=eq['id'],client_id=other)
    assert store.snapshot(second)['client']['id']==other
    assert store.get('equipment',eq['id'])['owner_id']==eq['owner_id']
    assert store.snapshot(first)['client']['id']==eq['owner_id']
