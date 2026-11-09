"""Embedded equipment chronology and explicit comparison of repair records."""
from PySide6.QtCore import QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QGridLayout, QLineEdit, QPlainTextEdit,
    QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QVBoxLayout, QWidget,
)

from ...service.record_text import readable_field, repair_display
from ...service.validation import rub
from ..flow import ActionBar
from ..theme import COLORS
from ..widgets import card, text
from .forms import DateField, fit_dialog
from .models import RowsModel
from .presentation import KINDS_DISPLAY, date_text, display
from .widgets import Grid, button


COLUMNS = [
    ('number', 'Ремонт'), ('received_at', 'Дата'), ('client', 'Заказчик'),
    ('status', 'Статус'), ('total', 'Стоимость'), ('financial_status', 'Расчёты'),
]
LIMIT = 6


class HistoryRows(RowsModel):
    """Store comparison choices by repair ID, independently of view selection."""

    checkedChanged = Signal()

    def __init__(self, columns, parent=None):
        super().__init__(columns, parent)
        self.checked = set()
        self.positions = {}

    def install(self, rows):
        rows = list(rows)
        self.positions = {row['id']: i for i, row in enumerate(rows)}
        super().install(rows)

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and index.column() == 0:
            row = self.rows[index.row()]
            if role == Qt.ItemDataRole.CheckStateRole:
                return Qt.CheckState.Checked if row['id'] in self.checked else Qt.CheckState.Unchecked
            if role == Qt.ItemDataRole.AccessibleTextRole:
                return f"Выбрать для сравнения ремонт № {row['number']}"
        return super().data(index, role)

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or index.column() != 0 or role != Qt.ItemDataRole.CheckStateRole:
            return False
        key = self.rows[index.row()]['id']
        if value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value):
            if len(self.checked) >= LIMIT and key not in self.checked:
                return False
            self.checked.add(key)
        elif value in (Qt.CheckState.Unchecked, Qt.CheckState.Unchecked.value):
            self.checked.discard(key)
        else:
            return False
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self.checkedChanged.emit()
        return True

    def clear_checks(self):
        self.checked.clear()
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, 0),
                                  [Qt.ItemDataRole.CheckStateRole])
        self.checkedChanged.emit()


class ComparisonCheckDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.data(Qt.ItemDataRole.CheckStateRole) != Qt.CheckState.Checked:
            return
        style_option = QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        style = option.widget.style()
        center = style.subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator,
                                      style_option, option.widget).center()
        x, y = center.x(), center.y()
        painter.save()
        painter.setPen(QPen(QColor(COLORS['accentText']), 2))
        painter.drawLine(x - 4, y, x - 1, y + 3)
        painter.drawLine(x - 1, y + 3, x + 5, y - 4)
        painter.restore()


def _show_or_empty(value):
    return value or 'Не заполнено'


def _item_text(item):
    name = readable_field(item['name'], 'name').text
    detail = readable_field(item['description'], 'description').text
    quantity = f"{display('quantity', item)} {item['unit']}"
    amount = rub(item['total_cents']) if item.get('price_known', True) else 'Цена не установлена'
    return f"{name} · {quantity} · {amount}" + (f"\n{detail}" if detail else '')


def _compare_fields(snapshot):
    repair = repair_display(snapshot['repair'])
    grouped = {kind: [] for kind in ('work', 'part', 'delivery', 'other')}
    for item in snapshot['repair_items']:
        grouped[item['kind']].append(_item_text(item))
    if repair['source_works']:
        grouped['work'].append('Работы из источника: ' + repair['source_works'])

    documents = [f"{KINDS_DISPLAY.get(doc['kind'], 'Документ')} · версия {doc['version']} · "
                 f"{date_text(doc['created_at'])}" for doc in snapshot['generated_documents']]
    details = [
        f"Заказчик: {snapshot['client']['name']}",
        f"Статус: {display('status', repair)}",
        f"План: {_show_or_empty(repair['plan'])}",
        f"Вложения: {len(snapshot['attachments'])}",
        f"Примечания: {_show_or_empty(repair['notes'])}",
    ]
    for kind in ('delivery', 'other'):
        if grouped[kind]:
            details.append(KINDS_DISPLAY[kind] + ':\n' + '\n\n'.join(grouped[kind]))

    total = snapshot['totals']['total']
    balance = snapshot['totals']['balance']
    return (
        _show_or_empty(repair['complaint']),
        _show_or_empty(repair['defects']),
        _show_or_empty('\n\n'.join(grouped['work'])),
        _show_or_empty('\n\n'.join(grouped['part'])),
        rub(total) if total is not None else 'Не установлено',
        rub(balance) if balance is not None else 'Не установлено',
        _show_or_empty('\n'.join(documents)),
        '\n\n'.join(details),
    )


