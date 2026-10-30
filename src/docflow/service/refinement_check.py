"""Opt-in a3 workflow verification; runs inside the exact frozen executable."""
import sys
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton
from ..ui.service.repair_editor import RepairDialog
from ..ui.service.estimates import DraftDialog
from .validation import rub
from .backup import create_backup,restore_backup
from .repository import ServiceStore

def exercise(workspace,app,output,idle,fill):
 checks=[];output=Path(output);store=workspace.store;window=workspace.window()
 def passed(name,**values):checks.append({'name':name,'passed':True,**values})
 window.resize(1366,768);workspace.tabs.setCurrentIndex(0);workspace.refresh();idle(workspace);app.processEvents();data=store.dashboard();dashboard=workspace.dashboard
 for key,label in dashboard.values.items():assert label.text()==(rub(data[key]) if key=='debt' else str(data[key]))
 assert dashboard.recent.proxy.rowCount()==len(data['recent_repairs']);captured=[];timer=QTimer()
 def observe():
  dialog=app.activeModalWidget()
  if isinstance(dialog,RepairDialog):captured.append(dialog.key);dialog.accept()
 timer.timeout.connect(observe);timer.start(1);index=dashboard.recent.proxy.index(0,0);key=dashboard.recent.records.rows[dashboard.recent.proxy.mapToSource(index).row()]['id'];QTest.mouseClick(dashboard.recent.viewport(),Qt.MouseButton.LeftButton,pos=dashboard.recent.visualRect(index).center());idle(workspace);timer.stop();assert captured and captured[0]==key
 from ..ui.service.search import SearchDialog
 search=SearchDialog(workspace);workspace.dialogs.append(search);search.show();idle(workspace);search.query.setFocus();QTest.keyClicks(search.query,'900');app.processEvents();assert search.equipment.proxy.rowCount()==1;search.accept();workspace.dialogs.remove(search);workspace.tabs.setCurrentIndex(0);app.processEvents();window.grab().save(str(output/'service-refined-dashboard.png'));passed('native_dashboard_actual_counters_row_open_and_keyboard_search')
 eq=next(x for x in store.equipment() if x['number']=='900');repair=store.create_repair(eq['id'],'SYNTH-ACCEPT-7500');editor=RepairDialog(workspace,store.snapshot(repair));workspace.dialogs.append(editor);editor.show();editor.tabs.show_section('Сметы');app.processEvents()
 fill(lambda:editor.estimates.freeze('preliminary'),{'actor':'Учебный оператор','reason':'Нулевой первоначальный расчёт'});idle(workspace);assert editor.snapshot['estimates'][0]['total']==0
 draft=DraftDialog(editor);workspace.dialogs.append(draft);draft.show()
 for kind,name,price in [('work','Учебная работа','4000'),('part','Учебная деталь','3000'),('delivery','Учебная доставка','500')]:fill(draft.add,{'kind':kind,'name':name,'quantity':'1','unit':'шт.','price':price})
 assert '7 500,00 ₽' in draft.total_label.text();draft.save();idle(workspace);workspace.dialogs.remove(draft);assert store.snapshot(repair)['totals']['balance']==0
 fill(lambda:editor.estimates.freeze('preliminary'),{'actor':'Учебный оператор','reason':'Уточнение учебного расчёта'});idle(workspace);editor.estimates.grid.selectRow(0);fill(editor.estimates.manual_event,{'action':'approved','actor':'Учебный оператор','comment':'Синтетическая ручная отметка, реального клиента нет'});idle(workspace)
 for kind,name,price in [('work','Фактическая учебная работа','5000'),('part','Фактическая учебная деталь','4000'),('delivery','Учебная доставка','500'),('other','Учебный расход','170')]:fill(lambda k=kind:editor.item(k),{'name':name,'quantity':'1','unit':'шт.','price':price,'change_reason':'Фактическое уточнение для теста'});idle(workspace)
 assert editor.snapshot['totals']['total']==967000 and editor.snapshot['estimate_comparison']['difference']==217000
 fill(lambda:editor.estimates.freeze('final'),{'actor':'Учебный оператор','reason':'Уточнён фактический объём'});idle(workspace)
 for kind in ('preliminary','final'):
  for row in range(editor.estimates.grid.proxy.rowCount()):
   source=editor.estimates.grid.proxy.mapToSource(editor.estimates.grid.proxy.index(row,0));quote=editor.estimates.grid.records.rows[source.row()]
   if quote['kind']==kind and (kind=='final' or quote['version']==2):editor.estimates.grid.selectRow(row);break
  editor.estimates.document();idle(workspace)
 assert len(editor.snapshot['generated_documents'])==2;editor.tabs.show_section('Сметы');app.processEvents();editor.grab().save(str(output/'service-refined-estimates.png'));editor.accept();workspace.dialogs.remove(editor);passed('native_owner_0_7500_9670_2170_real_forms_and_both_docx',repair_id=repair)
 archive=create_backup(store,output/'refinement.service-backup.zip');root=restore_backup(archive,output/'Refinement restored');again=ServiceStore(root);snapshot=again.snapshot(repair);assert snapshot['estimate_comparison']['difference']==217000 and len(snapshot['estimates'])==3 and len(snapshot['generated_documents'])==2;passed('native_refined_backup_restore_reopen',backup=archive.name)
 if getattr(sys,'frozen',False):
  from .layout_check import assess
  workspace.refresh();idle(workspace);layout=assess(window,workspace,app,output/'refined-layout',idle);assert layout['status']=='passed'
 else:layout={'status':'not_run_here','reason':'All scales run by tools/qa_refinement_ui.py; frozen binary runs native virtual layouts.'}
 return {'status':'passed','checks':checks,'layout':layout,'manual_windows_word_acceptance':False}
