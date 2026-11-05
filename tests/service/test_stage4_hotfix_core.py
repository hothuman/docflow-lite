"""Behavioural regressions from the independent rc7 audit, not pixel snapshots."""
import pytest
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QMessageBox
from PySide6.QtTest import QTest
from test_stage1_upgrade_copy import app,idle,dispose
from docflow.ui.service.workspace import ServiceWorkspace
from docflow.ui.service.forms import FieldsDialog
from docflow.ui.service.intake import IntakeDialog
from docflow.ui.service.catalog import CatalogDialog

def test_core_error_is_scoped_to_mode_and_cleared_by_success(app,tmp_path):
    from docflow.gui import MainWindow
    from types import SimpleNamespace
    w=MainWindow(service_root=tmp_path/'p');w.show()
    try:
        w.error('QA old Core failure');assert w.operation_notice.isVisible()
        w.navigate(5);idle(app,w.service_workspace);assert not w.operation_notice.isVisible()
        w.navigate(0);w.error('QA retry failed');w.on_result(SimpleNamespace(total=3,documents=4,accepted=2,rejected=1,directory=tmp_path,issues=[]));app.processEvents()
        assert not w.operation_notice.isVisible() and 'QA retry failed' not in w.status.text()
    finally:
        if w.service_workspace:idle(app,w.service_workspace)
        w.close();app.processEvents()
