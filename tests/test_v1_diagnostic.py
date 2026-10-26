"""Diagnostic argument failures preserve existing evidence and do not crash the GUI exe."""
from docflow.service.compatibility_check import main


def test_upgrade_refuses_existing_output_without_unhandled_exception(tmp_path):
    output=tmp_path/'Existing evidence';output.mkdir()
    sentinel=output/'keep.txt';sentinel.write_text('previous evidence')
    assert main(['--archive',str(tmp_path/'missing.zip'),'--output',str(output)])==2
    assert sentinel.read_text()=='previous evidence'
    assert sorted(p.name for p in output.iterdir())==['keep.txt']


import sqlite3
import shutil
import pytest
from docflow.service.compatibility_check import assert_upgrade_preserved
from docflow.service.database import MIGRATIONS
from docflow.service.repository import ServiceStore


def upgraded_fixture(tmp_path):
    root=tmp_path/'v4';root.mkdir();original=tmp_path/'original.db';db=root/'service.db'
    with sqlite3.connect(db) as c:
        for v in range(1,5):
            for sql in MIGRATIONS[v]:c.execute(sql)
        c.execute("INSERT INTO clients(id,kind,name,created_at,updated_at) VALUES('c','organization','Synthetic','x','x')")
        c.execute("INSERT INTO equipment(id,number,model,owner_id,created_at,updated_at) VALUES('e','E','Model','c','x','x')")
        c.execute("INSERT INTO repair_orders(id,number,equipment_id,client_id,received_at,created_at,updated_at) VALUES('r','R','e','c','2020-01-01','x','x')")
        c.execute("INSERT INTO import_sources VALUES('s','source','sha','sheet','{}','x')")
        c.execute("INSERT INTO import_records VALUES('i','s','key','sha','r','{}','x')")
        c.execute('PRAGMA user_version=4')
    shutil.copy2(db,original);ServiceStore(root)
    return original,db


def test_upgrade_diagnostic_accepts_explicit_v4_schema_additions(tmp_path):
    old,new=upgraded_fixture(tmp_path)
    assert_upgrade_preserved(old,new)
    assert_upgrade_preserved(new,new)


@pytest.mark.parametrize('mutation',[
    "UPDATE clients SET name='Changed'",
    "DELETE FROM import_records",
    "ALTER TABLE equipment ADD COLUMN unexpected TEXT",
    "CREATE TABLE unexpected(id TEXT)",
    "DELETE FROM repair_finance_evidence",
    "UPDATE repair_finance_evidence SET payments_known=1",
    "UPDATE repair_finance_evidence SET updated_at='invented'",
    "UPDATE repair_finance_evidence SET note='Changed'",
])
def test_upgrade_diagnostic_rejects_data_loss_or_invented_evidence(tmp_path,mutation):
    old,new=upgraded_fixture(tmp_path)
    with sqlite3.connect(new) as c:c.execute(mutation)
    with pytest.raises(AssertionError):assert_upgrade_preserved(old,new)
