"""Comparable actual Qt client captures. Synthetic fixture shared by before/after."""
import argparse,json,time,sys
from pathlib import Path
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QApplication,QPushButton
from docflow.gui import MainWindow,configure_app
from docflow.service.demo import seed_demo
from docflow.ui.service.intake import IntakeDialog
from docflow.ui.service.repair_editor import RepairDialog
from docflow.ui.service.history import HistoryDialog
from docflow.ui.service.profiles import ProfileDialog
from docflow.service.documents import generate_document
from docx import Document

def run(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False);seed=seed_demo(out/'Synthetic');window=MainWindow(service_root=out/'Synthetic');window.resize(1280,800);window.show()
    def idle():
        end=time.monotonic()+60
        while window._busy or (window.preview_worker and window.preview_worker.isRunning()) or (window.service_workspace and (window.service_workspace.worker or window.service_workspace._pending_refresh)):
            app.processEvents();time.sleep(.005);assert time.monotonic()<end
        app.processEvents();app.processEvents()
    stats=[]
    def capture(widget,name):
        app.processEvents();app.processEvents();widget.grab().save(str(out/(name+'.png')))
        buttons=[b for b in widget.findChildren(QPushButton) if b.isVisible()]
        stats.append({'screen':name,'size':[widget.width(),widget.height()],'visible_buttons':[b.text() for b in buttons],'visible_primary_buttons':[b.text() for b in buttons if b.objectName()=='primary']})
    window.navigate(0);capture(window,'core-empty');window.load_demo();idle();capture(window,'core-table')
    window.navigate(1);capture(window,'core-templates');window.navigate(2);capture(window,'core-fields');window.navigate(0);window.output_path.setText(str(out/'Core-output'));window.start_generation();idle();capture(window,'core-result')
    window.navigate(5);idle();capture(window,'workshop');workspace=window.service_workspace
    intake=IntakeDialog(workspace);intake.show();capture(intake,'intake-existing');intake.new_equipment.setChecked(True);intake.new_client.setChecked(True);intake.number.setText('SYNTH-NEW');intake.model.setText('Учебная модель');intake.name.setText('Учебный клиент');capture(intake,'intake-new');intake.accept()
    editor=RepairDialog(workspace,workspace.store.snapshot(seed['repair']));editor.show()
    for i,name in enumerate(('intake','diagnostics','estimate','work','issue')):editor.tabs.setCurrentIndex(i);capture(editor,'repair-'+name)
    editor.tabs.show_section('Документы');capture(editor,'repair-documents');editor.dirty=False;editor.accept()
    equipment=workspace.store.equipment()[0];history=HistoryDialog(workspace,equipment);history.show();idle();history.grid.selectRow(0);app.processEvents();capture(history,'history-one-selected')
    selection=history.grid.selectionModel();selection.select(history.grid.proxy.index(1,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows);capture(history,'history-two-selected');history.accept()
    profile=ProfileDialog(workspace);profile.show();idle();capture(profile,'organization-profile');profile.accept()
    act=generate_document(workspace.store,seed['repair'],'intake');doc=Document(act);paragraphs=[p.text for p in doc.paragraphs]
    (out/'BASELINE.json').write_text(json.dumps({'frozen':bool(getattr(sys,'frozen',False)),'qt_platform':app.platformName(),'synthetic_only':True,'screens':stats,'executor':workspace.store.snapshot(seed['repair'])['profile']['organization_name'],'document_paragraphs':paragraphs,'method':'Same demo_profile and seed_demo values. Qt widget client captures, not human usability acceptance.'},ensure_ascii=False,indent=2),encoding='utf-8')
    idle();window.close();app.processEvents();print(out)
    return 0

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);return run(a.output)
