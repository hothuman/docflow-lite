"""Cached widths, exact money and persistent user choices without per-cell widgets."""
from PySide6.QtCore import Qt,QSortFilterProxyModel,Signal,QSettings
from PySide6.QtWidgets import QTableView,QPushButton,QMessageBox,QHeaderView,QAbstractItemView
from .models import RowsModel
from .presentation import MONEY,display
from ..settings import load_widths,save_widths
class Grid(QTableView):
 openRequested=Signal()
 def __init__(self,columns,parent=None,settings_key=None):
  super().__init__(parent);self.records=RowsModel(columns,self);self.proxy=QSortFilterProxyModel(self);self.proxy.setSourceModel(self.records);self.proxy.setSortRole(Qt.ItemDataRole.UserRole);self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive);self.proxy.setFilterKeyColumn(0);self.proxy.setFilterRole(Qt.ItemDataRole.UserRole+1);self.setModel(self.proxy);self.setSortingEnabled(True);self.sortByColumn(-1,Qt.SortOrder.AscendingOrder)
  self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows);self.setSelectionMode(QTableView.SelectionMode.SingleSelection);self.setAlternatingRowColors(True);self.setWordWrap(False);self.setTextElideMode(Qt.TextElideMode.ElideRight);self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.setMinimumHeight(100);self.setMinimumWidth(0)
  self.verticalHeader().hide();self.verticalHeader().setDefaultSectionSize(38);header=self.horizontalHeader();header.setMinimumSectionSize(48);header.setStretchLastSection(False);header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
  self._sizing=False;self._preferred={};self._user_widths={};self.settings_key=settings_key
  if settings_key:
   self._user_widths=load_widths(settings_key)
  header.sectionResized.connect(self._remember);self.cache_widths();self.fit_columns()
 def _remember(self,index,old,new):
  if self._sizing:return
  self._user_widths[index]=max(48,new)
  if self.settings_key:
   self.preferences_saved=save_widths(self.settings_key,self._user_widths)
   if not self.preferences_saved:self.horizontalHeader().setToolTip('Ширина изменена для текущего окна. Не удалось сохранить настройки: проверьте доступ к папке конфигурации.')
 def cache_widths(self):
  fm=self.fontMetrics();self._preferred={};self._minimum={};self._content_minimum={}
  for i,(key,title) in enumerate(self.records.columns):
   if key in MONEY:
    values=[display(key,r) for r in self.records.rows];content=max((fm.horizontalAdvance(value) for value in values),default=fm.horizontalAdvance('9 999,00 ₽'))+26;self._content_minimum[i]=max(48,content);width=max(105,content)
   elif key in ('status','state','state_label','financial_status'):width=164
   elif key.endswith('_at'):width=134
   elif key in ('number','equipment_number'):width=105
   elif key in ('quantity','unit','version','size','voided','archived'):width=76
   else:width=180 if key in ('name','model','equipment_label','kind') else 145
   self._minimum[i]=max(48,fm.horizontalAdvance(title)+34);self._preferred[i]=max(width,self._minimum[i])
 def fit_columns(self):
  if self._sizing or not self.records.columns:return
  self._sizing=True
  try:
   available=max(100,self.viewport().width()-2);visible=list(range(len(self.records.columns)));widths={i:self._user_widths.get(i,self._preferred.get(i,130)) for i in visible}
   secondary=('description','complaint','notes','void_reason','source','path','logo_path','contact','email','phone','legal_name','serial','prepared_by','client','financial_status','status','received_at','created_at','changed_at','method','unit','kind','defects','item_text')
   for key in secondary:
    if sum(widths[i] for i in visible)<=available:break
    if len(visible)>3:
     for i in [i for i in visible if self.records.columns[i][0]==key]:visible.remove(i)
   extra=sum(widths[i] for i in visible)-available
   for i in visible:
    if extra<=0:break
    if self.records.columns[i][0] not in MONEY and i not in self._user_widths:
     amount=min(extra,max(0,widths[i]-self._minimum.get(i,75)));widths[i]-=amount;extra-=amount
   # At high DPI the header may be wider than its values. Keep every
   # amount visible before preserving full headers or preferred user widths.
   # Header tooltips retain the full labels; preferences are not overwritten.
   extra=sum(widths[i] for i in visible)-available
   for i in visible:
    if extra<=0:break
    key=self.records.columns[i][0]
    if key in MONEY:minimum=self._content_minimum[i]
    elif key in ('number','equipment_number'):
     minimum=max(48,max((self.fontMetrics().horizontalAdvance(display(key,r)) for r in self.records.rows),default=22)+26)
    else:continue
    amount=min(extra,max(0,widths[i]-minimum));widths[i]-=amount;extra-=amount
   remaining=available-sum(widths[i] for i in visible)
   if remaining>0 and visible:
    stretch=next((i for i in visible if self.records.columns[i][0] in ('name','model','equipment_label','client')),visible[0]);widths[stretch]+=remaining
   for i in range(len(self.records.columns)):
    self.setColumnHidden(i,i not in visible)
    if i in visible:self.horizontalHeader().resizeSection(i,widths[i])
  finally:self._sizing=False
 def resizeEvent(self,event):super().resizeEvent(event);self.fit_columns()
 def install(self,rows):
  selected=self.selected();key=selected.get('id') if selected else None;self.records.install(rows);self.cache_widths();self.fit_columns()
  if key:
   for i,row in enumerate(self.records.rows):
    if row.get('id')==key:
     proxy=self.proxy.mapFromSource(self.records.index(i,0))
     if proxy.isValid():self.selectRow(proxy.row())
     break
 def selected(self):
  index=self.currentIndex()
  if not index.isValid():return None
  row=self.proxy.mapToSource(index).row();return self.records.rows[row] if 0<=row<len(self.records.rows) else None
 def keyPressEvent(self,event):
  if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.openRequested.emit();event.accept()
  else:super().keyPressEvent(event)
def button(layout,title,fn,primary=False,danger=False):
 b=QPushButton(title);b.setAccessibleName(title)
 if primary:b.setObjectName('primary')
 if danger:b.setObjectName('danger')
 b.clicked.connect(fn);layout.addWidget(b);return b
def confirm(parent,text):return QMessageBox.question(parent,'Подтверждение',text,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes
