"""Measure observed dialogs/navigation, not guessed click savings or timings.

Run unchanged with PYTHONPATH pointing at rc4/src, then at the candidate/src.
"""
import argparse,json,time
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox,QComboBox,QPlainTextEdit
from PySide6.QtGui import QDesktopServices
from docflow.gui import MainWindow,configure_app
from docflow.ui.service.forms import FieldsDialog
from docflow.ui.service.repair_editor import RepairDialog
from docflow.ui.service.history import HistoryDialog
from docflow.service.documents import KINDS
from docflow import __version__

def run(output):
 output.mkdir(parents=True);app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False)
 window=MainWindow(service_root=output/'Synthetic');window.show();window.navigate(5);ui=window.service_workspace
 def idle():
  until=time.monotonic()+30
  while ui.worker or ui._pending_refresh:app.processEvents();time.sleep(.005);assert time.monotonic()<until
  app.processEvents()
 idle();modern=hasattr(ui,'start_intake');report={'version':__version__,'modern':modern,'scope':'Observed dialog openings and navigation signals; fixed routes excluding typing; no time or human UX measurement','routes':{}}
 def perform(action,values,trace):
  seen=[];timer=QTimer()
  def observe():
   d=app.activeModalWidget()
   if d is None or d in seen:return
   seen.append(d);trace.append(d.windowTitle())
   if isinstance(d,FieldsDialog):
    for key,value in values.items():
     field=d.fields[key]
     if isinstance(field,QComboBox):field.setCurrentIndex(field.findData(value))
     elif isinstance(field,QPlainTextEdit):field.setPlainText(value)
     else:field.setText(value)
    d.accept()
   elif isinstance(d,RepairDialog):d.accept()
   elif type(d).__name__=='IntakeDialog':
    if values.get('new',False):d.new_equipment.setChecked(True);d.new_client.setChecked(True);d.name.setText('Учебный клиент');d.model.setText('Учебный аппарат');d.number.setText('DEVICE-100')
    d.complaint.setPlainText('Учебная жалоба');d.submit.click()
   elif isinstance(d,HistoryDialog):d.accept()
  timer.timeout.connect(observe);timer.start(10)
  try:action();idle()
  finally:timer.stop()
 trace=[]
 if modern:perform(ui.start_intake,{'new':True},trace)
 else:
  perform(ui.new_client,{'name':'Учебный клиент'},trace);perform(ui.new_equipment,{'number':'DEVICE-100','model':'Учебный аппарат','owner_id':ui.store.clients()[0]['id']},trace)
  perform(ui.new_repair,{'equipment_id':ui.store.equipment()[0]['id'],'number':'','complaint':'Учебная жалоба','client_id':None},trace)
 assert len(ui.store.repairs())==1
 report['routes']['first_intake']={'observed_dialogs':len(trace),'trace':trace}
 eq=ui.store.equipment()[0];history=HistoryDialog(ui,eq);history.show();idle();trace=[history.windowTitle()]
 perform(history.new,{'equipment_id':eq['id'],'number':'','complaint':'Учебная жалоба','client_id':None},trace)
 assert len(ui.store.repairs())==2
 report['routes']['repeat_intake']={'observed_dialogs':len(trace),'trace':trace}
 editor=RepairDialog(ui,ui.store.snapshot(ui.store.repairs()[0]['id']));ui.dialogs.append(editor);editor.show();app.processEvents();events=[]
 editor.tabs.currentChanged.connect(lambda index:events.append('stage:'+str(index)))
 for title,card in editor.tabs.cards.items():card.toggle.toggled.connect(lambda expanded,name=title:events.append('details:'+name+':'+str(expanded)))
 editor.tabs.show_section('Приёмка');events.clear();editor.tabs.show_section('Сметы');app.processEvents()
 report['routes']['estimate']={'navigation_changes':len(events),'trace':events[:]}
 editor.tabs.show_section('Приёмка');events.clear();old_item=QInputDialog.getItem;old_open=QDesktopServices.openUrl;old_warning=QMessageBox.warning
 QInputDialog.getItem=lambda *args:(KINDS['completion'],True);QDesktopServices.openUrl=lambda *args:False;QMessageBox.warning=lambda *args:None
 try:editor.quick_document();idle()
 finally:QInputDialog.getItem=old_item;QDesktopServices.openUrl=old_open;QMessageBox.warning=old_warning
 assert len(editor.snapshot['generated_documents'])==1
 report['routes']['act']={'navigation_changes':len(events),'trace':events[:]}
 trace=[]
 if modern:perform(editor.equipment_history,{},trace);actions=['История аппарата']
 else:
  editor.accept();ui.dialogs.remove(editor);ui.find_equipment();ui.views['equipment'].selectRow(0);perform(ui.equipment_card,{},trace);actions=['Закрыть карточку','Оборудование','Выбрать аппарат','Карточка / история']
 assert any('История' in x for x in trace)
 report['routes']['history_after_work']={'executed_actions':len(actions),'actions':actions,'dialogs':trace}
 if modern:editor.accept();ui.dialogs.remove(editor)
 window.close();app.processEvents();(output/'ROUTES.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();run(args.output)
