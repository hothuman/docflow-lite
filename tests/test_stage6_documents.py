import hashlib,io,zipfile
import pytest
from docx import Document
from docx.shared import Mm
from docx.oxml.ns import qn
from docflow.templates import Template
from docflow.errors import DocFlowError
from docflow.service.documents import create_templates,generate_document,KINDS
from docflow.service.repository import ServiceStore
from docflow.template_diagnostics import configuration_messages
from docflow.gui import MainWindow
from docflow.release_check import wait_idle

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def text(p):
    with zipfile.ZipFile(p) as z:assert z.testzip() is None
    d=Document(p)
    return '\n'.join([p.text for p in d.paragraphs]+[c.text for t in d.tables for r in t.rows for c in r.cells])

@pytest.mark.parametrize('kind',KINDS)
def test_print_family_preserves_fields_and_print_area(tmp_path,kind):
    old=create_templates(tmp_path/'v6',modern=True)[kind]
    new=create_templates(tmp_path/'v7',modern=True,quality=True)[kind]
    assert Template.load(old).fields==Template.load(new).fields
    assert Template.load(new).diagnostics==()
    d=Document(new);s=d.sections[0]
    assert abs(s.page_width-Mm(210))<1000
    for table in d.tables:
        assert sum(c.width for c in table.columns)<=s.page_width-s.left_margin-s.right_margin+1000
        assert table.rows[0]._tr.trPr.find(qn('w:tblHeader')) is not None
        assert all(r._tr.trPr.find(qn('w:trHeight')) is None for r in table.rows)
    for p in d.paragraphs:
        if p.text.startswith(('Проект формы.','Производственный статус:')):assert p.paragraph_format.keep_with_next
    digest=sha(new);create_templates(tmp_path/'v7',modern=True,quality=True);assert sha(new)==digest

@pytest.mark.parametrize('count',[1,12,48,101])
def test_many_rows_exact_text_and_versions(tmp_path,count):
    s=ServiceStore(tmp_path/'p');r=s.intake(client={'name':'QA ООО Клиент / Client'},equipment={'number':'S6-1','model':'QA Машина'})
    old=generate_document(s,r,'completion');digest=sha(old)
    for i in range(count):s.save_item(r,{'kind':'work','name':f'QA Строка {i:03d}','description':'Русский English Unicode ё. '*12,'quantity':'1','price':'1.01'})
    new=generate_document(s,r,'completion');content=text(new)
    assert all(f'QA Строка {i:03d}' in content for i in range(count))
    assert '{{' not in content and 'Русский English Unicode ё.' in content
    assert s.snapshot(r)['totals']['total']==count*101
    assert sha(old)==digest and old!=new and (s.root/'templates/default-v7/completion.docx').exists()
    # Never migrate or rewrite previously present family files.
    v6=create_templates(s.root/'templates/default-v6',modern=True)['completion'];v6sha=sha(v6)
    generate_document(s,r,'completion',template=v6);assert sha(v6)==v6sha

def test_long_single_position_is_not_truncated(tmp_path):
    s=ServiceStore(tmp_path/'p');r=s.intake(client={'name':'QA '*95},equipment={'number':'S6-LONG','model':'QA'})
    description='Проверка очень длинного описания. '*100
    s.save_item(r,{'kind':'work','name':'QA Huge','description':description,'quantity':'1','price':'12.34'})
    content=text(generate_document(s,r,'completion'))
    assert description.strip() in content and s.snapshot(r)['totals']['total']==1234

@pytest.mark.parametrize('broken',['corrupt','missing','external','field'])
def test_invalid_template_then_valid_retry(tmp_path,broken):
    p=tmp_path/'input.docx'
    if broken=='corrupt':p.write_bytes(b'bad DOCX')
    elif broken!='missing':
        d=Document();d.add_paragraph('{{client}}' if broken=='external' else '{{client + 1}}');d.save(p)
        if broken=='external':
            with zipfile.ZipFile(p) as z:entries={n:z.read(n) for n in z.namelist()}
            entries['word/_rels/document.xml.rels']=entries['word/_rels/document.xml.rels'].replace(b'</Relationships>',b'<Relationship Id="bad" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="https://example.invalid/image.png" TargetMode="External"/></Relationships>')
            with zipfile.ZipFile(p,'w') as z:
                for n,b in entries.items():z.writestr(n,b)
    with pytest.raises(DocFlowError):Template.load(p)
    d=Document();d.add_paragraph('{{client}}');d.save(p);digest=sha(p);t=Template.load(p)
    assert 'Первый' in Document(io.BytesIO(t.render({'client':'Первый'}))).paragraphs[0].text
    assert 'Второй' in Document(io.BytesIO(t.render({'client':'Второй'}))).paragraphs[0].text
    assert sha(p)==digest

