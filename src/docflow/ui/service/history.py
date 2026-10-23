"""Equipment chronology and explicit side-by-side repair comparison."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,QTabWidget,QPlainTextEdit,QAbstractItemView,QMessageBox
from ...service.validation import rub
from .widgets import Grid,button

class HistoryDialog(QDialog):
    def __init__(self,workspace,equipment):
        super().__init__(workspace);self.workspace=workspace;self.equipment=equipment;self.setWindowTitle('История оборудования '+equipment['number']);self.resize(1050,650)
        layout=QVBoxLayout(self);identity=QLabel(equipment['number']+' · '+equipment['model']+'\nТекущий владелец: '+equipment['owner']);identity.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(identity)
        bar=QHBoxLayout();layout.addLayout(bar);self.search=QLineEdit();self.search.setPlaceholderText('Жалоба, дефект, производитель, работа или деталь');bar.addWidget(self.search)
        self.since=QLineEdit();self.since.setPlaceholderText('С даты ГГГГ-ММ-ДД');bar.addWidget(self.since);self.until=QLineEdit();self.until.setPlaceholderText('По дату ГГГГ-ММ-ДД');bar.addWidget(self.until)
        self.order=QComboBox();self.order.addItem('От старых к новым',True);self.order.addItem('От новых к старым',False);bar.addWidget(self.order);button(bar,'Применить даты',self.refresh)
        self.grid=Grid([('number','Ремонт'),('received_at','Дата'),('client','Клиент этого ремонта'),('complaint','Жалоба'),('defects','Дефекты'),('item_text','Работы / детали'),('status','Статус'),('total','Стоимость'),('financial_status','Расчёты')]);self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);layout.addWidget(self.grid)
        self.search.textChanged.connect(self.grid.proxy.setFilterFixedString);self.order.currentIndexChanged.connect(self.refresh)
        bar=QHBoxLayout();layout.addLayout(bar);button(bar,'Открыть ремонт и материалы',self.open);button(bar,'Сравнить выбранные ремонты (2–6)',self.compare);button(bar,'Новое обращение',self.new);button(bar,'Закрыть',self.accept);self.refresh()
    def refresh(self,*args):
        eq=self.equipment['id'];start=self.since.text();end=self.until.text();ascending=self.order.currentData()
        self.workspace.run(lambda:self.workspace.store.repairs(equipment_id=eq,date_from=start or None,date_to=end or None,ascending=ascending),self.grid.install)
    def open(self):
        row=self.grid.selected()
        if row:self.accept();self.workspace.open_repair(row['id'])
    def new(self):self.accept();self.workspace.new_repair_for(self.equipment)
    def compare(self):
        keys=[self.grid.records.rows[self.grid.proxy.mapToSource(i).row()]['id'] for i in self.grid.selectionModel().selectedRows()]
        if not 2<=len(keys)<=6:QMessageBox.information(self,'Сравнение','Выберите от двух до шести ремонтов одного аппарата, удерживая Ctrl');return
        self.workspace.run(lambda:self.workspace.store.compare_repairs(keys),self.show_comparison)
    def show_comparison(self,snapshots):
        d=QDialog(self);d.setWindowTitle('Сравнение ремонтов одного физического аппарата');d.resize(1050,650);layout=QHBoxLayout(d)
        for s in snapshots:
            r=s['repair'];box=QPlainTextEdit();box.setReadOnly(True);lines=[r['number']+' · '+r['received_at'],s['client']['name'],'Жалоба: '+r['complaint'],'Дефекты: '+r['defects'],'План: '+r['plan']]
            for x in s['repair_items']:lines.append(x['kind']+': '+x['name']+' · '+x['quantity']+' '+x['unit']+' · '+rub(x['total_cents'])+'\n'+x['description'])
            lines.extend(['Стоимость '+rub(s['totals']['total']),'Остаток '+rub(s['totals']['balance']),'Вложения: '+str(len(s['attachments'])),'DOCX: '+str(len(s['generated_documents'])),'Примечания: '+r['notes']]);box.setPlainText('\n\n'.join(lines));layout.addWidget(box)
        d.exec()
    def closeEvent(self,event):
        if self.workspace.worker:event.ignore()
        else:event.accept()
