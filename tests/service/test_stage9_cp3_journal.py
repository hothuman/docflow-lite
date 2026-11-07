
"""CP3 native widget tests with synthetic projects and real SQLite reads."""
import time

import pytest

pytest.importorskip('PySide6')

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from docflow.service.repository import ServiceStore
from docflow.ui.service.journal import JournalGrid, RepairJournal
from docflow.ui.settings import preferences
from docflow.ui.window import MainWindow


COLUMNS = [('number','Ремонт №'), ('equipment_label','Аппарат'), ('client','Клиент'),
           ('received_at','Приёмка'), ('status','Статус'), ('total','Стоимость'), ('balance','Остаток')]


def sample_rows():
    common = {'client':'Учебный заказчик','received_at':'2026-11-05','model':'Насос',
              'equipment_number':'0007','equipment_label':'0007 · Насос','serial':'ЗАВ-009',
              'equipment_id':'pump','status':'accepted','paid':0,'total':900,'balance':900}
    return [
        dict(common,id='a',number='R-1',complaint='Низкое давление'),
        dict(common,id='b',number='R-2',status='repair',total=10001,paid=2001,balance=8000),
        dict(common,id='c',number='R-3',status='historical',total=None,paid=None,balance=None),
    ]


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def journal(app):
    calls = []
    widget = RepairJournal(COLUMNS,lambda:calls.append('new'),lambda:calls.append('open'),
                           lambda:calls.append('history'))
    widget.resize(1200,700);widget.show()
    widget.install(sample_rows(),{'pump':{'owner':'Учебный владелец'}})
    widget.project_state(True,True)
    app.processEvents()
    yield widget,calls
    widget.close()


def wait_idle(window):
    app=QApplication.instance()
    workspace=window.service_workspace
    deadline=time.monotonic()+15
    while workspace.worker or workspace._pending_refresh:
        app.processEvents()
        if time.monotonic()>deadline:
            raise AssertionError(workspace.message.text())
        time.sleep(.005)
    app.processEvents()


def ids(journal):
    proxy=journal.grid.proxy
    return [journal.grid.records.rows[proxy.mapToSource(proxy.index(i,0)).row()]['id']
            for i in range(proxy.rowCount())]


def test_search_filters_keep_selection_focus_and_empty_inspector(journal):
    w,calls=journal
    assert ids(w)==['a','b','c']
    w.grid.selectRow(1)
    assert w.preferred_id=='b'
    w.search.setFocus()
    w.search.setText('давление')
    assert ids(w)==['a'] and 'R-1' in w.panels.inspector.title.text()
    w.search.setCursorPosition(4)
    QTest.keyClick(w.search,Qt.Key.Key_Right)
    assert w.search.cursorPosition()==5 and w.search.hasFocus()
    w.search.setText('зав-009')
    w.status_filter.setCurrentIndex(w.status_filter.findData('repair'))
    w.finance_filter.setCurrentIndex(w.finance_filter.findData('debt'))
    assert ids(w)==['b'] and 'R-2' in w.panels.inspector.title.text()
    w.archive_filter.setCurrentIndex(w.archive_filter.findData('archive'))
    assert ids(w)==[] and w.grid.selected() is None
    assert w.panels.inspector.title.text()=='Нет выбранного ремонта'
    assert not w.open_button.isEnabled() and w.panels.inspector.open_button.isHidden()
    w.reset_filters()
    assert ids(w)==['a','b','c'] and w.grid.selected()['id']=='b'
    assert 'Учебный владелец' in w.panels.inspector.fields['owner'].text()
    w.grid.setFocus()
    QTest.keyClick(w.grid,Qt.Key.Key_Return)
    assert calls==['open']


@pytest.mark.parametrize('column',[5,6])
def test_sort_uses_exact_money_and_places_unknown_last_in_both_directions(journal,column):
    w,_=journal
    w.grid.sortByColumn(column,Qt.SortOrder.AscendingOrder)
    assert ids(w)==['a','b','c']
    w.grid.sortByColumn(column,Qt.SortOrder.DescendingOrder)
    assert ids(w)==['b','a','c']
    w.grid.selectRow(2)
    assert 'Неизвестно' in w.panels.inspector.fields['balance'].text()
    assert w.panels.inspector.fields['paid'].text().endswith('Неизвестно')
    w.grid.selectRow(1)
    assert '0,00' in w.panels.inspector.fields['paid'].text()


