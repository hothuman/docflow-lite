"""Opt-in rc8 synthetic Qt routes, also executed inside the delivered EXE.

No external input injection, real customer data, Word or human UX acceptance.
"""
import argparse,hashlib,json,os,sqlite3,sys,time,traceback
from pathlib import Path

CHECKS={'client_retry','equipment_retry','permission_retry','intake_cancel_discard','catalog_geometry','core_retry_context','documents_versions'}

def exercise(window,app,output,idle):
    from PySide6.QtCore import QTimer,Qt
    from PySide6.QtWidgets import QApplication,QMessageBox,QDialogButtonBox
    from PySide6.QtTest import QTest
    from ..ui.service.forms import FieldsDialog
    from ..ui.service.intake import IntakeDialog
    from ..ui.service.catalog import CatalogDialog
    from ..release_check import wait_idle
    from .documents import generate_document,KINDS
    from .attachments import add_attachment
    from PySide6.QtGui import QImage,QColor
    window.navigate(5);ui=window.service_workspace;idle(ui);checks=[]
    def capture(widget,name):app.processEvents();assert widget.grab().save(str(output/(name+'.png')))
    def modal_retry(entity,permission=False):
        state={'phase':0,'observed':False};errors=[];owned=[];original=None
        if permission:
            original=ui.store.save_client;attempt=[]
            def denied_once(*args):
                attempt.append(1)
                if len(attempt)==1:raise PermissionError('Synthetic denied write')
                return original(*args)
            ui.store.save_client=denied_once
        def step():
            d=QApplication.activeModalWidget()
            if isinstance(d,QMessageBox):d.button(QMessageBox.StandardButton.Ok).click();return
            if not isinstance(d,FieldsDialog) or ui.worker:return
            try:
                if not state['phase']:
                    owned.append(d);state['phase']=1
                    if entity=='client':d.fields['name'].setText('QA Permission' if permission else '');d.fields['contact'].setText('QA PRESERVE')
                    else:d.fields['number'].setText('QA-EXISTING');d.fields['model'].setText('QA New');d.fields['serial'].setText('QA PRESERVE')
                    d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
                elif state['phase']==1:
                    assert d.isVisible() and d.error.isVisible();assert d.fields['contact' if entity=='client' else 'serial'].text()=='QA PRESERVE'
                    state['observed']=True;state['phase']=2;capture(d,entity+('-permission' if permission else '')+'-retained-error')
                    d.fields['name' if entity=='client' else 'number'].setText('QA Permission' if permission else 'QA Client' if entity=='client' else 'QA-NEW')
                    b=d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save);QTest.mouseClick(b,Qt.MouseButton.LeftButton);b.click()
            except Exception:
                errors.append(traceback.format_exc());d.reject()
        timer=QTimer();timer.timeout.connect(step);timer.start(15);timeout=QTimer();timeout.setSingleShot(True);timeout.timeout.connect(lambda:owned and owned[0].reject());timeout.start(20000)
        try:
            getattr(ui,'new_client' if entity=='client' else 'new_equipment')();idle(ui);assert not errors and state['observed'],errors
        finally:
            timer.stop();timeout.stop()
            if original:ui.store.save_client=original
    modal_retry('client');checks.append('client_retry')
    owner=ui.store.clients()[0]['id'];ui.store.save_equipment({'number':'QA-EXISTING','model':'QA','owner_id':owner});ui.refresh();idle(ui)
    modal_retry('equipment');checks.append('equipment_retry');modal_retry('client',True);checks.append('permission_retry')
    # Independent SQL verification rather than trusting the success banner.
    with sqlite3.connect((ui.store.root/'service.db').as_uri()+'?mode=ro',uri=True) as c:
        assert c.execute("SELECT COUNT(*) FROM clients WHERE name='QA Client'").fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM equipment WHERE number='QA-NEW'").fetchone()[0]==1
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    answer={'yes':False}
    def question():
        m=QApplication.activeModalWidget()
        if isinstance(m,QMessageBox):m.button(QMessageBox.StandardButton.Yes if answer['yes'] else QMessageBox.StandardButton.No).click()
    timer=QTimer();timer.timeout.connect(question);timer.start(15)
    try:
        for field in ('phone','repair_number'):
            d=IntakeDialog(ui);d.show();d.new_equipment.setChecked(True);d.new_client.setChecked(True)
            if field=='repair_number':d.more.setChecked(True)
            getattr(d,field).setText('QA UNSAVED');answer['yes']=False;d.reject();assert d.isVisible() and d.dirty;capture(d,field+'-cancel-keeps-input');answer['yes']=True;d.reject();assert not d.isVisible()
    finally:timer.stop()
    checks.append('intake_cancel_discard')
    d=CatalogDialog(ui);d.show();d.tabs.setCurrentIndex(1);layouts=[]
    for width,height in ((560,420),(820,620),(1060,740),(0,0)):
        avail=d.screen().availableGeometry()
        if width:d.showNormal();d.resize(min(width,avail.width()-20),min(height,avail.height()-40))
        else:d.showMaximized()
        for _ in range(3):app.processEvents();time.sleep(.01)
        d.import_scroll.ensureWidgetVisible(d.skip);app.processEvents();capture(d,'catalog-'+str(width or 'max'))
        assert d.import_scroll.horizontalScrollBar().maximum()==0
        layouts.append({'requested':[width,height],'actual':d.size().toTuple(),'available':avail.size().toTuple(),'horizontal_max':0})
    d.accept();checks.append('catalog_geometry')
    window.navigate(0);window.load_demo();wait_idle(window);window.navigate(3)
    invalid=output/'regular-file';invalid.write_bytes(b'QA preserve');window.output_path.setText(str(invalid));window.start_generation();wait_idle(window)
    assert window.operation_notice.isVisible() and window.last_result is None
    window.navigate(5);idle(ui);assert not window.operation_notice.isVisible()
    window.navigate(3);window.output_path.setText(str(output/'Core DOCX'));window.start_generation();wait_idle(window)
    assert window.last_result.documents==4 and not window.operation_notice.isVisible() and invalid.read_bytes()==b'QA preserve';capture(window,'core-retry-success');checks.append('core_retry_context')
    key=ui.store.intake(client={'name':'QA Documents'},equipment={'number':'QA-DOC','model':'QA Synthetic'});first=generate_document(ui.store,key,'intake');before=hashlib.sha256(first.read_bytes()).hexdigest()
    for n in range(48):ui.store.save_item(key,{'kind':'work','name':f'QA Длинная строка {n+1:02d}','description':'QA Проверка переноса. '+('Длинное описание синтетической работы. '*4),'quantity':'1','price':'1.01'})
    photo=output/'qa-photo.png';im=QImage(800,400,QImage.Format.Format_RGB32);im.fill(QColor('#193b3d'));assert im.save(str(photo));image=add_attachment(ui.store,key,photo,'QA синтетическая фотография')
    from .estimates import save_draft,freeze_estimate
    save_draft(ui.store,key,[{'kind':'work','name':f'QA Длинная строка {n+1:02d}','description':'QA Проверка переноса. '+('Длинное описание синтетической работы. '*4),'quantity':'1','price':'1.01'} for n in range(48)])
    documents={}
    for kind in KINDS:
        estimate=freeze_estimate(ui.store,key,kind.removeprefix('estimate_'),'QA Synthetic') if kind.startswith('estimate_') else None
        documents[kind]=str(generate_document(ui.store,key,kind,image_ids=(image,) if kind=='completion' else (),estimate_id=estimate))
    assert hashlib.sha256(first.read_bytes()).hexdigest()==before;checks.append('documents_versions')
    assert set(checks)==CHECKS
    return {'status':'passed','checks':checks,'layout':layouts,'documents':documents,'old_document_unchanged':True,'word_checked':False,'human_acceptance':False,'QA03':'Partial: OOXML/footer improvement; long-row ONLYOFFICE pagination requires separate renderer verification'}

