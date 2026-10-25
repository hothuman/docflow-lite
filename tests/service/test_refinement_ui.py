"""Real Qt paint, workflow, exact money, search and conflict regressions."""
import time
import pytest
from PySide6.QtCore import Qt,QTimer,QPoint,QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox,QPlainTextEdit
from docflow.gui import MainWindow,configure_app
from docflow.service.demo import seed_demo
from docflow.service.estimates import normalize_lines
from docflow.ui.service.repair_editor import RepairDialog
from docflow.ui.service.estimates import DraftDialog
from docflow.ui.service.widgets import Grid

def idle(app,ui):
 end=time.monotonic()+30
 while ui.worker or ui._pending_refresh:app.processEvents();time.sleep(.005);assert time.monotonic()<end
 app.processEvents()
@pytest.fixture
def ui(tmp_path,monkeypatch):
 app=QApplication.instance() or QApplication([]);configure_app(app);messages=[];monkeypatch.setattr(QMessageBox,'warning',lambda parent,title,message:messages.append(message));ids=seed_demo(tmp_path/'Synthetic');w=MainWindow(service_root=tmp_path/'Synthetic');w.resize(1366,768);w.show();w.navigate(5);sui=w.service_workspace;idle(app,sui)
 yield app,w,sui,ids,messages
 idle(app,sui);w.close();app.processEvents()

def test_dashboard_values_and_actual_row_open(ui):
 app,w,sui,ids,messages=ui;d=sui.dashboard;data=sui.store.dashboard();assert d.values['equipment'].text()==str(data['equipment']);assert d.values['active'].text()==str(data['active']);assert d.recent.proxy.rowCount()==len(data['recent_repairs']);assert not d.findChildren(QPlainTextEdit)
 captured=[];timer=QTimer()
 def capture():
  dialog=app.activeModalWidget()
  if isinstance(dialog,RepairDialog):captured.append(dialog.key);dialog.accept()
 timer.timeout.connect(capture);timer.start(2);index=d.recent.proxy.index(0,0);target=d.recent.records.rows[d.recent.proxy.mapToSource(index).row()]['id']
 QTest.mouseClick(d.recent.viewport(),Qt.MouseButton.LeftButton,pos=d.recent.visualRect(index).center());idle(app,sui);timer.stop();assert captured and captured[0]==target
 sui.find_equipment();app.processEvents();assert sui.searches['equipment'].hasFocus();QTest.keyClicks(sui.searches['equipment'],'DEMO-001');assert sui.views['equipment'].proxy.rowCount()==1;assert not messages

def test_real_dialog_dark_paint_and_three_groups(ui):
 import json,os
 from pathlib import Path
 app,w,sui,ids,_=ui;d=RepairDialog(sui,sui.store.snapshot(ids['repair']));d.show();app.processEvents();image=d.grab().toImage();probes=[]
 for widget in (d.fields['complaint'],d.tabs.sections['Приёмка'][2].widget()):
  point=QPoint(8,8);legacy=image.pixelColor(widget.mapTo(d,point));child=widget.childAt(point)
  target=widget.viewport() if isinstance(widget,QPlainTextEdit) else widget
  painted=target.grab().toImage()
  # A fixed point can hit a label glyph with Segoe UI on Windows. Measure
  # exposed container paint, excluding children; the empty text-edit bottom
  # is below its first text line. Keep the same dark-background threshold.
  points=([QPoint(x,target.height()-8) for x in range(8,target.width()-8,8)] if isinstance(widget,QPlainTextEdit) else
          [QPoint(x,y) for y in range(2,target.height()-2,4) for x in range(2,target.width()-2,8) if target.childAt(QPoint(x,y)) is None])
  assert points,'No exposed background sampled'
  colors=[painted.pixelColor(p) for p in points]
  probes.append({'widget':type(widget).__name__,'legacy_rgb':legacy.name(),'legacy_child':type(child).__name__ if child else None,'legacy_child_text':child.text() if hasattr(child,'text') else None,'background_samples':len(points),'maximum_channel':max(max(c.red(),c.green(),c.blue()) for c in colors)})
  assert all(max(c.red(),c.green(),c.blue())<70 for c in colors),probes[-1]
 proof=Path(os.environ.get('DOCFLOW_QA_ARTIFACTS','artifacts'))/'dialog-paint';proof.mkdir(parents=True,exist_ok=True);d.grab().save(str(proof/'repair-dialog.png'));(proof/'samples.json').write_text(json.dumps(probes,ensure_ascii=False,indent=2),encoding='utf-8')
 assert d.tabs.count()==3 and not d.tabs.usesScrollButtons();assert set(d.tabs.sections)==set(d.tabs.GROUPS);d.accept()

