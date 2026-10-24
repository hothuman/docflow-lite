import json,time
import pytest
from PySide6.QtWidgets import QApplication
from docflow.gui import MainWindow
from docflow.service.demo import seed_demo
from docflow.ui.service.repair_editor import RepairDialog

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])

def idle(app,workspace):
 deadline=time.monotonic()+15
 while workspace.worker or workspace._pending_refresh:
  app.processEvents();time.sleep(.005)
  assert time.monotonic()<deadline
 app.processEvents()

def test_actual_qt_service_and_core_workflow(app,tmp_path):
 from docflow.service.self_test import run
 assert run(tmp_path/'native-qt-workflow')==0
 proof=json.loads((tmp_path/'native-qt-workflow/SERVICE-SELF-TEST.json').read_text())
 assert proof['status']=='passed' and len(proof['checks'])==9

def test_editor_saves_real_changes_with_revision(app,tmp_path):
 root=tmp_path/'editor';ids=seed_demo(root);w=MainWindow(service_root=root);w.navigate(5);sui=w.service_workspace;idle(app,sui)
 d=RepairDialog(sui,sui.store.snapshot(ids['repair']));sui.dialogs.append(d)
 d.fields['defects'].setPlainText('Новая вымышленная дефектовка')
 assert d.dirty;d.save_button.click();idle(app,sui)
 assert not d.dirty and sui.store.snapshot(ids['repair'])['repair']['defects']=='Новая вымышленная дефектовка'
 d.accept();sui.dialogs.remove(d);w.close();app.processEvents()

@pytest.mark.parametrize('size',[(560,320),(800,600),(1024,640),(1280,720),(1366,768),(1920,1080)])
def test_service_window_remains_resizable(app,tmp_path,size):
 w=MainWindow(service_root=tmp_path/'resize');w.navigate(5);w.show();idle(app,w.service_workspace)
 w.resize(*size);app.processEvents()
 assert w.width()<=size[0] and w.height()<=size[1]
 assert w.service_workspace.tabs.isVisible() and w.pages.currentIndex()==5
 w.close();app.processEvents()
