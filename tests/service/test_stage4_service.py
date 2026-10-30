from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QApplication,QComboBox
from test_stage1_upgrade_copy import app,idle,dispose
from docflow.ui.service.workspace import ServiceWorkspace
from docflow.ui.service.intake import IntakeDialog
from docflow.ui.service.history import HistoryDialog
from docflow.ui.service.repair_editor import RepairDialog

def seed(w):
    key=w.store.intake(client={'name':'Учебный собственник'},equipment={'number':'A-001','model':'Учебная модель'});w.refresh();idle(QApplication.instance(),w);return key

def test_hidden_new_values_cannot_create_entities_in_repeat_intake(app,tmp_path):
    w=ServiceWorkspace(root=tmp_path/'p');idle(app,w);seed(w)
    try:
        d=IntakeDialog(w);d.show();d.new_equipment.setChecked(True);d.new_client.setChecked(True);d.name.setText('НЕ СОХРАНЯТЬ');d.number.setText('НЕ СОХРАНЯТЬ');d.model.setText('НЕ СОХРАНЯТЬ');d.existing_equipment.setChecked(True)
        assert d.existing_equipment.isChecked() and not d.new_equipment.isChecked() and not d.device_body.isVisible()
        assert 'история сохраняется' in d.confirmation.text() and 'НЕ СОХРАНЯТЬ' not in d.confirmation.text()
        d.submit.click();idle(app,w)
        assert len(w.store.equipment())==len(w.store.clients())==1 and len(w.store.repairs())==2
    finally:dispose(app,w)

def test_new_equipment_existing_client_ignores_hidden_new_client(app,tmp_path):
    w=ServiceWorkspace(root=tmp_path/'p');idle(app,w);seed(w)
    try:
        d=IntakeDialog(w);d.show();d.new_equipment.setChecked(True);d.new_client.setChecked(True);d.name.setText('НЕ СОХРАНЯТЬ');d.existing_client.setChecked(True);d.number.setText('A-002');d.model.setText('Другой аппарат');d.submit.click();idle(app,w)
        assert len(w.store.clients())==1 and len(w.store.equipment())==2
    finally:dispose(app,w)

def test_editable_search_cannot_silently_reuse_previous_id(app,tmp_path):
    w=ServiceWorkspace(root=tmp_path/'p');idle(app,w);seed(w)
    try:
        d=IntakeDialog(w);d.show();d.equipment.setEditText('Нет такого аппарата');d.submit.click();app.processEvents()
        assert len(w.store.repairs())==1 and w.worker is None and 'из списка' in d.note.text();d.accept()
    finally:dispose(app,w)

def test_repair_one_navigation_keeps_input_and_current_step_cta(app,tmp_path):
    w=ServiceWorkspace(root=tmp_path/'p');idle(app,w);key=seed(w)
    try:
        d=RepairDialog(w,w.store.snapshot(key));d.show();d.fields['complaint'].setPlainText('Не сохранено')
        for step in range(4):d.tabs.setCurrentIndex(step);d.next_button.click();app.processEvents();assert d.tabs.currentIndex()==step+1
        assert d.dirty and d.fields['complaint'].toPlainText()=='Не сохранено' and w.store.snapshot(key)['repair']['status']=='accepted'
        d.tabs.show_section('Финансы');app.processEvents();assert d.tabs.cards['Финансы'].content.isVisible()
        assert not any(x.accessibleName().startswith('Раздел:') for x in d.findChildren(QComboBox));d.dirty=False;d.accept()
    finally:dispose(app,w)

def test_history_selection_2_to_6_and_filter_reset(app,tmp_path):
    w=ServiceWorkspace(root=tmp_path/'p');idle(app,w);seed(w);eq=w.store.equipment()[0]
    try:
        for i in range(6):w.store.create_repair(eq['id'],'H-'+str(i))
        d=HistoryDialog(w,eq);d.show();idle(app,w);selection=d.grid.selectionModel()
        for count in range(8):
            selection.clearSelection()
            for i in range(count):selection.select(d.grid.proxy.index(i,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
            assert d.compare_button.isEnabled()==(2<=count<=6)
        d.search.setText('Несуществующая строка');app.processEvents();assert not d.compare_button.isEnabled() and d.empty_hint.isVisible()
        d.reset_filters();idle(app,w);assert d.grid.proxy.rowCount()==7 and not d.compare_button.isEnabled();d.accept()
    finally:dispose(app,w)
