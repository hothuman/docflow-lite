"""Opt-in synthetic project-opening acceptance for the source and frozen EXE."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time
import traceback


def _hashes(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def _cancel_windows_folder_dialog(result):
    """Close only our process's specifically titled native folder picker."""
    import ctypes
    from ctypes import wintypes
    user=ctypes.WinDLL('user32',use_last_error=True)
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.IsWindowVisible.argtypes=[wintypes.HWND]
    user.PostMessageW.argtypes=[wintypes.HWND,ctypes.c_uint,wintypes.WPARAM,wintypes.LPARAM]
    user.EnumWindows.argtypes=[callback,wintypes.LPARAM]
    @callback
    def visit(hwnd,_):
        pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==os.getpid() and user.IsWindowVisible(hwnd):
            title=ctypes.create_unicode_buffer(512);user.GetWindowTextW(hwnd,title,512)
            if title.value=='Папка для новой обновлённой копии':
                result['native_folder_dialog_seen']=True
                result['native_folder_dialog_close_sent']=bool(user.PostMessageW(hwnd,0x0010,0,0))
                return False
        return True
    deadline=time.monotonic()+20
    while time.monotonic()<deadline and not result.get('native_folder_dialog_close_sent'):
        user.EnumWindows(visit,0);time.sleep(.05)


def run(output,require_windows=False):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox
    from .. import __version__
    from ..gui import MainWindow,configure_app
    from .database import MIGRATIONS
    import docflow.ui.service.workspace as module
    output=Path(output).absolute()
    if output.exists():raise ValueError('Use a new synthetic QA folder')
    output.mkdir(parents=True)
    app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False)
    proof={'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),'qt_platform':app.platformName(),
           'checks':[],'word_checked':False,'printer_checked':False,'scope':'Synthetic project; native folder picker cancellation on Windows; not owner acceptance'}
    window=None;closer=None;old_confirm=module.confirm;old_picker=QFileDialog.getExistingDirectory;old_warning=QMessageBox.warning
    def check(name):proof['checks'].append({'name':name,'passed':True})
    def idle(ui):
        deadline=time.monotonic()+30
        while ui.worker or ui._pending_refresh:
            app.processEvents();time.sleep(.005);assert time.monotonic()<deadline,'Project did not settle'
        app.processEvents()
    try:
        if require_windows:assert sys.platform=='win32' and app.platformName()=='windows'
        root=output/'Legacy v4';root.mkdir()
        (root/'original.txt').write_text('Synthetic immutable original',encoding='utf-8')
        with sqlite3.connect(root/'service.db') as c:
            for version in range(1,5):
                for statement in MIGRATIONS[version]:c.execute(statement)
            c.execute('PRAGMA user_version=4')
        c.close();before=_hashes(root)
        module.confirm=lambda *args:True
        if sys.platform=='win32' and app.platformName()=='windows':
            closer=threading.Thread(target=_cancel_windows_folder_dialog,args=(proof,),daemon=True);closer.start()
        else:
            QFileDialog.getExistingDirectory=lambda *args:'';proof['folder_dialog_stubbed']=True
        window=MainWindow(service_root=root);window.show();window.navigate(5);ui=window.service_workspace;idle(ui)
        if closer:closer.join(timeout=1);assert proof.get('native_folder_dialog_close_sent'), 'Native picker cancellation not observed'
        assert ui.store is None and ui.worker is None and ui.project_state=='cancelled'
        assert 'Проект не открыт' in ui.location.text() and 'Открываю проект' not in ui.location.text()
        assert 'Копия не создана' in ui.message.text() and _hashes(root)==before
        check('native_folder_cancel_settles_without_touching_original')
        for width,height in ((1060,740),(820,620),(640,420)):
            window.resize(width,height);app.processEvents()
            assert ui.location.isVisible() and 'Проект не открыт' in ui.location.text()
            for index in range(ui.tabs.count()):
                ui.tabs.setCurrentIndex(index);app.processEvents()
                assert ui.store is None and ui.worker is None
            for control in (ui.open_project_button,ui.new_project_button,ui.restore_project_button):
                assert control.isEnabled() and control.isVisible()
                point=control.mapTo(window,QPoint())
                assert window.rect().contains(point) and window.rect().contains(point+QPoint(control.width()-1,control.height()-1))
            assert window.grab().save(str(output/f'cancelled-{width}.png'))
        check('no_store_navigation_and_recovery_actions_at_three_sizes')
        for fn in (ui.new_client,ui.new_equipment,ui.new_repair,ui.backup,ui.import_history,ui.organization_profiles,ui.diagnostics,ui.diagnose_links):
            fn();assert ui.store is None and ui.worker is None
        assert _hashes(root)==before
        check('business_entrypoints_guarded_without_store')
        ui.open_project(output/'Fresh project');idle(ui)
        assert ui.project_state=='opened' and ui.store.root.name=='Fresh project'
        client=ui.store.save_client({'name':'Synthetic recovered client'});ui.refresh();idle(ui)
        assert ui.cache['clients'][0]['id']==client
        check('retry_opens_fresh_project_and_can_create_client')
        module.confirm=lambda *args:False
        ui.open_project(root);idle(ui)
        assert ui.store.root.name=='Fresh project' and ui.location.text().startswith('Проект: Fresh project')
        assert ui.cache['clients'][0]['id']==client and _hashes(root)==before
        check('cancel_switch_retains_current_project_name_and_data')
        QMessageBox.warning=lambda *args:None
        corrupt=output/'Corrupt';corrupt.mkdir();(corrupt/'service.db').write_bytes(b'synthetic invalid database')
        ui.open_project(corrupt);idle(ui)
        assert ui.project_state=='error' and ui.store.root.name=='Fresh project'
        assert 'Операция выполнена' not in ui.message.text()
        ui.open_project(output/'Fresh project');idle(ui)
        assert ui.project_state=='opened' and ui.cache['clients'][0]['id']==client
        check('failed_switch_is_terminal_and_can_retry')
        window.close();app.processEvents();window=None;proof['status']='passed'
    except Exception:
        proof['status']='failed';proof['traceback']=traceback.format_exc()
    finally:
        module.confirm=old_confirm;QFileDialog.getExistingDirectory=old_picker;QMessageBox.warning=old_warning
        if window:
            while window.service_workspace.worker:app.processEvents();time.sleep(.01)
            window.close();app.processEvents()
        (output/'PROJECT-LOADING-SELF-TEST.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if proof['status']=='passed' else 1


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--require-windows',action='store_true');args=parser.parse_args(argv)
    try:return run(args.output,args.require_windows)
    except (ValueError,OSError) as exc:
        if sys.stderr is not None:print(str(exc),file=sys.stderr)
        return 2