def run(output,require_windows=False):
    from PySide6.QtWidgets import QApplication
    from ..gui import MainWindow,configure_app
    from .. import __version__
    output=Path(output).absolute()
    if output.exists():raise ValueError('Use a new synthetic QA folder')
    output.mkdir(parents=True);os.environ['DOCFLOW_SETTINGS_DIR']=str(output/'Settings');app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False)
    proof={'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),'qt_platform':app.platformName()};window=None
    def idle(ui):
        deadline=time.monotonic()+60
        while ui.worker or ui._pending_refresh:app.processEvents();time.sleep(.005);assert time.monotonic()<deadline
        app.processEvents();app.processEvents()
    try:
        if require_windows:assert sys.platform=='win32' and app.platformName()=='windows' and proof['frozen']
        window=MainWindow(service_root=output/'Synthetic');window.show();proof.update(exercise(window,app,output,idle))
    except Exception:proof.update(status='failed',traceback=traceback.format_exc())
    finally:
        if window:window.close();app.processEvents()
        (output/'HOTFIX-SELF-TEST.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if proof['status']=='passed' else 1

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--require-windows',action='store_true');a=p.parse_args(argv)
    try:return run(a.output,a.require_windows)
    except (ValueError,OSError) as exc:
        if sys.stderr is not None:print(str(exc),file=sys.stderr)
        return 2
