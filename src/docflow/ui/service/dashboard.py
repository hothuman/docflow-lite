"""Actionable local service overview, with compact tables and honest metrics."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QFrame,QScrollArea,QDialog,QPlainTextEdit,QSizePolicy,QPushButton,QMenu
from ..flow import ActionBar
from ..widgets import text,card
from .widgets import Grid,button
from .presentation import audit_text
from ...service.validation import rub

class Dashboard(QWidget):
 def __init__(self,workspace):
  super().__init__(workspace);self.workspace=workspace;self.setObjectName('servicePage')
  outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
  scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(0,8,4,8);layout.setSpacing(18);scroll.setWidget(body);outer.addWidget(scroll)
  self.actions=ActionBar();layout.addWidget(self.actions)
  self.new_button=button(self.actions,'Новый ремонт',workspace.new_repair,primary=True)
  self.equipment_button=button(self.actions,'Добавить оборудование',workspace.new_equipment)
  button(self.actions,'Найти аппарат',workspace.find_equipment)
  self.history_button=button(self.actions,'История аппарата',workspace.dashboard_history)
  self.backup_button=button(self.actions,'Резервная копия',workspace.backup)
  self.more=QPushButton('Ещё действия');menu=QMenu(self.more)
  for title,fn in [('Добавить оборудование',workspace.new_equipment),('История аппарата',workspace.dashboard_history),('Резервная копия',workspace.backup)]:menu.addAction(title,fn)
  self.more.setMenu(menu);self.more.setAccessibleName('Ещё действия обзора');self.actions.addWidget(self.more)
  self.cards=[];self.values={};self.metric_titles={};self.metric_grid=QGridLayout();self.metric_grid.setSpacing(12);layout.addLayout(self.metric_grid)
  self.queue_frame,self.queue_body=card('Очередь работ','Следующие этапы по текущим обращениям.')
  for key,title in [('active','В работе'),('ready','Готовы к выдаче'),('debt','Остаток к оплате'),('equipment','Оборудование'),('approval','На согласовании'),('parts','Ожидают запчастей')]:
   frame=QFrame();frame.setObjectName('metricCard');frame.setMaximumHeight(86);frame.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Maximum)
   content=QVBoxLayout(frame);content.setContentsMargins(16,10,16,10);content.setSpacing(4)
   label=text(title,'muted');value=text('—','metricValue');value.setAccessibleName(title);content.addWidget(label);content.addWidget(value)
   self.metric_titles[key]=label;self.cards.append(frame);self.values[key]=value
   if key in ('ready','approval','parts'):frame.setObjectName('queueRow');self.queue_body.addWidget(frame)
  recent_frame,recent_body=card('Последние обращения','Откройте строку, чтобы продолжить ремонт. Номер обращения отделён от номера аппарата.')
  recent_frame.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Maximum)
  heading=ActionBar();recent_body.addWidget(heading);button(heading,'Открыть журнал ремонтов',lambda:workspace.tabs.setCurrentIndex(2))
  self.empty=text('Обращений пока нет. Добавьте клиента и оборудование, затем оформите первый ремонт.','empty');recent_body.addWidget(self.empty)
  self.recent=Grid([('number','Ремонт №'),('equipment_label','Аппарат'),('client','Клиент'),('received_at','Приёмка'),('status','Статус'),('total','Стоимость')]);self.recent.setAccessibleName('Последние ремонты: нажмите строку или Enter для открытия')
  recent_body.addWidget(self.recent);self.recent.clicked.connect(self.open_recent);self.recent.openRequested.connect(self.open_recent)
  self.recent_frame=recent_frame;self.overview_grid=QGridLayout();self.overview_grid.setSpacing(16);layout.addLayout(self.overview_grid)
  helper,help_body=card('Рабочий проект','Начните с чистого журнала или перенесите историю через проверяемый импорт.')
  self.onboarding=helper;helper.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Maximum)
  helpers=ActionBar();help_body.addWidget(helpers);button(helpers,'Добавить клиента',workspace.new_client);button(helpers,'Импортировать историю',workspace.import_history);button(helpers,'Настройки проекта',lambda:workspace.tabs.setCurrentIndex(7));layout.addWidget(helper)
  secondary=ActionBar();layout.addWidget(secondary);button(secondary,'История действий / диагностика',workspace.diagnostics)
  self.summary=text('Суммы отражают внутренний учёт. Оплаты и согласования отмечаются вручную.','muted');layout.addWidget(self.summary)
  self.empty_filler=QWidget();layout.addWidget(self.empty_filler,1);self._columns=0;self._compact=None;self.arrange()
 def arrange(self):
  compact=self.width()<920 or self.height()<420
  self._compact=compact
  for b in (self.equipment_button,self.history_button,self.backup_button):b.setVisible(not compact)
  self.more.setVisible(compact)
  columns=3 if self.width()>=640 else 1
  wide=self.width()>=1100
  if (columns,wide)==self._columns:return
  self._columns=(columns,wide)
  for i,index in enumerate((0,3,2)):self.metric_grid.addWidget(self.cards[index],i//columns,i%columns)
  for i in range(3):self.metric_grid.setColumnStretch(i,1 if i<columns else 0)
  self.overview_grid.removeWidget(self.recent_frame);self.overview_grid.removeWidget(self.queue_frame)
  self.overview_grid.addWidget(self.recent_frame,0,0)
  self.overview_grid.addWidget(self.queue_frame,0 if wide else 1,1 if wide else 0)
  self.overview_grid.setColumnStretch(0,3);self.overview_grid.setColumnStretch(1,1 if wide else 0)
 def resizeEvent(self,event):super().resizeEvent(event);self.arrange()
 def install(self,data):
  for key,label in self.values.items():label.setText(rub(data[key]) if key=='debt' else str(data[key]))
  rows=[{**r,'equipment_label':r['equipment_number']+' · '+r['model']} for r in data['recent_repairs']]
  self.recent.install(rows);self.recent.setFixedHeight(min(380,52+max(2,len(rows))*38));self.empty.setVisible(not rows);self.recent.setVisible(bool(rows));self.empty_filler.setVisible(True);self.onboarding.setVisible(not rows)
 def open_recent(self,*args):
  row=self.recent.selected()
  if row:self.workspace.open_repair(row['id'])
class DiagnosticsDialog(QDialog):
 def __init__(self,workspace,rows,numbers,log_text):
  super().__init__(workspace);self.setWindowTitle('История действий и локальная диагностика');self.resize(900,600);layout=QVBoxLayout(self);layout.addWidget(text('Фактические локальные события. Подробности могут содержать рабочие данные; программа никуда их не отправляет.','muted'));self.grid=Grid([('created_at','Когда'),('event_text','Событие')]);self.grid.install([{**r,'event_text':audit_text(r,numbers)} for r in rows]);layout.addWidget(self.grid,1);self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(150);self.detail.setPlaceholderText('Выберите событие, чтобы раскрыть технические подробности.');layout.addWidget(self.detail);self.grid.selectionModel().currentRowChanged.connect(self.selected);self.log_text=log_text;bar=ActionBar();layout.addWidget(bar);button(bar,'Показать локальный журнал ошибок',lambda:self.detail.setPlainText(self.log_text or 'Ошибок в локальном журнале нет.'));button(bar,'Закрыть',self.accept)
 def selected(self,*args):
  row=self.grid.selected()
  if row:self.detail.setPlainText(row['entity']+' / '+row['action']+'\n'+row['detail'])
