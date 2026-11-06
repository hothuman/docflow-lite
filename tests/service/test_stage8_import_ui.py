import time
import pytest
from PySide6.QtWidgets import QWizard,QMessageBox
from docflow.gui import MainWindow
from docflow.ui.service.import_wizard import HistoryWizard
from docflow.service.validation import ServiceError


def idle(ui,app):
    end=time.monotonic()+20
    while ui.worker or ui._pending_refresh or ui._project_busy:
        app.processEvents();time.sleep(.005);assert time.monotonic()<end
    app.processEvents()


@pytest.fixture
def wizard(tmp_path,qt_application_lifetime):
    app=qt_application_lifetime;w=MainWindow(service_root=tmp_path/'project');w.show();w.navigate(5)
    ui=w.service_workspace;idle(ui,app);d=HistoryWizard(ui);ui.dialogs.append(d);d.show()
    yield d,ui,app
    idle(ui,app);d.reject();ui.dialogs.remove(d);w.close()


def test_csv_encoding_mapping_back_and_undo_keep_user_choices(wizard,tmp_path):
    d,ui,app=wizard;p=tmp_path/'journal.csv';p.write_bytes('Номер обращения;Дата приема;Постоянный номер;Модель;Клиент\nR1;06.11.2026;0007;Насос;QA\n'.encode('cp1251'))
    d.path.setText(str(p));d.encoding.setCurrentIndex(d.encoding.findData('cp1251'));d.next();idle(ui,app)
    assert d.currentId()==1 and d.mapping()['repair_number']=='Номер обращения' and d.table.records[0].values['Модель']=='Насос'
    d.mappings['client_name'].setCurrentIndex(0);d.propose();assert d.mapping()['client_name']=='Клиент'
    d.undo_mapping();assert 'client_name' not in d.mapping()
    d.back();d.next();idle(ui,app)
    assert d.currentId()==1 and 'client_name' not in d.mapping() and d.encoding.currentData()=='cp1251'
    assert ui.store.repairs()==[]


def test_cancel_control_stays_available_and_retry_preserves_input(wizard,monkeypatch):
    d,ui,app=wizard;errors=[];monkeypatch.setattr(QMessageBox,'warning',lambda *a:errors.append(a[-1]))
    d.path.setText('QA preserve selected file')
    def task():
        end=time.monotonic()+5
        while not d.cancel_event.is_set() and time.monotonic()<end:time.sleep(.005)
        if d.cancel_event.is_set():raise ServiceError('Импорт отменён')
        raise AssertionError('Cancel did not arrive')
    assert d.run_operation(task)
    assert d.isEnabled() and d.button(QWizard.WizardButton.CancelButton).isEnabled() and not d.currentPage().isEnabled()
    d.reject();assert d.isVisible() and d.cancel_event.is_set()
    idle(ui,app);assert d.isVisible() and d.path.text()=='QA preserve selected file' and d.currentPage().isEnabled()
    assert errors and not ui.store.repairs()
