"""Selected records and read-only relationships in the workshop lists."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ..flow import ActionBar
from ..widgets import section, text
from .presentation import display
from .widgets import Grid, button


def selected_context(key, row):
    if key == 'equipment':
        return f"Аппарат № {row['number']} · {row['model']} · Владелец: {row['owner'] or 'не указан'}"
    if key == 'clients':
        contact = ' · '.join(filter(None, (row.get('contact'), row.get('phone'), row.get('email'))))
        return f"{row['name']} · {contact}" if contact else row['name']
    if key == 'documents':
        return f"Ремонт № {row['number']} · {display('kind', row)} · Версия {row['version']}"
    if key == 'estimates':
        return (f"Ремонт № {row['number']} · {display('kind', row)} · Версия {row['version']}"
                f" · {display('total', row)}")
    return (f"Ремонт № {row['number']} · Стоимость {display('total', row)} · "
            f"Учтено {display('paid', row)} · Остаток {display('balance', row)}")


class ClientOverview(QWidget):
    """Keep historical customer identity separate from current ownership."""

    def __init__(self, workspace, client):
        super().__init__(workspace)
        self.workspace = workspace
        self.setWindowTitle('Карточка клиента')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAccessibleName('Контакты и связи клиента')
        layout.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 4, 0)
        body.setSpacing(8)

        card, info = section(client['name'], role='serviceContext')
        contact = ' · '.join(filter(None, (client.get('contact'), client.get('phone'), client.get('email'))))
        info.addWidget(text(contact or 'Контакты пока не указаны', 'muted'))
        body.addWidget(card)
        owned = [row for row in workspace.cache['journal_equipment'].values() if row['owner_id'] == client['id']]
        repairs = [row for row in workspace.cache['repairs'] if row['client_id'] == client['id']]
        self.equipment = self._list(body, 'Аппараты во владении', owned, [
            ('number', 'Постоянный №'), ('model', 'Модель'), ('serial', 'Серийный №'), ('archived', 'Состояние'),
        ], 'История аппарата', workspace.show_history)
        self.repairs = self._list(body, 'Обращения клиента', repairs, [
            ('number', 'Ремонт №'), ('equipment_label', 'Аппарат'), ('status', 'Статус'), ('balance', 'Остаток'),
        ], 'Открыть ремонт', lambda row: workspace.open_repair(row['id']))
        body.addStretch()

    def _list(self, body, title, rows, columns, action, open_record):
        panel, layout = section(f'{title} · {len(rows)}')
        body.addWidget(panel)
        grid = Grid(columns)
        grid.setObjectName('serviceLedger')
        grid.setShowGrid(False)
        grid.setAccessibleName(title)
        if not rows:
            layout.addWidget(text('Связанных записей пока нет.', 'muted'))
            return grid
        grid.install(rows)
        grid.fit_few_rows()
        grid.setMaximumHeight(min(220, grid.maximumHeight()))
        grid.selectRow(0)
        layout.addWidget(grid)
        bar = ActionBar()
        layout.addWidget(bar)

        def activate(*_):
            row = grid.selected()
            if row:
                open_record(row)

        control = button(bar, action, activate)
        grid.selectionModel().currentRowChanged.connect(lambda *_: control.setEnabled(grid.selected() is not None))
        grid.openRequested.connect(activate)
        grid.doubleClicked.connect(activate)
        return grid
