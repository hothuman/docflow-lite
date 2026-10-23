"""Lightweight Qt tables backed by immutable dictionaries, not per-cell widgets."""
from PySide6.QtCore import QAbstractTableModel,Qt,QSortFilterProxyModel
from PySide6.QtGui import QColor
from ...service.validation import rub
from ...service.statuses import STATUSES

class RowsModel(QAbstractTableModel):
    def __init__(self,columns,parent=None):
        super().__init__(parent);self.columns=columns;self.rows=[]
    def rowCount(self,parent=None):return 0 if parent and parent.isValid() else len(self.rows)
    def columnCount(self,parent=None):return 0 if parent and parent.isValid() else len(self.columns)
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():return None
        row=self.rows[index.row()];key=self.columns[index.column()][0];v=row.get(key,'')
        if role==Qt.ItemDataRole.UserRole:return v
        if role in (Qt.ItemDataRole.DisplayRole,Qt.ItemDataRole.ToolTipRole):
            if key in ('total','paid','balance','debt'):return rub(v)
            if key in ('status','old_status','new_status'):return STATUSES.get(v,(v,''))[0]
            if key=='voided':return 'Исправлена' if v else 'Действует'
            if key=='kind':return {'work':'Работа','part':'Запчасть','payment':'Оплата','refund':'Возврат'}.get(v,v)
            return str(v)
        if role==Qt.ItemDataRole.ForegroundRole:
            if key=='status':return QColor(STATUSES.get(v,('','#aaaaaa'))[1])
            if key=='balance' and v>0:return QColor('#ed9aab')
        return None
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole:return self.columns[section][1] if orientation==Qt.Orientation.Horizontal else str(section+1)
    def install(self,rows):self.beginResetModel();self.rows=list(rows);self.endResetModel()