def test_localized_exact_price_sort_and_visible_money(ui):
 app,w,sui,ids,_=ui;g=Grid([('name','Наименование'),('price','Цена'),('total','Сумма'),('created_at','Создано')]);g.resize(640,300);g.show();g.install([{'id':'a','name':'Б','price_cents':10000,'total':10000,'created_at':'2026-10-24T12:34:56+03:00'},{'id':'b','name':'А','price_cents':900,'total':900,'created_at':'2026-10-23'}]);app.processEvents();assert g.records.index(0,1).data()=='100,00 ₽';assert g.records.index(0,3).data()=='24.10.2026';g.sortByColumn(1,Qt.SortOrder.AscendingOrder);assert g.proxy.index(0,0).data()=='А'
 for col in (1,2):assert not g.isColumnHidden(col) and g.columnViewportPosition(col)+g.columnWidth(col)<=g.viewport().width()
 assert '24.10.2026' in g.records.index(0,0).data(Qt.ItemDataRole.ToolTipRole);g.close()

def test_draft_total_order_and_cancel_keep_saved_data(ui,monkeypatch):
 app,w,sui,ids,_=ui;r=ids['repair'];before=sui.store.snapshot(r)['preliminary_draft'];e=RepairDialog(sui,sui.store.snapshot(r));d=DraftDialog(e);d.show();d.lines=normalize_lines([{'kind':'work','name':'Первая','price':'7000'},{'kind':'delivery','name':'Вторая','price':'500'}]);d.changed();d.install();d.grid.selectRow(1);d.move(-1);assert [x['name'] for x in d.lines]==['Вторая','Первая'];assert '7 500,00 ₽' in d.total_label.text();d.discount.setText('100');assert '7 400,00 ₽' in d.total_label.text()
 monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Cancel);d.reject();assert d.isVisible() and d.dirty;assert sui.store.snapshot(r)['preliminary_draft']==before
 monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Discard);d.reject();assert not d.isVisible();assert sui.store.snapshot(r)['preliminary_draft']==before;e.accept()

def test_revision_conflict_preserves_unsaved_fields_and_error_state(ui):
 app,w,sui,ids,messages=ui;e=RepairDialog(sui,sui.store.snapshot(ids['repair']));sui.dialogs.append(e);e.show();e.fields['defects'].setPlainText('Несохранённая учебная правка');sui.store.save_repair(e.key,{'defects':'Другая сохранённая правка'},e.revision);e.save_button.click();idle(app,sui);assert e.dirty and 'Не сохранено' in e.dirty_label.text();assert e.fields['defects'].toPlainText()=='Несохранённая учебная правка';assert sui.store.snapshot(e.key)['repair']['defects']=='Другая сохранённая правка';assert messages and 'изменена' in messages[-1];e.dirty=False;e.accept();sui.dialogs.remove(e)

def test_internal_exception_visible_without_raw_details(ui):
 app,w,sui,ids,messages=ui;completed=[]
 def failure():raise RuntimeError('SYNTHETIC_INTERNAL_TRACEBACK_MARKER')
 sui.run(failure,lambda _:completed.append(True));idle(app,sui);assert not completed and messages and 'диагностике' in messages[-1];assert 'SYNTHETIC_INTERNAL_TRACEBACK_MARKER' not in sui.message.text()

def test_client_archive_filter_independent(ui):
 app,w,sui,ids,_=ui;key=sui.store.save_client({'name':'Учебный архивный клиент'});sui.store.archive('clients',key);sui.refresh();idle(app,sui);assert key not in {x['id'] for x in sui.cache['clients']};sui.clients_archived.setChecked(True);idle(app,sui);assert key in {x['id'] for x in sui.cache['clients']} and not sui.archived.isChecked()

def test_user_width_persists(ui,tmp_path):
 app,w,sui,ids,_=ui;key='synthetic-test-'+tmp_path.name;settings=QSettings('DocFlowLite','Interface')
 try:
  a=Grid([('name','Название'),('total','Стоимость')],settings_key=key);a.resize(800,300);a.show();app.processEvents();a.horizontalHeader().resizeSection(1,180);a.close();settings.sync();b=Grid([('name','Название'),('total','Стоимость')],settings_key=key);b.resize(800,300);b.show();app.processEvents();assert b.columnWidth(1)==180;b.close()
 finally:settings.remove('columns/'+key)

def test_local_dates_and_localized_search_excludes_ids(ui):
 app,w,sui,ids,_=ui;e=RepairDialog(sui,sui.store.snapshot(ids['repair']));sui.dialogs.append(e);e.fields['received_at'].setText('24.10.2026');e.save();idle(app,sui);assert sui.store.snapshot(e.key)['repair']['received_at']=='2026-10-24';assert e.fields['received_at'].text()=='24.10.2026';e.accept();sui.dialogs.remove(e)
 g=Grid([('number','Ремонт'),('state','Отметка')]);g.install([{'id':'900-private-id','number':'100','state':'prepared'}]);g.proxy.setFilterFixedString('Подготовлена');assert g.proxy.rowCount()==1;g.proxy.setFilterFixedString('900');assert g.proxy.rowCount()==0


