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



def assert_upgrade_preserved(original, upgraded):
    """Check old rows exactly and explicit v4→v5→v6 additions independently.

    Opening a migrated database is not expected to reproduce the old schema.
    Supports the public v4 baseline, Stage2 v5 and current v6.
    """
    before=snapshot(original);after=snapshot(upgraded)
    with closing(sqlite3.connect(original.as_uri()+'?mode=ro',uri=True)) as old, closing(sqlite3.connect(upgraded.as_uri()+'?mode=ro',uri=True)) as new:
        version=old.execute('PRAGMA user_version').fetchone()[0]
        target=new.execute('PRAGMA user_version').fetchone()[0]
        from .database import SCHEMA_VERSION
        assert target==SCHEMA_VERSION,'Unexpected target schema'
        catalog={'catalog_items','catalog_profiles','catalog_imports'}
        if version<SCHEMA_VERSION:assert all(not after[name] for name in catalog),'New catalog tables must start empty'
        if version==SCHEMA_VERSION:
            assert after==before,'Current-version restore changed stored rows'
            return after
        if version==5:
            assert set(after)==set(before)|catalog
            for name,rows in before.items():assert after[name]==rows,'Changed stage2 rows: '+name
            return after
        assert version==4,'Upgrade diagnostic baseline must use schema v4, v5 or current'
        assert set(after)==set(before)|{'repair_finance_evidence'}|catalog,'Unexpected table additions/removals'
        for name,rows in before.items():
            quoted='"'+name.replace('"','""')+'"'
            old_columns=[r[1] for r in old.execute('PRAGMA table_info('+quoted+')')]
            new_columns=[r[1] for r in new.execute('PRAGMA table_info('+quoted+')')]
            expected=old_columns+(['price_known'] if name=='repair_items' else [])
            assert new_columns==expected,'Unexpected column change: '+name
            columns=','.join('"'+c.replace('"','""')+'"' for c in old_columns)
            assert [list(r) for r in new.execute('SELECT '+columns+' FROM '+quoted+' ORDER BY rowid')]==rows,'Changed original rows: '+name
        assert all(r[0]==1 for r in new.execute('SELECT price_known FROM repair_items')),'Existing item price flags changed'
        expected={r[0] for r in old.execute('SELECT DISTINCT repair_id FROM import_records')}
        evidence=list(new.execute('SELECT repair_id,cost_known,payments_known,note,updated_at FROM repair_finance_evidence'))
        assert len(evidence)==len(expected) and {r[0] for r in evidence}==expected,'Historical evidence coverage changed'
        for repair,cost,payments,note,stamp in evidence:
            assert cost==payments==0,'Historical completeness must remain unknown'
            assert note=='Исторический импорт прежней версии: полнота стоимости и оплат не подтверждена','Unexpected migration note'
            assert stamp in {r[0] for r in old.execute('SELECT imported_at FROM import_records WHERE repair_id=?',(repair,))},'Invented migration date'
    return after


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
        migrated=assert_upgrade_preserved(original,root/'service.db')
        proof['checks'].append('old_columns_and_explicit_schema_additions_verified')
        window=MainWindow(service_root=root);window.show();window.navigate(5)
        deadline=time.monotonic()+40
        while window.service_workspace.worker or window.service_workspace._pending_refresh:
            app.processEvents();time.sleep(.01)
            if time.monotonic()>deadline:raise AssertionError('Upgrade UI timeout')
        app.processEvents();assert not errors,errors
        assert len(window.service_workspace.cache['repairs'])==len(before['repair_orders'])
        assert window.grab().save(str(output/'upgrade.png'))
        window.close();app.processEvents();window=None
        assert snapshot(root/'service.db')==migrated,'Opening the migrated project changed stored rows'
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
    try:
        return run(args.archive,args.output,args.require_windows)
    except (ValueError,OSError) as exc:
        # Invalid diagnostic arguments must not open PyInstaller's crash dialog.
        # Preserve pre-existing output; a failed invocation never overwrites it.
        if sys.stderr is not None:print(str(exc),file=sys.stderr)
        return 2
