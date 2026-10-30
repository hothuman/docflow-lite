from test_stage1_upgrade_copy import app,idle,dispose
from docflow.ui.service.workspace import ServiceWorkspace
from docflow.ui.service.catalog import CatalogDialog
from docflow.service import catalog as api
from PySide6.QtWidgets import QMessageBox

def test_mapping_profile_roundtrip_invalidation_and_sheet_reread(app,tmp_path,monkeypatch):
    from openpyxl import Workbook
    workspace=ServiceWorkspace(root=tmp_path/'project');idle(app,workspace)
    path=tmp_path/'synthetic.xlsx';wb=Workbook();ws=wb.active;ws.title='First';ws.append(['Код','Название']);ws.append(['001','Учебная деталь']);ws=wb.create_sheet('Second');ws.append(['Код','Название']);ws.append(['002','Другая деталь']);wb.save(path)
    warnings=[];monkeypatch.setattr(QMessageBox,'warning',lambda *args:warnings.append(args[-1]))
    dialog=CatalogDialog(workspace);workspace.dialogs.append(dialog)
    try:
        dialog.path=str(path);dialog.source.setText('Synthetic');dialog.read();idle(app,workspace)
        for field,header in [('external_id','Код'),('name','Название')]:dialog.mapping[field].setCurrentIndex(dialog.mapping[field].findData(header))
        dialog.preview();assert dialog.plan.rows[0].key=='001' and dialog.apply_button.isEnabled()
        config=dialog.config();api.save_profile(workspace.store,'Custom',config);dialog.reload_profiles()
        dialog.currency.setText('RUB');assert dialog.plan is None and not dialog.apply_button.isEnabled()
        dialog.load_profile();assert dialog.config()==config
        dialog.sheet.setCurrentText('Second');dialog.preview();assert warnings and dialog.plan is None
        dialog.read();idle(app,workspace);dialog.preview();assert dialog.plan.rows[0].key=='002'
        # Loading before selecting a file must retain a custom mapping for the next read.
        other=CatalogDialog(workspace);workspace.dialogs.append(other);other.load_profile();other.path=str(path);other.read();idle(app,workspace)
        assert other.mapping['external_id'].currentData()=='Код' and other.mapping['name'].currentData()=='Название'
        other.accept();workspace.dialogs.remove(other)
    finally:dialog.accept();workspace.dialogs.remove(dialog);dispose(app,workspace)
