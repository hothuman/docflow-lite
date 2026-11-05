"""Selected DOCX is a file identity, including when basenames collide."""
import hashlib
from pathlib import Path
import pytest
from docx import Document
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog
from docflow.gui import MainWindow
from docflow.release_check import wait_idle


@pytest.fixture
def duplicate_templates(tmp_path,qt_application_lifetime,monkeypatch):
    w=MainWindow(service_root=tmp_path/'project');w.show();w.load_demo();wait_idle(w)
    files=[]
    for name in ('First','Second'):
        folder=tmp_path/name;folder.mkdir();p=folder/'form.docx'
        d=Document();d.add_paragraph(name+' {{client}}');d.save(p);files.append(p)
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
    monkeypatch.setattr(QFileDialog,'getOpenFileNames',lambda *args:([str(p) for p in files],''))
    w.select_templates();wait_idle(w)
    index=next(i for i,t in enumerate(w.active_templates()) if t.path==files[1])
    w.config_template.setCurrentIndex(index);wait_idle(w)
    assert 'Second' in w.config_preview.toPlainText()
    yield w,files
    wait_idle(w);w.close()
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in files]==hashes


@pytest.mark.parametrize('action',['refresh','undo','reload'])
def test_selected_file_survives_refresh_undo_reload(duplicate_templates,action):
    w,files=duplicate_templates
    if action=='refresh':w.refresh(*w.mapping())
    elif action=='reload':w.reload_data()
    else:
        row=next(i for i in range(w.mapping_table.rowCount()) if w.mapping_table.item(i,0).text()=='client')
        w.mapping_table.cellWidget(row,1).setCurrentIndex(0);wait_idle(w);w.restore_config_btn.click()
    wait_idle(w)
    assert w.active_templates()[w.config_template.currentIndex()].path==files[1]
    assert 'Second' in w.config_preview.toPlainText()
    assert w.config_template.currentIndex()==w.template_selector.currentIndex()


def test_ambiguous_captions_expose_distinct_paths(duplicate_templates):
    w,files=duplicate_templates
    labels=[w.config_template.itemText(i) for i in range(w.config_template.count())]
    assert len(labels)==len(set(labels))
    for path in files:
        i=w.config_template.findData(str(path));assert i>=0
        assert str(path.parent) in w.config_template.itemText(i)
        assert w.config_template.itemData(i,Qt.ItemDataRole.ToolTipRole)==str(path)


@pytest.mark.parametrize('removed',['other','selected'])
def test_disabled_template_uses_valid_remaining_identity(duplicate_templates,removed):
    w,files=duplicate_templates;path=files[0 if removed=='other' else 1]
    for i in range(w.template_list.count()):
        item=w.template_list.item(i)
        if Path(item.data(Qt.ItemDataRole.UserRole))==path:item.setCheckState(Qt.CheckState.Unchecked);break
    wait_idle(w)
    remaining=w.active_templates();chosen=remaining[w.config_template.currentIndex()]
    assert chosen.path!=path
    if removed=='other':assert chosen.path==files[1] and 'Second' in w.config_preview.toPlainText()
    assert w.config_template.currentData()==str(chosen.path)