class HistoryComparison(QWidget):
    """Aligned sections with responsive cards and explicit difference markers."""

    SECTION_NAMES = ('Причина обращения', 'Диагностика', 'Работы', 'Запчасти',
                     'Стоимость', 'Остаток', 'Документы', 'Подробности')

    def __init__(self, snapshots, *, show_heading=True):
        super().__init__()
        self.setObjectName('historyComparison')
        self.setAccessibleName('Сравнение ремонтов одного аппарата')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        if show_heading:
            outer.addWidget(text('Сравнение ремонтов', 'title'))
        outer.addWidget(text('Найдите, что повторилось, что изменилось и как отличались расходы.', 'muted'))
        actions = ActionBar()
        self.details_button = button(actions, 'Подробности', self.toggle_details)
        self.details_button.setCheckable(True)
        outer.addWidget(actions)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAccessibleName('Разделы сравнения ремонтов')
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(0, 0, 5, 0)
        content.setSpacing(14)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        captions = [f"Ремонт № {s['repair']['number']} · {date_text(s['repair']['received_at'])}"
                    for s in snapshots]
        values = list(zip(*(_compare_fields(snapshot) for snapshot in snapshots)))
        self.sections = {}
        self._columns = 0
        self._groups = []
        for section_name, section_values in zip(self.SECTION_NAMES, values):
            group = self._section(section_name, captions, section_values)
            content.addWidget(group)
            self.sections[section_name] = group
        self.sections['Подробности'].hide()
        content.addStretch()
        self._arrange(1)

    def _section(self, name, captions, values):
        group = QWidget()
        group.setAccessibleName(name)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        differs = len(set(values)) > 1
        heading = text(name + (' · Есть различия' if differs else ''), 'section')
        if differs:
            heading.setStyleSheet(f"color: {COLORS['info']};")
        layout.addWidget(heading)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        layout.addLayout(grid)
        cards = []
        for caption, value in zip(captions, values):
            panel, panel_layout = card(caption)
            label = text(value)
            panel_layout.itemAt(0).widget().setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                          | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            panel_layout.addWidget(label)
            cards.append(panel)
        self._groups.append((grid, cards))
        return group

    def _arrange(self, columns):
        if columns == self._columns:
            return
        previous = self._columns
        self._columns = columns
        for grid, cards in self._groups:
            count = min(columns, len(cards))
            for panel in cards:
                grid.removeWidget(panel)
            for i in range(max(previous, count)):
                grid.setColumnStretch(i, int(i < count))
            for i, panel in enumerate(cards):
                grid.addWidget(panel, i // count, i % count)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange(max(1, min(3, event.size().width() // 295)))

    def toggle_details(self, checked):
        self.sections['Подробности'].setVisible(checked)
        label = 'Скрыть подробности' if checked else 'Подробности'
        self.details_button.setText(label)
        self.details_button.setAccessibleName(label)


class _HistoryContent:
    """Shared Qt controls for the workspace page and standalone diagnostics."""

    def _build_history(self, parent, workspace, equipment, view, *, embedded):
        self.workspace = workspace
        self.equipment = equipment
        self._saved_view = view
        self._embedded = embedded

        outer = QVBoxLayout(parent)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAccessibleName('История и сведения о выбранном ремонте')
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 3, 0)
        if not embedded or not workspace.shell_navigation:
            layout.addWidget(text('История аппарата', 'title'))
        serial = ' · Серийный № ' + equipment['serial'] if equipment.get('serial') else ''
        owner = equipment.get('owner') or 'Не заполнено'
        identity = f"Аппарат № {equipment['number']} · {equipment['model']}{serial}\nВладелец: {owner}"
        self.identity = text(identity, 'section')
        layout.addWidget(self.identity)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Номер ремонта, жалоба, диагностика, работы или запчасти')
        self.search.setAccessibleName('Поиск по истории аппарата')
        layout.addWidget(self.search)

        bar = ActionBar()
        layout.addWidget(bar)
        self.since = DateField()
        self.since.setPlaceholderText('С даты')
        self.since.setAccessibleName('Начальная дата ДД.ММ.ГГГГ')
        bar.addWidget(self.since)
        self.until = DateField()
        self.until.setPlaceholderText('По дату')
        self.until.setAccessibleName('Конечная дата ДД.ММ.ГГГГ')
        bar.addWidget(self.until)
        self.order = QComboBox()
        self.order.setAccessibleName('Порядок ремонтов')
        self.order.addItem('От старых к новым', True)
        self.order.addItem('От новых к старым', False)
        bar.addWidget(self.order)
        self.apply_dates = button(bar, 'Применить даты', self.refresh)
        button(bar, 'Сбросить фильтры', self.reset_filters)

        if embedded:
            self.date_toggle = button(bar, 'Даты', self._adjust_dates)
            self.date_toggle.setCheckable(True)
            self.date_toggle.setAccessibleDescription('Показать или скрыть поля фильтра по датам')
            self.grid = Grid(COLUMNS, settings_key='workspace/v2/equipment-history', model_type=HistoryRows)
            self.grid.setItemDelegateForColumn(0, ComparisonCheckDelegate(self.grid))
            self.grid.setAccessibleDescription('Пробел ставит отметку для сравнения в столбце «Ремонт». '
                                               'Enter открывает выбранный ремонт.')
            self.grid.records.checked.update((view or {}).get('checked', ()))
            self.grid.records.checkedChanged.connect(self.update_selection)
        else:
            self.grid = Grid(COLUMNS)
            self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grid.setAccessibleName('Хронология ремонтов выбранного аппарата')
        self.empty_hint = text('', 'muted')
        layout.addWidget(self.empty_hint)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.grid)
        layout.addWidget(self.splitter, 1)
        if embedded:layout.addStretch()

        details = QWidget()
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        self.selection_heading = text('Выберите обращение', 'section')
        detail_layout.addWidget(self.selection_heading)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(105)
        self.detail.setAccessibleName('Жалоба, диагностика и выполненные работы')
        self.detail.setPlaceholderText('Выберите ремонт, чтобы посмотреть его подробности.')
        detail_layout.addWidget(self.detail)
        self.splitter.addWidget(details)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.compare_hint = text('', 'muted')
        outer.addWidget(self.compare_hint)

        actions = ActionBar()
        outer.addWidget(actions)
        self.open_button = button(actions, 'Открыть ремонт', self.open, primary=True)
        self.compare_button = button(actions, 'Сравнить ремонты', self.compare)
        self.compare_button.setAccessibleDescription('Сравнение двух–шести ремонтов одного аппарата')
        if embedded:
            self.clear_checks = button(actions, 'Снять отметки', self.grid.records.clear_checks)
        self.new_button = button(actions, 'Новое обращение', self.new)
        if not embedded:
            button(actions, 'Закрыть', self.accept)

        self.grid.selectionModel().currentRowChanged.connect(self.selected_detail)
        self.grid.selectionModel().selectionChanged.connect(self.update_selection)
        self.grid.openRequested.connect(self.open)
        self.grid.doubleClicked.connect(self.open)
        self.grid.proxy.modelReset.connect(self.update_selection)
        self.grid.proxy.rowsRemoved.connect(self.update_selection)
        self.search.textChanged.connect(self.grid.proxy.setFilterFixedString)
        self.search.textChanged.connect(self.update_selection)
        if view:
            self.search.setText(view.get('query', ''))
            self.since.set_date(view.get('since', ''))
            self.until.set_date(view.get('until', ''))
            self.order.setCurrentIndex(self.order.findData(view.get('order', True)))
        self.order.currentIndexChanged.connect(self.refresh)
        self.update_selection()
        self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'splitter'):
            orientation = Qt.Orientation.Horizontal if self.width() >= 900 else Qt.Orientation.Vertical
            self.splitter.setOrientation(orientation)
            if self._embedded:
                self._adjust_dates()
                self._fit_history_splitter()

    def _fit_history_splitter(self):
        self.grid.fit_few_rows()
        maximum=self.grid.maximumHeight()
        if self.grid.proxy.rowCount()<=4:
            vertical=self.splitter.orientation()==Qt.Orientation.Vertical
            details_height=max(230,min(420,self.height()-210))
            if vertical:
                maximum+=details_height+self.splitter.handleWidth()
            else:
                maximum=max(maximum,details_height)
        self.splitter.setMaximumHeight(maximum)

    def _adjust_dates(self, *_):
        compact = self.width() < 700
        self.date_toggle.setVisible(compact)
        show_fields = not compact or self.date_toggle.isChecked()
        for widget in (self.since, self.until, self.apply_dates):
            widget.setVisible(show_fields)

    def reset_filters(self):
        self.search.clear()
        self.since.set_date('')
        self.until.set_date('')
        self.refresh()

    def selected_rows(self):
        rows = self.grid.records.rows
        selected = self.grid.selectionModel().selectedRows()
        return [rows[source.row()] for index in selected
                if (source := self.grid.proxy.mapToSource(index)).isValid()]

    def comparison_keys(self):
        if self._embedded:
            return sorted(self.grid.records.checked)
        return [row['id'] for row in self.selected_rows() if row['equipment_id'] == self.equipment['id']]

    def update_selection(self, *args):
        count = len(self.comparison_keys())
        self.compare_button.setEnabled(2 <= count <= LIMIT)
        self.open_button.setEnabled(bool(self.selected_rows()))
        if self._embedded:
            proxy = self.grid.proxy
            records = self.grid.records
            visible = sum(proxy.mapFromSource(records.index(records.positions[key], 0)).isValid()
                          for key in records.checked if key in records.positions)
            hidden = count - visible
            maximum = min(len(records.rows), LIMIT)
            if maximum < 2:
                hint = 'Для сравнения нужны минимум два обращения.'
            else:
                hint = f'Отмечено {count} из {maximum}. Отметьте от двух обращений для сравнения.'
            if hidden:
                hint += f' Скрыто фильтрами: {hidden}.'
            if count == maximum and maximum >= 2:
                hint = f'Отмечено обращений: {count}. Снимите отметку, чтобы изменить выбор.' + (
                    f' Скрыто фильтрами: {hidden}.' if hidden else '')
            self.clear_checks.setEnabled(bool(count))
        else:
            hint = 'Выделите от двух до шести ремонтов для сравнения.'
        self.compare_hint.setText(hint)
        if self._embedded:self._fit_history_splitter()
        has_rows = self.grid.proxy.rowCount() > 0
        self.empty_hint.setText('Обращений по текущим фильтрам нет. '
                                'Сбросьте фильтры или создайте новое обращение.' if not has_rows else '')
        self.empty_hint.setVisible(not has_rows)
        self.selected_detail()

    def selected_detail(self, *args):
        row = self.grid.selected()
        if not row or not self.selected_rows():
            self.selection_heading.setText('Выберите обращение')
            self.detail.clear()
            return
        self.selection_heading.setText(f"Ремонт № {row['number']} · {date_text(row['received_at'])} · {row['client']}")
        shown = repair_display(row)
        source_works = f"\nРаботы из источника: {shown['source_works']}" if shown['source_works'] else ''
        items = readable_field(row['item_text'], 'description').text
        self.detail.setPlainText(f"Приёмка: {date_text(row['received_at'])}\n\n"
                                 f"Жалоба: {_show_or_empty(shown['complaint'])}\n\n"
                                 f"Диагностика: {_show_or_empty(shown['defects'])}\n\n"
                                 f"Работы и материалы: {_show_or_empty(items)}{source_works}\n\n"
                                 'Откройте ремонт для DOCX, фото и подробностей.')

    def view_state(self):
        grid = self.grid
        header = grid.horizontalHeader()
        row = grid.selected()
        return {'query': self.search.text(), 'since': self.since.storage_text(),
                'until': self.until.storage_text(), 'order': self.order.currentData(),
                'current': row['id'] if row else None, 'selected': {r['id'] for r in self.selected_rows()},
                'column': max(0, grid.currentIndex().column()),
                'checked': set(grid.records.checked) if self._embedded else set(),
                'sort': header.sortIndicatorSection(), 'direction': header.sortIndicatorOrder(),
                'vertical': grid.verticalScrollBar().value(), 'horizontal': grid.horizontalScrollBar().value()}

    def refresh(self, *args):
        equipment_id = self.equipment['id']
        start = self.since.storage_text()
        end = self.until.storage_text()
        ascending = self.order.currentData()
        store = self.workspace.store
        view = self._saved_view or self.view_state()

        def install(rows):
            if self.workspace.store is store:
                self._saved_view = view
                self.install(rows)

        self.workspace.run(lambda: store.repairs(equipment_id=equipment_id, date_from=start or None,
                                                 date_to=end or None, ascending=ascending),
                           install, 'Читаю историю аппарата…')

    def install(self, rows):
        self.grid.install(rows)
        view, self._saved_view = self._saved_view, None
        if view:
            if view['sort'] >= 0:
                self.grid.sortByColumn(view['sort'], view['direction'])
            selection = self.grid.selectionModel()
            for i in range(self.grid.proxy.rowCount()):
                index = self.grid.proxy.index(i, 0)
                source = self.grid.proxy.mapToSource(index)
                row = self.grid.records.rows[source.row()]
                if row['id'] == view['current']:
                    selection.setCurrentIndex(index.siblingAtColumn(view.get('column', 0)),
                                              QItemSelectionModel.SelectionFlag.NoUpdate)
                if row['id'] in view['selected']:
                    selection.select(index, QItemSelectionModel.SelectionFlag.Select |
                                     QItemSelectionModel.SelectionFlag.Rows)
            self.grid.verticalScrollBar().setValue(view['vertical'])
            self.grid.horizontalScrollBar().setValue(view['horizontal'])
        self.update_selection()

    def compare(self):
        keys = self.comparison_keys()
        if not 2 <= len(keys) <= LIMIT:
            return
        store = self.workspace.store

        def show(snapshots):
            if self.workspace.store is store:
                self.show_comparison(snapshots)

        self.workspace.run(lambda: store.compare_repairs(keys), show, 'Собираю данные для сравнения…')


