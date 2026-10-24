"""Actual Qt large-journal probes; measurements are not an SLA."""
import time
from pathlib import Path
from PySide6.QtCore import QTimer,QCoreApplication,QEvent
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from docflow.gui import MainWindow,configure_app
from docflow.service.estimates import save_draft
from docflow.service.attachments import add_attachment
from docflow.ui.service.repair_editor import RepairDialog
from docflow.ui.service.estimates import DraftDialog
from docflow.ui.service.history import HistoryDialog
_APP=None

def probe(store,expected,output):
 global _APP
 _APP=QApplication.instance() or QApplication([]);app=_APP;configure_app(app);app.setQuitOnLastWindowClosed(False);output=Path(output);ticks=[];errors=[]
 timer=QTimer();timer.timeout.connect(lambda:ticks.append(time.perf_counter()));timer.start(5)
 guard=QTimer()
 def message():
  d=app.activeModalWidget()
  if isinstance(d,QMessageBox):errors.append(d.text());d.accept()
 guard.timeout.connect(message);guard.start(10)
 def idle(ui):
  end=time.monotonic()+30
  while ui.worker or ui._pending_refresh:app.processEvents();time.sleep(.005);assert time.monotonic()<end
  app.processEvents();assert not errors,errors
 start=time.perf_counter();w=MainWindow(service_root=store.root);w.show();w.navigate(5);ui=w.service_workspace;idle(ui);opened=time.perf_counter()-start
 try:
  view=ui.views['repairs'];ui.tabs.setCurrentIndex(2);app.processEvents();assert view.proxy.rowCount()==expected
  start=time.perf_counter();ui.searches['repairs'].setText('Учебная позиция 2');app.processEvents();assert view.proxy.rowCount()==expected;filtered=time.perf_counter()-start
  ui.searches['repairs'].clear();start=time.perf_counter();col=next(i for i,x in enumerate(view.records.columns) if x[0]=='total');view.sortByColumn(col,__import__('PySide6.QtCore',fromlist=['Qt']).Qt.SortOrder.DescendingOrder);app.processEvents();assert view.proxy.index(0,0).data()=='TEST-0-0';sorted_time=time.perf_counter()-start
  calls=[];original=ui.store.repairs
  def counted(*a,**kw):calls.append(1);return original(*a,**kw)
  ui.store.repairs=counted;w.resize(1280,720);view.verticalScrollBar().setValue(view.verticalScrollBar().maximum());QTest.mouseMove(view.viewport());app.processEvents();assert not calls,'Resize/hover/scroll queried the whole repair journal';ui.store.repairs=original
  eq=next(e for e in ui.cache['active_equipment'] if e['id']=='e0');start=time.perf_counter();history=HistoryDialog(ui,eq);history.show();idle(ui);assert history.grid.proxy.rowCount()==30;history_seconds=time.perf_counter()-start;history.accept()
  rows=store.snapshot('r0-0')['repair_items'];save_draft(store,'r0-0',rows)
  editor=RepairDialog(ui,store.snapshot('r0-0'));editor.show();start=time.perf_counter();draft=DraftDialog(editor);draft.show();draft.discount.setText('1');app.processEvents();assert len(draft.lines)==103;draft_seconds=time.perf_counter()-start;draft.dirty=False;draft.reject()
  photo=output/'synthetic-preview.png';image=QImage(800,450,QImage.Format.Format_RGB32);image.fill(QColor('#781326'));assert image.save(str(photo));add_attachment(store,'r0-0',photo,'Синтетическая проверка preview');editor.install(store.snapshot('r0-0'));editor.tabs.show_section('Вложения');editor.grids['attachments'].selectRow(0);start=time.perf_counter();editor.preview_image();idle(ui);assert not editor.image.pixmap().isNull();preview_seconds=time.perf_counter()-start;editor.accept()
  gaps=[b-a for a,b in zip(ticks,ticks[1:])];result={'journal_rows':expected,'open_seconds':round(opened,4),'filter_seconds':round(filtered,4),'sort_seconds':round(sorted_time,4),'history_seconds':round(history_seconds,4),'edit_103_line_draft_seconds':round(draft_seconds,4),'photo_preview_seconds':round(preview_seconds,4),'heartbeat_ticks':len(ticks),'max_heartbeat_gap_seconds':round(max(gaps,default=0),4),'whole_journal_queries_on_resize_hover_scroll':len(calls)}
  assert len(ticks)>2 and max(gaps,default=0)<3,'GUI heartbeat exceeded 3 seconds on this runner'
  assert max(opened,filtered,sorted_time,history_seconds,draft_seconds,preview_seconds)<30
  return result
 finally:
  idle(ui);timer.stop();guard.stop();w.close();w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