def test_empty_dashboard_keeps_compact_metrics_and_working_actions(ui,tmp_path):
 app,w,sui,ids,_=ui
 empty=MainWindow(service_root=tmp_path/'Empty synthetic');empty.resize(1366,768);empty.show();empty.navigate(5);panel=empty.service_workspace;idle(app,panel);app.processEvents()
 assert panel.dashboard.empty.isVisible() and not panel.dashboard.recent.isVisible()
 assert all(card.height()<=90 for card in panel.dashboard.cards)
 assert panel.dashboard.new_button.isVisible() and panel.dashboard.new_button.isEnabled()
 empty.close();app.processEvents()


def test_short_input_form_keeps_fields_at_top(ui):
 from docflow.ui.service.forms import FieldsDialog
 app,w,sui,ids,_=ui
 d=FieldsDialog('Учебный ввод',[('name','Название *','text'),('notes','Примечания','long')],parent=sui);d.resize(1020,680);d.show();app.processEvents()
 assert d.fields['name'].mapTo(d,QPoint(0,0)).y()<70
 d.reject()


def test_history_follows_selected_dates_until_user_sorts(ui):
 from docflow.ui.service.history import HistoryDialog
 app,w,sui,ids,_=ui
 sui.store.save_repair(ids['first_repair'],{'received_at':'2023-01-01'})
 sui.store.save_repair(ids['repair'],{'received_at':'2026-01-01'})
 equipment=sui.cache['active_equipment'][0];d=HistoryDialog(sui,equipment);sui.dialogs.append(d);d.show();idle(app,sui)
 assert d.grid.proxy.index(0,0).data()=='DEMO-R-001'
 d.order.setCurrentIndex(1);idle(app,sui)
 assert d.grid.proxy.index(0,0).data()=='DEMO-R-002'
 d.accept();sui.dialogs.remove(d)


def test_history_wizard_footer_uses_shared_dark_theme(ui):
 from PySide6.QtWidgets import QWizard
 from docflow.ui.service.import_wizard import HistoryWizard
 app,w,sui,ids,_=ui;d=HistoryWizard(sui);sui.dialogs.append(d);d.show();app.processEvents()
 assert d.wizardStyle()==QWizard.WizardStyle.ClassicStyle
 capture=d.grab();ratio=capture.devicePixelRatio();color=capture.toImage().pixelColor(round(8*ratio),round((d.height()-8)*ratio))
 assert max(color.red(),color.green(),color.blue())<70,color.name()
 d.reject();sui.dialogs.remove(d)


def test_context_navigation_preserves_core_and_service_state(ui):
 app,w,sui,ids,_=ui
 assert w.mode_picker.currentIndex()==1 and all(b.isHidden() for b in w.nav_buttons)
 assert not sui.tabs.tabBar().isVisible() and not sui.section_picker.isVisible()
 for i,b in enumerate(w.service_nav):
  b.click();app.processEvents();assert sui.tabs.currentIndex()==i and b.isChecked()
 assert 'Настройки' in w.title.text()
 w.mode_picker.setCurrentIndex(0);w.load_demo()
 from docflow.release_check import wait_idle
 wait_idle(w);table=w.table
 w.mode_picker.setCurrentIndex(1);app.processEvents();assert w.service_workspace is sui and sui.tabs.currentIndex()==7
 w.mode_picker.setCurrentIndex(0);assert w.table is table


def test_preferences_failure_keeps_session_width_and_explains(ui,monkeypatch):
 from docflow.ui.service import widgets
 app,*_=ui
 monkeypatch.setattr(widgets,'save_widths',lambda *args:False)
 grid=Grid([('name','Название'),('total','Стоимость')],settings_key='failure-case')
 grid.resize(800,300);grid.show();app.processEvents();grid.horizontalHeader().resizeSection(1,180)
 assert grid._user_widths[1]==180 and grid.preferences_saved is False
 assert 'Не удалось сохранить' in grid.horizontalHeader().toolTip()
 grid.close()


def test_narrow_finance_keeps_all_money_columns_visible(ui):
 app,*_=ui
 grid=Grid([('number','Ремонт №'),('client','Клиент'),('status','Статус'),('total','Стоимость'),('paid','Учтено'),('balance','Остаток'),('financial_status','Расчёты')])
 grid.resize(600,260);grid.show();grid.install([{'number':'1','client':'Учебный клиент','status':'repair','total':170050,'paid':100000,'balance':70050}]);app.processEvents();grid.fit_columns();app.processEvents()
 for i in (3,4,5):assert not grid.isColumnHidden(i) and grid.columnViewportPosition(i)+grid.columnWidth(i)<=grid.viewport().width()
 grid.close()