def test_stable_columns_and_legacy_preferences(app):
    settings=preferences()
    settings.setValue('columns/workspace/repairs','{"1":300}')
    settings.sync()
    grid=JournalGrid(COLUMNS)
    assert grid.columnWidth(1)==300
    grid.setColumnWidth(1,315)
    grid.horizontalHeader().moveSection(1,0)
    reopened=JournalGrid(COLUMNS)
    assert reopened.columnWidth(1)==315
    assert reopened.horizontalHeader().logicalIndex(0)==1
    assert all(not reopened.isColumnHidden(i) for i in range(len(COLUMNS)))
    assert preferences().value('columns/workspace/repairs')=='{"1":300}'


def test_compact_details_preserve_scroll_and_return_focus(app,journal):
    w,calls=journal
    many=[dict(sample_rows()[0],id=str(i),number=f'ТЕСТ-{i}') for i in range(30)]
    w.install(many,{'pump':{'owner':'Учебный владелец'}})
    w.resize(650,420)
    app.processEvents()
    w.grid.selectRow(20)
    w.grid.verticalScrollBar().setValue(400)
    w.grid.horizontalScrollBar().setValue(25)
    w.grid.setFocus()
    context=w.view_context()
    assert context[2]>0 and context[3]>0
    w.panels.context_button.click()
    assert w.panels.currentWidget() is w.panels.summary
    assert 'ТЕСТ-20' in w.panels.inspector.title.text()
    assert w.panels.back.hasFocus()
    QTest.keyClick(w.panels.back,Qt.Key.Key_Escape)
    assert w.panels.currentWidget() is w.panels.list_page
    assert w.view_context()==context


def test_real_card_returns_to_journal_and_new_project_clears_old_selection(app,tmp_path,monkeypatch):
    first=tmp_path/'Первый проект'
    store=ServiceStore(first)
    client=store.save_client({'name':'Учебный клиент'})
    pump=store.save_equipment({'owner_id':client,'number':'001','model':'Модель с длинной русской подписью'})
    key=store.create_repair(pump,'ТЕСТ-РЕМОНТ','Учебная проверка')
    window=MainWindow(service_root=first);window.show();window.navigate(5)
    try:
        wait_idle(window)
        workspace=window.service_workspace
        workspace.tabs.setCurrentWidget(workspace.journal)
        window.resize(820,620);app.processEvents()
        journal=workspace.journal
        journal.search.setText('ремонт')
        journal.grid.setFocus()
        app.processEvents()

        from docflow.ui.service import workspace as implementation
        original=implementation.RepairDialog
        opened=[]
        def capture(parent,snapshot):
            dialog=original(parent,snapshot)
            opened.append(snapshot['repair']['id'])
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0,dialog.reject)
            return dialog
        monkeypatch.setattr(implementation,'RepairDialog',capture)
        QTest.keyClick(journal.grid,Qt.Key.Key_Return)
        wait_idle(window);app.processEvents()
        assert opened==[key]
        assert journal.grid.selected()['id']==key and journal.search.text()=='ремонт'
        assert window.focusWidget() is journal.grid
        window.activateWindow();app.processEvents()
        assert journal.grid.hasFocus()

        workspace.open_project(tmp_path/'Второй проект')
        wait_idle(window);app.processEvents()
        assert workspace.project_state=='opened'
        assert 'Второй проект' in workspace.location.text()
        assert journal.search.text()=='' and journal.grid.selected() is None
        assert journal.panels.inspector.title.text()=='Нет выбранного ремонта'
        assert not journal.panels.inspector.history_button.isVisible()
    finally:
        window.close()


def test_versioned_shell_preferences_roundtrip(app,tmp_path):
    root=tmp_path/'Учебный проект'
    settings=preferences()
    settings.setValue('workspace/mode',1)
    settings.setValue('workspace/workshop',2)
    settings.sync()
    window=MainWindow(service_root=root);window.show()
    wait_idle(window)
    assert window.service_workspace.tabs.currentIndex()==2
    window.move(10,10);window.resize(760,640);window._navigate_service(7);window.close()
    settings=preferences()
    assert int(settings.value('workspace/workshop'))==2
    assert int(settings.value('workspace/v2/workshop'))==7
    restored=MainWindow(service_root=root)
    restored.show();wait_idle(restored)
    try:
        assert restored.size()==window.size()
        assert restored.service_workspace.tabs.currentIndex()==7
    finally:
        restored.close()
