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

@pytest.mark.parametrize('size',[(560,420),(820,620),(1060,740)])
def test_catalog_import_has_no_page_horizontal_overflow(app,tmp_path,size):
    w=ServiceWorkspace(root=tmp_path/'p');idle(app,w);d=CatalogDialog(w);d.tabs.setCurrentIndex(1);d.show();d.resize(*size)
    try:
        app.processEvents();app.processEvents();d.import_scroll.ensureWidgetVisible(d.skip);app.processEvents()
        assert d.import_scroll.horizontalScrollBar().maximum()==0
    finally:d.accept();dispose(app,w)

