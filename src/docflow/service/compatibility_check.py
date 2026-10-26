"""Opt-in frozen upgrade acceptance on a synthetic previous-version backup."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import traceback
import zipfile


def snapshot(path):
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
        tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        result={}
        for name in tables:
            quoted='"'+name.replace('"','""')+'"'
            result[name]=[list(row) for row in c.execute('SELECT * FROM '+quoted+' ORDER BY rowid')]
        return result


def run(archive,output,require_windows=False):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication,QMessageBox
    from .. import __version__
    from ..gui import MainWindow,configure_app
    from .backup import restore_backup,create_backup
    from .repository import ServiceStore
    from .documents import generate_document
    archive=Path(archive).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Use a new synthetic QA folder')
    output.mkdir(parents=True)
    raw=archive.read_bytes();checksum=hashlib.sha256(raw).hexdigest()
    proof={'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),
           'previous_backup_sha256':checksum,'checks':[],'owner_acceptance':False,'word_checked':False}
    app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False)
    errors=[];window=None
    def modal():
        widget=app.activeModalWidget()
        if isinstance(widget,QMessageBox):errors.append(widget.text());widget.accept()
    timer=QTimer();timer.timeout.connect(modal);timer.start(25)
    try:
        if require_windows:assert sys.platform=='win32' and app.platformName()=='windows'
        with zipfile.ZipFile(archive) as z:
            assert z.getinfo('service.db').file_size<=64*1024*1024,'Diagnostic requires a small synthetic backup'
            original=output/'original-snapshot.db';original.write_bytes(z.read('service.db'))
        before=snapshot(original)
        root=restore_backup(archive,output/'Upgraded project')
        assert snapshot(root/'service.db')==before
        window=MainWindow(service_root=root);window.show();window.navigate(5)
        deadline=time.monotonic()+40
        while window.service_workspace.worker or window.service_workspace._pending_refresh:
            app.processEvents();time.sleep(.01)
            if time.monotonic()>deadline:raise AssertionError('Upgrade UI timeout')
        app.processEvents();assert not errors,errors
        assert len(window.service_workspace.cache['repairs'])==len(before['repair_orders'])
        assert window.grab().save(str(output/'upgrade.png'))
        window.close();app.processEvents();window=None
        assert snapshot(root/'service.db')==before,'Opening the previous project changed stored rows'
        proof['checks'].append('previous_database_rows_survive_restore_and_real_gui_open')
        store=ServiceStore(root);repair=store.repairs()[0]['id']
        document=generate_document(store,repair,'completion')
        assert document.is_file()
        proof['checks'].append('generate_document_on_previous_project')
        backup=create_backup(store,output/'after-update.zip')
        recovered=restore_backup(backup,output/'Recovered project')
        assert snapshot(recovered/'service.db')==snapshot(root/'service.db')
        proof['checks'].append('updated_project_backup_restore_preserves_all_rows_and_files')
        assert hashlib.sha256(archive.read_bytes()).hexdigest()==checksum
        proof['checks'].append('previous_backup_unchanged')
        proof['status']='passed'
    except Exception:
        proof['status']='failed';proof['traceback']=traceback.format_exc()
    finally:
        timer.stop()
        if window:window.close();app.processEvents()
        (output/'UPGRADE-SELF-TEST.json').write_bytes((json.dumps(proof,ensure_ascii=False,indent=2)+'\n').encode())
    return 0 if proof['status']=='passed' else 1


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--require-windows',action='store_true');args=p.parse_args(argv)
    return run(args.archive,args.output,args.require_windows)
