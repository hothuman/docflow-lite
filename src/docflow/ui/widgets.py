from PySide6.QtCore import QAbstractListModel, QAbstractTableModel, QModelIndex, Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QTableView, QVBoxLayout


def icon(kind='document', color='#52647A', size=24):
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
    def __init__(self,parent=None):super().__init__(parent);self.table=None
    def set_table(self,table):
        self.beginResetModel();self.table=table;self.endResetModel()
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() or not self.table else len(self.table.records)
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() or not self.table else len(self.table.headers)
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not self.table or not index.isValid():return None
        if role in (Qt.ItemDataRole.DisplayRole,Qt.ItemDataRole.ToolTipRole):
            value=self.table.records[index.row()].values[self.table.headers[index.column()]]
            return value if role==Qt.ItemDataRole.ToolTipRole else value[:250]
        return None
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if not self.table or role!=Qt.ItemDataRole.DisplayRole:return None
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
