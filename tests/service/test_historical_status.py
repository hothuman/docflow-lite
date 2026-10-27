import csv
from pathlib import Path
import pytest
from docflow.service.repository import ServiceStore
from docflow.service.history_import import preview_history,import_history
from docflow.service.backup import create_backup,restore_backup
from docflow.service.validation import ServiceError


def source(tmp_path):
    p=tmp_path/'archive.csv'
    values={'repair_number':'ARCH-1','equipment_number':'TEMP-1','model':'Provisional source observation',
            'client_key':'temp-client','client_name':'Identity not reconciled','received_at':'',
            'works':'Original work description','cost_state':'unknown','payment_state':'unknown',
            'notes':'Source observation; not a confirmed physical equipment identity'}
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(values);w.writerow(values.values())
    s=ServiceStore(tmp_path/'project')
    def preview(status):return preview_history(s,p,{k:k for k in values},equipment_decisions={'temp-1':'new'},client_decisions={'temp-client':'new'},default_status=status)
    return s,preview


def test_undated_archive_is_searchable_but_not_active_or_a_debt(tmp_path):
    s,preview=source(tmp_path);plan=preview('historical')
    report=import_history(s,plan,confirmed=True);r=report['rows'][0]['repair_id']
    snap=s.snapshot(r);assert snap['repair']['received_at']=='' and snap['repair']['status']=='historical'
    assert snap['totals']['paid'] is None and snap['totals']['balance'] is None
    assert s.dashboard()['active']==0 and s.dashboard()['debt']==0
    assert len(s.repairs(query='original work'))==1
    assert import_history(s,plan,confirmed=True)['already_imported']==1
    s.save_repair(r,{'notes':'Source kept, still undated'})
    with pytest.raises(ServiceError):s.save_repair(r,{'status':'accepted'})
    create_backup(s,tmp_path/'copy.zip');restore_backup(tmp_path/'copy.zip',tmp_path/'restored')
    assert ServiceStore(tmp_path/'restored').snapshot(r)['repair']['received_at']==''
    s.save_repair(r,{'received_at':'2020-01-02','status':'accepted'})
    assert s.dashboard()['active']==1


def test_working_import_still_rejects_missing_date(tmp_path):
    s,preview=source(tmp_path);plan=preview('accepted')
    assert plan['groups'][0]['errors']
    with pytest.raises(ServiceError):import_history(s,plan,confirmed=True)
    assert not s.repairs()


def test_archive_does_not_accept_malformed_date(tmp_path):
    s,preview=source(tmp_path);plan=preview('historical');p=Path(plan['path'])
    text=p.read_text(encoding='utf-8-sig');text=text.replace(';;Original',';01.02;Original');p.write_text(text,encoding='utf-8-sig')
    fresh=preview('historical');assert fresh['groups'][0]['errors']
