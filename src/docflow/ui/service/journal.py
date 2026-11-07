
"""Read-only repair journal backed by the existing Service rows model."""
import json
import hashlib
import os
from contextlib import contextmanager

from PySide6.QtCore import QItemSelectionModel, QSignalBlocker, QSortFilterProxyModel, QTimer, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ...service.statuses import STATUSES, TERMINAL
from ..flow import ActionBar
from ..settings import load_widths, preferences
from ..widgets import icon, text
from .presentation import MONEY, display
from .repair_inspector import JournalPanels
from .widgets import Grid, button


class JournalProxy(QSortFilterProxyModel):
    status = ''
    archive = ''
    finance = ''

    def filterAcceptsRow(self, source_row, source_parent):
        row = self.sourceModel().rows[source_row]
        if self.status and row['status'] != self.status:
            return False
        archived = row['status'] in TERMINAL
        if self.archive and archived != (self.archive == 'archive'):
            return False
        balance = row.get('balance')
        if self.finance == 'debt' and (balance is None or balance <= 0):
            return False
        if self.finance == 'incomplete' and balance is not None:
            return False
        return super().filterAcceptsRow(source_row, source_parent)

    def lessThan(self, left, right):
        model = self.sourceModel()
        key = model.columns[left.column()][0]
        a, b = model.data(left, self.sortRole()), model.data(right, self.sortRole())
        if key in MONEY and (a is None) != (b is None):
            return a is not None if self.sortOrder() == Qt.SortOrder.AscendingOrder else a is None
        if key == 'status':
            a, b = (display(key, model.rows[i.row()]) for i in (left, right))
        if a != b:
            if type(a) is int and type(b) is int:
                return a < b
            return str(a).casefold() < str(b).casefold()
        return model.rows[left.row()]['id'] < model.rows[right.row()]['id']


