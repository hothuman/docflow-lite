"""Five real Qt business routes, reusable in pytest and the frozen Portable."""
import argparse,json,sys,time,traceback
from pathlib import Path

def exercise(ui,app,output,idle):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog,QInputDialog,QMessageBox
    from PySide6.QtGui import QDesktopServices
    from ..ui.service.intake import IntakeDialog
    from ..ui.service.repair_editor import RepairDialog
    from ..ui.service.forms import FieldsDialog
    from ..ui.service.estimates import DraftDialog
    from ..ui.service.history import HistoryDialog
    from ..ui.service.search import SearchDialog
    from .documents import KINDS
    from .backup import create_backup,restore_backup
    from .repository import ServiceStore
    output=Path(output);output.mkdir(parents=True,exist_ok=True);checks=[];routes={}
    def passed(name,actions):checks.append({'name':name,'passed':True});routes[name]=actions
    def intake(equipment=None):
        captured=[];handled=[];timer=QTimer()
        def visit():
            d=app.activeModalWidget()
            if isinstance(d,IntakeDialog) and d not in handled:
                handled.append(d)
                if not equipment:
                    d.new_equipment.setChecked(True);d.new_client.setChecked(True);d.name.setText('Учебный клиент');d.number.setText('DEVICE-100');d.model.setText('Учебный аппарат')
                d.complaint.setPlainText('Учебная жалоба\nДлинная строка на русском языке');d.grab().save(str(output/('repeat-intake.png' if equipment else 'new-intake.png')));d.submit.click()
            elif isinstance(d,RepairDialog):captured.append(d.key);d.accept()
        timer.timeout.connect(visit);timer.start(10)
        try:ui.start_intake(equipment);idle(ui)
        finally:timer.stop()
        assert len(captured)==1
        return captured[0]
    def fill(action,values):
        entered=[];timer=QTimer()
        def visit():
            d=app.activeModalWidget()
            if isinstance(d,FieldsDialog) and d not in entered:
                entered.append(d)
                from PySide6.QtWidgets import QComboBox,QPlainTextEdit
                for key,value in values.items():
                    w=d.fields[key]
                    if isinstance(w,QComboBox):w.setCurrentIndex(w.findData(value))
                    elif isinstance(w,QPlainTextEdit):w.setPlainText(value)
                    else:w.setText(value)
                d.accept()
        timer.timeout.connect(visit);timer.start(10)
        try:action();idle(ui)
        finally:timer.stop()
        assert entered
    first=intake();assert len(ui.store.clients())==len(ui.store.equipment())==1
    ui.window().grab().save(str(output/'first-intake.png'))
    passed('first_intake',['Новый ремонт','Принять в ремонт'])
    equipment=ui.store.equipment()[0];second=intake(equipment)
    assert first!=second and len(ui.store.equipment())==1 and len(ui.store.repairs(equipment_id=equipment['id']))==2
    passed('repeat_intake',['История аппарата','Новое обращение','Принять в ремонт'])
    editor=RepairDialog(ui,ui.store.snapshot(second));ui.dialogs.append(editor);editor.show();app.processEvents()
    try:
        editor.fields['defects'].setPlainText('Учебная причина');editor.save();idle(ui)
        editor.tabs.show_section('Сметы');draft=DraftDialog(editor);ui.dialogs.append(draft);draft.show()
        fill(draft.add,{'kind':'work','name':'Учебная работа','price':'1200','quantity':'1','unit':'шт.'})
        draft.save();idle(ui);ui.dialogs.remove(draft)
        fill(lambda:editor.estimates.freeze('preliminary'),{'actor':'Учебный мастер','reason':'Первый расчёт'})
        editor.estimates.grid.selectRow(0);fill(editor.estimates.manual_event,{'action':'approved','actor':'Учебный мастер','comment':'Синтетическое подтверждение'})
        assert editor.snapshot['estimate_comparison']['preliminary_total']==120000
        assert editor.snapshot['estimate_comparison']['approved_estimate_id']
        editor.grab().save(str(output/'estimate.png'))
        passed('estimate_approval',['Смета','Редактировать расчёт','Добавить позицию','Сохранить расчёт','Сохранить версию','Ручная отметка'])
        fill(lambda:editor.item('work'),{'name':'Учебная работа','price':'1200','quantity':'1','unit':'шт.','change_reason':'Проверка фактических работ'})
        old_item=QInputDialog.getItem;old_open=QDesktopServices.openUrl;old_warning=QMessageBox.warning
        QInputDialog.getItem=lambda *args:(KINDS['completion'],True);QDesktopServices.openUrl=lambda *args:False;QMessageBox.warning=lambda *args:None
        try:
            editor.quick_document_button.click();idle(ui);first_doc=editor._last_document
            assert first_doc.is_file() and 'не удалось' in editor.document_status.text().lower()
            editor.quick_document_button.click();idle(ui);assert first_doc.is_file() and first_doc!=editor._last_document
        finally:QInputDialog.getItem=old_item;QDesktopServices.openUrl=old_open;QMessageBox.warning=old_warning
        editor.grab().save(str(output/'document-no-editor.png'))
        passed('act_without_excel',['Сформировать акт','Выбрать форму (открытие редактора автоматизировано)'])
        fill(editor.payment,{'kind':'payment','amount':'1200','method':'Учебная запись'})
        import docflow.ui.service.repair_editor as repair_module
        original=repair_module.confirm;repair_module.confirm=lambda *args:True
        try:editor.issue();idle(ui)
        finally:repair_module.confirm=original
        assert editor.snapshot['repair']['status']=='issued' and editor.snapshot['totals']['balance']==0
        editor.fields['notes'].setPlainText('Несохранённая заметка остаётся при переходах')
        captured=[];timer=QTimer()
        def close_history():
            d=app.activeModalWidget()
            if isinstance(d,HistoryDialog):captured.append(d.equipment['id']);d.accept()
        timer.timeout.connect(close_history);timer.start(10)
        try:editor.equipment_history();idle(ui)
        finally:timer.stop()
        assert captured==[equipment['id']] and editor.dirty and 'Несохранённая заметка' in editor.fields['notes'].toPlainText()
        editor.dirty=False
        passed('issue_payment_history',['Учесть оплату','Выдать','Подтвердить','История аппарата'])
        editor.grab().save(str(output/'issued.png'))
    finally:editor.dirty=False;editor.accept();ui.dialogs.remove(editor)
    archive=create_backup(ui.store,output/'synthetic.service-backup.zip');recovered=ServiceStore(restore_backup(archive,output/'Restored'))
    assert len(recovered.repairs())==2 and recovered.snapshot(second)['totals']['balance']==0 and len(recovered.documents())==2
    search=SearchDialog(ui);ui.dialogs.append(search);search.show();idle(ui);search.query.setText('DEVICE-100');app.processEvents();assert search.equipment.proxy.rowCount()==1 and search.repairs.proxy.rowCount()==2;search.accept();ui.dialogs.remove(search)
    return {'status':'passed','checks':checks,'routes':routes,'route_unit':'Named intentional actions excluding typing; not elapsed time or human usability acceptance','backup_restore':True,'editor_open_stubbed':True,'word_checked':False,'printer_checked':False}

