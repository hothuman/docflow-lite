"""Opt-in synthetic Stage8 contracts shared by pytest and the frozen candidate.

Uses the existing engines. Never opens a customer project or sends any data.
"""
import csv
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from threading import Event


def samples_root():
    import sys
    return (Path(sys.executable).parent/'examples/stage8' if getattr(sys,'frozen',False)
            else Path(__file__).resolve().parents[3]/'examples/stage8')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def business(store):
    tables=('clients','equipment','repair_orders','repair_items','payments','estimate_versions',
            'generated_documents','attachments','catalog_items')
    with store.db.connection() as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==6
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not list(c.execute('PRAGMA foreign_key_check'))
        return {t:[tuple(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY rowid')] for t in tables}


def expect_error(fn,phrase=''):
    from .validation import ServiceError
    try:fn()
    except ServiceError as exc:
        assert phrase in str(exc),(phrase,str(exc));return str(exc)
    raise AssertionError('Expected safe rejection')


def history_options():
    return dict(sheet='Журнал',source_label='QA Stage8 journal',separate_clients=True,
                equipment_decisions={'0007':'new','0008':'new'},
                client_decisions={'0001':'new','0002':'new'},owner_decisions={'owner:qa-own1':'new'},
                status_map={'Принято':'accepted'})


def run_domain(root,samples=None):
    from docx import Document
    from .repository import ServiceStore
    from .history_import import preview_history,import_history
    from .import_mapping import propose_history
    from ..data import load_table
    from .profiles import save_profile,profile
    from .documents import generate_document,KINDS
    from .estimates import save_draft,freeze_estimate,get_estimate,record_event
    from .attachments import add_attachment
    from .backup import create_backup,restore_backup
    from .catalog_loader import parse_file
    from .catalog import preview,apply,search
    root=Path(root);root.mkdir(exist_ok=False,parents=True);samples=Path(samples or samples_root())
    inputs={p.relative_to(samples).as_posix():sha(p) for p in samples.rglob('*') if p.is_file()}
    assert inputs and (samples/'journal-qa.xlsx').is_file()
    proof={'method':'synthetic domain calls; independent SQL, Decimal and SHA oracles',
           'real_customer_data':False,'schema':6,'scenarios':{},'documents':{}}
    s=ServiceStore(root/'Journal');path=samples/'journal-qa.xlsx'
    headers=load_table(path,sheet='Журнал').headers;mapping,_=propose_history(headers)
    # An ambiguous financial column must be explicitly selected, never inferred.
    mapping.update(final_total='Окончательный итог',payment_state='Полнота оплат (known / unknown)')
    before=business(s);opt=history_options();plan=preview_history(s,path,mapping,**opt)
    assert business(s)==before
    assert all(g['status']=='ready' for g in plan['groups']),plan['groups']
    report=import_history(s,plan,confirmed=True);assert report['imported']==3
    assert (len(s.clients()),len(s.equipment()),len(s.repairs()))==(3,2,3)
    r1=next(r for r in s.repairs() if r['number']=='QA-R1');r2=next(r for r in s.repairs() if r['number']=='QA-R2')
    r3=next(r for r in s.repairs() if r['number']=='QA-R3')
    assert r1['equipment_id']==r2['equipment_id'] and r1['client_id']!=r2['client_id']
    snap=s.snapshot(r1['id']);assert snap['owner']['name']=='QA Собственник' and snap['client']['name']=='QA Заказчик А'
    assert (r1['total'],r1['paid'],r1['balance'])==(10001,2001,8000)
    assert r3['total'] is None and r3['paid'] is None and r3['balance'] is None
    proof['scenarios']['C_excel']={'counts':[3,2,3],'leading_zero':'0007','unknown_finances':True,'preview_writes':False}
    before=business(s);again=preview_history(s,path,mapping,**opt)
    replay=import_history(s,again,confirmed=True);assert replay['already_imported']==3 and business(s)==before
    proof['scenarios']['D_replay']=replay
    # Change a previously seen row under the same source identity, without overwriting it.
    table=load_table(samples/'journal-qa-no-bom.csv');changed=root/'changed.csv'
    with changed.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(table.headers)
        for i,record in enumerate(table.records):
            values=dict(record.values)
            if not i:values['Неисправность']='QA changed complaint'
            w.writerow([values.get(h,'') for h in table.headers])
    # Sheet is part of source identity: compare CSV against its own initial import.
    conflict_store=ServiceStore(root/'Conflicts');csvopt={**opt,'sheet':None}
    import_history(conflict_store,preview_history(conflict_store,samples/'journal-qa-no-bom.csv',mapping,**csvopt),confirmed=True)
    before=business(conflict_store);conflict=preview_history(conflict_store,changed,mapping,**csvopt)
    assert conflict['groups'][0]['status']=='conflict'
    expect_error(lambda:import_history(conflict_store,conflict,confirmed=True))
    assert business(conflict_store)==before
    proof['scenarios']['E_conflict']={'states':[g['status'] for g in conflict['groups']],'unchanged':True}
    for filename,encoding in [('journal-qa-utf8.csv','utf-8-sig'),('journal-qa-no-bom.csv','utf-8'),('journal-qa-cp1251.csv','cp1251')]:
        p=preview_history(ServiceStore(root/encoding),samples/filename,mapping,**{**csvopt,'encoding':encoding})
        assert all(g['status']=='ready' for g in p['groups'])
    expect_error(lambda:preview_history(s,samples/'journal-qa-cp1251.csv',mapping,encoding='utf-8',**csvopt))
    # A: a new repair, all recorded transitions, explicit manual consent and exact money.
    owner=s.save_client({'name':'QA New Owner','phone':'QA-PHONE'})
    customer=s.save_client({'name':'QA New Requester','contact':'QA Contact'})
    eq=s.save_equipment({'number':'QA-NEW-009','model':'QA Pump','serial':'QA-009','owner_id':owner})
    key=s.create_repair(eq,'QA-NEW-R1','QA New complaint',client_id=customer)
    items=[{'kind':'work','name':'QA Осмотр','quantity':'1.5','price':'1000.25'},
           {'kind':'part','name':'QA Деталь','quantity':'2','price':'200.10'}]
    for item in items:s.save_item(key,item)
    expected=sum(int((Decimal(x['quantity'])*Decimal(x['price'])*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) for x in items)-2
    assert expected==190056
    s.save_repair(key,{'status':'diagnostics','defects':'QA Причина','plan':'QA План','discount':'0.02'})
    save_draft(s,key,items,discount='0.02');pre=freeze_estimate(s,key,'preliminary','QA Operator',reason='QA synthetic profile configuration')
    record_event(s,pre,'approved','QA Operator','QA manual synthetic consent, not real customer approval')
    s.save_repair(key,{'status':'repair','approval':'Согласовано','approval_note':'QA Manual'})
    s.add_payment(key,'400.00',occurred_at='2026-11-06');s.add_payment(key,'0.01',kind='refund',occurred_at='2026-11-06')
    s.save_repair(key,{'status':'ready','completed_at':'2026-11-06'})
    final=freeze_estimate(s,key,'final','QA Operator',reason='QA synthetic profile configuration')
    with s.db.connection() as c:payload=get_estimate(c,final)['payload_json']
    totals=s.snapshot(key)['totals'];assert (totals['total'],totals['paid'],totals['balance'])==(expected,39999,150057)
    proof['scenarios']['A_new']={'total_cents':expected,'paid_cents':39999,'balance_cents':150057,'manual_consent':True}
    settings=json.loads((samples/'Templates-QA/QA-TEMPLATE-SETTINGS.json').read_text(encoding='utf-8'))
    profile_data={'name':'QA SAMPLE','organization_name':'QA SAMPLE Workshop','contact':'QA only',
                  'details':'QA SAMPLE — fictional, no real requisites','warranty_terms':'',
                  'template_field_mapping':{k:v['mapping'] for k,v in settings.items()},
                  'template_required_fields':{k:v['required'] for k,v in settings.items()}}
    assets={'templates':{k:samples/'Templates-QA'/v['file'] for k,v in settings.items()}}
    save_profile(s,profile_data,assets=assets,repair_id=key)
    expect_error(lambda:generate_document(s,key,'warranty'),'УсловияГарантии')
    profile_data['warranty_terms']='QA SAMPLE: условие только для проверки поля. Реальных обязательств не устанавливает.'
    save_profile(s,profile_data,assets=assets,repair_id=key)
    image=add_attachment(s,key,samples/'qa-photo.png','QA synthetic image')
    # Quotes frozen before branding keep their old organization snapshots by design.
    pre=freeze_estimate(s,key,'preliminary','QA Operator',reason='QA synthetic profile configuration');final=freeze_estimate(s,key,'final','QA Operator',reason='QA synthetic profile configuration')
    for kind in KINDS:
        doc=generate_document(s,key,kind,image_ids=(image,) if kind=='completion' else (),
                              estimate_id=pre if kind=='estimate_preliminary' else final if kind=='estimate_final' else None)
        d=Document(doc);text='\n'.join([p.text for p in d.paragraphs]+[c.text for t in d.tables for r in t.rows for c in r.cells])
        assert '{{' not in text
        if kind in settings:assert 'QA New Owner' in text and 'QA New Requester' in text
        proof['documents'][kind]=str(doc)
    olddocs={p:sha(p) for p in proof['documents'].values()}
    s.save_repair(key,{'status':'issued','issued_at':'2026-11-06','handover':'QA handed over'})
    repeat=s.create_repair(eq,'QA-NEW-R2','QA Repeat',client_id=owner)
    assert len(s.repairs(equipment_id=eq))==2 and s.snapshot(key)['client']['id']==customer
    assert s.snapshot(repeat)['owner']['id']==owner
    assert all(sha(p)==h for p,h in olddocs.items())
    proof['scenarios']['B_repeat']={'equipment_number':'QA-NEW-009','repairs':2,'old_files_unchanged':True}
    proof['scenarios']['G_documents']={'kinds':list(KINDS),'source_hashes_unchanged':True,'required_field_retry':True,'word_checked':False}
    parsed=parse_file(samples/'catalog-1c-qa.xlsx',sheet='Каталог')
    cm=dict(zip(('external_id','sku','name','kind','price','currency'),parsed['headers']))
    cp=preview(s,parsed,'QA 1C synthetic',cm);before=business(s)
    assert cp.counts=={'new':2} and business(s)==before
    expect_error(lambda:apply(s,cp))
    stop=Event();stop.set();expect_error(lambda:apply(s,cp,confirmed=True,cancel=stop),'отмен')
    assert business(s)==before;apply(s,cp,confirmed=True)
    assert {x['external_key'] for x in search(s)}=={'00007','00008'}
    before=business(s);apply(s,preview(s,parsed,'QA 1C synthetic',cm),confirmed=True);assert business(s)==before
    changed_catalog={**parsed,'rows':[(line,{**raw,'Цена':'112.34'}) for line,raw in parsed['rows']]}
    apply(s,preview(s,changed_catalog,'QA 1C synthetic',cm,update_prices=True),confirmed=True)
    with s.db.connection() as c:assert get_estimate(c,final)['payload']['totals']['total']==expected
    assert all(sha(p)==h for p,h in olddocs.items())
    proof['scenarios']['F_catalog']={'leading_zero':'00007','cancel_rollback':True,'repeat_no_duplicates':True,'frozen_quote_unchanged':True}
    # Transactional failure after person creation and safe retry.
    failed=ServiceStore(root/'Rollback');p=preview_history(failed,path,mapping,**opt);before=business(failed)
    with failed.db.connection(True) as c:c.execute("CREATE TRIGGER qa_abort BEFORE INSERT ON repair_orders BEGIN SELECT RAISE(ABORT,'QA failure'); END")
    try:import_history(failed,p,confirmed=True)
    except Exception as exc:assert 'QA failure' in str(exc.__cause__),repr(exc)
    else:raise AssertionError('SQL trigger did not abort')
    assert business(failed)==before
    with failed.db.connection(True) as c:c.execute('DROP TRIGGER qa_abort')
    assert import_history(failed,p,confirmed=True)['imported']==3
    proof['scenarios']['J_negative']={'sql_rollback':True,'retry':True,'wrong_encoding':True,'cancel':True}
    archive=create_backup(s,root/'Full-backup.zip');restored=restore_backup(archive,root/'Restored')
    restored=ServiceStore(restored);assert business(restored)==business(s)
    for p,h in olddocs.items():assert sha(restored.root/Path(p).relative_to(s.root))==h
    proof['scenarios']['H_backup']={'database_equal':True,'documents_equal':True,'archive_sha256':sha(archive)}
    proof['scenarios']['I_legacy']={'status':'covered separately by v4/v5/v6 tests and frozen compatibility route'}
    assert inputs=={p.relative_to(samples).as_posix():sha(p) for p in samples.rglob('*') if p.is_file()}
    proof['status']='passed';(root/'STAGE8-DOMAIN.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return proof


def exercise(window,app,output,idle):
    """Qt handler tests; not native human input or customer acceptance."""
    from ..ui.service.import_wizard import HistoryWizard
    from ..ui.service.template_fields import TemplateFieldsDialog
    from PySide6.QtWidgets import QWizard,QScrollArea
    samples=samples_root();proof=run_domain(output/'Stage8')
    window.navigate(5);ui=window.service_workspace;idle(ui)
    d=HistoryWizard(ui);ui.dialogs.append(d);d.show();layouts=[]
    try:
        d.path.setText(str(samples/'journal-qa-cp1251.csv'));d.encoding.setCurrentIndex(d.encoding.findData('cp1251'));d.source_label.setText('QA Stage8 UI')
        d.next();idle(ui);assert d.currentId()==1 and d.mapping()['repair_number']=='Номер обращения'
        for width,height in ((560,420),(820,620),(1060,740)):
            d.resize(width,height);app.processEvents()
            assert d.button(QWizard.WizardButton.NextButton).isVisible()
            assert d.currentPage().findChild(QScrollArea).horizontalScrollBar().maximum()==0
            assert d.grab().save(str(output/f'stage8-import-{width}.png'))
            layouts.append({'requested':[width,height],'actual':d.size().toTuple()})
        d.next();idle(ui);assert d.currentId()==2
        for combo in d.statuses.values():combo.setCurrentIndex(combo.findData('accepted'))
        d.decisions=history_options();d.decisions={k:v for k,v in d.decisions.items() if k.endswith('decisions')}
        d.mappings['final_total'].setCurrentIndex(d.mappings['final_total'].findData('Окончательный итог'))
        d.mappings['payment_state'].setCurrentIndex(d.mappings['payment_state'].findData('Полнота оплат (known / unknown)'))
        d.next();idle(ui);assert d.currentId()==3
        assert all(g['status']=='ready' for g in d.plan['groups']),d.plan
        assert d.grab().save(str(output/'stage8-dry-run.png'))
        d.confirmed.setChecked(True);d.next();idle(ui);assert d.currentId()==4 and d.result_report['imported']==3
        assert d.grab().save(str(output/'stage8-import-report.png'))
    finally:d.reject();ui.dialogs.remove(d)
    t=TemplateFieldsDialog(['Собственник','Заказчик','Дополнение'],{},'intake',ui);t.show()
    try:
        assert t.mapping_widgets['Собственник'].currentData()=='owner_name'
        t.mapping_widgets['Дополнение'].setCurrentIndex(t.mapping_widgets['Дополнение'].findData(''))
        t.required_widgets['Заказчик'].setChecked(True)
        assert t.values()[0]['Дополнение']=='' and 'Заказчик' in t.values()[1]
        for width,height in ((560,420),(820,620),(1060,740)):
            t.resize(width,height);app.processEvents()
            assert all(scroll.horizontalScrollBar().maximum()==0 for scroll in t.findChildren(QScrollArea))
            assert t.grab().save(str(output/f'stage8-template-fields-{width}.png'))
    finally:t.reject()
    proof.update(qt_layouts=layouts,method_qt='synthetic Qt controls in the running application; not native file picker/Word')
    (output/'STAGE8-REGRESSIONS.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return ['stage8_history_and_documents']
