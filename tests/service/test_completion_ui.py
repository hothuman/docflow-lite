"""Real Qt forms/wizard operations against a persistent SQLite project."""
import time
from pathlib import Path
import pytest
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog,QDialogButtonBox,QComboBox,QPlainTextEdit,QMessageBox,QWizard
from docflow.gui import MainWindow
from docflow.ui.service.forms import FieldsDialog
from docflow.ui.service.repair_editor import RepairDialog
from docflow.ui.service.estimates import DraftDialog
from docflow.ui.service.profiles import ProfileDialog
from docflow.ui.service.import_wizard import HistoryWizard
from docflow.service.demo import seed_demo

@pytest.fixture
def ui(tmp_path):
 app=QApplication.instance() or QApplication([]);errors=[]
 def message():
  d=app.activeModalWidget()
  if isinstance(d,QMessageBox):
   if d.standardButtons() & QMessageBox.StandardButton.Yes:d.button(QMessageBox.StandardButton.Yes).click()
   else:errors.append(d.text());d.accept()
 timer=QTimer();timer.timeout.connect(message);timer.start(10)
 w=MainWindow(service_root=tmp_path/'UI project');w.show();w.navigate(5);sui=w.service_workspace
 idle(app,sui)
 yield app,w,sui,errors
 while sui.worker:app.processEvents();time.sleep(.005)
 timer.stop();w.close();app.processEvents();assert not errors,errors

def idle(app,sui):
 until=time.monotonic()+30
 while sui.worker or sui._pending_refresh:
  app.processEvents();time.sleep(.005);assert time.monotonic()<until
 app.processEvents()

