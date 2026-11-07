
"""Two presentations of the same selected repair; amounts come from Service."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from ..flow import ActionBar
from ..widgets import text
from .presentation import date_text, display
from .widgets import button


class RepairInspector(QScrollArea):
    def __init__(self, open_repair, open_history):
        super().__init__()
        self.setObjectName('repairInspector')
        self.setAccessibleName('Сведения о выбранном ремонте')
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QFrame()
        content.setObjectName('journalInspectorCard')
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        layout.addWidget(text('ВЫБРАННЫЙ РЕМОНТ', 'eyebrow'))
        self.title = text('', 'journalSelectionTitle')
        layout.addWidget(self.title)
        self.fields = {}
        for key in ('status', 'equipment_number', 'serial', 'client', 'owner', 'total', 'paid', 'balance', 'context'):
            label = text('', 'journalDetail')
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse |
                                          Qt.TextInteractionFlag.TextSelectableByKeyboard)
            self.fields[key] = label
            layout.addWidget(label)
        actions = ActionBar()
        self.open_button = button(actions, 'Открыть ремонт', open_repair, primary=True)
        self.open_button.setAccessibleName('Открыть выбранный ремонт')
        self.history_button = button(actions, 'История аппарата', open_history)
        layout.addWidget(actions)
        layout.addStretch()
        self.update_repair(None, None, False)

    def update_repair(self, row, equipment, ready):
        self.title.setText('Ремонт № '+str(row['number']) if row else 'Нет выбранного ремонта')
        fields = {}
        if row:
            fields = {
                'status': ('Статус', display('status', row)),
                'equipment_number': ('Аппарат', f"№ {row['equipment_number']} · {row['model']}"),
                'serial': ('Серийный номер', row.get('serial')),
                'client': ('Заказчик', row.get('client')),
                'owner': ('Владелец', equipment.get('owner') if equipment else None),
                'total': ('Стоимость', display('total', row)),
                'paid': ('Учтено оплат', display('paid', row)),
                'balance': ('Остаток', display('balance', row)),
                'context': ('Обновлено', date_text(row.get('updated_at'))),
            }
        for key, label in self.fields.items():
            name, value = fields.get(key, ('', None))
            message = f'{name}: {value}' if value else ''
            label.setText(message)
            label.setAccessibleName(message)
            label.setToolTip(message)
            label.setVisible(bool(message))
        balance = self.fields['balance']
        debt = row is not None and (row.get('balance') or 0) > 0
        if balance.property('debt') != debt:
            balance.setProperty('debt', debt)
            balance.style().unpolish(balance)
            balance.style().polish(balance)
        self.open_button.setVisible(row is not None)
        self.open_button.setEnabled(ready and row is not None)
        self.history_button.setVisible(equipment is not None)
        self.history_button.setEnabled(ready and equipment is not None)


class JournalPanels(QStackedWidget):
    """Reparent the inspector when space changes; the table and search stay alive."""
    def __init__(self, journal, list_page, body, toolbar, open_repair, history):
        super().__init__()
        self.journal = journal
        self.list_page = QScrollArea()
        self.list_page.setObjectName('repairJournalScroll')
        self.list_page.setAccessibleName('Прокручиваемая область журнала')
        self.list_page.setFrameShape(QFrame.Shape.NoFrame)
        self.list_page.setWidgetResizable(True)
        self.list_page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.list_page.setWidget(list_page)
        self.list_content = list_page
        self.body = body
        self.addWidget(self.list_page)
        self.context_button = button(toolbar, 'Кратко о ремонте', self.show_summary)
        self.context_button.setAccessibleDescription('Стоимость, остаток и история выбранного аппарата')
        self.summary = QWidget()
        self.summary.setAccessibleName('Кратко о выбранном ремонте')
        self.summary_layout = QVBoxLayout(self.summary)
        self.summary_layout.setContentsMargins(0, 4, 0, 0)
        self.back = button(self.summary_layout, 'К журналу ремонтов', self.return_to_list)
        self.addWidget(self.summary)
        self.escape = QShortcut(QKeySequence('Esc'), self.summary)
        self.escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.escape.activated.connect(self.return_to_list)
        self.inspector = RepairInspector(open_repair, history)
        self.compact = None
        self.context = None

    def responsive(self, width):
        metrics = self.fontMetrics()
        # Reserve an actual usable form and a full first row. In a short
        # window QScrollArea takes the overflow, not the child controls.
        self.list_content.setMinimumHeight(max(272, metrics.height() * 17))
        action_width = max(self.inspector.open_button.sizeHint().width(),
                           self.inspector.history_button.sizeHint().width())
        panel_width = max(255, metrics.horizontalAdvance('ВЫБРАННЫЙ РЕМОНТ') + 42,
                          action_width + self.inspector.verticalScrollBar().sizeHint().width() + 28)
        compact = width < panel_width + max(620, metrics.horizontalAdvance('Ремонт № · Аппарат · Заказчик') * 2)
        if compact == self.compact:
            return
        was_summary = self.currentWidget() is self.summary
        self.compact = compact
        self.context_button.setVisible(compact)
        if compact:
            self.body.removeWidget(self.inspector)
            self.inspector.setMinimumWidth(0)
            self.inspector.setMaximumWidth(16777215)
            self.summary_layout.addWidget(self.inspector, 1)
        else:
            self.summary_layout.removeWidget(self.inspector)
            self.inspector.setFixedWidth(panel_width)
            self.body.addWidget(self.inspector)
            if was_summary:
                self.return_to_list()
        self.inspector.show()

    def show_summary(self):
        if not self.journal.grid.selected():
            return
        self.context = self.journal.view_context()
        self.setCurrentWidget(self.summary)
        self.back.setFocus()

    def return_to_list(self, restore=True):
        if self.currentWidget() is not self.summary:
            return
        self.setCurrentWidget(self.list_page)
        if restore and self.context:
            self.journal.restore_view(self.context)
        self.context = None

    def update_repair(self, row, equipment, ready):
        if not row:
            self.return_to_list(restore=False)
        self.context_button.setEnabled(ready and row is not None)
        self.inspector.update_repair(row, equipment, ready)
