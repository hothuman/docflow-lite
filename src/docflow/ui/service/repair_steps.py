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
    sectionChanged=Signal(str)
    GROUPS={'Приёмка':0,'Дефектовка':1,'Согласование':2,'Сметы':2,'Работы':3,'Запчасти':3,'Доставка':3,'Прочие расходы':3,'Финансы':3,'Вложения':3,'Документы':4,'Статус и история':4}
    def __init__(self,parent=None,embedded=False):
        super().__init__(parent);self.editor=parent;self.embedded=embedded;self._selecting_section=False;self.sections={};self.cards={};self.layouts=[];self.status_labels=[];self.section_tabs=[];self.section_stacks=[];self.stage_bar=QTabBar();self.stage_bar.setExpanding(True);self.stage_bar.setAccessibleName('Пять этапов ремонта');self.stage_bar.setUsesScrollButtons(embedded);self.stack=ActiveStack() if embedded else QStackedWidget();outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(self.stack)
        if embedded:self.stage_bar.setObjectName('repairStageBar')
        for title in ('Приёмка','Диагностика','Смета','Работы','Выдача'):
            body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(0,6,0,0);layout.setSpacing(8);hint=QLabel();hint.setWordWrap(True);hint.setObjectName('muted');layout.addWidget(hint);self.status_labels.append(hint)
            if embedded:
                hint.hide()
                selector=QTabBar();selector.setAccessibleName('Разделы этапа '+title);selector.setUsesScrollButtons(True);selector.setExpanding(False);selector.hide()
                pages=ActiveStack();selector.currentChanged.connect(pages.setCurrentIndex)
                selector.currentChanged.connect(self.update_section)
                layout.addWidget(selector);layout.addWidget(pages,1)
                self.section_tabs.append(selector);self.section_stacks.append(pages)
            layout.addStretch();self.layouts.append(layout);self.stack.addWidget(body);self.stage_bar.addTab(title)
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
        if self.embedded:
            index=self.section_stacks[group].addWidget(content)
            self.sections[title]=(group,index,content)
            labels={'Дефектовка':'Диагностика','Сметы':'Состав и версии','Согласование':'Ответ заказчика','Статус и история':'Передача','Финансы':'Оплаты'}
            selector=self.section_tabs[group];selector.addTab(labels.get(title,title));selector.setVisible(selector.count()>1)
            return index
        card=Disclosure('Диагностика' if title=='Дефектовка' else title,content);self.layouts[group].insertWidget(self.layouts[group].count()-1,card);index=sum(g==group for g,_,_ in self.sections.values());self.sections[title]=(group,index,content);self.cards[title]=card
        primary=title in ('Приёмка','Дефектовка','Сметы','Работы','Запчасти','Документы');card.set_expanded(primary)
        if group in (0,1):card.toggle.hide();card.set_expanded(True)
        return index
    def stage_changed(self,*args):
        owner=self.editor
        if owner and hasattr(owner,'body_scroll'):QTimer.singleShot(0,owner,lambda:owner.body_scroll.verticalScrollBar().setValue(0))
        self.update_section()
    def show_section(self,title):
        group,index,widget=self.sections[title]
        if self.embedded:
            self._selecting_section=True
            try:
                self.setCurrentIndex(group)
                self.section_tabs[group].setCurrentIndex(index)
            finally:
                self._selecting_section=False
            self.update_section()
            return
        self.setCurrentIndex(group)
        self.cards[title].set_expanded(True)
        owner=self.editor
        if owner and hasattr(owner,'body_scroll'):QTimer.singleShot(0,owner,lambda:owner.body_scroll.ensureWidgetVisible(self.cards[title],12,12))
    def setCurrentWidget(self,widget):
        for title,(_,_,child) in self.sections.items():
            if child is widget:self.show_section(title);return
        self.stack.setCurrentWidget(widget)

    def update_section(self,*_):
        if not self.embedded or self._selecting_section:return
        stage=self.currentIndex()
        selector=self.section_tabs[stage]
        self.section_stacks[stage].updateGeometry()
        self.stack.updateGeometry()
        self.sectionChanged.emit(self.tabText(stage)+(f' / {selector.tabText(selector.currentIndex())}' if selector.count()>1 else ''))

    def is_section(self,title):
        stage,index,_=self.sections[title]
        return self.currentIndex()==stage and self.section_tabs[stage].currentIndex()==index

    def selected_section(self):
        return next(title for title in self.sections if self.is_section(title))


class ActiveStack(QStackedWidget):
    """Inactive long forms must not set the height of a short active view."""
    def sizeHint(self):
        current=self.currentWidget()
        return current.sizeHint() if current else super().sizeHint()

    def minimumSizeHint(self):
        current=self.currentWidget()
        return current.minimumSizeHint() if current else super().minimumSizeHint()
