from PySide6.QtCore import Qt,QSortFilterProxyModel
from PySide6.QtWidgets import QTableView,QPushButton,QMessageBox
from .models import RowsModel

class Grid(QTableView):
    def __init__(self,columns,parent=None):
        super().__init__(parent);self.records=RowsModel(columns,self);self.proxy=QSortFilterProxyModel(self);self.proxy.setSourceModel(self.records);self.proxy.setSortRole(Qt.ItemDataRole.UserRole);self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive);self.proxy.setFilterKeyColumn(0);self.proxy.setFilterRole(Qt.ItemDataRole.UserRole+1);self.setModel(self.proxy);self.setSortingEnabled(True)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows);self.setSelectionMode(QTableView.SelectionMode.SingleSelection);self.setAlternatingRowColors(True);self.setWordWrap(False);self.setMinimumHeight(150);self.horizontalHeader().setDefaultSectionSize(145);self.horizontalHeader().setStretchLastSection(True)
    def install(self,rows):self.records.install(rows)
    def selected(self):
        i=self.currentIndex()
        return self.records.rows[self.proxy.mapToSource(i).row()] if i.isValid() else None

def button(layout,title,fn):
    b=QPushButton(title);b.setAccessibleName(title);b.clicked.connect(fn);layout.addWidget(b);return b

def confirm(parent,text):return QMessageBox.question(parent,'Подтверждение',text,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes

