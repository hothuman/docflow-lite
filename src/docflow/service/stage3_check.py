"""Opt-in synthetic Stage3 Qt routes, also executed inside the real Portable."""
import argparse,hashlib,json,sys,time,traceback
from pathlib import Path

CHECKS={'file_preview_apply_replay','catalog_to_quote_snapshot_docx','catalog_update_preserves_history','catalog_profiles_backup_restore','dashboard_presets_reset_restart','compact_catalog_layouts'}

def exercise(ui,app,output,idle):
    from PySide6.QtCore import QTimer,QPoint
    from PySide6.QtWidgets import QDialog,QMessageBox,QPushButton
    from ..ui.service.catalog import CatalogDialog,CatalogPicker
    from ..ui.service.forms import FieldsDialog
    from ..ui.service.repair_editor import RepairDialog
    from ..ui.service.estimates import DraftDialog
    from ..ui.service import dashboard_preferences as prefs
    from ..ui.settings import preferences
    from . import catalog as api
    from .estimates import freeze_estimate,get_estimate
    from .documents import generate_document
    from .backup import create_backup,restore_backup
    from .repository import ServiceStore
    output=Path(output);checks=[]
    path=output/'Synthetic.csv';path.write_text('external_id;sku;name;kind;unit;price;currency;group;subgroup\n001;S-001;Учебная деталь;part;шт.;123.45;RUB;Группа;Подгруппа\n',encoding='utf-8-sig')
    dialog=CatalogDialog(ui);ui.dialogs.append(dialog);dialog.tabs.setCurrentIndex(1);dialog.show();app.processEvents();dialog.path=str(path);dialog.source.setText('Synthetic');dialog.read();idle(ui)
    assert dialog.parsed['rows'][0][1]['external_id']=='001';dialog.preview();assert dialog.plan.counts=={'new':1};assert dialog.apply_button.isEnabled()
    dialog.grab().save(str(output/'import-preview.png'))
    question=QMessageBox.question;QMessageBox.question=lambda *args:QMessageBox.StandardButton.Yes
    try:
        dialog.apply();idle(ui);dialog.preview();assert dialog.plan.counts=={'unchanged':1};dialog.apply();idle(ui)
    finally:QMessageBox.question=question
    assert len(api.search(ui.store))==1;checks.append('file_preview_apply_replay')
    config=dialog.config();api.save_profile(ui.store,'Synthetic',config)
    cases=[]
    for width,height in ((560,420),(820,620),(1060,740)):
        dialog.resize(width,height);app.processEvents();app.processEvents()
        assert dialog.width()==width and dialog.height()==height
        for control in dialog.findChildren(QPushButton):
            if control.text()=='Закрыть':
                point=control.mapTo(dialog,QPoint());assert dialog.rect().contains(point+QPoint(control.width()-1,control.height()-1))
        dialog.grab().save(str(output/f'catalog-{width}.png'));cases.append({'size':[width,height],'footer_visible':True})
    checks.append('compact_catalog_layouts');dialog.accept();ui.dialogs.remove(dialog)
    key=ui.store.intake(client={'name':'Учебный клиент'},equipment={'number':'CAT-001','model':'Учебный аппарат'});editor=RepairDialog(ui,ui.store.snapshot(key));ui.dialogs.append(editor);editor.show();draft=DraftDialog(editor);ui.dialogs.append(draft);draft.show();timer=QTimer();visited=[]
    def choose():
        modal=app.activeModalWidget()
        if isinstance(modal,CatalogPicker) and modal not in visited:visited.append(modal);modal.query.setText('S-001');assert modal.grid.proxy.rowCount()==1;modal.grid.selectRow(0);QTimer.singleShot(0,modal.choose)
        elif isinstance(modal,FieldsDialog) and modal not in visited:visited.append(modal);modal.fields['quantity'].setText('2');modal.accept()
    timer.timeout.connect(choose);timer.start(10)
    try:draft.from_catalog()
    finally:timer.stop()
    assert len(draft.lines)==1 and draft.lines[0]['total_cents']==24690;draft.grab().save(str(output/'catalog-in-quote.png'));draft.save();idle(ui);ui.dialogs.remove(draft)
    estimate=freeze_estimate(ui.store,key,'preliminary','Учебный мастер');document=generate_document(ui.store,key,'estimate_preliminary',estimate_id=estimate);before_sha=hashlib.sha256(document.read_bytes()).hexdigest()
    with ui.store.db.connection() as c:before=get_estimate(c,estimate)
    checks.append('catalog_to_quote_snapshot_docx')
    path.write_text(path.read_text(encoding='utf-8-sig').replace('123.45','999.99'),encoding='utf-8-sig');from .catalog_loader import parse_file
    parsed=parse_file(path);mapping={k:k for k in parsed['headers']};api.apply(ui.store,api.preview(ui.store,parsed,'Synthetic',mapping,update_prices=True),confirmed=True)
    assert api.search(ui.store)[0]['price_cents']==99999 and ui.store.snapshot(key)['totals']['total']==0
    with ui.store.db.connection() as c:assert get_estimate(c,estimate)==before
    assert hashlib.sha256(document.read_bytes()).hexdigest()==before_sha;checks.append('catalog_update_preserves_history')
    editor.dirty=False;editor.accept();ui.dialogs.remove(editor)
    recovered=ServiceStore(restore_backup(create_backup(ui.store,output/'synthetic.service-backup.zip'),output/'Restored'))
    assert api.search(recovered)==api.search(ui.store) and api.profiles(recovered)==api.profiles(ui.store)
    with recovered.db.connection() as c:assert get_estimate(c,estimate)==before and c.execute('SELECT COUNT(*) FROM catalog_imports').fetchone()[0]==3
    checks.append('catalog_profiles_backup_restore')
    old=preferences().value('dashboard/actions')
    try:
        for order in prefs.PRESETS.values():assert prefs.save_actions(order);ui.dashboard.apply_actions();assert prefs.load_actions()==(order,'')
        from ..ui.service.dashboard import Dashboard
        restarted=Dashboard(ui);assert not restarted.catalog_button.isHidden();restarted.deleteLater()
        timer=QTimer();handled=[]
        def reset_editor():
            modal=app.activeModalWidget()
            if isinstance(modal,QDialog) and modal not in handled:
                handled.append(modal)
                for b in modal.findChildren(QPushButton):
                    if b.text()=='Вернуть по умолчанию':b.click()
                modal.grab().save(str(output/'dashboard-customization.png'));modal.accept()
        timer.timeout.connect(reset_editor);timer.start(10)
        try:prefs.show_editor(ui)
        finally:timer.stop()
        assert handled and prefs.load_actions()==(prefs.DEFAULT,'');assert ui.dashboard.catalog_button.isHidden();ui.window().grab().save(str(output/'dashboard-default.png'));checks.append('dashboard_presets_reset_restart')
    finally:
        settings=preferences()
        if old is None:settings.remove('dashboard/actions')
        else:settings.setValue('dashboard/actions',old)
        settings.sync();ui.dashboard.apply_actions()
    assert set(checks)==CHECKS
    return {'status':'passed','checks':[{'name':name,'passed':True} for name in checks],'layout':cases,'backup_restore':True,'word_checked':False,'owner_acceptance':False}

