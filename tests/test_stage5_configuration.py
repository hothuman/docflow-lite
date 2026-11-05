import hashlib
import pytest
from PySide6.QtWidgets import QFileDialog
from docflow.matching import suggestions
from docflow.gui import MainWindow
from docflow.release_check import wait_idle
from docflow.profile import Profile


@pytest.mark.parametrize('field,headers,expected',[
    ('client',['Заказчик'],'Заказчик'),('amount',['Сумма'],'Сумма'),
    ('invoice_no',['Invoice No'],'Invoice No'),('email',['Электронная почта'],'Электронная почта'),
    ('Серийный_номер',['серийный номер'],'серийный номер'),
    ('client',['Клиент','Заказчик'],None),('amount',['Amount','AMOUNT'],None),
    ('client',['client','Client'],'client'),('odd',['Другой'],None),
    ('номер_счёта',['Номер счета'],'Номер счета'),
])
def test_suggestion_is_unique_and_deterministic(field,headers,expected):
    choices,candidates=suggestions([field],headers)
    assert choices.get(field)==expected
    assert (choices,candidates)==suggestions([field],headers)


@pytest.fixture
def window(tmp_path,qt_application_lifetime):
    w=MainWindow(service_root=tmp_path/'project');w.show();w.load_demo();wait_idle(w)
    yield w
    wait_idle(w);w.close()


def row(w,field):return next(i for i in range(w.mapping_table.rowCount()) if w.mapping_table.item(i,0).text()==field)


def test_manual_blank_restore_and_redo_preserve_rules_and_preview(window):
    w=window;w.navigate(2);i=row(w,'client');combo=w.mapping_table.cellWidget(i,1)
    before=w.mapping();combo.setCurrentIndex(0);wait_idle(w)
    assert 'client' not in w.mapping()[0] and 'client' in w.config_message.text()
    assert w.config_preview.toPlainText()==w.preview_text.toPlainText()
    w.restore_config_btn.click();wait_idle(w);assert w.mapping()==before
    w.restore_config_btn.click();wait_idle(w);assert 'client' not in w.mapping()[0]


def test_suggestions_fill_blank_without_overwriting_manual_choice(window):
    w=window;i=row(w,'client');w.mapping_table.cellWidget(i,1).setCurrentIndex(0)
    j=row(w,'amount');w.mapping_table.cellWidget(j,1).setCurrentText('Клиент')
    w.suggest_config_btn.click();wait_idle(w)
    assert w.mapping()[0]['client']=='Клиент' and w.mapping()[0]['amount']=='Клиент'
    w.restore_config_btn.click();wait_idle(w)
    assert 'client' not in w.mapping()[0] and w.mapping()[0]['amount']=='Клиент'


def test_old_v1_profile_roundtrip_restore_and_failed_load_keep_work(window,tmp_path,monkeypatch):
    w=window;before=w.profile();path=tmp_path/'profile.json';before.save(path)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    w.mapping_table.cellWidget(row(w,'client'),1).setCurrentIndex(0);wait_idle(w)
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(path),''))
    w.open_profile();wait_idle(w);assert w.profile()==before
    w.restore_config_btn.click();wait_idle(w);assert 'client' not in w.mapping()[0]
    bad=tmp_path/'broken.json';bad.write_text('{}',encoding='utf-8')
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(bad),''))
    current=w.mapping();w.open_profile();wait_idle(w);assert w.mapping()==current
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest


def test_ambiguous_headers_remain_blank_and_validate_blocks_generation(window,tmp_path):
    w=window;source=tmp_path/'ambiguous.csv';source.write_text('Клиент;Заказчик\nQA One;QA Two\n',encoding='utf-8')
    w._mapping_cache={};w._rules_cache={};w._load_data(source);wait_idle(w)
    w.mapping_table.cellWidget(row(w,'client'),1).setCurrentIndex(0);wait_idle(w)
    w.suggest_config_btn.click();wait_idle(w)
    assert 'client' not in w.mapping()[0] and 'client' in w.config_message.text()
    w.navigate(3);assert not w.generate_btn.isEnabled()


def test_controls_disabled_during_operation_and_undo_preserves_output(window,tmp_path):
    w=window;w.navigate(3);w.output_path.setText(str(tmp_path/'docs'));w.start_generation();wait_idle(w)
    paths=list(w.last_result.directory.rglob('*.docx'));before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    w.navigate(2);w.mapping_table.cellWidget(row(w,'client'),1).setCurrentIndex(0);wait_idle(w)
    w.set_busy(True);assert not w.suggest_config_btn.isEnabled() and not w.restore_config_btn.isEnabled()
    w.set_busy(False);w.restore_config_btn.click();wait_idle(w)
    assert w.profile().mapping['client']=='Клиент'
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p,digest in before.items())
