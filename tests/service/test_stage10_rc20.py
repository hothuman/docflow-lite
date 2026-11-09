from PySide6.QtWidgets import QLabel

from docflow.service.estimates import freeze_estimate, save_draft
from test_stage10_rc18_hotfix import journal, capture
from test_stage1_document_actions import idle


def test_history_details_have_room_in_desktop_window(journal):
    app, window, workspace, first = journal
    repair = workspace.store.snapshot(first)
    workspace.show_history({**repair['equipment'],'owner':repair['client']['name']})
    idle(app, workspace)
    history = workspace.current_page
    history.grid.selectRow(0)
    app.processEvents()
    capture(window,'rc20-history')
    assert history.detail.height() >= 300
    assert history.grid.height() <= 130
    assert history.detail.width() >= 320


def test_history_comparison_has_one_heading(journal):
    app, window, workspace, first = journal
    snapshot = workspace.store.snapshot(first)
    workspace.show_history({**snapshot['equipment'],'owner':snapshot['client']['name']})
    idle(app, workspace)
    workspace.current_page.show_comparison([snapshot,snapshot])
    app.processEvents()
    page = workspace.current_page
    capture(window,'rc20-comparison')
    assert not any(label.text()=='Сравнение ремонтов' for label in page.findChildren(QLabel))
    assert {'Диагностика','Работы','Запчасти','Стоимость','Остаток'} <= page.sections.keys()


def test_estimate_tabs_keep_names_and_no_bare_category(journal):
    app, window, workspace, first = journal
    save_draft(workspace.store,first,[{'kind':'work','name':'Диагностика','quantity':'1','price':'2450'}])
    freeze_estimate(workspace.store,first,'preliminary','Учебный автор с длинным именем')
    workspace.open_repair(first,'Сметы')
    idle(app, workspace)
    panel=workspace.current_page.estimates
    panel.mode.setCurrentIndex(2)
    app.processEvents()
    capture(window,'rc20-estimates')
    assert panel.mode.width() >= panel.mode.sizeHint().width()
    assert panel.line_detail.isHidden()


def test_documents_uses_space_for_the_filename(journal):
    from docflow.service.documents import generate_document
    app, window, workspace, first = journal
    generate_document(workspace.store,first,'intake')
    workspace.refresh()
    idle(app,workspace)
    workspace.go_to_section(5)
    app.processEvents()
    table=workspace.views['documents']
    capture(window,'rc20-documents')
    assert table.columnWidth(0) <= 150
    assert table.columnWidth(4) > table.columnWidth(1)

def test_history_and_versions_stay_scrollable_with_many_rows(journal):
    app, window, workspace, first = journal
    store=workspace.store
    snapshot=store.snapshot(first)
    workspace.show_history({**snapshot['equipment'],'owner':snapshot['client']['name']})
    idle(app,workspace)
    history=workspace.current_page
    source=dict(history.grid.records.rows[0])
    for count in (1,2,10,100):
        history.grid.install([{**source,'id':str(i),'number':str(i)} for i in range(count)])
        history.update_selection()
        app.processEvents()
        assert history.grid.proxy.rowCount()==count
        if count<=2:assert history.grid.height()<=140
        if count==100:assert history.grid.verticalScrollBar().maximum()>0
    workspace.back_page()
    idle(app,workspace)
    quote_id=freeze_estimate(store,first,'preliminary','Очень длинное учебное имя автора для проверки подсказки')
    workspace.open_repair(first,'Сметы')
    idle(app,workspace)
    panel=workspace.current_page.estimates
    snapshot=store.snapshot(first)
    original=next(q for q in snapshot['estimates'] if q['id']==quote_id)
    panel.mode.setCurrentIndex(2)
    for count in (0,1,2,10,100):
        rows=[{**original,'id':str(i),'version':i+1} for i in range(count)]
        panel.install({**snapshot,'estimates':rows})
        app.processEvents()
        assert panel.grid.isVisible()==bool(count)
        if 0<count<=2:assert panel.grid.maximumHeight()<=140
        if count==100:assert panel.grid.verticalScrollBar().maximum()>0
    from PySide6.QtCore import Qt
    panel.grid.selectRow(0)
    author=panel.grid.proxy.index(0,3)
    assert original['prepared_by'] in author.data(Qt.ItemDataRole.ToolTipRole)
    assert panel.grid.columnWidth(3)>=190
    selected=panel.grid.selected()['id']
    panel.mode.setCurrentIndex(0)
    panel.mode.setCurrentIndex(2)
    assert panel.grid.selected()['id']==selected