def run(output,require_windows=False):
    from PySide6.QtWidgets import QApplication
    from ..gui import MainWindow,configure_app
    from .. import __version__
    output=Path(output).absolute()
    if output.exists():raise ValueError('Use a new synthetic QA folder')
    output.mkdir(parents=True);app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False);window=None
    proof={'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),'qt_platform':app.platformName()}
    def idle(ui):
        deadline=time.monotonic()+60
        while ui.worker or ui._pending_refresh:app.processEvents();time.sleep(.005);assert time.monotonic()<deadline
        app.processEvents()
    try:
        if require_windows:assert sys.platform=='win32' and app.platformName()=='windows'
        window=MainWindow(service_root=output/'Synthetic');window.show();window.navigate(5);idle(window.service_workspace);proof.update(exercise(window.service_workspace,app,output,idle))
    except Exception:proof.update(status='failed',traceback=traceback.format_exc())
    finally:
        if window:
            for d in window.service_workspace.dialogs:
                if hasattr(d,'dirty'):d.dirty=False
                d.accept()
            window.close();app.processEvents()
        (output/'STAGE3-SELF-TEST.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if proof['status']=='passed' else 1

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--require-windows',action='store_true');a=p.parse_args(argv)
    try:return run(a.output,a.require_windows)
    except (ValueError,OSError) as exc:
        if sys.stderr is not None:print(str(exc),file=sys.stderr)
        return 2
