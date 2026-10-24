"""Wrapping actions without toolbar arrows, shared by Core/Service dialogs."""
from PySide6.QtCore import QRect,QSize,Qt
from PySide6.QtWidgets import QLayout,QWidget,QSizePolicy,QLabel
class FlowLayout(QLayout):
 def __init__(self,parent=None,spacing=6):super().__init__(parent);self.items=[];self.setContentsMargins(0,0,0,0);self.setSpacing(spacing)
 def addItem(self,item):self.items.append(item)
 def __del__(self):
  while self.items:
   item=self.items.pop(0);del item
 def count(self):return len(self.items)
 def itemAt(self,index):return self.items[index] if 0<=index<len(self.items) else None
 def takeAt(self,index):return self.items.pop(index) if 0<=index<len(self.items) else None
 def expandingDirections(self):return Qt.Orientation(0)
 def hasHeightForWidth(self):return True
 def heightForWidth(self,width):return self.arrange(QRect(0,0,width,0),False)
 def setGeometry(self,rect):super().setGeometry(rect);self.arrange(rect,True)
 def sizeHint(self):return self.minimumSize()
 def minimumSize(self):
  result=QSize(0,0)
  for item in self.items:
   if not item.isEmpty():result=result.expandedTo(item.minimumSize())
  return result
 def arrange(self,rect,place):
  x=rect.x();y=rect.y();line=0
  for item in self.items:
   if item.isEmpty():continue
   size=item.sizeHint();width=min(size.width(),max(1,rect.width()))
   if x>rect.x() and x+width>rect.right()+1:y+=line+self.spacing();x=rect.x();line=0
   height=item.heightForWidth(width) if item.hasHeightForWidth() else size.height()
   if place:item.setGeometry(QRect(x,y,width,height))
   x+=width+self.spacing();line=max(line,height)
  return y-rect.y()+line
class ActionBar(QWidget):
 def __init__(self,parent=None):super().__init__(parent);self.flow=FlowLayout(self);self.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Minimum)
 def addWidget(self,widget):
  if isinstance(widget,QLabel):widget.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Preferred)
  self.flow.addWidget(widget)
