from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_stage1_upgrade_copy import app,idle,dispose
from docflow.ui.service.workspace import ServiceWorkspace
from docflow.ui.service.intake import IntakeDialog
from docflow.ui.service.repair_editor import RepairDialog
from docflow.service.stage2_check import run

def test_five_business_routes_and_backup_restore(tmp_path):
    assert run(tmp_path/'five-real-routes')==0

def test_intake_required_fields_and_cancel_do_not_write(app,tmp_path,monkeypatch):
    workspace=ServiceWorkspace(root=tmp_path/'project');idle(app,workspace)
    try:
        dialog=IntakeDialog(workspace);dialog.show();dialog.submit.click();app.processEvents()
        assert 'Заполните' in dialog.note.text() and not workspace.store.clients()
        dialog.name.setText('Not saved')
        import docflow.ui.service.widgets as widgets
        monkeypatch.setattr(widgets,'confirm',lambda *args:False);dialog.reject();assert dialog.isVisible()
        monkeypatch.setattr(widgets,'confirm',lambda *args:True);dialog.reject();assert not dialog.isVisible()
        assert not workspace.store.clients() and not workspace.store.equipment() and not workspace.store.repairs()
    finally:dispose(app,workspace)

def test_step_navigation_and_keyboard_save_preserve_unsaved_input(app,tmp_path):
    workspace=ServiceWorkspace(root=tmp_path/'project');idle(app,workspace)
    try:
        key=workspace.store.intake(client={'name':'Synthetic'},equipment={'number':'1','model':'Synthetic'})
        editor=RepairDialog(workspace,workspace.store.snapshot(key));workspace.dialogs.append(editor);editor.show()
        editor.fields['complaint'].setPlainText('Длинная учебная жалоба\n'+ 'Строка '*100)
        for i in range(5):editor.tabs.setCurrentIndex(i);app.processEvents()
        assert editor.dirty and 'Длинная' in editor.fields['complaint'].toPlainText()
        QTest.keyClick(editor,Qt.Key.Key_S,Qt.KeyboardModifier.ControlModifier);idle(app,workspace)
        assert not editor.dirty and 'Длинная' in workspace.store.snapshot(key)['repair']['complaint']
        assert [editor.tabs.tabText(i) for i in range(5)]==['Приёмка','Диагностика','Смета','Работы','Выдача']
        editor.accept();workspace.dialogs.remove(editor)
    finally:dispose(app,workspace)


def test_compact_estimates_keep_total_and_repair_number_visible(app):
    from docflow.ui.service.widgets import Grid
    grid=Grid([('number','Ремонт №'),('client','Клиент'),('kind','Смета'),('version','Версия'),('state','Ручная отметка'),('total','Итог')])
    grid.resize(340,200);grid.install([{'number':'1000','client':'Учебный клиент','kind':'preliminary','version':1,'state':'approved','total':120000}]);grid.show();app.processEvents();grid.fit_columns();app.processEvents()
    for column in (0,5):assert not grid.isColumnHidden(column) and grid.columnViewportPosition(column)+grid.columnWidth(column)<=grid.viewport().width()
    grid.close()
