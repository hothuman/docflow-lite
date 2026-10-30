"""Always-visible, keyboard-operable choice of two workspaces."""
from PySide6.QtCore import Qt,Signal,QEvent
from PySide6.QtWidgets import QWidget,QHBoxLayout,QPushButton,QButtonGroup
from .widgets import icon

class ModeSwitch(QWidget):
    currentIndexChanged=Signal(int)
    def __init__(self,parent=None):
        super().__init__(parent);self._index=0;self.buttons=[];self.group=QButtonGroup(self);self.group.setExclusive(True);layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(4)
        for index,(title,detail,kind) in enumerate((('Документы','Таблица и шаблон Word → готовые документы','document'),('Мастерская','Клиенты, оборудование и история ремонтов','tool'))):
            b=QPushButton(title);b.setObjectName('modeSegment');b.setCheckable(True);b.setIcon(icon(kind));b.setAccessibleName(title);b.setAccessibleDescription(detail);b.setToolTip(detail);b.installEventFilter(self);self.group.addButton(b,index);layout.addWidget(b,1);self.buttons.append(b)
        self.buttons[0].setChecked(True);self.group.idClicked.connect(self.setCurrentIndex)
    def currentIndex(self):return self._index
    def setCurrentIndex(self,index):
        if index not in (0,1):return
        changed=index!=self._index;self._index=index;self.buttons[index].setChecked(True)
        if changed:self.currentIndexChanged.emit(index)
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_Up,Qt.Key.Key_Down):
            index=1-self._index;self.setCurrentIndex(index);self.buttons[index].setFocus();return True
        return super().eventFilter(obj,event)
