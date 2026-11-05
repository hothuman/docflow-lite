"""Behavioural regressions from the independent rc7 audit, not pixel snapshots."""
import pytest
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QMessageBox
from PySide6.QtTest import QTest
from test_stage1_upgrade_copy import app,idle,dispose
from docflow.ui.service.workspace import ServiceWorkspace
from docflow.ui.service.forms import FieldsDialog
from docflow.ui.service.intake import IntakeDialog
from docflow.ui.service.catalog import CatalogDialog

@pytest.mark.parametrize('field',['phone','repair_number','number','model','name','complaint','equipment','client','repair_client'])
@pytest.mark.parametrize('exit_kind',['cancel','escape','close'])
def test_intake_active_edit_guard_all_exit_routes(app,tmp_path,monkeypatch,field,exit_kind):
    w=ServiceWorkspace(root=tmp_path/'p');idle(app,w)
    for i in range(2):w.store.intake(client={'name':f'QA Owner{i}'},equipment={'number':f'QA-{i}','model':'QA'})
    w.refresh();idle(app,w);d=IntakeDialog(w);d.show();app.processEvents();asked=[]
    monkeypatch.setattr('docflow.ui.service.widgets.confirm',lambda *a:asked.append(a[1]) or False)
    try:
        assert not d.dirty
        if field in ('phone','number','model','name','client'):d.new_equipment.setChecked(True)
        if field in ('phone','name'):d.new_client.setChecked(True)
        if field=='client':d.existing_client.setChecked(True)
        if field=='repair_number':d.more.setChecked(True)
        if field=='repair_client':d.other_client.setChecked(True)
        f=getattr(d,field)
        if hasattr(f,'setPlainText'):f.setPlainText('QA unsaved')
        elif hasattr(f,'setEditText'):f.setEditText('QA changed selection')
        else:f.setText('QA unsaved')
        assert d.dirty
        if exit_kind=='cancel':d.reject()
        elif exit_kind=='escape':QTest.keyClick(d,Qt.Key.Key_Escape)
        else:d.close()
        app.processEvents();assert d.isVisible() and len(asked)==1
        monkeypatch.setattr('docflow.ui.service.widgets.confirm',lambda *a:True);d.reject();assert not d.isVisible();assert len(w.store.repairs())==2
    finally:d.accept();dispose(app,w)

def test_unchanged_intake_and_hidden_values_do_not_prompt(app,tmp_path,monkeypatch):
    w=ServiceWorkspace(root=tmp_path/'p');idle(app,w);w.store.intake(client={'name':'QA'},equipment={'number':'QA','model':'QA'});w.refresh();idle(app,w)
    d=IntakeDialog(w);d.show();asked=[];monkeypatch.setattr('docflow.ui.service.widgets.confirm',lambda *a:asked.append(1) or False)
    try:
        d.new_equipment.setChecked(True);d.name.setText('HIDDEN');d.phone.setText('HIDDEN');d.existing_equipment.setChecked(True);d.repair_number.setText('HIDDEN')
        assert not d.dirty;d.reject();assert not d.isVisible() and not asked
    finally:d.accept();dispose(app,w)

