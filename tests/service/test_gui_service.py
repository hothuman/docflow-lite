import json,time
import pytest
from PySide6.QtWidgets import QApplication, QPushButton
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

def test_actual_qt_service_and_core_workflow(app,tmp_path,monkeypatch):
 from PySide6.QtCore import QThread
 from docflow.service.self_test import run
 from docflow.ui.service.forms import FieldsDialog
 original=FieldsDialog.values
 def values_on_gui_thread(dialog):
  assert QThread.currentThread()==app.thread()
  return original(dialog)
 monkeypatch.setattr(FieldsDialog,'values',values_on_gui_thread)
 result=run(tmp_path/'native-qt-workflow')
 proof=json.loads((tmp_path/'native-qt-workflow/SERVICE-SELF-TEST.json').read_text())
 assert result==0,proof.get('traceback',proof)
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



@pytest.mark.parametrize('opened', [False, True])
def test_settings_keep_a_usable_category_viewport_in_short_window(app, tmp_path, opened):
    w = MainWindow(service_root=tmp_path / 'settings' if opened else None)
    w.resize(560, 320)
    w.show()
    w.navigate(5)
    ui = w.service_workspace
    try:
        idle(app, ui)
        assert (ui.store is not None) == opened
        w._navigate_service(ui.tabs.indexOf(ui.settings_page))
        idle(app, ui)
        settings = ui.settings_page
        assert settings.category.isVisible()
        assert ui.section_picker.isVisible()
        viewport = settings.pages.currentWidget().viewport()
        assert viewport.height() >= 100, viewport.height()

        if not opened:
            actions = settings.pages.currentWidget().findChildren(QPushButton)
            project = next(button for button in actions if button.text() == 'Открыть проект')
            assert project.isEnabled()
            assert any(button.text() == 'Восстановить копию' and button.isEnabled()
                       for button in actions)
            assert not ui.project_actions.isVisible()

        # Leaving Settings must expose the original first-run commands again.
        ui.section_picker.setCurrentIndex(0)
        idle(app, ui)
        assert ui.tabs.currentWidget() is ui.dashboard
        assert ui.project_actions.isVisible() != opened
        assert w.compact_settings.isVisible()
    finally:
        w.close()
        app.processEvents()
