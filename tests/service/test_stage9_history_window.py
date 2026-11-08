from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from docflow.service.repository import ServiceStore
from docflow.ui.service.history import HistoryComparison, HistoryPage, LIMIT
from docflow.ui.window import MainWindow
from test_stage9_cp3_journal import wait_idle


def test_embedded_history_returns_from_repair_and_releases_old_project(tmp_path):
    root = tmp_path / 'original'
    store = ServiceStore(root)
    repair = store.intake(client={'name': 'Учебный клиент'},
                          equipment={'number': '0007', 'model': 'Насос'},
                          complaint='Падает давление')
    window = MainWindow(service_root=root)
    window.show()
    window.navigate(5)
    try:
        wait_idle(window)
        workspace = window.service_workspace
        workspace.show_history(workspace.store.equipment()[0])
        wait_idle(window)
        history = workspace.current_page
        assert isinstance(history, HistoryPage) and history.isVisible() and history.window() is window
        history.search.setText('давление')
        history.grid.selectRow(0)
        assert history.grid.selected()['id'] == repair

        history.open()
        wait_idle(window)
        opened = workspace.current_page
        assert opened.key == repair and opened.window() is window and not opened.isWindow()
        assert not history.isVisible()
        workspace.back_page()
        wait_idle(window)
        assert workspace.current_page is history and history.isVisible()
        assert history.search.text() == 'давление'
        assert history.grid.selected()['id'] == repair

        workspace.open_project(tmp_path / 'other')
        wait_idle(window)
        assert workspace.current_page is None
        assert workspace.store.root.name == 'other'
    finally:
        window.close()


def test_comparison_checkboxes_preserve_ids_and_show_structured_differences(tmp_path):
    root = tmp_path / 'comparison'
    store = ServiceStore(root)
    first = store.intake(client={'name': 'Учебный заказчик'},
                         equipment={'number': 'QA16-001', 'model': 'Насос'},
                         complaint='Не включается')
    equipment = store.equipment()[0]
    second = store.create_repair(equipment['id'], 'QA-R2', 'Новая жалоба')
    store.save_item(first, {'kind': 'work', 'name': 'Диагностика', 'price': '1500'})
    store.save_item(first, {'kind': 'part', 'name': 'Кабель', 'price': '350'})
    store.add_payment(first, '1000')
    before = [store.snapshot(key) for key in (first, second)]
    window = MainWindow(service_root=root)
    window.resize(820, 620)
    window.show()
    window.navigate(5)
    try:
        wait_idle(window)
        workspace = window.service_workspace
        workspace.show_history(equipment)
        wait_idle(window)
        history = workspace.current_page
        model = history.grid.proxy
        assert isinstance(history, HistoryPage)
        assert model.rowCount() == 2
        assert not history.compare_button.isEnabled()
        for i in range(model.rowCount()):
            index = model.index(i, 0)
            assert index.flags() & Qt.ItemFlag.ItemIsUserCheckable
            assert 'Выбрать для сравнения ремонт №' in index.data(Qt.ItemDataRole.AccessibleTextRole)
            history.grid.setCurrentIndex(index)
            history.grid.setFocus()
            QTest.keyClick(history.grid, Qt.Key.Key_Space)
            assert index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
        assert history.compare_button.isEnabled()
        assert set(history.comparison_keys()) == {first, second}

        history.search.setText('Новая жалоба')
        assert model.rowCount() == 1 and history.compare_button.isEnabled()
        assert 'Скрыто фильтрами: 1' in history.compare_hint.text()
        history.compare_button.click()
        wait_idle(window)
        comparison = workspace.current_page
        assert isinstance(comparison, HistoryComparison) and comparison.window() is window
        assert QApplication.activeModalWidget() is None
        assert set(comparison.sections) == {'Причина обращения', 'Диагностика', 'Работы', 'Запчасти',
                                            'Стоимость', 'Остаток', 'Документы', 'Подробности'}
        values = [label.text() for label in comparison.sections['Остаток'].findChildren(QLabel)]
        assert 'Остаток · Есть различия' in values and '850,00 ₽' in values and '0,00 ₽' in values
        assert any('Кабель' in label.text() for label in comparison.sections['Запчасти'].findChildren(QLabel))
        assert any(label.text() == 'Не заполнено' for label in comparison.sections['Диагностика'].findChildren(QLabel))
        assert not comparison.sections['Подробности'].isVisible()
        comparison.details_button.click()
        assert comparison.sections['Подробности'].isVisible()

        workspace.back_page()
        assert workspace.current_page is history and history.search.text() == 'Новая жалоба'
        assert set(history.comparison_keys()) == {first, second}
        history.since.set_date('2100-01-01')
        history.refresh()
        wait_idle(window)
        assert model.rowCount() == 0 and history.compare_button.isEnabled()
        history.clear_checks.click()
        assert not history.comparison_keys() and not history.compare_button.isEnabled()
        assert [store.snapshot(key) for key in (first, second)] == before
    finally:
        window.close()


def test_history_checks_accept_at_most_six_distinct_repairs():
    from docflow.ui.service.history import COLUMNS, HistoryRows

    model = HistoryRows(COLUMNS)
    model.install([{'id': str(i), 'number': str(i)} for i in range(LIMIT + 1)])
    for row in range(LIMIT):
        assert model.setData(model.index(row, 0), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    seventh = model.index(LIMIT, 0)
    assert not model.setData(seventh, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert seventh.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert model.setData(model.index(1, 0), Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    assert model.setData(seventh, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert len(model.checked) == LIMIT
