"""Virtual localized tables; raw identities and payloads stay out of search."""
import html
from PySide6.QtCore import QAbstractTableModel,Qt
from PySide6.QtGui import QColor
from ...service.statuses import STATUSES
from .presentation import display,sort_value,MONEY
from ..theme import COLORS
class RowsModel(QAbstractTableModel):
 def __init__(self,columns,parent=None):super().__init__(parent);self.columns=columns;self.rows=[];self.search=[]
 def rowCount(self,parent=None):return 0 if parent and parent.isValid() else len(self.rows)
 def columnCount(self,parent=None):return 0 if parent and parent.isValid() else len(self.columns)
 def data(self,index,role=Qt.ItemDataRole.DisplayRole):
  if not index.isValid():return None
  row=self.rows[index.row()];key=self.columns[index.column()][0];value=row.get(key,'')
  if role==Qt.ItemDataRole.UserRole+1:return self.search[index.row()]
  if role==Qt.ItemDataRole.UserRole:return sort_value(key,row)
  if role==Qt.ItemDataRole.DisplayRole:return display(key,row)
  if role==Qt.ItemDataRole.ToolTipRole:
   lines=[title+': '+display(k,row) for k,title in self.columns]
   if row.get('path'):lines.append('Локальный файл: '+str(row['path']))
   return '<qt>'+'<br>'.join(html.escape(x) for x in lines)+'</qt>'
  if role==Qt.ItemDataRole.TextAlignmentRole and key in MONEY|{'quantity','version'}:return Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter
  if role==Qt.ItemDataRole.ForegroundRole:
   if key=='status':return QColor(STATUSES.get(value,('','#aaaaaa'))[1])
   if key=='balance' and type(value) is int and value>0:return QColor(COLORS['error'])
  return None
 def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
  if role in (Qt.ItemDataRole.DisplayRole,Qt.ItemDataRole.ToolTipRole):return self.columns[section][1] if orientation==Qt.Orientation.Horizontal else str(section+1)
 def install(self,rows):
  self.beginResetModel();self.rows=list(rows)
  searchable={key for key,title in self.columns}|{'manufacturer','model','serial','equipment_number','client','name','legal_name','contact','phone','email','complaint','defects','plan','item_text','notes','number','description','comment','path'}
  self.search=[' '.join(str(row.get(key,'')) for key in searchable)+' '+' '.join(display(key,row) for key,title in self.columns) for row in self.rows];self.endResetModel()
