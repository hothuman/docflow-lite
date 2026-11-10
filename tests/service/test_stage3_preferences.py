import json
import pytest
from docflow.ui.service import dashboard_preferences as p
from docflow.ui.settings import preferences,save_widths,load_widths

@pytest.mark.parametrize('value',[None,{},['new',{}],['new',[]],['new','documents','evil()'],['new','new'],['documents'],"__import__('os')"])
def test_damaged_or_executable_settings_fall_back(tmp_path,monkeypatch,value):
    monkeypatch.setenv('DOCFLOW_SETTINGS_DIR',str(tmp_path));settings=preferences();settings.setValue('dashboard/actions',json.dumps(value));settings.sync()
    actions,warning=p.load_actions();assert actions==p.DEFAULT and warning

def test_presets_persist_reset_and_preserve_other_ini_keys(tmp_path,monkeypatch):
    monkeypatch.setenv('DOCFLOW_SETTINGS_DIR',str(tmp_path));save_widths('repairs',{0:123})
    for order in p.PRESETS.values():assert p.save_actions(order) and p.load_actions()==(order,'')
    assert p.reset_actions() and p.load_actions()==(p.DEFAULT,'') and load_widths('repairs')=={0:123}
    with pytest.raises(ValueError):p.save_actions(['new'])

def test_quote_requires_explicit_price_unit_type():
    from docflow.ui.service.catalog import quote_line
    from docflow.service.validation import ServiceError
    row={'description':'','source':'Synthetic','external_key':'001','sku':'P-1'}
    values={'kind':'part','name':'Учебная деталь','unit':'шт.','quantity':'1','price':''}
    with pytest.raises(ServiceError):quote_line(row,values)
    values['price']='0';assert quote_line(row,values)['price_cents']==0
    values['unit']=''
    with pytest.raises(ServiceError):quote_line(row,values)
