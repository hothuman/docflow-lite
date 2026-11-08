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

def measure_embedded(window,ui,app,idle):
 from docflow.ui.service.history import HistoryPage
 from docflow.ui.service.intake import IntakeDialog
 from docflow.ui.service.repair_editor import RepairPage
 from PySide6.QtWidgets import QPushButton

 def current(expected,trace):
  idle()
  page=ui.current_page
  assert isinstance(page,expected),type(page)
  assert page.window() is window and page.isVisible() and not page.isWindow()
  assert app.activeModalWidget() is None
  owned=[widget for widget in app.topLevelWidgets()
         if widget is not window and widget.isVisible() and window.isAncestorOf(widget)]
  assert not owned,[widget.windowTitle() for widget in owned]
  trace.append(ui.pages.titles[-1])
  return page

 def intake(trace,new=False):
  form=current(IntakeDialog,trace)
  if new:
   form.new_equipment.setChecked(True);form.new_client.setChecked(True)
   form.name.setText('Учебный клиент');form.model.setText('Учебный аппарат');form.number.setText('DEVICE-100')
  form.complaint.setPlainText('Учебная жалоба');form.submit.click()
  return current(RepairPage,trace)

 routes={}
 trace=[]
 ui.go_to_section(2)
 ui.journal.new_button.click()
 editor=intake(trace,new=True)
 assert len(ui.store.repairs())==1 and ui.store.repairs()[0]['id']==editor.key
 routes['first_intake']={'observed_dialogs':0,'embedded_pages':len(trace),'trace':trace}

 trace=[]
 editor.equipment_history()
 history=current(HistoryPage,trace)
 history.new_button.click()
 repeated=intake(trace)
 assert len(ui.store.repairs())==2 and repeated.key!=editor.key
 assert repeated.snapshot['equipment']['id']==editor.snapshot['equipment']['id']
 routes['repeat_intake']={'observed_dialogs':0,'embedded_pages':len(trace),'trace':trace}
 ui.back_page()
 current(HistoryPage,[])
 ui.back_page()
 assert current(RepairPage,[]) is editor

 events=[]
 editor.tabs.currentChanged.connect(lambda index:events.append('stage:'+str(index)))
 editor.tabs.sectionChanged.connect(lambda title:events.append('section:'+title))
 editor.tabs.show_section('Приёмка');events.clear()
 editor.tabs.show_section('Сметы');idle()
 assert editor.estimates.isVisible() and events
 routes['estimate']={'navigation_changes':len(events),'trace':events[:]}

 editor.tabs.show_section('Приёмка');events.clear()
 editor.tabs.show_section('Документы')
 wizard=editor.document_wizard
 wizard.start('completion')
 wizard.check_document();wizard.preview_button.click();idle()
 assert wizard.prepared and not editor.snapshot['generated_documents']
 ready=wizard.prepared.rendered
 action=next(item for item in wizard.findChildren(QPushButton) if item.text()=='Продолжить к созданию' and item.isVisible())
 action.click();wizard.generate_button.click();idle()
 assert len(editor.snapshot['generated_documents'])==1 and wizard._last_document.read_bytes()==ready
 routes['act']={'navigation_changes':len(events),'trace':events[:],
                'wizard_steps':list(wizard.steps[:5]),'preview_matches_docx':True}
 trace=[]
 editor.equipment_history()
 history=current(HistoryPage,trace)
 assert history.grid.proxy.rowCount()==2
 routes['history_after_work']={'executed_actions':1,'actions':['История аппарата'],
                              'dialogs':[],'embedded_pages':trace}
 ui.back_page()
 assert current(RepairPage,[]) is editor
 ui.back_page();idle()
 assert ui.current_page is None
 return routes

def run(output):
 output.mkdir(parents=True);app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False)
 window=MainWindow(service_root=output/'Synthetic');window.show();window.navigate(5);ui=window.service_workspace
 def idle():
  until=time.monotonic()+30
  while ui.worker or ui._pending_refresh:app.processEvents();time.sleep(.005);assert time.monotonic()<until
  app.processEvents()
 idle();modern=hasattr(ui,'start_intake');report={'version':__version__,'modern':modern,'scope':'Observed dialog openings and navigation signals; fixed routes excluding typing; no time or human UX measurement','routes':{}}
 if hasattr(ui,'current_page'):
  try:
   report['embedded']=True
   report['scope']='Observed main-window pages and navigation signals; fixed routes excluding typing; no elapsed time or human UX measurement'
   report['routes']=measure_embedded(window,ui,app,idle)
  finally:
   idle()
   # Failure may leave a synthetic unsaved form. Do not block the traceback
   # waiting for a manual confirmation in this standalone QA runner.
   while ui.current_page is not None:ui.pages.pop(notify=False)
   window.close();app.processEvents()
  (output/'ROUTES.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  print(json.dumps(report,ensure_ascii=False))
  return
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
