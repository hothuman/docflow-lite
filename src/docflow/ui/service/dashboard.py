"""Daily work desk: four tasks, confirmed metrics and a resumable repair list."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QFrame,QScrollArea,QDialog,QPlainTextEdit,QSizePolicy
from ..flow import ActionBar
from ..widgets import text,card
from .widgets import Grid,button
from .presentation import audit_text
from ...service.validation import rub

class Dashboard(QWidget):
 def __init__(self,workspace):
  super().__init__(workspace);self.workspace=workspace;self.setObjectName('servicePage')
  outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(0,6,4,8);layout.setSpacing(16);scroll.setWidget(body);outer.addWidget(scroll)
  layout.addWidget(text('Что делаем сейчас?','section'))
  self.actions=ActionBar();layout.addWidget(self.actions)
  self.new_button=button(self.actions,'Новый ремонт',workspace.start_intake,primary=True)
  self.search_button=button(self.actions,'Найти оборудование / ремонт',workspace.search_all)
  self.continue_button=button(self.actions,'Продолжить работу',workspace.continue_repair)
  self.documents_button=button(self.actions,'Документы',lambda:workspace.tabs.setCurrentIndex(5))
  self.catalog_button=button(self.actions,'Каталог',workspace.open_catalog);self.backup_button=button(self.actions,'Резервная копия',workspace.backup)
  self.action_buttons={'new':self.new_button,'search':self.search_button,'continue':self.continue_button,'documents':self.documents_button,'catalog':self.catalog_button,'backup':self.backup_button}
  self.apply_actions()
  self.preference_note=text(self.preference_warning,'muted');self.preference_note.setWordWrap(True);self.preference_note.setVisible(bool(self.preference_warning));layout.addWidget(self.preference_note)
  for control in (self.new_button,self.search_button,self.continue_button,self.documents_button):control.setMinimumHeight(50)
  self.cards=[];self.values={};self.metric_grid=QGridLayout();layout.addLayout(self.metric_grid)
  for key,title in [('active','В работе'),('ready','Готовы к выдаче'),('attention','Требует внимания')]:
   panel=QFrame();panel.setObjectName('metricCard');panel.setMaximumHeight(80);box=QVBoxLayout(panel);box.setContentsMargins(14,8,14,8);box.addWidget(text(title,'muted'));value=text('—','metricValue');box.addWidget(value);self.values[key]=value;self.cards.append(panel)
  self.finance_hint=text('','muted');layout.addWidget(self.finance_hint)
  self.onboarding,help_body=card('Первый ремонт','Добавьте клиента → оборудование → ремонт. Всё это можно сделать в одной форме «Новый ремонт».')
  helpers=ActionBar();help_body.addWidget(helpers);button(helpers,'Начать приёмку',workspace.start_intake,primary=True);button(helpers,'Как работать за 5 минут',workspace.quick_help);layout.addWidget(self.onboarding)
  layout.addWidget(text('Последние ремонты · нажмите строку, чтобы продолжить','section'))
  self.empty=text('Обращений пока нет. Начните с кнопки «Новый ремонт».','empty');layout.addWidget(self.empty)
  self.recent=Grid([('number','Ремонт №'),('equipment_label','Аппарат'),('client','Клиент'),('received_at','Приёмка'),('status','Статус'),('total','Стоимость')]);self.recent.setMinimumHeight(160);self.recent.setMaximumHeight(340);layout.addWidget(self.recent,1);self.recent.clicked.connect(self.open_recent);self.recent.openRequested.connect(self.open_recent)
  self.totals=QWidget();bar=QHBoxLayout(self.totals);bar.setContentsMargins(0,0,0,0)
  for key,title in [('equipment','Аппаратов'),('debt','Подтверждённый остаток'),('approval','Согласование'),('parts','Запчасти')]:
   value=text('—','muted');value.setAccessibleName(title);value.setToolTip(title);self.values[key]=value;holder=QVBoxLayout();holder.addWidget(text(title,'muted'));holder.addWidget(value);bar.addLayout(holder)
  layout.addWidget(self.totals);self._columns=0;self.arrange()
 def apply_actions(self):
  from .dashboard_preferences import load_actions
  order,warning=load_actions();self.preference_warning=warning
  while self.actions.flow.count():self.actions.flow.takeAt(0)
  for key,control in self.action_buttons.items():control.setVisible(key in order)
  for key in order:self.actions.addWidget(self.action_buttons[key])
  from PySide6.QtWidgets import QWidget
  for a,b in zip(order,order[1:]):QWidget.setTabOrder(self.action_buttons[a],self.action_buttons[b])
  self.actions.updateGeometry()
  if hasattr(self,'preference_note'):self.preference_note.setText(warning);self.preference_note.setVisible(bool(warning))
 def arrange(self):
  columns=3 if self.width()>=600 else 1
  if columns==self._columns:return
  self._columns=columns
  for i,panel in enumerate(self.cards):self.metric_grid.addWidget(panel,i//columns,i%columns)
  for i in range(3):self.metric_grid.setColumnStretch(i,1 if i<columns else 0)
 def resizeEvent(self,event):super().resizeEvent(event);self.arrange()
 def install(self,data):
  for key,label in self.values.items():label.setText(rub(data[key]) if key=='debt' else str(data[key]))
  self.totals.setToolTip('Аппаратов / подтверждённый остаток / на согласовании / ожидают запчасти')
  n=data.get('finance_unknown',0);self.finance_hint.setText(f'Неполная история расчётов: {n}. Неизвестные оплаты не считаются нулём или долгом.');self.finance_hint.setVisible(n>0)
  rows=[{**r,'equipment_label':r['equipment_number']+' · '+r['model']} for r in data['recent_repairs']]
  self.recent.install(rows);self.empty.setVisible(not rows);self.recent.setVisible(bool(rows));self.onboarding.setVisible(not rows)
 def open_recent(self,*args):
  row=self.recent.selected()
  if row:self.workspace.open_repair(row['id'])
class DiagnosticsDialog(QDialog):
 def __init__(self,workspace,rows,numbers,log_text):
  super().__init__(workspace);self.setWindowTitle('История действий и локальная диагностика');self.resize(900,600);layout=QVBoxLayout(self);layout.addWidget(text('Фактические локальные события. Подробности могут содержать рабочие данные; программа никуда их не отправляет.','muted'));self.grid=Grid([('created_at','Когда'),('event_text','Событие')]);self.grid.install([{**r,'event_text':audit_text(r,numbers)} for r in rows]);layout.addWidget(self.grid,1);self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(150);self.detail.setPlaceholderText('Выберите событие, чтобы раскрыть технические подробности.');layout.addWidget(self.detail);self.grid.selectionModel().currentRowChanged.connect(self.selected);self.log_text=log_text;bar=ActionBar();layout.addWidget(bar);button(bar,'Показать локальный журнал ошибок',lambda:self.detail.setPlainText(self.log_text or 'Ошибок в локальном журнале нет.'));button(bar,'Закрыть',self.accept)
 def selected(self,*args):
  row=self.grid.selected()
  if row:self.detail.setPlainText(row['entity']+' / '+row['action']+'\n'+row['detail'])