class HistoryPage(_HistoryContent, QWidget):
    """Real working page. The workspace stack owns it and keeps its view state."""

    def __init__(self, workspace, equipment, view=None, *, on_back=None, on_open=None, on_new=None):
        super().__init__()
        self.setObjectName('equipmentHistoryPage')
        self.setAccessibleName('История аппарата')
        self._on_back = on_back or workspace.back_page
        self._on_open = on_open or self._open_repair
        self._on_new = on_new or workspace.start_intake
        self._build_history(self, workspace, equipment, view, embedded=True)

    def go_back(self):
        return self._on_back()

    def open(self):
        row = self.grid.selected()
        if row and self.selected_rows():
            self._on_open(row['id'], self.view_state())

    def _open_repair(self, key, _view):
        self.workspace.open_repair(key, 'Документы', return_to=self.refresh)

    def new(self):
        self._on_new(self.equipment)

    def show_comparison(self, snapshots):
        if self.workspace.current_page is self:
            self.workspace.push_page(HistoryComparison(snapshots, show_heading=not self.workspace.shell_navigation), 'Сравнение ремонтов',
                                     back_label='Назад к истории')


class HistoryDialog(_HistoryContent, QDialog):
    """Stand-alone history entry point for compatibility diagnostics."""

    def __init__(self, workspace, equipment, view=None, workspace_view=False):
        super().__init__(workspace)
        self.setWindowTitle('История оборудования ' + equipment['number'])
        fit_dialog(self, 1050, 650)
        self.workspace_view = workspace_view
        outer = QVBoxLayout(self)
        self._stack = QStackedWidget()
        outer.addWidget(self._stack)
        body = QWidget()
        self._stack.addWidget(body)
        self._build_history(body, workspace, equipment, view, embedded=False)

    def open(self):
        row = self.grid.selected()
        if not row or not self.selected_rows():
            return
        workspace, equipment, view = self.workspace, self.equipment, self.view_state()
        if self.workspace_view:
            reopen = lambda: workspace.show_history(equipment, view)
        else:
            reopen = lambda: workspace.modal(HistoryDialog(workspace, equipment, view))
        self.accept()
        workspace.open_repair(row['id'], 'Документы', return_to=reopen)

    def new(self):
        self.accept()
        self.workspace.start_intake(self.equipment)

    def show_comparison(self, snapshots):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(HistoryComparison(snapshots), 1)
        actions = ActionBar()
        layout.addWidget(actions)

        def back():
            self._stack.setCurrentIndex(0)
            self._stack.removeWidget(page)
            page.deleteLater()

        button(actions, 'Назад к истории', back)
        self._stack.addWidget(page)
        self._stack.setCurrentWidget(page)

    def closeEvent(self, event):
        if self.workspace.worker:
            event.ignore()
        else:
            super().closeEvent(event)
