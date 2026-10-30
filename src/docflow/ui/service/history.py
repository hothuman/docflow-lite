"""Equipment chronology and explicit side-by-side repair comparison."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,QTabWidget,QPlainTextEdit,QAbstractItemView,QMessageBox,QScrollArea,QWidget
from ...service.validation import rub
from ...service.record_text import repair_display, readable_field
from .presentation import date_text,KINDS_DISPLAY
from ..widgets import text
from ..flow import FlowLayout
from .forms import fit_dialog,DateField
from .widgets import Grid,button

class HistoryDialog(QDialog):
    def __init__(self,workspace,equipment):
        super().__init__(workspace);self.workspace=workspace;self.equipment=equipment;self.setWindowTitle('История оборудования '+equipment['number']);fit_dialog(self,1050,650)
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();scroll.setWidget(body);outer.addWidget(scroll,1);layout=QVBoxLayout(body);self.identity=text(equipment['number']+' · '+equipment['model']+'\nСерийный №: '+(equipment['serial'] or '—')+' · Текущий владелец: '+equipment['owner']);layout.addWidget(self.identity)
        bar=FlowLayout();layout.addLayout(bar);self.search=QLineEdit();self.search.setPlaceholderText('Жалоба, дефект, производитель, работа или деталь');bar.addWidget(self.search)
        self.since=DateField();self.since.setPlaceholderText('С даты ДД.ММ.ГГГГ');bar.addWidget(self.since);self.until=DateField();self.until.setPlaceholderText('По дату ДД.ММ.ГГГГ');bar.addWidget(self.until)
        self.order=QComboBox();self.order.addItem('От старых к новым',True);self.order.addItem('От новых к старым',False);bar.addWidget(self.order);button(bar,'Применить даты',self.refresh)
        self.grid=Grid([('number','Ремонт'),('received_at','Дата'),('client','Клиент этого ремонта'),('status','Статус'),('total','Стоимость'),('financial_status','Расчёты')]);self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);layout.addWidget(self.grid)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(160);self.detail.setPlaceholderText('Выберите ремонт: здесь появятся жалоба, дефектовка и выполненные позиции.');layout.addWidget(self.detail)
        self.grid.selectionModel().currentRowChanged.connect(self.selected_detail);self.grid.openRequested.connect(self.open)
        self.search.textChanged.connect(self.grid.proxy.setFilterFixedString);self.order.currentIndexChanged.connect(self.refresh)
        bar=FlowLayout();outer.addLayout(bar);button(bar,'Открыть ремонт и материалы',self.open);button(bar,'Сравнить выбранные ремонты (2–6)',self.compare);button(bar,'Новое обращение',self.new);button(bar,'Закрыть',self.accept);self.refresh()
    def selected_detail(self,*args):
        row=self.grid.selected()
        if row:
            shown=repair_display(row)
            source_works=('\nРаботы из источника: '+shown['source_works']) if shown['source_works'] else ''
            self.detail.setPlainText('Приёмка: '+date_text(row['received_at'])+'\nЖалоба: '+shown['complaint']+'\nДиагностика: '+shown['defects']+'\nРаботы и материалы: '+readable_field(row['item_text'],'description').text+source_works+'\nОткройте ремонт для прежних DOCX, фото и подробностей.')
    def refresh(self,*args):
        eq=self.equipment['id'];start=self.since.storage_text();end=self.until.storage_text();ascending=self.order.currentData()
        self.workspace.run(lambda:self.workspace.store.repairs(equipment_id=eq,date_from=start or None,date_to=end or None,ascending=ascending),self.grid.install)
    def open(self):
        row=self.grid.selected()
        if row:self.accept();self.workspace.open_repair(row['id'],'Документы')
    def new(self):self.accept();self.workspace.new_repair_for(self.equipment)
    def compare(self):
        keys=[self.grid.records.rows[self.grid.proxy.mapToSource(i).row()]['id'] for i in self.grid.selectionModel().selectedRows()]
        if not 2<=len(keys)<=6:QMessageBox.information(self,'Сравнение','Выберите от двух до шести ремонтов одного аппарата, удерживая Ctrl');return
        self.workspace.run(lambda:self.workspace.store.compare_repairs(keys),self.show_comparison)
    def show_comparison(self,snapshots):
        d=QDialog(self);d.setWindowTitle('Сравнение ремонтов одного физического аппарата');d.resize(1050,650);layout=QHBoxLayout(d)
        for s in snapshots:
            r=repair_display(s['repair']);box=QPlainTextEdit();box.setReadOnly(True);lines=[r['number']+' · '+date_text(r['received_at']),s['client']['name'],'Жалоба: '+r['complaint'],'Диагностика: '+r['defects'],'План: '+r['plan']]
            if r['source_works']:lines.append('Работы из источника: '+r['source_works'])
            for x in s['repair_items']:lines.append(KINDS_DISPLAY[x['kind']]+': '+readable_field(x['name'],'name').text+' · '+x['quantity']+' '+x['unit']+' · '+rub(x['total_cents'])+'\n'+readable_field(x['description'],'description').text)
            lines.extend(['Стоимость '+rub(s['totals']['total']),'Остаток '+rub(s['totals']['balance']),'Вложения: '+str(len(s['attachments'])),'DOCX: '+str(len(s['generated_documents'])),'Примечания: '+r['notes']]);box.setPlainText('\n\n'.join(lines));layout.addWidget(box)
        d.exec()
    def closeEvent(self,event):
        if self.workspace.worker:event.ignore()
        else:event.accept()
