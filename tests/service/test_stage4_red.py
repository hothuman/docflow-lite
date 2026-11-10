from PySide6.QtWidgets import QComboBox,QPushButton
from test_stage1_upgrade_copy import app,idle,dispose
from docflow.gui import MainWindow
from docflow.ui.service.workspace import ServiceWorkspace
from docflow.ui.service.intake import IntakeDialog
from docflow.ui.service.history import HistoryDialog
from docflow.ui.service.repair_editor import RepairDialog

def test_st4_modes_are_both_visible_without_dropdown(app,tmp_path):
    w=MainWindow();w.show();app.processEvents()
    try:
        assert not isinstance(w.mode_picker,QComboBox)
        assert [b.text() for b in w.mode_picker.buttons]==['Документы','Мастерская']
        assert all(b.isVisible() for b in w.mode_picker.buttons)
    finally:w.close()

def test_st4_core_empty_has_no_empty_table_and_one_primary(app):
    w=MainWindow();w.show();app.processEvents()
    try:
        assert not w.source_table.isVisible()
        assert len([b for b in w.findChildren(QPushButton) if b.isVisible() and b.objectName()=='primary'])==1
    finally:w.close()

def test_st4_intake_hides_inactive_equipment_and_client_rows(app,tmp_path):
    w=ServiceWorkspace(root=tmp_path/'p');idle(app,w)
    try:
        w.store.intake(client={'name':'Учебный'},equipment={'number':'01','model':'Учебная'});w.refresh();idle(app,w)
        d=IntakeDialog(w);d.show();app.processEvents();d.new_equipment.setChecked(True);app.processEvents()
        assert not d.equipment.isVisible()
        d.new_client.setChecked(True);app.processEvents();assert not d.client.isVisible()
        d.accept()
    finally:dispose(app,w)

def test_st4_repair_has_no_nested_section_navigation(app,tmp_path):
    w=ServiceWorkspace(root=tmp_path/'p');idle(app,w)
    try:
        key=w.store.intake(client={'name':'Учебный'},equipment={'number':'01','model':'Учебная'});d=RepairDialog(w,w.store.snapshot(key));d.show();d.tabs.setCurrentIndex(3);app.processEvents()
        assert not any(x.isVisible() and x.accessibleName().startswith('Раздел:') for x in d.findChildren(QComboBox))
        assert d.next_button.objectName()=='primary';d.accept()
    finally:dispose(app,w)

def test_st4_history_compare_disabled_until_two_selected(app,tmp_path):
    w=ServiceWorkspace(root=tmp_path/'p');idle(app,w)
    try:
        w.store.intake(client={'name':'Учебный'},equipment={'number':'01','model':'Учебная'});d=HistoryDialog(w,w.store.equipment()[0]);d.show();idle(app,w);d.grid.selectRow(0);app.processEvents()
        compare=next(b for b in d.findChildren(QPushButton) if b.text().startswith('Сравнить'));assert not compare.isEnabled();d.accept()
    finally:dispose(app,w)
