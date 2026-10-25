"""Qt application lifetime and GUI-thread destruction between regression cases."""
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
 for widget in QApplication.topLevelWidgets():
  if isinstance(widget,(QDialog,QMainWindow)) and not widget.isVisible():
   if not any(thread.isRunning() for thread in widget.findChildren(QThread)):widget.deleteLater()
 QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);qt_application_lifetime.processEvents()

@pytest.fixture(autouse=True)
def isolate_interface_preferences(tmp_path,monkeypatch):
 """Never write a developer's settings or require registry access for tests."""
 monkeypatch.setenv('DOCFLOW_SETTINGS_DIR',str(tmp_path/'interface-preferences'))
