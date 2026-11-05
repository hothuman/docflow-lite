"""Opt-in synthetic Stage7 regressions, also run inside the packaged EXE."""
import hashlib
import json
from pathlib import Path


def exercise(window,app,output,idle):
    from docx import Document
    from PySide6.QtCore import QLockFile,QTimer
    from PySide6.QtWidgets import QFileDialog
    from ..release_check import wait_idle
    from ..ui.service.repair_editor import RepairDialog
    window.navigate(0);window.load_demo();wait_idle(window)
    files=[]
    for name in ('First','Second'):
        folder=output/('same-name-'+name);folder.mkdir()
        path=folder/'form.docx';d=Document();d.add_paragraph(name+' {{client}}');d.save(path);files.append(path)
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
    chooser=QFileDialog.getOpenFileNames
    try:
        QFileDialog.getOpenFileNames=lambda *args:([str(p) for p in files],'')
        window.select_templates();wait_idle(window)
    finally:QFileDialog.getOpenFileNames=chooser
    window.navigate(2)
    index=next(i for i,t in enumerate(window.active_templates()) if t.path==files[1])
    window.config_template.setCurrentIndex(index);wait_idle(window)
    observations=[]
    def inspect(action):
        assert Path(window.config_template.currentData())==files[1]
        assert 'Second' in window.config_preview.toPlainText()
        assert window.config_template.currentIndex()==window.template_selector.currentIndex()
        observations.append({'action':action,'selected':window.config_template.currentData(),'preview':window.config_preview.toPlainText()})
    inspect('select');window.reload_data();wait_idle(window);inspect('reload')
    row=next(i for i in range(window.mapping_table.rowCount()) if window.mapping_table.item(i,0).text()=='client')
    window.mapping_table.cellWidget(row,1).setCurrentIndex(0);wait_idle(window)
    window.restore_config_btn.click();wait_idle(window);inspect('undo')
    labels=[window.config_template.itemText(i) for i in range(window.config_template.count())]
    assert len(labels)==len(set(labels))
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in files]==hashes
    assert window.grab().save(str(output/'stage7-template-identity.png'))
    window.navigate(5);ui=window.service_workspace;idle(ui)
    key=ui.store.intake(client={'name':'QA Stage7'},equipment={'number':'QA-ST7-CLOSE','model':'QA'})
    d=RepairDialog(ui,ui.store.snapshot(key));d.fields['complaint'].setPlainText('QA Stage7 unsaved draft')
    ui.dialogs.append(d);observed={};probe=QLockFile(str(ui.store.root/'.docflow-service.lock'))
    def attempt():
        window.close();app.processEvents();acquired=probe.tryLock(0)
        observed.update(owner_visible=window.isVisible(),dialog_visible=d.isVisible(),dirty=d.dirty,
                        text=d.fields['complaint'].toPlainText(),other_lock_acquired=acquired)
        if acquired:probe.unlock()
        assert d.grab().save(str(output/'stage7-retained-draft.png'))
        d.dirty=False;d.reject()
    try:
        QTimer.singleShot(50,attempt);d.exec()
        assert observed==dict(owner_visible=True,dialog_visible=True,dirty=True,
                             text='QA Stage7 unsaved draft',other_lock_acquired=False)
    finally:ui.dialogs.remove(d);d.dirty=False;d.close()
    (output/'STAGE7-REGRESSIONS.json').write_text(json.dumps({'status':'passed','preview':observations,
        'owner_close':observed,'method':'frozen/source synthetic Qt controls and direct close(), not native user input'},
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return ['stage7_template_identity','stage7_owner_close']
