
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from docflow.service.repository import ServiceStore
from docflow.ui.service.widgets import confirm
from docflow.ui.window import MainWindow
from docflow.ui.settings import preferences
from test_stage9_cp3_journal import wait_idle


def test_confirmation_has_russian_action_and_cancel_default(qt_application_lifetime):
    captured = []

    def dismiss():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        yes = dialog.button(QMessageBox.StandardButton.Yes)
        no = dialog.button(QMessageBox.StandardButton.No)
        captured.append((yes.text(), no.text(), dialog.defaultButton() is no))
        no.click()

    QTimer.singleShot(0, dismiss)
    assert not confirm(None, 'Продолжить?', 'Выдать аппарат')
    assert captured == [('Выдать аппарат', 'Отмена', True)]


def test_repair_id_and_sort_are_restored_per_project(tmp_path):
    root = tmp_path / 'project'
    store = ServiceStore(root)
    owner = store.save_client({'name':'Учебный заказчик'})
    device = store.save_equipment({'owner_id':owner,'number':'0007','model':'Учебный насос'})
    repair = store.create_repair(device,'QA-ONE','Осмотр')
    store.create_repair(device,'QA-TWO','Повторная диагностика')
    settings = preferences()
    settings.setValue('workspace/v2/mode', 1)
    settings.setValue('workspace/v2/workshop', 2)
    settings.sync()

    window = MainWindow(service_root=root)
    window.show()
    wait_idle(window)
    journal = window.service_workspace.journal
    journal.grid.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    journal.search.setText('QA-ONE')
    journal.grid.selectRow(0)
    assert journal.grid.selected()['id'] == repair
    assert 'QA-ONE' in journal.selected_summary.text()
    window.close()

    reopened = MainWindow(service_root=root)
    reopened.show()
    try:
        wait_idle(reopened)
        QApplication.processEvents()
        view = reopened.service_workspace.journal
        assert view.search.text() == ''
        assert view.grid.selected()['id'] == repair
        assert view.grid.horizontalHeader().sortIndicatorSection() == 0
        assert view.grid.horizontalHeader().sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
        assert 'QA-ONE' in view.selected_summary.text()
    finally:
        reopened.close()
