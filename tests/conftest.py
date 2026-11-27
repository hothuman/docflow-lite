"""Qt application lifetime and GUI-thread destruction between regression cases."""
import gc
import os
import pytest
@pytest.fixture(scope='session',autouse=True)
def qt_application_lifetime():
 os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
 from PySide6.QtWidgets import QApplication
 app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
 yield app
 app.processEvents()
@pytest.fixture(autouse=True)
def release_closed_qt_windows(qt_application_lifetime):
 yield
 from PySide6.QtCore import QCoreApplication,QEvent,QThread
 from PySide6.QtWidgets import QApplication,QDialog,QMainWindow
 # Some editors defer accepting close() until their route has unwound.
 qt_application_lifetime.processEvents()
 retired = False
 for widget in QApplication.topLevelWidgets():
  if isinstance(widget,(QDialog,QMainWindow)) and not widget.isVisible():
   if not any(thread.isRunning() for thread in widget.findChildren(QThread)):
    widget.deleteLater()
    retired = True
 QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);qt_application_lifetime.processEvents()
 if retired:
  # Retire Python cycles from closed Qt windows on the GUI thread. The
  # next case may otherwise first trigger collection while a worker runs.
  gc.collect()

@pytest.fixture(autouse=True)
def isolate_interface_preferences(tmp_path_factory,monkeypatch):
 """Never write a developer's settings or require registry access for tests."""
 monkeypatch.setenv('DOCFLOW_SETTINGS_DIR',str(tmp_path_factory.mktemp('interface-preferences')))