def test_handover_warns_for_draft_and_keeps_issued_documents_immutable(journal):
    app, window, workspace, first=journal
    store=workspace.store
    workspace.open_repair(first,'Приёмка')
    idle(app,workspace)
    editor=workspace.current_page
    editor.tabs.stage_bar.setCurrentIndex(4)
    editor.tabs.section_tabs[4].setCurrentIndex(1)
    wizard=editor.document_wizard
    wizard.check_document()
    assert wizard.check_handover_warning.isVisible()
    assert 'дата выдачи' in wizard.check_handover_warning.text()
    wizard.preview()
    idle(app,workspace)
    wizard.preview_continue.click()
    assert wizard.create_handover_warning.isVisible()
    preview=wizard.prepared.rendered
    wizard.generate_button.click()
    idle(app,workspace)
    saved=wizard._last_document
    assert saved.read_bytes()==preview
    assert store.snapshot(first)['repair']['status']=='accepted'
    store.save_repair(first,{'status':'issued','issued_at':'2026-11-09','handover':'Учебный получатель'})
    editor.install(store.snapshot(first))
    wizard.start('handover')
    wizard.check_document()
    assert wizard.check_handover_warning.isHidden()
    assert saved.read_bytes()==preview


def test_issued_cost_change_can_be_cancelled_and_audited(journal, monkeypatch):
    from docflow.service.documents import generate_document
    import docflow.ui.service.repair_editor as module

    app, window, workspace, first=journal
    store=workspace.store
    item=store.save_item(first,{'kind':'work','name':'Ремонт','price':'2450','quantity':'1'})
    store.add_payment(first,'1600')
    store.save_repair(first,{'status':'issued','issued_at':'2026-11-09'})
    issued=generate_document(store,first,'completion')
    original=issued.read_bytes()
    before=store.snapshot(first)
    workspace.open_repair(first,'Работы')
    idle(app,workspace)
    editor=workspace.current_page
    editor.items_grid.selectRow(0)
    prompts=[]
    monkeypatch.setattr(module,'confirm',lambda _,message,*args,**kwargs:prompts.append(message) or False)
    form=editor.item('',edit=True)
    form.fields['price'].setText('2500')
    form.save_button.click()
    idle(app,workspace)
    assert workspace.current_page is form
    assert store.snapshot(first)==before
    assert 'задолженность' in prompts[-1]
    monkeypatch.setattr(module,'confirm',lambda *args,**kwargs:True)
    form.save_button.click()
    idle(app,workspace)
    updated=store.snapshot(first)
    assert (updated['totals']['total'],updated['totals']['paid'],updated['totals']['balance'])==(250000,160000,90000)
    assert updated['repair_status_history']==before['repair_status_history']
    assert issued.read_bytes()==original
    with store.db.connection() as connection:
        assert connection.execute("SELECT count(*) FROM operations WHERE entity='item' AND entity_id=? AND action='save'",(item,)).fetchone()[0]==2


def test_localized_csv_retains_utf8_decimal_values_and_original_contract(journal,tmp_path):
    import csv
    from docflow.service.estimates import export_specification

    _,_,workspace,first=journal
    store=workspace.store
    save_draft(store,first,[{'kind':'work','name':'Проверка оборудования','quantity':'2','price':'12.35'}])
    estimate=freeze_estimate(store,first,'preliminary','Учебный автор')
    usual=export_specification(store,estimate,tmp_path/'ordinary.csv')
    translated=export_specification(store,estimate,tmp_path/'localized.csv',localized=True)
    assert usual.read_bytes().startswith(b'\xef\xbb\xbf') and translated.read_bytes().startswith(b'\xef\xbb\xbf')
    normal=list(csv.reader(usual.read_text(encoding='utf-8-sig').splitlines(),delimiter=';'))
    russian=list(csv.reader(translated.read_text(encoding='utf-8-sig').splitlines(),delimiter=';'))
    assert normal[1][2]=='preliminary'
    assert russian[1][2]=='Предварительная смета'
    assert normal[1][-2:]==russian[1][-2:]==['12.35','24.70']
    assert normal[0]==russian[0] and normal[-1]==russian[-1]
