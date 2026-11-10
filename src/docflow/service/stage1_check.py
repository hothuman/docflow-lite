"""Opt-in synthetic stage-1 acceptance, usable inside the frozen EXE.

System editor opening is stubbed; no printer, Word or client data is claimed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback


def run(output,require_windows=False):
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox
    from docx import Document
    from .. import __version__
    from ..gui import MainWindow,configure_app
    from ..ui.service.repair_editor import RepairDialog
    from .repository import ServiceStore
    from .documents import KINDS
    from .backup import create_backup,restore_backup
    output=Path(output).resolve()
    if output.exists():raise ValueError('Выберите новую пустую папку синтетической проверки')
    output.mkdir(parents=True)
    app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False)
    proof={'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),'qt_platform':app.platformName(),
           'word_checked':False,'printer_checked':False,'system_editor_stubbed':True,'checks':[]}
    def check(name):proof['checks'].append({'name':name,'passed':True})
    def idle(ui):
        deadline=time.monotonic()+30
        while ui.worker or ui._pending_refresh:
            app.processEvents();time.sleep(.005)
            assert time.monotonic()<deadline,'UI timeout'
        app.processEvents()
    opened=[];errors=[];window=None;card=None
    old_open=QDesktopServices.openUrl;old_item=QInputDialog.getItem
    QDesktopServices.openUrl=lambda url:opened.append(Path(url.toLocalFile())) or True
    QInputDialog.getItem=lambda *args:(KINDS['completion'],True)
    timer=QTimer()
    def modal():
        widget=app.activeModalWidget()
        if isinstance(widget,QMessageBox):errors.append(widget.text());widget.accept()
    timer.timeout.connect(modal);timer.start(20)
    try:
        if require_windows:assert sys.platform=='win32' and app.platformName()=='windows'
        store=ServiceStore(output/'Synthetic project')
        client=store.save_client({'name':'Синтетическая мастерская'})
        equipment=store.save_equipment({'number':'APPARATUS-7','model':'Учебный аппарат','owner_id':client})
        repair=store.create_repair(equipment,'1000')
        assert store.preview_repair_number()=='1001'
        raw=json.dumps({'requires_identity_date_money_review':True,'mapped_raw':{'complaint':'Нет давления\nПовторная строка','works':'Учебная замена узла','notes':'Исходное примечание'}},ensure_ascii=False)
        store.save_repair(repair,{'notes':raw})
        window=MainWindow(service_root=store.root);window.show();window.navigate(5);ui=window.service_workspace;idle(ui)
        card=RepairDialog(ui,store.snapshot(repair));ui.dialogs.append(card);card.show();app.processEvents()
        assert card.fields['complaint'].toPlainText()=='Нет давления\nПовторная строка'
        assert card.fields['plan'].toPlainText()==''
        assert card.source_works.toPlainText()=='Учебная замена узла'
        assert 'requires_identity' not in card.fields['notes'].toPlainText()
        check('readable_fields_and_performed_works_not_a_plan')
        card.quick_document_button.click();idle(ui)
        assert len(opened)==1 and opened[0].is_file() and not errors,errors
        first=opened[0];digest=hashlib.sha256(first.read_bytes()).hexdigest()
        content='\n'.join(p.text for p in Document(first).paragraphs)
        assert 'Работы из источника' in content and 'requires_identity' not in content
        assert store.get('repair_orders',repair)['notes']==raw
        check('act_from_card_without_excel_source_retained')
        card.quick_document_button.click();idle(ui)
        assert len(opened)==2 and first!=opened[1] and hashlib.sha256(first.read_bytes()).hexdigest()==digest
        check('second_export_keeps_old_document')
        card.resize(820,620);app.processEvents();card.grab().save(str(output/'stage1-card.png'))
        card.dirty=False;card.close();ui.dialogs.remove(card);card=None
        store.rename_repair(repair,'1005','Синтетическая явная смена')
        assert store.repairs('1000')[0]['id']==repair and store.preview_repair_number()=='1006'
        assert hashlib.sha256(first.read_bytes()).hexdigest()==digest
        check('renumber_keeps_id_old_search_and_issued_document')
        store.save_repair(repair,{'status':'historical'})
        store.archive('equipment',equipment);store.archive('clients',client)
        ui.refresh();idle(ui);ui.tabs.setCurrentIndex(3)
        assert not ui.cache['clients'] and ui.cache['link_audit']['counts']['clients']['archived']==1
        ui.show_archived('clients');idle(ui);assert len(ui.cache['clients'])==1
        check('archive_filter_explained_without_changing_links')
        backup=create_backup(store,output/'synthetic.service-backup.zip')
        restored=ServiceStore(restore_backup(backup,output/'Restored'))
        assert restored.get('repair_orders',repair)['notes']==raw
        assert restored.repairs('1000')[0]['id']==repair and len(restored.documents())==2
        assert (restored.root/first.relative_to(store.root)).read_bytes()==first.read_bytes()
        check('backup_restore_numbers_raw_sources_and_document_versions')
        window.close();app.processEvents();window=None
        proof['status']='passed'
    except Exception:
        proof['status']='failed';proof['traceback']=traceback.format_exc()
    finally:
        timer.stop();QDesktopServices.openUrl=old_open;QInputDialog.getItem=old_item
        if card:card.dirty=False;card.close()
        if window:
            while window.service_workspace.worker:app.processEvents();time.sleep(.01)
            window.close();app.processEvents()
        (output/'STAGE1-SELF-TEST.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if proof['status']=='passed' else 1


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--require-windows',action='store_true');a=p.parse_args(argv)
    return run(a.output,a.require_windows)
