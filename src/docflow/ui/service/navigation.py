"""Three repair groups with explicit section names and scrollable contents."""
from PySide6.QtWidgets import QTabWidget,QWidget,QVBoxLayout,QComboBox,QStackedWidget,QScrollArea,QListWidget,QHBoxLayout
class RepairNavigation(QTabWidget):
 GROUPS={'Приёмка':0,'Дефектовка':0,'Статус и история':0,'Работы':1,'Запчасти':1,'Доставка':1,'Прочие расходы':1,'Финансы':1,'Сметы':1,'Вложения':2,'Документы':2}
 def __init__(self,parent=None):
  super().__init__(parent);self.groups=[];self.sections={};self.lists=[];self.setUsesScrollButtons(False)
  for title in ('Основное','Стоимость','Материалы'):
   body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(0,8,0,0);picker=QComboBox();picker.setAccessibleName('Раздел: '+title);stack=QStackedWidget();layout.addWidget(picker);row=QHBoxLayout();row.setSpacing(16);sidebar=QListWidget();sidebar.setObjectName('sectionList');sidebar.setFixedWidth(156);sidebar.setAccessibleName('Разделы: '+title);row.addWidget(sidebar);row.addWidget(stack,1);layout.addLayout(row,1);picker.currentIndexChanged.connect(stack.setCurrentIndex);picker.currentIndexChanged.connect(sidebar.setCurrentRow);sidebar.currentRowChanged.connect(picker.setCurrentIndex);super().addTab(body,title);self.groups.append((picker,stack));self.lists.append(sidebar)
 def addTab(self,widget,title):
  group=self.GROUPS[title];picker,stack=self.groups[group];container=widget
  if not isinstance(widget,QScrollArea):container=QScrollArea();container.setWidgetResizable(True);container.setWidget(widget)
  index=stack.addWidget(container);picker.addItem(title);self.lists[group].addItem(title);self.lists[group].setCurrentRow(picker.currentIndex());self.sections[title]=(group,index,widget);return index
 def show_section(self,title):
  group,index,widget=self.sections[title];self.setCurrentIndex(group);self.groups[group][0].setCurrentIndex(index)
 def setCurrentWidget(self,widget):
  for title,(group,index,child) in self.sections.items():
   if widget is child:self.show_section(title);return
  super().setCurrentWidget(widget)

 def resizeEvent(self,event):
  super().resizeEvent(event)
  if hasattr(self,'lists'):
   wide=self.width()>=850
   for (picker,stack),sidebar in zip(self.groups,self.lists):picker.setVisible(not wide);sidebar.setVisible(wide)
