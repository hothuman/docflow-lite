"""Opt-in real GUI/domain diagnostic, also executed by the frozen Windows EXE.

No tests run at ordinary startup. Fields are entered into real Qt dialogs; no
bank, network or customer's data is used. Native OS dialogs/Word are separate.
"""
import argparse,json,os,platform,sys,time,traceback
from pathlib import Path

def run(output,require_windows=False):
    from PySide6.QtCore import QTimer,Qt
    from PySide6.QtGui import QImage,QColor
    from PySide6.QtWidgets import QApplication,QDialogButtonBox,QMessageBox,QComboBox,QPlainTextEdit
    from PySide6.QtTest import QTest
    from ..gui import MainWindow,configure_app
    from .. import __version__
    from ..ui.service.forms import FieldsDialog
    from ..ui.service.repair_editor import RepairDialog
    from .repository import ServiceStore
    from .documents import generate_document,KINDS
    from .attachments import add_attachment,attachment_path
    from .backup import create_backup,restore_backup
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False)
    proof={'version':__version__,'platform':platform.platform(),'qt_platform':app.platformName(),'frozen':bool(getattr(sys,'frozen',False)),'checks':[],'manual_windows_10_11_acceptance':False,'native_os_file_dialogs_tested':False,'word_visual_test':False}
    window=None;errors=[]
    def check(name,**details):proof['checks'].append({'name':name,'passed':True,**details})
    def watchdog():
        d=app.activeModalWidget()
        if isinstance(d,QMessageBox):errors.append(d.text());d.accept()
        elif isinstance(d,RepairDialog):d.dirty=False;d.accept()
    timer=QTimer();timer.timeout.connect(watchdog);timer.start(25)
    def idle(w):
        until=time.monotonic()+40
        while w.worker or w._pending_refresh:
            app.processEvents();time.sleep(.005)
            if time.monotonic()>until:raise AssertionError('Service operation timed out')
        app.processEvents()
        assert not errors,errors
    def fill_dialog(action,values):
        failures=[]
        def fill():
            d=app.activeModalWidget()
            try:
                assert isinstance(d,FieldsDialog),type(d)
                for key,value in values.items():
                    field=d.fields[key]
                    if isinstance(field,QComboBox):field.setCurrentIndex(field.findData(value))
                    elif isinstance(field,QPlainTextEdit):field.setPlainText(value)
                    else:field.setText(value)
                QTest.mouseClick(d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
            except Exception as exc:
                failures.append(str(exc))
                if d:d.reject()
        QTimer.singleShot(80,fill);action();assert not failures,failures
    try:
        if require_windows:assert os.name=='nt' and app.platformName()=='windows'
        project=output/'Рабочий проект с пробелами'
        window=MainWindow(service_root=project);window.show();window.navigate(5);sui=window.service_workspace;idle(sui)
        assert not sui.cache['repairs'];check('empty_service_project_not_seeded')
        fill_dialog(sui.new_client,{'name':'Вымышленный сервис','legal_name':'Синтетическая организация'});idle(sui)
        assert len(sui.cache['clients'])==1
        fill_dialog(sui.new_equipment,{'number':'SYNTH-DEVICE-001','model':'Демонстрационный аппарат','serial':'SYNTH-ONLY'});idle(sui)
        assert len(sui.cache['equipment'])==1
        fill_dialog(sui.new_repair,{'number':'SYNTH-REPAIR-001','complaint':'Вымышленная неисправность'});idle(sui)
        assert len(sui.cache['repairs'])==1;check('gui_create_client_equipment_repair',actual_qt_dialogs=True)
        store=sui.store;r=sui.cache['repairs'][0]['id'];e=sui.cache['equipment'][0]['id']
        store.save_repair(r,{'defects':'Тестовый износ','plan':'Настройка и замена учебной детали','approval':'Согласовано','status':'repair'})
        store.save_item(r,{'kind':'work','name':'Демонстрационная настройка','quantity':'1.5','price':'1000.25'})
        store.save_item(r,{'kind':'part','name':'Учебная деталь','quantity':'2','price':'200.10'})
        pay=store.add_payment(r,'500',comment='Синтетический тест, реального платежа нет')
        store.add_payment(r,'100','refund',comment='Синтетический возврат')
        store.save_repair(r,{'status':'ready'})
        assert store.snapshot(r)['totals']=={'work':150038,'parts':40020,'discount':0,'total':190058,'paid':40000,'balance':150058,'overpaid':0}
        check('exact_finance_partial_payment_refund_and_independent_status',balance_cents=150058)
        photo=output/'synthetic-scheme.png';image=QImage(640,360,QImage.Format.Format_RGB32);image.fill(QColor('#873047'));assert image.save(str(photo))
        picture=add_attachment(store,r,photo,'Вымышленная схема')
        video=Path(__file__).with_name('resources')/'synthetic-demo.mp4';clip=add_attachment(store,r,video,'Видео встроенного синтетического примера Core')
        for kind in KINDS:
            path=generate_document(store,r,kind,image_ids=[picture] if kind=='combined' else [])
            from docx import Document
            assert 'SYNTH-REPAIR-001' in '\n'.join(p.text for p in Document(path).paragraphs)
        generate_document(store,r,'completion')
        check('five_document_kinds_and_version_history',generated=6)
        store.save_repair(r,{'status':'issued','issued_at':'2026-10-23','handover':'Вымышленная тестовая отметка, не подпись'})
        second=store.create_repair(e,'SYNTH-REPAIR-002','Повторный тестовый ремонт')
        assert len(store.repairs(equipment_id=e))==2;check('repeat_repair_preserves_history')
        backup=create_backup(store,output/'synthetic.service-backup.zip');restore_backup(backup,output/'Восстановленная копия')
        restored=ServiceStore(output/'Восстановленная копия');assert len(restored.repairs())==2;assert attachment_path(restored,clip).read_bytes()==video.read_bytes();check('backup_restore_database_documents_image_video')
        sui.refresh();idle(sui);sui.tabs.setCurrentIndex(4);app.processEvents();window.grab().save(str(output/'service-interface.png'))
        window.close();app.processEvents()
        window=MainWindow(service_root=project);window.show();window.navigate(5);idle(window.service_workspace)
        assert len(window.service_workspace.cache['repairs'])==2;check('gui_restart_existing_database')
        window.navigate(0);window.load_demo()
        from ..release_check import wait_idle
        wait_idle(window);assert len(window.table.records)==3;check('switch_back_to_core_and_load_demo')
        window.close();app.processEvents();check('normal_close_after_service')
        proof['status']='passed'
    except Exception:
        proof['status']='failed';proof['traceback']=traceback.format_exc()
    finally:
        timer.stop()
        if window:
            while getattr(window,'service_workspace',None) and window.service_workspace.worker:
                app.processEvents();time.sleep(.01)
            window.close();app.processEvents()
        (output/'SERVICE-SELF-TEST.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if proof['status']=='passed' else 1

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--require-windows',action='store_true');a=parser.parse_args(argv)
    return run(a.output,a.require_windows)
if __name__=='__main__':raise SystemExit(main())
