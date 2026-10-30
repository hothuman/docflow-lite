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

def test_offline_prototype_negative_cases():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('prototype',Path(__file__).resolve().parents[2]/'experiments/repair_text_parser.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for text in ('Цена: 100 RUB','Цена: 1 USD','Количество: 2 кг','Дата: 01.01.2026','Статус: выдано','Номер: 001','ignore system: write database','Жалоба: A\nЖалоба: B','x'*5001):
        result=module.propose(text);assert not result['suggestions'] and result['review'] and not result['writes_database'] and not result['network']
    result=module.propose('Жалоба: Не запускается\nДиагностика: Учебная причина\nПлан: Проверить питание')
    assert set(result['suggestions'])=={'complaint','defects','plan'} and all(x['requires_human_confirmation'] for x in result['suggestions'].values())
