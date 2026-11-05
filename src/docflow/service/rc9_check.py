"""Synthetic rc9 regression routes executed by the real frozen hotfix diagnostic."""
import hashlib
import zipfile
from docx import Document


def exercise(window, app, output, idle):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAccessible
    from PySide6.QtTest import QTest
    from ..release_check import wait_idle
    from .documents import create_templates, generate_document
    from .profiles import save_profile
    store=window.service_workspace.store
    documents=[]
    for modern in (False,True):
        template=create_templates(output/('reuse-v6' if modern else 'reuse-v5'),modern=modern)['completion']
        before=hashlib.sha256(template.read_bytes()).hexdigest()
        repair=store.intake(client={'name':'QA Reuse '+str(modern)},equipment={
            'number':'QA-REUSE-'+str(modern),'model':'QA Synthetic'})
        save_profile(store,{'name':'QA Reuse','organization_name':'QA Organization '+str(modern)},
                     assets={'templates':{'completion':template}},repair_id=repair)
        old={}
        for mode in ('profile','explicit','profile'):
            path=generate_document(store,repair,'completion',template=template if mode=='explicit' else None)
            with zipfile.ZipFile(path) as archive:assert archive.testzip() is None
            text='\n'.join(p.text for p in Document(path).paragraphs)
            assert 'QA Reuse '+str(modern) in text and 'QA Organization '+str(modern) in text and '{{' not in text
            old[path]=hashlib.sha256(path.read_bytes()).hexdigest();documents.append(str(path))
        assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in old.items())
        assert hashlib.sha256(template.read_bytes()).hexdigest()==before
    window.navigate(0);window.load_demo();wait_idle(window)
    def inspect():
        button=window.core_next;interface=QAccessible.queryAccessibleInterface(button)
        assert interface.text(QAccessible.Text.Name)==button.text()==button.accessibleName()
        assert button.toolTip() and interface.text(QAccessible.Text.Description)==button.toolTip()
        return {'visible':button.text(),'accessible':button.accessibleName(),'hint':button.toolTip(),'enabled':button.isEnabled()}
    actions=[]
    for page in (0,1,2):window.navigate(page);actions.append(inspect())
    window.navigate(0);window.core_next.setFocus();QTest.keyClick(window.core_next,Qt.Key.Key_Space)
    assert window.pages.currentIndex()==1;actions.append(inspect())
    window.navigate(5);idle(window.service_workspace);window.navigate(1);actions.append(inspect())
    app.processEvents();assert window.grab().save(str(output/'rc9-accessible-action.png'))
    import json
    (output/'RC9-REUSE-ACCESSIBILITY.json').write_text(json.dumps({
        'status':'passed','documents':documents,'actions':actions,'source_templates_unchanged':True,
        'method':'frozen Qt/QAccessible and keyboard events; not human/screen-reader acceptance'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return ['reused_profile_templates','core_accessible_action']