class JournalGrid(Grid):
    preference_key = 'workspace/v2/journal/columns'

    def __init__(self, columns):
        super().__init__(columns, proxy_type=JournalProxy)
        self.setObjectName('repairJournal')
        self.setMouseTracking(True)
        self.setAccessibleName('Журнал ремонтов')
        self.setAccessibleDescription(
            'Стрелки выбирают запись, Ввод открывает ремонт. '
            'Таблицу можно прокручивать горизонтально. Полный текст ячейки есть в подсказке.'
        )
        self.setHorizontalScrollMode(self.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(self.ScrollMode.ScrollPerPixel)
        self.setMinimumHeight(64)
        header = self.horizontalHeader()
        header.setSectionsMovable(True)
        header.setAccessibleName('Столбцы журнала ремонтов')
        self._load_columns()
        header.sectionMoved.connect(self._save_columns)
        self.fit_columns()

    def _load_columns(self):
        header = self.horizontalHeader()
        keys = [key for key, _ in self.records.columns]
        raw = preferences().value(self.preference_key, '')
        try:
            saved = json.loads(raw)
            widths, order = saved['widths'], saved['order']
            if not isinstance(widths, dict) or not isinstance(order, list):
                raise ValueError('Invalid column preferences')
        except (TypeError, ValueError, KeyError):
            self._user_widths = load_widths('workspace/repairs')
            return
        self._user_widths = {
            i: min(4096, max(48, widths[key]))
            for i, key in enumerate(keys) if type(widths.get(key)) is int
        }
        ordered = [key for key in dict.fromkeys(value for value in order if isinstance(value, str)) if key in keys]
        ordered.extend(key for key in keys if key not in ordered)
        for visual, key in enumerate(ordered):
            header.moveSection(header.visualIndex(keys.index(key)), visual)

    def _remember(self, index, old, new):
        if self._sizing:
            return
        width = max(new, self._content_minimum.get(index, 0), 48)
        if width != new:
            self._sizing = True
            try:
                self.horizontalHeader().resizeSection(index, width)
            finally:
                self._sizing = False
        self._user_widths[index] = width
        self._save_columns()

    def _save_columns(self, *_):
        header = self.horizontalHeader()
        columns = self.records.columns
        state = {
            'widths': {columns[i][0]: width for i, width in self._user_widths.items()},
            'order': [columns[header.logicalIndex(i)][0] for i in range(len(columns))],
        }
        settings = preferences()
        settings.setValue(self.preference_key, json.dumps(state))
        settings.sync()
        if settings.status() != settings.Status.NoError:
            header.setToolTip('Ширина изменена в этом окне. Не удалось записать настройки столбцов.')

    def fit_columns(self):
        if self._sizing:
            return
        self._sizing = True
        try:
            widths = {
                i: max(self._minimum[i], self._content_minimum.get(i, 0),
                       self._user_widths.get(i, self._preferred[i]))
                for i in self._preferred
            }
            if not widths:
                return
            keys = {key:i for i, (key, _) in enumerate(self.records.columns)}
            available = self.viewport().width()
            remaining = available - sum(widths.values())
            for key in ('received_at', 'status', 'client', 'equipment_label'):
                if remaining >= 0:
                    break
                index = keys[key]
                if index in self._user_widths:
                    continue
                minimum = self._minimum[index]
                if key == 'received_at':
                    minimum = max(minimum, self.fontMetrics().horizontalAdvance('29.12.2026') + 26)
                amount = min(-remaining, max(0, widths[index] - minimum))
                widths[index] -= amount
                remaining += amount
            flexible = keys['equipment_label']
            if flexible not in self._user_widths:
                widths[flexible] += max(0, remaining)
            for i, width in widths.items():
                self.horizontalHeader().resizeSection(i, width)
        finally:
            self._sizing = False


class RepairJournal(QWidget):
    """Keep explicit selection separate from the fallback row visible under filters."""

    def __init__(self, columns, start, open_repair, open_history):
        super().__init__()
        self.preferred_id = None
        self.project_key = None
        self.pending_context = None
        self.equipment = {}
        self._changing = False
        self._ready = False
        self._has_project = False
        self.setObjectName('repairJournalPage')
        self.setAccessibleName('Ремонты')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        list_page = QWidget()
        layout = QVBoxLayout(list_page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)
        actions = ActionBar()
        layout.addWidget(actions)
        self.new_button = button(actions, 'Новый ремонт', start, primary=True)
        self.open_button = button(actions, 'Открыть ремонт', open_repair)
        self.open_button.setAccessibleDescription('Открыть выбранную запись в карточке ремонта')

        self.search = QLineEdit()
        self.search.setAccessibleName('Поиск ремонтов')
        self.search.setPlaceholderText('Ремонт, аппарат, серийный номер или заказчик')
        self.search.addAction(icon('search'), QLineEdit.ActionPosition.LeadingPosition)
        layout.addWidget(self.search)
        filters = ActionBar()
        layout.addWidget(filters)
        self.status_filter = self._filter(filters, 'Производственный статус',
            [('Все статусы',''), *((label, key) for key, (label, _) in STATUSES.items())])
        self.archive_filter = self._filter(filters, 'Обращения в архиве',
            [('Все обращения',''), ('В работе и ожидают','active'), ('Завершённые и архив','archive')])
        self.finance_filter = self._filter(filters, 'Финансовый фильтр',
            [('Все расчёты',''), ('Есть долг','debt'), ('Расчёт неполон','incomplete')])
        self.reset_button = button(filters, 'Сбросить фильтры', self.reset_filters)
        self.grid = JournalGrid(columns)
        self.empty = text('', 'empty')
        self.empty.setAccessibleName('Состояние выдачи журнала')
        self.table_area = QVBoxLayout()
        self.table_area.setContentsMargins(0, 0, 0, 0)
        self.table_area.setSpacing(5)
        self.table_area.addWidget(self.empty)
        self.table_area.addWidget(self.grid, 1)
        self.body = QHBoxLayout()
        self.body.setSpacing(12)
        self.body.addLayout(self.table_area, 1)
        layout.addLayout(self.body, 1)
        self.count = text('', 'journalCount')
        self.count.setAccessibleName('Количество найденных ремонтов')
        self.selected_summary = text('', 'journalSelectedSummary')
        summary_policy = self.selected_summary.sizePolicy()
        summary_policy.setRetainSizeWhenHidden(True)
        self.selected_summary.setSizePolicy(summary_policy)
        self.selected_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.count)
        self.search.textChanged.connect(self.apply_filters)
        self.grid.selectionModel().currentRowChanged.connect(self._user_selected)
        self.grid.pressed.connect(lambda _: self._user_selected())
        self.grid.openRequested.connect(self.open_button.click)
        self.grid.doubleClicked.connect(lambda _: self.open_button.click())
        self.panels = JournalPanels(self, list_page, self.body, actions, open_repair, open_history)
        outer.addWidget(self.panels, 1)
        outer.addWidget(self.selected_summary)
        self.panels.currentChanged.connect(self._sync)
        self._sync()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.panels.responsive(event.size().width())

    def view_context(self):
        if self.panels.currentWidget() is self.panels.summary and self.panels.context:
            return self.panels.context
        row = self.grid.selected()
        focus = QApplication.focusWidget()
        if focus is None or not self.isAncestorOf(focus):
            focus = self.grid
        return (row['id'] if row else None, max(0, self.grid.currentIndex().column()),
                self.grid.verticalScrollBar().value(), self.grid.horizontalScrollBar().value(), focus,
                self.panels.list_page.verticalScrollBar().value())

    def restore_view(self, context):
        repair_id, column, vertical, horizontal, focus, page_scroll = context
        if repair_id:
            self.preferred_id = repair_id
        self._changing = True
        try:
            self._select_visible(column)
        finally:
            self._changing = False
        self._sync()
        self.layout().activate()
        if self.isVisible():
            (focus if focus.isVisible() and focus.isEnabled() else self.grid).setFocus()
        self.grid.updateGeometries()
        self.grid.verticalScrollBar().setValue(vertical)
        self.grid.horizontalScrollBar().setValue(horizontal)
        self.panels.list_page.verticalScrollBar().setValue(page_scroll)

    def selected_equipment(self):
        row = self.grid.selected()
        return self.equipment.get(row.get('equipment_id')) if row else None

    def _filter(self, layout, name, items):
        control = QComboBox()
        control.setAccessibleName(name)
        for label, key in items:
            control.addItem(label, key)
        layout.addWidget(control)
        control.currentIndexChanged.connect(self.apply_filters)
        return control

    @contextmanager
    def _preserve_view(self):
        vertical, horizontal = self.grid.verticalScrollBar(), self.grid.horizontalScrollBar()
        position = vertical.value(), horizontal.value()
        self._changing = True
        try:
            yield
            self._select_visible()
            vertical.setValue(position[0])
            horizontal.setValue(position[1])
        finally:
            self._changing = False
        self._sync()

    def _select_visible(self, column=0):
        proxy = self.grid.proxy
        current = self.grid.selected()
        if current and current.get('id') == self.preferred_id:
            target = proxy.index(self.grid.currentIndex().row(), column)
        else:
            target = proxy.index(0, column)
        if self.preferred_id:
            row = next((i for i, item in enumerate(self.grid.records.rows)
                        if item['id'] == self.preferred_id), None)
            if row is not None:
                index = proxy.mapFromSource(self.grid.records.index(row, column))
                if index.isValid():
                    target = index
        self.grid.selectionModel().setCurrentIndex(
            target, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows
        )

    def _user_selected(self, *_):
        if not self._changing:
            row = self.grid.selected()
            if row:
                self.preferred_id = row['id']
            self._sync()

    def _set_filter_values(self):
        proxy = self.grid.proxy
        proxy.status = self.status_filter.currentData()
        proxy.archive = self.archive_filter.currentData()
        proxy.finance = self.finance_filter.currentData()
        query = self.search.text().strip()
        if query != getattr(proxy, 'query', ''):
            proxy.query = query
            proxy.setFilterFixedString(query)
        else:
            proxy.beginFilterChange()
            proxy.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def apply_filters(self, *_):
        with self._preserve_view():
            self._set_filter_values()

    def reset_filters(self):
        controls = (self.search, self.status_filter, self.archive_filter, self.finance_filter)
        with self._preserve_view():
            blockers = [QSignalBlocker(control) for control in controls]
            self.search.clear()
            for control in controls[1:]:
                control.setCurrentIndex(0)
            del blockers
            self._set_filter_values()

    def install(self, rows, equipment):
        self.equipment = equipment
        with self._preserve_view():
            self.grid.install(rows)

    def persist_context(self):
        if not self.project_key or self.pending_context:
            return
        grid = self.grid
        context = self.view_context()
        sort = grid.horizontalHeader().sortIndicatorSection()
        settings = preferences()
        settings.setValue(self.project_key, json.dumps({
            'id': self.preferred_id or context[0],
            'column': grid.records.columns[context[1]][0],
            'sort': grid.records.columns[sort][0] if 0 <= sort < len(grid.records.columns) else '',
            'descending': grid.horizontalHeader().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder,
            'vertical': context[2], 'horizontal': context[3], 'page': context[5],
            'focus_search': context[4] is self.search,
        }))
        settings.sync()

    def project_changed(self, root):
        self.panels.return_to_list(restore=False)
        key = hashlib.sha256(os.path.normcase(str(root)).encode('utf-8')).hexdigest()
        self.project_key = 'workspace/v2/journal/project/' + key
        self.preferred_id = None
        self.reset_filters()
        self.grid.verticalScrollBar().setValue(0)
        self.grid.horizontalScrollBar().setValue(0)
        self.panels.list_page.verticalScrollBar().setValue(0)
        self.pending_context = self._read_context()
        if self.isVisible():
            QTimer.singleShot(0, self, self._restore_pending)

    def _read_context(self):
        try:
            data = json.loads(preferences().value(self.project_key, '{}'))
            if not isinstance(data, dict):
                return None
            columns = {key: i for i, (key, _) in enumerate(self.grid.records.columns)}
            repair_id = data.get('id')
            if not isinstance(repair_id, str) or not any(r['id']==repair_id for r in self.grid.records.rows):
                return None
            order = Qt.SortOrder.DescendingOrder if data.get('descending') else Qt.SortOrder.AscendingOrder
            self.grid.sortByColumn(columns.get(data.get('sort'), -1), order)
            return (repair_id, columns.get(data.get('column'), 0), int(data.get('vertical', 0)),
                    int(data.get('horizontal', 0)), self.search if data.get('focus_search') else self.grid,
                    int(data.get('page', 0)))
        except (TypeError, ValueError):
            return None

    def _restore_pending(self):
        if self.isVisible() and self.pending_context:
            context, self.pending_context = self.pending_context, None
            self.restore_view(context)

    def showEvent(self, event):
        super().showEvent(event)
        if self.pending_context:
            QTimer.singleShot(0, self, self._restore_pending)

    def project_state(self, has_project, ready):
        self._has_project = has_project
        self._ready = ready
        for control in (self.new_button, self.search, self.grid, self.status_filter,
                        self.archive_filter, self.finance_filter):
            control.setEnabled(ready)
        self._sync()

    def _sync(self,*_):
        count = self.grid.proxy.rowCount()
        filtered = bool(self.search.text().strip() or any(control.currentIndex() for control in (
            self.status_filter, self.archive_filter, self.finance_filter)))
        self.reset_button.setEnabled(self._ready and filtered)
        row = self.grid.selected()
        self.open_button.setEnabled(self._ready and row is not None)
        self.panels.update_repair(row, self.selected_equipment(), self._ready)
        self.selected_summary.setVisible(row is not None and self.panels.currentWidget() is self.panels.list_page)
        if row:
            self.selected_summary.setText(f"Выбран ремонт № {row['number']}   ·   Остаток: {display('balance', row)}")
        else:
            self.selected_summary.clear()
        self.count.setText(f'Найдено обращений: {count}' if self._has_project else '')
        self.count.setVisible(self._has_project)
        self.empty.setVisible(not count)
        if not self._has_project:
            self.empty.setText('Откройте проект, чтобы увидеть журнал ремонтов.')
        elif filtered:
            self.empty.setText('По этим условиям ничего не найдено. Измените поиск или сбросьте фильтры.')
        else:
            self.empty.setText('Ремонтов пока нет. Создайте первое обращение.')
