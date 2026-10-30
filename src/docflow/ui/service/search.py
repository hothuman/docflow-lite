"""One search entry for existing equipment and repair history, including archives."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLineEdit,QCheckBox,QTabWidget,QLabel
from .forms import fit_dialog
from .widgets import Grid,button
from ..flow import FlowLayout

class SearchDialog(QDialog):
    def __init__(self,workspace):
        super().__init__(workspace);self.workspace=workspace;self.setWindowTitle('Найти оборудование / ремонт');fit_dialog(self,920,620)
        layout=QVBoxLayout(self);self.query=QLineEdit();self.query.setPlaceholderText('Номер аппарата или ремонта, клиент, телефон, жалоба');self.query.setAccessibleName('Общий поиск Service');layout.addWidget(self.query)
        self.archived=QCheckBox('Включая архив');layout.addWidget(self.archived);self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.repairs=Grid([('number','Ремонт №'),('equipment_number','Аппарат №'),('model','Модель'),('client','Клиент'),('status','Статус')]);self.equipment=Grid([('number','Аппарат №'),('model','Модель'),('owner','Владелец')])
        self.tabs.addTab(self.repairs,'Ремонты');self.tabs.addTab(self.equipment,'Оборудование')
        self.hint=QLabel();self.hint.setWordWrap(True);layout.addWidget(self.hint);bar=FlowLayout();layout.addLayout(bar);button(bar,'Открыть',self.open,primary=True);button(bar,'Назад',self.accept)
        for grid in (self.repairs,self.equipment):grid.openRequested.connect(self.open);grid.doubleClicked.connect(self.open)
        self.query.textChanged.connect(self.filter);self.archived.toggled.connect(self.reload);self.reload();self.query.setFocus()
    def reload(self):
        store=self.workspace.store;archive=self.archived.isChecked()
        def query():return store.repairs(),store.equipment()+ (store.equipment(archived=True) if archive else [])
        def install(data):
            repairs,equipment=data;self.repairs.install([r for r in repairs if archive or r['status']!='historical']);self.equipment.install(equipment);self.filter()
        self.workspace.run(query,install,'Ищу в журнале…')
    def filter(self,*args):
        for grid in (self.repairs,self.equipment):grid.proxy.setFilterFixedString(self.query.text())
        count=self.repairs.proxy.rowCount()+self.equipment.proxy.rowCount()
        self.hint.setText('Найдено: '+str(count) if count else 'Совпадений нет. Измените запрос или включите архив; данные не удалены.')
    def open(self,*args):
        grid=self.repairs if self.tabs.currentIndex()==0 else self.equipment;row=grid.selected()
        if not row:self.hint.setText('Выберите строку и нажмите Enter или «Открыть».');return
        if grid is self.repairs:self.accept();self.workspace.open_repair(row['id'])
        else:
            from .history import HistoryDialog
            self.workspace.modal(HistoryDialog(self.workspace,row))

    def reject(self):
        if not self.workspace.worker:super().reject()
    def closeEvent(self,event):
        if self.workspace.worker:event.ignore()
        else:event.accept()
