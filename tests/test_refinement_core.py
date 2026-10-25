"""CP2: real interactive persistence and current-run result truthfulness."""
import threading
import time
import pytest
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QFileDialog
from docflow.gui import MainWindow
from docflow.profile import Profile
from docflow.cli import demo_profile
from docflow.release_check import wait_idle
from docflow.errors import DocFlowError
from docflow.ui import window as core

@pytest.fixture
def ui():
 app=QApplication.instance() or QApplication([])
 w=MainWindow();w.show();w.load_demo();wait_idle(w)
 yield app,w
 wait_idle(w);w.close();app.processEvents()

def test_profile_button_saves_off_thread_and_reports_only_after_commit(ui,tmp_path,monkeypatch):
 app,w=ui;target=tmp_path/'Профиль с пробелами.json'
 entered=threading.Event();release=threading.Event();original=Profile.save
 def slow(profile,path):
  entered.set()
  if not release.wait(4):raise RuntimeError('test gate')
  return original(profile,path)
 monkeypatch.setattr(Profile,'save',slow)
 monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(target),''))
 ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(5)
 w.save_profile_btn.click()
 end=time.monotonic()+3
 while not entered.is_set() or len(ticks)<4:
  app.processEvents();time.sleep(.005);assert time.monotonic()<end
 assert w._busy and not target.exists() and 'сохранён' not in w.status.text()
 release.set();wait_idle(w);timer.stop()
 assert Profile.load(target).mapping==w.mapping()[0] and 'сохранён' in w.status.text()

def test_new_failed_generation_does_not_show_old_success(ui,tmp_path,monkeypatch):
 app,w=ui;w.output_path.setText(str(tmp_path));w.start_generation();wait_idle(w)
 old=w.last_result;assert old.documents==4
 def fail(*a,**kw):raise DocFlowError('Диск недоступен')
 monkeypatch.setattr(core,'generate',fail)
 w.start_generation();wait_idle(w)
 assert w.last_result is None and not w.result_open_btn.isEnabled()
 assert 'Готово:' not in w.result_summary.text() and 'Диск недоступен' in w.status.text()
 assert len(list(old.directory.rglob('*.docx')))==4

@pytest.mark.parametrize('extension',['csv','xlsx'])
def test_one_valid_record_roundtrip_through_real_core_ui(ui,tmp_path,extension):
 from openpyxl import Workbook
 import csv
 app,w=ui;demo=Profile.load(demo_profile());record=w.table.records[0];headers=w.table.headers
 data=tmp_path/('Одна запись.'+extension)
 if extension=='xlsx':
  book=Workbook();book.active.append(list(headers));book.active.append([record.values[h] for h in headers]);book.save(data);book.close()
 else:
  with data.open('w',encoding='utf-8-sig',newline='') as f:
   writer=csv.writer(f,delimiter=';');writer.writerow(headers);writer.writerow([record.values[h] for h in headers])
 w.apply_profile(Profile(data,demo.templates,demo.mapping,demo.rules,demo.name_column));wait_idle(w)
 w.output_path.setText(str(tmp_path/'Результат'));QTest.mouseClick(w.generate_btn,Qt.MouseButton.LeftButton);wait_idle(w)
 assert (w.last_result.total,w.last_result.accepted,w.last_result.documents)==(1,1,2)
 assert len(list(w.last_result.directory.rglob('*.docx')))==2
