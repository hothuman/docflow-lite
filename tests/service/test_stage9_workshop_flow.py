
from docx import Document

from docflow.service.estimates import freeze_estimate, save_draft
from docflow.service.repository import ServiceStore
from docflow.ui.service.repair_editor import RepairDialog
from docflow.ui.window import MainWindow
from test_stage9_cp3_journal import wait_idle


def test_workshop_preserves_partial_payment_and_versions_after_issue_and_repeat(tmp_path, monkeypatch):
    root = tmp_path/'workshop'
    store = ServiceStore(root)
    owner = store.save_client({'name':'Учебный владелец'})
    customer = store.save_client({'name':'Учебный заказчик'})
    equipment = store.save_equipment({'owner_id':owner,'number':'0007','model':'Учебный насос'})
    first = store.create_repair(equipment,'QA-FIRST','Нет давления',client_id=customer)
    store.save_repair(first,{'defects':'Износ уплотнения','plan':'Проверить и заменить уплотнение'})
    work = {'kind':'work','name':'Диагностика и работа','quantity':'1','price':'1500'}
    part = {'kind':'part','name':'Уплотнение','quantity':'1','price':'350'}
    save_draft(store,first,[work,part])
    freeze_estimate(store,first,'preliminary','Учебный мастер')
    store.save_item(first,work)
    store.save_item(first,part)
    freeze_estimate(store,first,'final','Учебный мастер')
    store.add_payment(first,'1000')
    window=MainWindow(service_root=root);window.show();window.navigate(5)
    try:
        wait_idle(window)
        workspace=window.service_workspace
        dialog=RepairDialog(workspace,workspace.store.snapshot(first));workspace.dialogs.append(dialog)
        import docflow.ui.service.repair_editor as editor
        asked=[]
        monkeypatch.setattr(editor,'confirm',lambda parent,message,action:asked.append((message,action)) or True)
        dialog.issue()
        wait_idle(window)
        assert asked and '850,00 ₽' in asked[0][0] and asked[0][1]=='Подтвердить выдачу'
        assert workspace.store.snapshot(first)['repair']['status']=='issued'
        assert (dialog.snapshot['totals']['total'],dialog.snapshot['totals']['paid'],dialog.snapshot['totals']['balance'])==(185000,100000,85000)
        before=workspace.store.snapshot(first)
        second=workspace.store.create_repair(equipment,'QA-REPEAT','Повторная проверка')
        current=workspace.store.snapshot(first)
        assert current['totals']==before['totals'] and current['estimates']==before['estimates']
        assert workspace.store.snapshot(second)['totals']['balance']==0
        assert workspace.store.snapshot(first)['owner']['id']==owner and current['client']['id']==customer
        assert len(workspace.store.repairs(equipment_id=equipment))==2
        dialog.doc_kind.setCurrentIndex(dialog.doc_kind.findData('completion'))
        dialog.check_document()
        assert 'нейтральная форма' in dialog.document_status.text().lower()
        dialog.generate()
        wait_idle(window)
        path=dialog._last_document
        assert path.is_file()
        document=Document(path)
        actual='\n'.join([p.text for p in document.paragraphs]+[c.text for t in document.tables for row in t.rows for c in row.cells])
        assert 'QA-FIRST' in actual and '850,00' in actual and 'Уплотнение' in actual
        workspace.dialogs.remove(dialog);dialog.close()
    finally:
        window.close()
