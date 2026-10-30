"""Opt-in synthetic UX routes; same code runs inside the delivered Portable.

Qt events exercise our own widgets. File paths, editors and domain fixtures are
explicit harness inputs, not claims of human usability, Word or printer QA.
"""
import argparse,hashlib,json,os,sys,time,traceback
from pathlib import Path

CHECKS=frozenset({'visible_modes_keyboard_memory','empty_core_demo_full_check',
 'core_error_retry_generation','exclusive_intake_hidden_fields',
 'repeat_requester_preserves_owner','single_stages_preserve_draft_status',
 'dirty_mode_guard_ctrl_s','organization_wizard_and_act','history_selection_filter',
 'frozen_quote_profile_and_catalog','backup_restore_immutable_documents',
 'compact_footer_and_accessible_controls'})

def exercise(window,app,output,idle):
    from PySide6.QtCore import Qt,QItemSelectionModel,QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QComboBox,QListWidget,QScrollArea,QWizard
    from ..release_check import wait_idle
    from ..cli import demo_profile
    from ..profile import Profile
    from ..ui.service.intake import IntakeDialog
    from ..ui.service.repair_editor import RepairDialog
    from ..ui.service.history import HistoryDialog
    from ..ui.service.organization_setup import OrganizationWizard
    from .documents import generate_document
    from .estimates import save_draft,freeze_estimate,get_estimate
    from .backup import create_backup,restore_backup
    from .repository import ServiceStore
    from .document_readiness import assess
    from . import catalog
    from .catalog_loader import parse_file
    output=Path(output);checks=[];layouts=[]
    def passed(name,**facts):checks.append({'name':name,'passed':True,**facts})
    def click(widget):
        assert widget.isVisible() and widget.isEnabled(),widget.accessibleName() or widget.text()
        QTest.mouseClick(widget,Qt.MouseButton.LeftButton);app.processEvents()
    def capture(name,widget):assert widget.grab().save(str(output/(name+'.png')))
    assert not isinstance(window.mode_picker,QComboBox)
    assert [b.text() for b in window.mode_picker.buttons]==['Документы','Мастерская']
    assert not window.source_table.isVisible();capture('core-empty',window)
    click(window.demo_btn);wait_idle(window);window.navigate(2);table=window.table
    QTest.keyClick(window.mode_picker.buttons[0],Qt.Key.Key_Right);ui=window.service_workspace;idle(ui)
    ui.tabs.setCurrentIndex(7);QTest.keyClick(window.mode_picker.buttons[1],Qt.Key.Key_Left)
    assert window.pages.currentIndex()==2 and window.table is table
    QTest.keyClick(window.mode_picker.buttons[0],Qt.Key.Key_Right);idle(ui);assert ui.tabs.currentIndex()==7
    QTest.keyClick(window.mode_picker.buttons[1],Qt.Key.Key_Left)
    passed('visible_modes_keyboard_memory',simultaneous_modes=2)
    assert not window.route_buttons[2].property('complete');window.check_all();wait_idle(window)
    assert window.route_buttons[2].property('complete') and window._full_check[1:]==(1,3)
    passed('empty_core_demo_full_check',rows_checked=3,invalid_rows=1)
    window._load_data(output/'missing.csv');wait_idle(window);assert 'missing.csv' in window.status.text()
    window.apply_profile(Profile.load(demo_profile()));wait_idle(window);window.output_path.setText(str(output/'Core DOCX'));window.navigate(3);app.processEvents();click(window.generate_btn);wait_idle(window)
    assert window.last_result.documents==4;first_output=window.last_result.directory
    capture('core-result',window);click(window.generate_btn);wait_idle(window)
    assert window.last_result.documents==4 and first_output.is_dir()
    passed('core_error_retry_generation',documents_per_run=4)
    click(window.mode_picker.buttons[1]);idle(ui)
    d=IntakeDialog(ui);d.show();app.processEvents();assert d.new_equipment.isChecked() and not d.equipment.isVisible()
    d.name.setText('Учебный собственник');d.number.setText('UX-001');d.model.setText('Учебный аппарат');d.complaint.setPlainText('Учебная жалоба');capture('intake-new',d);click(d.submit);idle(ui);first=d.created_key
    assert len(ui.store.equipment())==len(ui.store.clients())==1
    equipment=ui.store.equipment()[0];owner=equipment['owner_id'];other=ui.store.save_client({'name':'Учебный другой заказчик'});ui.refresh();idle(ui)
    d=IntakeDialog(ui,equipment);d.show();app.processEvents();assert not d.device_body.isVisible() and d.equipment.isVisible()
    d.name.setText('СКРЫТЫЙ НЕ СОЗДАВАТЬ');d.model.setText('СКРЫТАЯ МОДЕЛЬ');d.number.setText('HIDDEN');d.complaint.setPlainText('Повторная учебная жалоба')
    d.other_client.setChecked(True);d.repair_client.setCurrentIndex(d.repair_client.findData(other));capture('intake-repeat',d);click(d.submit);idle(ui);second=d.created_key
    assert len(ui.store.equipment())==1 and len(ui.store.clients())==2 and not any(c['name']=='СКРЫТЫЙ НЕ СОЗДАВАТЬ' for c in ui.store.clients())
    passed('exclusive_intake_hidden_fields')
    assert ui.store.snapshot(second)['client']['id']==other and ui.store.equipment()[0]['owner_id']==owner
    passed('repeat_requester_preserves_owner',repairs=2,equipment=1)
    editor=RepairDialog(ui,ui.store.snapshot(second));ui.dialogs.append(editor);editor.show();app.processEvents();status=editor.snapshot['repair']['status'];editor.fields['defects'].setPlainText('Учебная причина');editor.fields['plan'].setPlainText('Учебный план')
    assert not editor.tabs.findChildren(QListWidget) and not hasattr(editor.tabs,'groups')
    for stage in range(5):
        QTest.mouseClick(editor.tabs.stage_bar,Qt.MouseButton.LeftButton,pos=editor.tabs.stage_bar.tabRect(stage).center());app.processEvents();assert editor.tabs.currentIndex()==stage;capture('repair-'+str(stage+1),editor)
    assert editor.dirty and editor.fields['plan'].toPlainText()=='Учебный план' and ui.store.snapshot(second)['repair']['status']==status
    passed('single_stages_preserve_draft_status',stages=5,automatic_status_changes=0)
    click(window.mode_picker.buttons[0]);assert window.mode_picker.currentIndex()==1
    editor.activateWindow();QTest.qWait(30);QTest.keyClick(editor,Qt.Key.Key_S,Qt.KeyboardModifier.ControlModifier);idle(ui)
    assert not editor.dirty and ui.store.snapshot(second)['repair']['plan']=='Учебный план';passed('dirty_mode_guard_ctrl_s')
    neutral=generate_document(ui.store,second,'intake');neutral_sha=hashlib.sha256(neutral.read_bytes()).hexdigest()
    wizard=OrganizationWizard(ui,editor);wizard.show();app.processEvents();wizard.organization.setText('Учебная мастерская — синтетика');wizard.contact.setText('Демонстрационный контакт');wizard.details.setPlainText('Учебные сведения, не реквизиты организации')
    click(wizard.button(QWizard.WizardButton.NextButton));click(wizard.button(QWizard.WizardButton.NextButton));capture('organization',wizard);click(wizard.button(QWizard.WizardButton.FinishButton));idle(ui)
    assert wizard.saved_profile_id and not assess(editor.snapshot,'intake')['missing']
    editor.doc_kind.setCurrentIndex(editor.doc_kind.findData('intake'));editor.generate();idle(ui);assert editor._last_document.is_file() and hashlib.sha256(neutral.read_bytes()).hexdigest()==neutral_sha
    passed('organization_wizard_and_act',old_document_unchanged=True,editor_opened=False)
    history=HistoryDialog(ui,ui.store.equipment()[0]);history.show();idle(ui);history.grid.selectRow(0);assert not history.compare_button.isEnabled()
    selection=history.grid.selectionModel();selection.select(history.grid.proxy.index(1,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows);assert history.compare_button.isEnabled();capture('history',history)
    history.search.setText('НЕСУЩЕСТВУЮЩАЯ СТРОКА');app.processEvents();assert not history.compare_button.isEnabled() and history.grid.proxy.rowCount()==0;history.reset_filters();idle(ui);assert history.grid.proxy.rowCount()==2;history.accept();passed('history_selection_filter')
    path=output/'catalog.csv';path.write_text('external_id;sku;name;kind;unit;price;currency\nUX01;UX01;Учебная позиция;work;усл.;123.45;RUB\n',encoding='utf-8-sig');parsed=parse_file(path);catalog.apply(ui.store,catalog.preview(ui.store,parsed,'UX',{k:k for k in parsed['headers']}),confirmed=True)
    entry=catalog.search(ui.store)[0];save_draft(ui.store,second,[{'kind':'work','name':entry['name'],'price':'123.45'}]);quote=freeze_estimate(ui.store,second,'preliminary','Учебный мастер');quoted=generate_document(ui.store,second,'estimate_preliminary',estimate_id=quote)
    with ui.store.db.connection() as c:frozen=get_estimate(c,quote)
    assert frozen['payload']['profile']['organization_name']=='Учебная мастерская — синтетика';passed('frozen_quote_profile_and_catalog')
    backup=create_backup(ui.store,output/'synthetic.service-backup.zip');restored=ServiceStore(restore_backup(backup,output/'Restored'))
    assert len(restored.repairs())==2 and len(restored.documents())==3 and hashlib.sha256(neutral.read_bytes()).hexdigest()==neutral_sha
    with restored.db.connection() as c:assert get_estimate(c,quote)==frozen
    passed('backup_restore_immutable_documents',schema=6)
    for size in ((560,420),(820,620),(1060,740)):
        available=editor.screen().availableGeometry();target=(min(size[0],available.width()-40),min(size[1],available.height()-60));editor.resize(*target);app.processEvents();app.processEvents()
        assert editor.size().toTuple()==target
        for stage in range(5):
            editor.tabs.setCurrentIndex(stage);app.processEvents();app.processEvents()
            for w in (editor.save_button,editor.next_button,editor.tabs.stage_bar):
                assert w.isVisible();p=w.mapTo(editor,QPoint());assert editor.rect().contains(p) and editor.rect().contains(p+QPoint(w.width()-1,w.height()-1))
            assert not editor.body_scroll.horizontalScrollBar().maximum()
        capture('repair-compact-'+str(size[0]),editor);layouts.append({'requested':list(size),'actual':list(target),'stages':5,'footer_visible':True})
    editor.accept();ui.dialogs.remove(editor)
    for size in ((560,420),(820,620),(1060,740)):
        window.resize(*size);app.processEvents()
        for b in window.mode_picker.buttons:
            assert b.isVisible() and b.accessibleName() and b.width()>=b.sizeHint().width()
        capture('main-compact-'+str(size[0]),window)
    passed('compact_footer_and_accessible_controls',layouts=len(layouts))
    assert {c['name'] for c in checks}==CHECKS and len(checks)==len(CHECKS)
    return {'status':'passed','checks':checks,'layout':layouts,'backup_restore':True,'word_checked':False,'printer_checked':False,'owner_acceptance':False,'scope':'Automated Qt widget routes; synthetic fixtures; no human speed or independent UX acceptance'}

def run(output,require_windows=False):
    from PySide6.QtWidgets import QApplication
    from ..gui import MainWindow,configure_app
    from ..ui.settings import preferences
    from .. import __version__
    output=Path(output).absolute()
    if output.exists():raise ValueError('Use a new synthetic QA folder')
    output.mkdir(parents=True);os.environ['DOCFLOW_SETTINGS_DIR']=str(output/'Settings');app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False);window=None
    proof={'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),'qt_platform':app.platformName(),'executable':sys.executable}
    def idle(ui):
        until=time.monotonic()+60
        while ui.worker or ui._pending_refresh:app.processEvents();time.sleep(.005);assert time.monotonic()<until,'Workspace timeout'
        app.processEvents();app.processEvents()
    try:
        if require_windows:assert sys.platform=='win32' and app.platformName()=='windows' and proof['frozen']
        preferences().clear();window=MainWindow(service_root=output/'Synthetic');window.show();app.processEvents();proof.update(exercise(window,app,output,idle))
    except Exception:proof.update(status='failed',traceback=traceback.format_exc())
    finally:
        if window:
            for d in window.service_workspace.dialogs:
                if hasattr(d,'dirty'):d.dirty=False
                d.accept()
            window.close();app.processEvents()
        (output/'STAGE4-SELF-TEST.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if proof['status']=='passed' else 1

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--require-windows',action='store_true');a=p.parse_args(argv)
    try:return run(a.output,a.require_windows)
    except (ValueError,OSError) as exc:
        if sys.stderr is not None:print(str(exc),file=sys.stderr)
        return 2
