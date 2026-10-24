"""Per-document image selection, order, stage groups and captions."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QTableWidget,QTableWidgetItem,QMessageBox
from ..flow import FlowLayout
from .forms import fit_dialog
from .widgets import button

class ImagesDialog(QDialog):
    def __init__(self,attachments,parent=None,choices=()):
        super().__init__(parent);self.setWindowTitle('Изображения именно для этого документа');fit_dialog(self,900,540);layout=QVBoxLayout(self)
        self.rows=[x for x in attachments if x['kind']=='image'];selected={x['id']:x for x in choices}
        order={x['id']:i for i,x in enumerate(choices)};self.rows.sort(key=lambda x:order.get(x['id'],len(order)))
        self.table=QTableWidget(len(self.rows),4);self.table.setHorizontalHeaderLabels(['Включить','Изображение','Подпись','Группа / этап']);self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table)
        for i,row in enumerate(self.rows):
            choose=QTableWidgetItem();choose.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable);choose.setCheckState(Qt.CheckState.Checked if row['id'] in selected else Qt.CheckState.Unchecked);self.table.setItem(i,0,choose)
            for j,value in enumerate([row['name'],selected.get(row['id'],{}).get('caption',row['comment']),selected.get(row['id'],{}).get('stage','')],1):
                cell=QTableWidgetItem(value)
                if j==1:cell.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(i,j,cell)
        bar=FlowLayout();layout.addLayout(bar);button(bar,'Выше',lambda:self.move(-1));button(bar,'Ниже',lambda:self.move(1));button(bar,'Применить',self.accept);button(bar,'Отмена',self.reject)
    def move(self,direction):
        i=self.table.currentRow();j=i+direction
        if i<0 or not 0<=j<len(self.rows):return
        self.rows[i],self.rows[j]=self.rows[j],self.rows[i]
        for col in range(4):
            a=self.table.takeItem(i,col);b=self.table.takeItem(j,col);self.table.setItem(i,col,b);self.table.setItem(j,col,a)
        self.table.setCurrentCell(j,1)
    def values(self):return [{'id':row['id'],'caption':self.table.item(i,2).text(),'stage':self.table.item(i,3).text()} for i,row in enumerate(self.rows) if self.table.item(i,0).checkState()==Qt.CheckState.Checked]
    def accept(self):
        if len(self.values())>10:QMessageBox.information(self,'Изображения','Выберите не более десяти изображений');return
        super().accept()
