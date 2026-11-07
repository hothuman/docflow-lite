
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from docflow.service.repository import ServiceStore
from docflow.ui.window import MainWindow
from test_stage9_cp3_journal import wait_idle


def test_modeless_history_returns_from_repair_and_releases_old_project(tmp_path,monkeypatch):
    root=tmp_path/'original'
    store=ServiceStore(root)
    repair=store.intake(client={'name':'Учебный клиент'},equipment={'number':'0007','model':'Насос'},
                        complaint='Падает давление')
    window=MainWindow(service_root=root);window.show();window.navigate(5)
    try:
        wait_idle(window)
        workspace=window.service_workspace
        workspace.show_history(workspace.store.equipment()[0])
        wait_idle(window)
        history=workspace.history_window
        assert history.isVisible() and not history.isModal()
        history.search.setText('давление')
        history.grid.selectRow(0)
        assert history.grid.selected()['id']==repair

        from docflow.ui.service import workspace as implementation
        original=implementation.RepairDialog
        opened=[]
        def capture(parent,snapshot):
            dialog=original(parent,snapshot)
            opened.append(snapshot['repair']['id'])
            QTimer.singleShot(0,dialog.reject)
            return dialog
        monkeypatch.setattr(implementation,'RepairDialog',capture)
        history.open()
        wait_idle(window);QApplication.processEvents();wait_idle(window)
        assert opened==[repair]
        restored=workspace.history_window
        assert restored is not None and restored is not history
        assert restored.search.text()=='давление'
        assert restored.grid.selected()['id']==repair
        workspace.open_project(tmp_path/'other')
        wait_idle(window)
        assert workspace.history_window is None
        assert workspace.store.root.name=='other'
    finally:
        window.close()
