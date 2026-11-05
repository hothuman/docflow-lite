"""Behavioural regressions from the independent rc7 audit, not pixel snapshots."""
import pytest
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QMessageBox
from PySide6.QtTest import QTest
from test_stage1_upgrade_copy import app,idle,dispose
from docflow.ui.service.workspace import ServiceWorkspace
from docflow.ui.service.forms import FieldsDialog
from docflow.ui.service.intake import IntakeDialog
from docflow.ui.service.catalog import CatalogDialog

@pytest.mark.parametrize('entity',['client','equipment'])
@pytest.mark.parametrize('edit',[False,True])
@pytest.mark.parametrize('failure',['validation','permission'])
def test_save_error_retains_form_then_retry_is_single_atomic_write(app,tmp_path,monkeypatch,entity,edit,failure):
    w=ServiceWorkspace(root=tmp_path/'p');idle(app,w)
    client=w.store.save_client({'name':'QA Owner'});equipment=w.store.save_equipment({'number':'QA-1','model':'QA Old','owner_id':client})
    key=client if entity=='client' else equipment
    table='clients' if entity=='client' else 'equipment';method='save_client' if entity=='client' else 'save_equipment'
    original=getattr(w.store,method);calls=[]
    def save(*args):
        calls.append(args)
        if failure=='permission' and len(calls)==1:raise PermissionError('QA denied')
        return original(*args)
    monkeypatch.setattr(w.store,method,save);monkeypatch.setattr(QMessageBox,'warning',lambda *a:None)
    w.refresh();idle(app,w);before=w.store.get(table,key);state={'phase':0,'dialog':None,'observed':False};errors=[]
    def step():
        try:
            d=QApplication.activeModalWidget()
            if not isinstance(d,FieldsDialog) or w.worker:return
            if not state['phase']:
                state['dialog']=d
                values={'name':'QA Updated','contact':'QA Preserve'} if entity=='client' else {'number':'QA-1' if not edit else 'QA-2','model':'QA Updated','serial':'QA Preserve','owner_id':client}
                if failure=='validation':values['name' if entity=='client' else 'number']='' if entity=='client' or edit else 'QA-1'
                for k,v in values.items():
                    f=d.fields[k]
                    if hasattr(f,'setCurrentIndex'):f.setCurrentIndex(f.findData(v))
                    else:f.setText(v)
                state['phase']=1;d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
            elif state['phase']==1:
                assert d.isVisible();assert d.fields['contact' if entity=='client' else 'serial'].text()=='QA Preserve'
                assert w.store.get(table,key)==before
                assert any(x.isVisible() and x.text() for x in d.errors.values()) or d.error.isVisible()
                state['observed']=True;state['phase']=2
                d.fields['name' if entity=='client' else 'number'].setText('QA Updated' if entity=='client' else 'QA-2')
                button=d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save);button.click();button.click()
        except Exception as e:
            errors.append(e)
            if isinstance(QApplication.activeModalWidget(),FieldsDialog):QApplication.activeModalWidget().reject()
    timer=QTimer();timer.timeout.connect(step);timer.start(10);timeout=QTimer();timeout.setSingleShot(True);timeout.timeout.connect(lambda:state['dialog'] and state['dialog'].reject());timeout.start(5000)
    try:
        getattr(w,'_client_dialog' if entity=='client' else '_equipment_dialog')(before if edit else None);idle(app,w)
        assert not errors,errors;assert state['observed'],'Form closed before validation/save failure could be corrected'
        assert not state['dialog'].isVisible()
        result=w.store.clients() if entity=='client' else w.store.equipment()
        assert len(result)==(1 if edit else 2)
        assert len([r for r in result if r['name' if entity=='client' else 'number']==('QA Updated' if entity=='client' else 'QA-2')])==1
    finally:timer.stop();timeout.stop();dispose(app,w)

