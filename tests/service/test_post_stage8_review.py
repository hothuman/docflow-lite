import pytest
from docflow.service.repository import ServiceStore
from docflow.service.documents import create_templates
from docflow.templates import Template


def test_existing_builtin_template_fields_remain_self_mapped(qt_application_lifetime,tmp_path):
    from docflow.ui.service.template_fields import TemplateFieldsDialog
    for kind,path in create_templates(tmp_path/'Forms',modern=True,quality=True).items():
        d=TemplateFieldsDialog(Template.load(path).fields,{},kind)
        try:
            unresolved=[name for name,w in d.mapping_widgets.items() if w.currentData() is None]
            assert not unresolved,(kind,unresolved)
            assert all(w.currentData()==name for name,w in d.mapping_widgets.items())
        finally:d.reject()


def test_return_to_import_columns_preserves_status_choices(qt_application_lifetime,tmp_path):
    from docflow.gui import MainWindow
    from docflow.ui.service.import_wizard import HistoryWizard
    from docflow.data import load_table
    from docflow.release_check import wait_idle
    w=MainWindow(service_root=tmp_path/'p');w.show();w.navigate(5)
    ui=w.service_workspace
    import time
    end=time.monotonic()+20
    while ui.worker or ui._pending_refresh:qt_application_lifetime.processEvents();time.sleep(.005);assert time.monotonic()<end
    d=HistoryWizard(ui)
    try:
        p=tmp_path/'data.csv';p.write_text('Статус;Примечания\nПринято;Принято\n',encoding='utf-8')
        d.table=load_table(p);d._source_signature=('QA','same bytes')
        from PySide6.QtWidgets import QComboBox
        combo=QComboBox();combo.addItem('Статус','Статус');combo.addItem('Примечания','Примечания');d.mappings={'status':combo}
        d.build_statuses();d.statuses['Принято'].setCurrentIndex(d.statuses['Принято'].findData('accepted'))
        d.build_statuses();assert d.statuses['Принято'].currentData()=='accepted'
        combo.setCurrentIndex(1);d.build_statuses();assert d.statuses['Принято'].currentData() is None
    finally:d.reject();w.close()


def test_readiness_and_render_use_identical_known_values(tmp_path):
    from docflow.service.profiles import save_profile
    from docflow.service.document_readiness import assess
    from docflow.service.documents import generate_document
    from docx import Document
    s=ServiceStore(tmp_path/'p');r=s.intake(client={'name':'QA'},equipment={'number':'QA-1','model':'QA'})
    form=tmp_path/'form.docx';d=Document();d.add_paragraph('{{accessories}} / {{status}} / {{executor_display}}');d.save(form)
    s.save_repair(r,{'accessories':'QA Work'})
    # The supported source text projection must not be reported missing only in GUI.
    save_profile(s,{'name':'QA','organization_name':'QA Workshop','contact':'QA contact','details':'QA details',
                    'template_required_fields':{'intake':['accessories','status','executor_display']}},
                 assets={'templates':{'intake':form}},repair_id=r)
    check=assess(s.snapshot(r),'intake');assert not check['required_missing'] and not check['blocked']
    doc=generate_document(s,r,'intake');assert 'QA Work / Принято / QA Workshop' in '\n'.join(p.text for p in Document(doc).paragraphs)
