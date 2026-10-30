"""One stage bar; details expand in place, without another navigation level."""
from PySide6.QtCore import Qt,QTimer,Signal
from PySide6.QtWidgets import QTabBar,QStackedWidget,QWidget,QVBoxLayout,QScrollArea,QFrame,QToolButton,QLabel

class Disclosure(QFrame):
    def __init__(self,title,content,parent=None):
        super().__init__(parent);self.setObjectName('detailSection');layout=QVBoxLayout(self);layout.setContentsMargins(0,6,0,8);layout.setSpacing(8);self.toggle=QToolButton();self.toggle.setObjectName('detailToggle');self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon);self.toggle.setCheckable(True);self.toggle.setText(title);self.toggle.setAccessibleName('Показать: '+title);layout.addWidget(self.toggle);layout.addWidget(content);self.content=content;self.toggle.toggled.connect(self.set_expanded);self.set_expanded(False)
    def set_expanded(self,expanded):
        self.toggle.blockSignals(True);self.toggle.setChecked(expanded);self.toggle.blockSignals(False);self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow);self.content.setVisible(expanded)

class RepairNavigation(QWidget):
    currentChanged=Signal(int)
    GROUPS={'Приёмка':0,'Дефектовка':1,'Согласование':2,'Сметы':2,'Работы':3,'Запчасти':3,'Доставка':3,'Прочие расходы':3,'Финансы':3,'Вложения':3,'Документы':4,'Статус и история':4}
    def __init__(self,parent=None):
        super().__init__(parent);self.editor=parent;self.sections={};self.cards={};self.layouts=[];self.status_labels=[];self.stage_bar=QTabBar();self.stage_bar.setExpanding(True);self.stage_bar.setAccessibleName('Пять этапов ремонта');self.stage_bar.setUsesScrollButtons(False);self.stack=QStackedWidget();outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(self.stack)
        for title in ('Приёмка','Диагностика','Смета','Работы','Выдача'):
            body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(0,6,0,0);layout.setSpacing(8);hint=QLabel();hint.setWordWrap(True);hint.setObjectName('muted');layout.addWidget(hint);self.status_labels.append(hint);layout.addStretch();self.layouts.append(layout);self.stack.addWidget(body);self.stage_bar.addTab(title)
        self.stage_bar.currentChanged.connect(self.stack.setCurrentIndex);self.stack.currentChanged.connect(self.stage_bar.setCurrentIndex);self.stack.currentChanged.connect(self.currentChanged);self.currentChanged.connect(self.stage_changed)
    def setCurrentIndex(self,index):self.stack.setCurrentIndex(index)
    def currentIndex(self):return self.stack.currentIndex()
    def count(self):return self.stack.count()
    def tabText(self,index):return self.stage_bar.tabText(index)
    def tabBar(self):return self.stage_bar
    def setTabToolTip(self,index,value):self.stage_bar.setTabToolTip(index,value)
    def setUsesScrollButtons(self,value):self.stage_bar.setUsesScrollButtons(value)
    def usesScrollButtons(self):return self.stage_bar.usesScrollButtons()
    def addTab(self,widget,title):
        group=self.GROUPS[title];content=widget
        if isinstance(widget,QScrollArea):content=widget.takeWidget();widget.deleteLater()
        card=Disclosure('Диагностика' if title=='Дефектовка' else title,content);self.layouts[group].insertWidget(self.layouts[group].count()-1,card);index=sum(g==group for g,_,_ in self.sections.values());self.sections[title]=(group,index,content);self.cards[title]=card
        primary=title in ('Приёмка','Дефектовка','Сметы','Работы','Запчасти','Документы');card.set_expanded(primary)
        if group in (0,1):card.toggle.hide();card.set_expanded(True)
        return index
    def stage_changed(self,*args):
        owner=self.editor
        if owner and hasattr(owner,'body_scroll'):QTimer.singleShot(0,owner,lambda:owner.body_scroll.verticalScrollBar().setValue(0))
    def show_section(self,title):
        group,index,widget=self.sections[title];self.setCurrentIndex(group);self.cards[title].set_expanded(True)
        owner=self.editor
        if owner and hasattr(owner,'body_scroll'):QTimer.singleShot(0,owner,lambda:owner.body_scroll.ensureWidgetVisible(self.cards[title],12,12))
    def setCurrentWidget(self,widget):
        for title,(_,_,child) in self.sections.items():
            if child is widget:self.show_section(title);return
        self.stack.setCurrentWidget(widget)