def fill(app,action,values):
 failures=[]
 def enter():
  d=app.activeModalWidget()
  try:
   assert isinstance(d,FieldsDialog),type(d)
   for k,v in values.items():
    widget=d.fields[k]
    if isinstance(widget,QComboBox):
     i=widget.findData(v);assert i>=0,(k,v);widget.setCurrentIndex(i)
    elif isinstance(widget,QPlainTextEdit):widget.setPlainText(v)
    else:widget.setText(v)
   QTest.mouseClick(d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
  except Exception as exc:
   failures.append(repr(exc))
   if d:d.reject()
 QTimer.singleShot(40,enter);action();assert not failures,failures

def test_real_history_wizard_three_repairs_one_device_and_two_owners(ui,tmp_path):
 app,w,sui,_=ui
 source=tmp_path/'История.csv';source.write_text('repair_number;equipment_number;model;client_key;client_name;received_at;works;work_cost\n101;900;Учебный аппарат;A;Синтетический клиент А;2023-01-01;Осмотр;100\n305;900;Учебный аппарат;B;Синтетический клиент Б;2024-02-03;Настройка;200\n900;900;Учебный аппарат;B;Синтетический клиент Б;2026-03-04;Ремонт;300\n',encoding='utf-8-sig')
 d=HistoryWizard(sui);sui.dialogs.append(d);d.show();d.path.setText(str(source));app.processEvents()
 QTest.mouseClick(d.button(QWizard.WizardButton.NextButton),Qt.MouseButton.LeftButton);idle(app,sui);assert d.currentId()==1 and not sui.store.repairs()
 assert d.mappings['equipment_number'].currentData()=='equipment_number'
 d.default_status.setCurrentIndex(d.default_status.findData('closed'))
 QTest.mouseClick(d.button(QWizard.WizardButton.NextButton),Qt.MouseButton.LeftButton);idle(app,sui);assert d.currentId()==2
 d.confirm_new();idle(app,sui);assert not sui.store.repairs()
 d.identity.selectRow(0);fill(app,d.decide,{'equipment':'new','client':'new','owner':'b'});idle(app,sui)
 QTest.mouseClick(d.button(QWizard.WizardButton.NextButton),Qt.MouseButton.LeftButton);idle(app,sui);assert d.currentId()==3
 assert d.selection.rowCount()==3;d.confirmed.setChecked(True)
 QTest.mouseClick(d.button(QWizard.WizardButton.NextButton),Qt.MouseButton.LeftButton);idle(app,sui)
 assert d.currentId()==4 and d.result_report['imported']==3
 assert len(sui.store.equipment())==1 and len(sui.store.clients())==2
 eq=sui.store.equipment()[0];assert eq['number']=='900' and eq['owner']=='Синтетический клиент Б'
 fourth=sui.store.create_repair(eq['id'],'FOURTH');assert len(sui.store.repairs(equipment_id=eq['id']))==4
 assert len(sui.store.compare_repairs([r['id'] for r in sui.store.repairs(equipment_id=eq['id'])]))==4
 d.accept();sui.dialogs.remove(d)


def test_real_profile_draft_quote_event_and_actual_expense_forms(ui):
 app,w,sui,_=ui
 p=ProfileDialog(sui);sui.dialogs.append(p);p.show();idle(app,sui)
 fill(app,lambda:p.edit(False),{'name':'Синтетический профиль','organization_name':'Учебное предприятие','number_prefix':'TEST-','number_start':'900','status_accepted':'На осмотре'})
 idle(app,sui);p.grid.selectRow(0);p.activate();idle(app,sui);p.accept();sui.dialogs.remove(p)
 client=sui.store.save_client({'name':'Учебный клиент'});eq=sui.store.save_equipment({'number':'DEVICE','model':'Учебный аппарат','owner_id':client});r=sui.store.create_repair(eq)
 assert sui.store.get('repair_orders',r)['number']=='TEST-000900'
 editor=RepairDialog(sui,sui.store.snapshot(r));sui.dialogs.append(editor);editor.show()
 d=DraftDialog(editor);sui.dialogs.append(d);d.show()
 fill(app,d.add,{'kind':'delivery','name':'Учебная доставка','quantity':'2','unit':'рейс','price':'100.25'})
 assert len(d.lines)==1;d.comment.setPlainText('Только проверочный расчёт');d.save();idle(app,sui);sui.dialogs.remove(d)
 assert sui.store.snapshot(r)['totals']['balance']==0 and len(sui.store.snapshot(r)['preliminary_draft']['lines'])==1
 fill(app,lambda:editor.estimates.freeze('preliminary'),{'actor':'Тестовый оператор','reason':'Первый расчёт'});idle(app,sui)
 editor.estimates.grid.selectRow(0)
 fill(app,editor.estimates.manual_event,{'action':'approved','actor':'Тестовый оператор','comment':'Вымышленная ручная отметка для теста'});idle(app,sui)
 assert editor.snapshot['estimate_comparison']['approved_estimate_id']
 fill(app,lambda:editor.item('delivery'),{'name':'Фактическая учебная доставка','quantity':'1','unit':'рейс','price':'150','change_reason':'Изменился тестовый маршрут'});idle(app,sui)
 assert editor.snapshot['totals']['total']==15000 and editor.snapshot['estimate_comparison']['difference']==-5050
 fill(app,lambda:editor.estimates.freeze('final'),{'actor':'Тестовый оператор','reason':'Изменился тестовый маршрут'});idle(app,sui)
 editor.estimates.grid.selectRow(0);editor.estimates.document();idle(app,sui)
 assert len(editor.snapshot['generated_documents'])==1
 editor.accept();sui.dialogs.remove(editor)


def test_search_uses_hidden_manufacturer_item_text_and_exact_money_sort(ui):
 app,w,sui,_=ui
 from docflow.ui.service.widgets import Grid
 g=Grid([('number','Номер'),('total','Стоимость')]);g.install([{'number':'R-1','manufacturer':'Тестовый производитель','item_text':'Редкая деталь','total':10000},{'number':'R-2','manufacturer':'Другой','total':900}])
 g.proxy.setFilterFixedString('Редкая деталь');assert g.proxy.rowCount()==1
 g.proxy.setFilterFixedString('Тестовый производитель');assert g.proxy.rowCount()==1
 g.proxy.setFilterFixedString('');g.sortByColumn(1,Qt.SortOrder.AscendingOrder);assert g.proxy.index(0,0).data()=='R-2'
