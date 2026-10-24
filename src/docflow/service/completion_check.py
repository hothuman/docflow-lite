"""Opt-in native Qt completion scenarios, used by the frozen EXE diagnostic."""
import json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog,QWizard
from ..ui.service.import_wizard import HistoryWizard
from ..ui.service.profiles import ProfileDialog
from ..ui.service.estimates import DraftDialog
from ..ui.service.repair_editor import RepairDialog
from ..ui.service.images import ImagesDialog
from .attachments import add_attachment
from .backup import create_backup,restore_backup
from .repository import ServiceStore


def exercise(workspace,app,output,idle,fill):
    checks=[];s=workspace.store
    def passed(name,**details):checks.append({'name':name,'passed':True,**details})
    p=ProfileDialog(workspace);workspace.dialogs.append(p);p.show();idle(workspace)
    fill(lambda:p.edit(False),{'name':'Синтетический профиль проверки','organization_name':'Учебное предприятие','number_prefix':'CHECK-','number_start':'900','status_accepted':'На осмотре'})
    idle(workspace);p.grid.selectRow(0);p.activate();idle(workspace);p.accept();workspace.dialogs.remove(p)
    passed('native_profile_form_numbering_status_labels')
    source=output/'History-900.csv';source.write_text('repair_number;equipment_number;model;client_key;client_name;received_at;works;work_cost\n101;900;Учебный аппарат;A;Учебный клиент А;2023-01-01;Осмотр;100\n305;900;Учебный аппарат;B;Учебный клиент Б;2024-02-03;Настройка;200\n900;900;Учебный аппарат;B;Учебный клиент Б;2026-03-04;Ремонт;300\n',encoding='utf-8-sig')
    wizard=HistoryWizard(workspace);workspace.dialogs.append(wizard);wizard.show();wizard.path.setText(str(source));app.processEvents()
    next_button=lambda:QTest.mouseClick(wizard.button(QWizard.WizardButton.NextButton),Qt.MouseButton.LeftButton)
    count=len(s.repairs());next_button();idle(workspace);assert wizard.currentId()==1
    wizard.default_status.setCurrentIndex(wizard.default_status.findData('closed'));next_button();idle(workspace);assert wizard.currentId()==2
    # Every decision is entered into the real dialog; no bulk automatic identity.
    for row in range(wizard.identity.proxy.rowCount()):
        wizard.identity.selectRow(row);fill(wizard.decide,{'equipment':'new','client':'new','owner':'b'});idle(workspace)
    assert len(s.repairs())==count
    next_button();idle(workspace);assert wizard.currentId()==3;wizard.confirmed.setChecked(True);next_button();idle(workspace)
    assert wizard.currentId()==4 and wizard.result_report['imported']==3
    (output/'HISTORY-IMPORT-REPORT.json').write_text(json.dumps(wizard.result_report,ensure_ascii=False,indent=2),encoding='utf-8')
    plan=wizard.plan;wizard.accept();workspace.dialogs.remove(wizard)
    from .history_import import import_history
    replay=import_history(s,plan,confirmed=True);assert replay['already_imported']==3 and replay['imported']==0
    eq=next(x for x in s.equipment() if x['number']=='900');assert eq['owner']=='Учебный клиент Б'
    r=s.create_repair(eq['id']);assert s.get('repair_orders',r)['number']=='CHECK-000900'
    assert len(s.repairs(equipment_id=eq['id']))==4;assert len(s.compare_repairs([x['id'] for x in s.repairs(equipment_id=eq['id'])]))==4
    passed('native_five_page_history_wizard_900_101_305_900_fourth_two_owners_and_replay',source_file=source.name)
    editor=RepairDialog(workspace,s.snapshot(r));workspace.dialogs.append(editor);editor.show()
    draft=DraftDialog(editor);workspace.dialogs.append(draft);draft.show()
    fill(draft.add,{'kind':'work','name':'Учебная настройка','quantity':'1','unit':'ч','price':'100'})
    fill(draft.add,{'kind':'delivery','name':'Учебная доставка','quantity':'2','unit':'рейс','price':'100.25'})
    draft.comment.setPlainText('Синтетический предварительный расчёт');draft.save();idle(workspace);workspace.dialogs.remove(draft)
    assert s.snapshot(r)['totals']['balance']==0
    fill(lambda:editor.estimates.freeze('preliminary'),{'actor':'Тестовый оператор','reason':'Первый расчёт'});idle(workspace)
    editor.estimates.grid.selectRow(0);fill(editor.estimates.manual_event,{'action':'approved','actor':'Тестовый оператор','comment':'Синтетическая ручная отметка, не согласие реального клиента'});idle(workspace)
    fill(lambda:editor.item('work'),{'name':'Фактическая учебная настройка','quantity':'1','unit':'ч','price':'100','change_reason':'Уточнение состава'})
    idle(workspace)
    fill(lambda:editor.item('delivery'),{'name':'Фактическая учебная доставка','quantity':'1','unit':'рейс','price':'150','change_reason':'Изменился тестовый маршрут'});idle(workspace)
    fill(lambda:editor.item('other'),{'name':'Согласованный учебный расход','quantity':'1','unit':'компл.','price':'25','change_reason':'Учебное уточнение'});idle(workspace)
    fill(lambda:editor.estimates.freeze('final'),{'actor':'Тестовый оператор','reason':'Уточнены маршрут и расходы'});idle(workspace)
    assert editor.snapshot['totals']['total']==27500 and editor.snapshot['estimate_comparison']['difference']==-2550
    for kind in ('preliminary','final'):
        for row in range(editor.estimates.grid.proxy.rowCount()):
            index=editor.estimates.grid.proxy.mapToSource(editor.estimates.grid.proxy.index(row,0))
            if editor.estimates.grid.records.rows[index.row()]['kind']==kind:editor.estimates.grid.selectRow(row);break
        editor.estimates.document();idle(workspace)
    assert {x['kind'] for x in editor.snapshot['generated_documents']}=={'estimate_preliminary','estimate_final'}
    passed('native_draft_versions_manual_approval_actual_expenses_and_both_quote_docx')
    from PySide6.QtGui import QImage,QColor
    ids=[]
    for i,dimensions in enumerate(((150,800),(800,150))):
        path=output/f'synthetic-selection-{i}.png';image=QImage(*dimensions,QImage.Format.Format_RGB32);image.fill(QColor('#873047'));assert image.save(str(path));ids.append(add_attachment(s,r,path,'Учебное изображение'))
    editor.install(s.snapshot(r));selection=ImagesDialog(editor.snapshot['attachments'],editor);selection.show();app.processEvents()
    for row in range(2):selection.table.item(row,0).setCheckState(Qt.CheckState.Checked);selection.table.item(row,2).setText('Проверочная подпись '+str(row));selection.table.item(row,3).setText('После осмотра')
    selection.table.setCurrentCell(1,1);selection.move(-1);choices=selection.values();assert choices[0]['id']==ids[1];selection.accept()
    from .documents import generate_document
    path=generate_document(s,r,'combined',image_choices=choices)
    from docx import Document
    assert len(Document(path).inline_shapes)==2
    editor.install(s.snapshot(r));editor.tabs.setCurrentWidget(editor.estimates);editor.grab().save(str(output/'service-estimates-interface.png'));editor.accept();workspace.dialogs.remove(editor)
    passed('native_individual_image_choice_order_captions_and_docx',image_order=[x['id'] for x in choices])
    b=create_backup(s,output/'completion.service-backup.zip');root=restore_backup(b,output/'Completion restored');again=ServiceStore(root)
    assert len(again.repairs())==len(s.repairs())
    snap=again.snapshot(r);assert snap['estimate_comparison']['approved_estimate_id'] and len(snap['generated_documents'])==3
    passed('completion_backup_restore_profiles_history_quotes_and_selected_images')
    return {'status':'passed','checks':checks,'native_os_file_dialogs_tested':False,'customer_or_word_acceptance':False}
