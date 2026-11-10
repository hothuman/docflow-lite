"""Direct Qt close must not bypass a visible repair dialog or release its lock."""
from PySide6.QtCore import QLockFile, QTimer
from docflow.gui import MainWindow
from docflow.ui.service.repair_editor import RepairDialog
from docflow.release_check import wait_idle


def idle(ui,app):
    import time
    end=time.monotonic()+15
    while ui.worker or ui._pending_refresh or ui._project_busy:
        app.processEvents();time.sleep(.005);assert time.monotonic()<end
    app.processEvents()


def test_direct_owner_close_preserves_modal_draft_and_project_lock(tmp_path,qt_application_lifetime):
    app=qt_application_lifetime;w=MainWindow(service_root=tmp_path/'project');w.show();w.navigate(5)
    ui=w.service_workspace;idle(ui,app)
    key=ui.store.intake(client={'name':'QA Owner'},equipment={'number':'ST7-DIRTY','model':'QA'})
    d=RepairDialog(ui,ui.store.snapshot(key));d.fields['complaint'].setPlainText('QA unsaved text')
    ui.dialogs.append(d);observed={};other=QLockFile(str(ui.store.root/'.docflow-service.lock'))
    def attempt():
        w.close();app.processEvents()
        acquired=other.tryLock(0)
        observed.update(owner=w.isVisible(),dialog=d.isVisible(),dirty=d.dirty,
                        text=d.fields['complaint'].toPlainText(),acquired=acquired)
        if acquired:other.unlock()
        d.dirty=False;d.reject()
    try:
        QTimer.singleShot(50,attempt);d.exec()
        assert observed==dict(owner=True,dialog=True,dirty=True,text='QA unsaved text',acquired=False)
    finally:
        ui.dialogs.remove(d);d.dirty=False;d.close();wait_idle(w);w.close();app.processEvents()
    assert not w.isVisible() and other.tryLock(0)
    other.unlock()


def test_hidden_tracked_dialog_does_not_prevent_normal_close(tmp_path,qt_application_lifetime):
    w=MainWindow(service_root=tmp_path/'project');w.show();w.navigate(5)
    ui=w.service_workspace;idle(ui,qt_application_lifetime)
    key=ui.store.intake(client={'name':'QA'},equipment={'number':'ST7-HIDDEN','model':'QA'})
    d=RepairDialog(ui,ui.store.snapshot(key));ui.dialogs.append(d)
    try:w.close();assert not w.isVisible()
    finally:ui.dialogs.remove(d);d.close();w.close()
