from PySide6.QtWidgets import QApplication

from docflow.service.estimates import freeze_estimate, save_draft
from docflow.service.repository import ServiceStore
from docflow.ui.service.repair_editor import RepairPage
from docflow.ui.window import MainWindow
from test_stage9_cp3_journal import wait_idle
from test_stage3_catalog import commit, item


def test_estimate_workspace_shows_itemized_draft_and_preserves_frozen_quote(tmp_path):
    root = tmp_path / 'Мастерская'
    store = ServiceStore(root)
    client = store.save_client({'name': 'Учебный клиент'})
    device = store.save_equipment({'number': 'QA-001', 'model': 'Насос', 'owner_id': client})
    repair = store.create_repair(device, 'QA-001-R')
    work = {'kind': 'work', 'name': 'Диагностика', 'price': '1500', 'quantity': '1'}
    part = {'kind': 'part', 'name': 'Уплотнитель', 'price': '350', 'quantity': '1'}
    save_draft(store, repair, [work])
    original = freeze_estimate(store, repair, 'preliminary', 'Учебный мастер')
    store.save_item(repair, work)
    store.save_item(repair, part)
    store.add_payment(repair, '1000')
    initial = store.snapshot(repair)['estimates'][0]

    window = MainWindow(service_root=root)
    window.show()
    window.navigate(5)
    workspace = window.service_workspace
    try:
        wait_idle(window)
        workspace.open_repair(repair, 'Сметы')
        wait_idle(window)
        editor = workspace.current_page
        assert isinstance(editor, RepairPage)
        panel = editor.estimates
        assert panel.lines.isVisible()
        assert [item['name'] for item in panel.lines.records.rows] == ['Диагностика']
        assert '1 500,00 ₽' in panel.summary.text()
        assert 'Фактически: 1 850,00 ₽' in panel.summary.text()
        assert 'Остаток: 850,00 ₽' in panel.summary.text()

        panel.mode.setCurrentIndex(1)
        assert [item['kind'] for item in panel.lines.records.rows] == ['work', 'part']
        assert 'Запчасти 350,00 ₽' in panel.costs.text()
        panel.mode.setCurrentIndex(0)
        draft = panel.edit_draft()
        assert workspace.current_page is draft and not draft.isWindow()
        form = draft.add()
        assert workspace.current_page is form and not form.isWindow()
        form.fields['kind'].setCurrentIndex(form.fields['kind'].findData('part'))
        form.fields['name'].setText('Учебная запчасть')
        form.fields['price'].setText('-1')
        form.accept()
        assert workspace.current_page is form and QApplication.activeModalWidget() is None
        assert 'Цена, ₽' in form.error.text() and form.fields['name'].text() == 'Учебная запчасть'
        form.fields['price'].setText('350')
        form.accept()
        assert workspace.current_page is draft and len(draft.lines) == 2
        draft.save()
        wait_idle(window)
        assert workspace.current_page is editor
        assert 'Итого 1 850,00 ₽' in panel.costs.text()
        assert workspace.store.snapshot(repair)['estimates'][0] == initial

        form = panel.freeze('preliminary')
        form.fields['actor'].setText('Учебный мастер')
        form.fields['reason'].setPlainText('Добавлена запчасть')
        form.accept()
        wait_idle(window)
        assert workspace.current_page is editor and panel.mode.currentIndex() == 2
        assert panel.grid.selected()['version'] == 2
        assert '№2 · Сохранена' in panel.caption.text()
        panel.select_version(original)
        assert [item['name'] for item in panel.lines.records.rows] == ['Диагностика']
        assert 'Итого 1 500,00 ₽' in panel.costs.text()
        panel.document()
        assert workspace.current_page is editor and QApplication.activeModalWidget() is None
        assert editor.document_wizard.doc_kind.currentData() == 'estimate_preliminary'
        assert not workspace.store.snapshot(repair)['generated_documents']
        assert next(item for item in workspace.store.snapshot(repair)['estimates'] if item['id'] == original) == initial
        workspace.back_page()
        wait_idle(window)
    finally:
        window.close()


def test_catalog_pick_validates_price_and_returns_to_embedded_draft(tmp_path):
    root = tmp_path / 'Мастерская'
    store = ServiceStore(root)
    repair = store.intake(client={'name':'Учебный клиент'},equipment={'number':'CAT-01','model':'Учебный аппарат'})
    commit(store,[item()])
    window=MainWindow(service_root=root);window.show();window.navigate(5)
    workspace=window.service_workspace
    try:
        wait_idle(window)
        workspace.open_repair(repair,'Сметы');wait_idle(window)
        editor=workspace.current_page
        draft=editor.estimates.edit_draft()
        draft.from_catalog();wait_idle(window)
        catalog=workspace.current_page
        assert not catalog.isWindow() and catalog.grid.selected()['sku']=='SKU-001'
        catalog.choose()
        form=workspace.current_page
        assert not form.isWindow() and QApplication.activeModalWidget() is None
        form.fields['quantity'].setText('2')
        form.fields['price'].clear()
        form.accept()
        assert workspace.current_page is form and 'неизвестная цена' in form.error.text()
        form.fields['price'].setText('123,45')
        form.accept();wait_idle(window)
        assert workspace.current_page is draft
        assert len(draft.lines)==1 and draft.lines[0]['total_cents']==24690
        draft.save();wait_idle(window)
        assert workspace.current_page is editor
        assert workspace.store.snapshot(repair)['preliminary_draft']['lines'][0]['total_cents']==24690
        assert workspace.store.snapshot(repair)['totals']['total']==0
        workspace.back_page();wait_idle(window)
    finally:
        window.close()
