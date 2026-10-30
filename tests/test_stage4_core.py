from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from docflow.gui import MainWindow
from docflow.release_check import wait_idle

def test_full_check_is_not_inferred_from_mapping_or_preview(tmp_path):
    w=MainWindow();w.show();w.load_demo();wait_idle(w)
    try:
        assert not w.route_buttons[2].property('complete')
        w.row_selector.setCurrentIndex(1);wait_idle(w);assert not w.route_buttons[2].property('complete')
        w.check_all();wait_idle(w);assert w.route_buttons[2].property('complete') and 'Все 3 строк' in w.mapping_feedback.text()
        w.mapping_table.cellWidget(0,3).setChecked(False);wait_idle(w);assert not w.route_buttons[2].property('complete')
        w.output_path.setText(str(tmp_path/'results'));w.start_generation();wait_idle(w)
        assert w.last_result.documents==4 and w.route_buttons[2].property('complete')
        assert w._full_check[1:]==(1,3) and 'Строка' in w.validation_report.toPlainText()
    finally:w.close()

def test_mode_keyboard_remembers_pages_and_preserves_core_input(tmp_path):
    from tests.service.test_stage1_upgrade_copy import idle
    w=MainWindow(service_root=tmp_path/'p');w.show();w.load_demo();wait_idle(w);w.navigate(2);table=w.table
    try:
        QTest.keyClick(w.mode_picker.buttons[0],Qt.Key.Key_Right);idle(QApplication.instance(),w.service_workspace)
        assert w.mode_picker.currentIndex()==1;w.service_workspace.tabs.setCurrentIndex(7)
        QTest.keyClick(w.mode_picker.buttons[1],Qt.Key.Key_Left);assert w.pages.currentIndex()==2 and w.table is table
        w.mode_picker.setCurrentIndex(1);assert w.service_workspace.tabs.currentIndex()==7
        w.close();again=MainWindow(service_root=tmp_path/'p');again.show();idle(QApplication.instance(),again.service_workspace)
        assert again.mode_picker.currentIndex()==1 and again.service_workspace.tabs.currentIndex()==7;again.close()
    finally:w.close()

def test_busy_mode_switch_is_blocked_without_losing_data(tmp_path):
    w=MainWindow(service_root=tmp_path/'p');w.show();w.load_demo();wait_idle(w);table=w.table
    try:
        w.set_busy(True);w.mode_picker.setCurrentIndex(1)
        assert w.pages.currentIndex()==0 and w.mode_picker.currentIndex()==0 and w.table is table
        assert 'Дождитесь' in w.status.text()
        w.set_busy(False);w.mode_picker.setCurrentIndex(1)
        from tests.service.test_stage1_upgrade_copy import idle
        idle(QApplication.instance(),w.service_workspace);assert w.pages.currentIndex()==5
    finally:w.set_busy(False);w.close()