def run(output,require_windows=False):
    from PySide6.QtWidgets import QApplication
    from ..gui import MainWindow,configure_app
    from .. import __version__
    output=Path(output).absolute()
    if output.exists():raise ValueError('Use a new synthetic QA folder')
    output.mkdir(parents=True);app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False)
    proof={'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),'qt_platform':app.platformName()};window=None
    def idle(ui):
        deadline=time.monotonic()+45
        while ui.worker or ui._pending_refresh:app.processEvents();time.sleep(.005);assert time.monotonic()<deadline
        app.processEvents()
    try:
        if require_windows:assert sys.platform=='win32' and app.platformName()=='windows'
        window=MainWindow(service_root=output/'Synthetic');window.show();window.navigate(5);idle(window.service_workspace)
        proof.update(exercise(window.service_workspace,app,output,idle));window.close();app.processEvents();window=None
    except Exception:proof['status']='failed';proof['traceback']=traceback.format_exc()
    finally:
        if window:
            for dialog in window.service_workspace.dialogs:
                if hasattr(dialog,'dirty'):dialog.dirty=False
                dialog.accept()
            window.close();app.processEvents()
        (output/'STAGE2-SELF-TEST.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if proof['status']=='passed' else 1

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--require-windows',action='store_true');a=p.parse_args(argv)
    try:return run(a.output,a.require_windows)
    except (ValueError,OSError) as exc:
        if sys.stderr is not None:print(str(exc),file=sys.stderr)
        return 2