def test_advisory_diagnostics_do_not_block_multiple_tables_or_wide_layout(tmp_path):
    p=tmp_path/'wide.docx';d=Document();d.add_paragraph('{{client}}')
    for i in range(2):
        t=d.add_table(rows=12,cols=2)
        for col in t.columns:col.width=Mm(150)
        t.cell(0,0).text='Заголовок';t.cell(1,1).text='{{client}}'
    d.save(p);digest=sha(p);t=Template.load(p)
    assert {'table_width','table_header'}<={f.code for f in t.diagnostics}
    data=t.render({'client':'QA 客户 / Клиент'});assert '{{' not in text(io.BytesIO(data))
    assert sha(p)==digest

def test_diagnostics_preserve_stage5_work_and_refresh_messages(tmp_path,qt_application_lifetime):
    w=MainWindow(service_root=tmp_path/'project');w.show();w.load_demo();wait_idle(w);w.navigate(2)
    try:
        row=next(i for i in range(w.mapping_table.rowCount()) if w.mapping_table.item(i,0).text()=='client')
        before=w.mapping();w.mapping_table.cellWidget(row,1).setCurrentIndex(0);wait_idle(w)
        w.diagnose_templates_btn.click();assert 'Поле «client» не связано' in w.template_diagnostics.toPlainText()
        w.restore_config_btn.click();wait_idle(w)
        assert w.mapping()==before and 'Поле «client» не связано' not in w.template_diagnostics.toPlainText()
        w.set_busy(True);assert not w.diagnose_templates_btn.isEnabled();w.set_busy(False)
        assert not any('не связано' in m for m in configuration_messages(w))
    finally:wait_idle(w);w.close()

def test_close_during_generation_cancel_and_retry(tmp_path,qt_application_lifetime,monkeypatch):
    import time
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication,QMessageBox
    from docflow.data import Record,Table
    w=MainWindow(service_root=tmp_path/'project');w.show();w.load_demo();wait_idle(w)
    original=Template.render
    def slow(self,values):time.sleep(.01);return original(self,values)
    monkeypatch.setattr(Template,'render',slow)
    try:
        w.table=Table(w.table.source,w.table.headers,tuple(Record(i+2,w.table.records[0].values.copy()) for i in range(100)))
        w.refresh(*w.mapping());w.navigate(3);output=tmp_path/'output';w.output_path.setText(str(output));w.start_generation()
        assert w._busy
        def dismiss():
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget,QMessageBox):widget.accept()
        QTimer.singleShot(50,dismiss);w.close();assert w.isVisible()
        w.cancel_generation();wait_idle(w)
        assert not list(output.rglob('*.docx')) and not list(output.glob('.docflow-*'))
        w.table=Table(w.table.source,w.table.headers,w.table.records[:1]);w.refresh(*w.mapping());w.start_generation();wait_idle(w)
        assert w.last_result.documents==2
    finally:wait_idle(w);w.close()

def test_service_template_diagnostics_failed_selection_preserves_previous(tmp_path,qt_application_lifetime,monkeypatch):
    from PySide6.QtWidgets import QFileDialog,QMessageBox
    from docflow.ui.service.repair_editor import RepairDialog
    w=MainWindow(service_root=tmp_path/'project');w.show();w.navigate(5);wait_idle(w.service_workspace)
    ui=w.service_workspace;key=ui.store.intake(client={'name':'QA'},equipment={'number':'QA-S6','model':'QA'})
    dialog=RepairDialog(ui,ui.store.snapshot(key));dialog.show()
    try:
        good=create_templates(tmp_path/'forms',modern=True,quality=True)['completion']
        monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a:(str(good),''))
        dialog.pick_template();wait_idle(ui)
        assert dialog.template_path.text()==str(good) and 'DOCX проверен' in dialog.document_status.text()
        bad=tmp_path/'bad.docx';bad.write_bytes(b'broken')
        warnings=[]
        monkeypatch.setattr(QMessageBox,'warning',lambda *a:(warnings.append(a[-1]),QMessageBox.StandardButton.Ok)[1])
        monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a:(str(bad),''))
        dialog.pick_template();wait_idle(ui)
        assert dialog.template_path.text()==str(good) and 'повреждён' in dialog.document_status.text() and warnings
    finally:wait_idle(ui);dialog.close();w.close()
