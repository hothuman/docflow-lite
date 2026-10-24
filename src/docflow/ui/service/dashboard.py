"""SQLite overview, compact at high DPI; raw audit is secondary."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QFrame,QScrollArea,QDialog,QPlainTextEdit,QBoxLayout,QSizePolicy,QPushButton,QMenu
from ..flow import ActionBar
from ..widgets import text
from .widgets import Grid,button
from .presentation import audit_text
from ...service.validation import rub
class Dashboard(QWidget):
 def __init__(self,workspace):
  super().__init__(workspace);self.workspace=workspace;self.setObjectName('servicePage');outer=QVBoxLayout(self);outer.setContentsMargins(0,4,0,0);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(6,4,6,4);layout.setSpacing(10);scroll.setWidget(body);outer.addWidget(scroll)
  self.cards=[];self.values={};self.metric_titles={};self.metric_layouts={};self.metric_grid=QGridLayout();self.metric_grid.setSpacing(8);layout.addLayout(self.metric_grid)
  for key,title in [('equipment','Оборудование'),('active','Активные ремонты'),('approval','Ожидают согласования'),('parts','Ожидают запчастей'),('ready','Готовы к выдаче'),('debt','Задолженность')]:
   card=QFrame();card.setObjectName('metricCard');content=QVBoxLayout(card);content.setContentsMargins(10,8,10,8);content.setSpacing(4);label=text(title,'muted');content.addWidget(label,1);self.metric_titles[key]=label;self.metric_layouts[key]=content;value=text('—','metricValue');value.setSizePolicy(QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Preferred);value.setAccessibleName(title);content.addWidget(value);self.cards.append(card);self.values[key]=value
  self.actions=ActionBar();layout.addWidget(self.actions);self.new_button=button(self.actions,'Новый ремонт',workspace.new_repair,primary=True);self.equipment_button=button(self.actions,'Добавить оборудование',workspace.new_equipment);button(self.actions,'Найти аппарат',workspace.find_equipment);self.history_button=button(self.actions,'Открыть историю',workspace.dashboard_history);self.backup_button=button(self.actions,'Резервная копия',workspace.backup)
  self.more=QPushButton('Ещё действия');self.more.setAccessibleName('Ещё действия обзора');menu=QMenu(self.more)
  for title,fn in [('Добавить оборудование',workspace.new_equipment),('Открыть историю',workspace.dashboard_history),('Резервная копия',workspace.backup)]:menu.addAction(title,fn)
  self.more.setMenu(menu);self.actions.addWidget(self.more);heading=ActionBar();layout.addWidget(heading);heading.addWidget(text('Последние ремонты','section'));button(heading,'Все ремонты',lambda:workspace.tabs.setCurrentIndex(2))
  self.empty=text('Ремонтов пока нет. Добавьте оборудование и создайте первое обращение.','empty');layout.addWidget(self.empty);self.recent=Grid([('number','Ремонт №'),('equipment_label','Аппарат'),('client','Клиент'),('received_at','Приёмка'),('status','Статус'),('total','Стоимость')]);self.recent.setAccessibleName('Последние ремонты: нажмите строку или Enter для открытия');layout.addWidget(self.recent,1);self.recent.clicked.connect(self.open_recent);self.recent.openRequested.connect(self.open_recent)
  secondary=ActionBar();layout.addWidget(secondary);button(secondary,'История действий / диагностика',workspace.diagnostics);self.summary=text('Показатели из локальной базы. Оплаты учитываются вручную.','muted');layout.addWidget(self.summary);self._columns=0;self._compact=None;self.arrange()
 def arrange(self):
  compact=self.width()<920 or self.height()<420
  if compact!=self._compact:
   self._compact=compact;self.setProperty('compact',compact);short={'equipment':'Оборудование','active':'Активные','approval':'Согласование','parts':'Запчасти','ready':'К выдаче','debt':'Долг'};full={'equipment':'Оборудование','active':'Активные ремонты','approval':'Ожидают согласования','parts':'Ожидают запчастей','ready':'Готовы к выдаче','debt':'Задолженность'}
   for key,box in self.metric_layouts.items():box.setDirection(QBoxLayout.Direction.LeftToRight if compact else QBoxLayout.Direction.TopToBottom);box.setContentsMargins(8,4 if compact else 8,8,4 if compact else 8);self.metric_titles[key].setText((short if compact else full)[key])
   for b in (self.equipment_button,self.history_button,self.backup_button):b.setVisible(not compact)
   self.more.setVisible(compact)
   for widget in [self,*self.findChildren(QPushButton),*self.values.values()]:widget.style().unpolish(widget);widget.style().polish(widget)
  columns=6 if self.width()>=1080 and not compact else 3 if self.width()>=520 else 2
  if columns==self._columns:return
  self._columns=columns
  for i,card in enumerate(self.cards):self.metric_grid.addWidget(card,i//columns,i%columns)
  for i in range(6):self.metric_grid.setColumnStretch(i,1 if i<columns else 0)
 def resizeEvent(self,event):super().resizeEvent(event);self.arrange()
 def install(self,data):
  for key,label in self.values.items():label.setText(rub(data[key]) if key=='debt' else str(data[key]))
  rows=[{**r,'equipment_label':r['equipment_number']+' · '+r['model']} for r in data['recent_repairs']];self.recent.install(rows);self.empty.setVisible(not rows);self.recent.setVisible(bool(rows))
 def open_recent(self,*args):
  row=self.recent.selected()
  if row:self.workspace.open_repair(row['id'])
class DiagnosticsDialog(QDialog):
 def __init__(self,workspace,rows,numbers,log_text):
  super().__init__(workspace);self.setWindowTitle('История действий и локальная диагностика');self.resize(900,600);layout=QVBoxLayout(self);layout.addWidget(text('Фактические локальные события. Подробности могут содержать рабочие данные; программа никуда их не отправляет.','muted'));self.grid=Grid([('created_at','Когда'),('event_text','Событие')]);self.grid.install([{**r,'event_text':audit_text(r,numbers)} for r in rows]);layout.addWidget(self.grid,1);self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(150);self.detail.setPlaceholderText('Выберите событие, чтобы раскрыть технические подробности.');layout.addWidget(self.detail);self.grid.selectionModel().currentRowChanged.connect(self.selected);self.log_text=log_text;bar=ActionBar();layout.addWidget(bar);button(bar,'Показать локальный журнал ошибок',lambda:self.detail.setPlainText(self.log_text or 'Ошибок в локальном журнале нет.'));button(bar,'Закрыть',self.accept)
 def selected(self,*args):
  row=self.grid.selected()
  if row:self.detail.setPlainText(row['entity']+' / '+row['action']+'\n'+row['detail'])
