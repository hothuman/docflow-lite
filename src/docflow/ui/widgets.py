from PySide6.QtCore import QAbstractListModel, QAbstractTableModel, QModelIndex, Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QTableView, QVBoxLayout

from .theme import COLORS


def icon(kind='document', color='#A7BDB5', size=24):
    """Small original line icons; painted at 2x for fractional Windows scaling."""
    image = QPixmap(size*2, size*2); image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size/12, size/12); p.setPen(QPen(QColor(color), 1.4))
    if kind in ('document', 'templates'):
        p.drawRoundedRect(6, 3, 12, 18, 2, 2)
        for y in (9, 13, 17): p.drawLine(9,y,15,y)
    elif kind == 'folder':
        p.drawRoundedRect(3,7,19,14,2,2); p.drawLine(4,7,4,4);p.drawLine(4,4,11,4);p.drawLine(11,4,14,7)
    elif kind == 'check':
        p.drawEllipse(3,3,18,18);p.drawLine(7,12,10,15);p.drawLine(10,15,17,8)
    elif kind == 'fields':
        for y in (5,12,19):p.drawLine(3,y,21,y);p.drawEllipse(8 if y==12 else 14,y-2,4,4)
    elif kind == 'info':
        p.drawEllipse(3,3,18,18);p.drawLine(12,10,12,17);p.drawPoint(12,7)
    elif kind == 'people':
        p.drawEllipse(9,3,6,6);p.drawArc(5,10,14,13,0,180*16);p.drawEllipse(2,6,4,4);p.drawLine(2,14,5,12)
    elif kind == 'money':
        p.drawEllipse(2,2,20,20);p.drawText(7,17,'₽')
    elif kind == 'tool':
        p.drawLine(5,20,17,8);p.drawEllipse(14,2,8,8);p.drawLine(3,17,6,20)
    elif kind == 'gear':
        from math import cos, pi, sin
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPolygonF
        points = []
        for i in range(32):
            angle = i * pi / 16
            radius = 10 if i % 4 in (1, 2) else 8
            points.append(QPointF(12 + radius*cos(angle), 12 + radius*sin(angle)))
        p.drawPolygon(QPolygonF(points));p.drawEllipse(8,8,8,8)
    elif kind == 'history':
        p.drawEllipse(3,3,18,18);p.drawLine(12,6,12,12);p.drawLine(12,12,17,15)
    elif kind == 'search':
        p.drawEllipse(3,3,12,12);p.drawLine(14,14,21,21)
    elif kind == 'plus':
        p.drawLine(4,12,20,12);p.drawLine(12,4,12,20)
    p.end();image.setDevicePixelRatio(2)
    return QIcon(image)


def text(value='', role=None):
    label=QLabel(value);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True)
    label.setMinimumWidth(0);label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
    if role:label.setObjectName(role)
    return label


def card(title, description=''):
    widget=QFrame();widget.setObjectName('card')
    layout=QVBoxLayout(widget);layout.setContentsMargins(18,16,18,18);layout.setSpacing(12)
    layout.addWidget(text(title,'section'))
    if description:layout.addWidget(text(description,'muted'))
    return widget,layout


class DataModel(QAbstractTableModel):
    """Read-only virtual view of every loaded record, without per-cell widgets."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = None
        self._row_positions = {}
        self._column_positions = {}
        self._issues = {}
        self._mapping = {}

    def set_table(self,table):
        self.beginResetModel()
        self.table = table
        self._row_positions = {record.row_number: index for index, record in enumerate(table.records)} if table else {}
        self._column_positions = {header: index for index, header in enumerate(table.headers)} if table else {}
        self._issues.clear()
        self._mapping = {}
        self.endResetModel()

    def set_issues(self, issues, mapping):
        if not issues and not self._issues:
            return
        self._issues = {}
        for issue in issues:
            self._issues.setdefault(issue.row, []).append(issue)
        self._mapping = mapping
        if self.rowCount() and self.columnCount():
            self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, self.columnCount() - 1))

    def issues_for(self, row):
        if not self.table or not 0 <= row < self.rowCount():
            return ()
        return self._issues.get(self.table.records[row].row_number, ())

    def index_for_issue(self, issue, mapping):
        row = self._row_positions.get(issue.row, -1)
        column = self._column_positions.get(mapping.get(issue.field), 0)
        return self.index(row, column)

    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() or not self.table else len(self.table.records)
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() or not self.table else len(self.table.headers)
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not self.table or not index.isValid():return None
        column = self.table.headers[index.column()]
        value = self.table.records[index.row()].values[column]
        if role == Qt.ItemDataRole.DisplayRole:
            return value[:250]
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleDescriptionRole,
                    Qt.ItemDataRole.ForegroundRole, Qt.ItemDataRole.BackgroundRole):
            errors = [issue.message for issue in self.issues_for(index.row())
                      if self._mapping.get(issue.field) == column]
            if role == Qt.ItemDataRole.ToolTipRole:
                return '\n'.join([*errors, value]) if errors else value
            if errors and role == Qt.ItemDataRole.AccessibleDescriptionRole:
                return 'Ошибка. ' + ' '.join(errors)
            if errors and role == Qt.ItemDataRole.ForegroundRole:
                return QColor(COLORS['error'])
            if errors and role == Qt.ItemDataRole.BackgroundRole:
                color = QColor(COLORS['error'])
                color.setAlpha(36)
                return color
        return None
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if not self.table or role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):return None
        return self.table.headers[section] if orientation==Qt.Orientation.Horizontal else str(self.table.records[section].row_number)


class DataView(QTableView):
    def rowCount(self):return self.model().rowCount()
    def columnCount(self):return self.model().columnCount()


class RecordModel(QAbstractListModel):
    def __init__(self,parent=None):super().__init__(parent);self.table=None
    def set_table(self,table):self.beginResetModel();self.table=table;self.endResetModel()
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() or not self.table else len(self.table.records)
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if self.table and index.isValid() and role==Qt.ItemDataRole.DisplayRole:
            return f'Запись {index.row()+1} · строка {self.table.records[index.row()].row_number}'
        return None
