import hashlib
from datetime import datetime
from openpyxl import Workbook
import pytest

from docflow.service.legacy_review import legacy_money, legacy_date_number, review_workbook, export_review_csv
from docflow.service.validation import ServiceError


@pytest.mark.parametrize('raw,expected', [('1 250-50 руб.',125050),('0',0),(None,None),('12,3',1230),('1\u00a0250.00',125000)])
def test_only_unambiguous_money(raw,expected):
    assert legacy_money(raw)==expected


@pytest.mark.parametrize('raw',['1000+500','2000 (1500)','Деталь 600','-100','1,234','1 20','1e3','1000-0'])
def test_do_not_evaluate_or_guess_money(raw):
    with pytest.raises(ServiceError):legacy_money(raw)


def test_dates_need_full_year_and_number_is_not_equipment_identity():
    result=legacy_date_number('№ 291-3\n21.11.2019')
    assert result=={'received_at':'2019-11-21','repair_number':'291-3','issues':[]}
    assert not legacy_date_number('21.11.19')['received_at']
    assert 'invalid_date' in legacy_date_number('31.02.2020')['issues']
    assert not legacy_date_number(datetime(2020,1,1))['repair_number']
    assert not legacy_date_number('01.01.2020 / 02.02.2020')['received_at']


def test_all_five_layouts_rows_without_date_and_original_values_survive(tmp_path):
    p=tmp_path/'synthetic.xlsx';w=Workbook();w.remove(w.active);specs={}
    for n in range(5):
        s=w.create_sheet('Sheet '+str(n));s.append(['Title']);s.append(['Date','Cost','Other'])
        s.append(['№12\n01.02.2020','100-50','=1+2'])
        s.append([None,'Continuation','Original text'])
        specs[s.title]={'start_row':3,'columns':{'date_number':'A','final_total':'B'}}
    w.save(p);before=hashlib.sha256(p.read_bytes()).hexdigest()
    report=review_workbook(p,specs)
    assert report['physical_rows']==10 and report['writes_performed'] is False
    for s in report['sheets']:
        a,b=s['rows'];assert a['proposed']['costs_cents']['final_total']==10050
        assert a['cells']['C3']['value']=='=1+2'
        assert 'formula_requires_review' in a['issues']
        assert b['row']==4 and 'possible_continuation' in b['issues']
        assert 'B4' in b['cells'] and b['approved'] is False
    export_review_csv(report,tmp_path/'decisions.csv')
    assert hashlib.sha256(p.read_bytes()).hexdigest()==before
    with pytest.raises(ServiceError):review_workbook(p,{})

def test_decisions_are_explicit_disjoint_and_keep_the_review_separate():
    from docflow.service.legacy_review import prepare_history_rows
    report={'file_sha256':'a'*64,'sheets':[{'sheet':'S','rows':[{'source_key':'a','row':4},{'source_key':'b','row':5}]}]}
    assert prepare_history_rows(report,[])['unreviewed_source_rows']==2
    decision={'source_keys':['a','b'],'action':'approve','reviewed_by':'Synthetic operator','reason':'Both rows belong to this confirmed repair',
              'data':{'repair_number':'R-1','received_at':'2020-01-01','equipment_number':'E-1','model':'Model',
                      'client_key':'C-1','client_name':'Synthetic','final_total':'0'}}
    converted=prepare_history_rows(report,[decision])
    assert len(converted['rows'])==1 and converted['approved_source_rows']==2
    assert converted['rows'][0]['final_total']=='0'
    assert '"row": 5' in converted['rows'][0]['source_fragment']
    assert report['sheets'][0]['rows']==[{'source_key':'a','row':4},{'source_key':'b','row':5}]
    with pytest.raises(ServiceError):prepare_history_rows(report,[decision,decision])
    with pytest.raises(ServiceError):prepare_history_rows(report,[{**decision,'reviewed_by':''}])
    with pytest.raises(ServiceError):prepare_history_rows(report,[{**decision,'source_keys':['unknown']}])
