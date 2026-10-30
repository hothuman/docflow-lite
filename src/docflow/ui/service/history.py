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
        self.order=QComboBox();self.order.addItem('От старых к новым',True);self.order.addItem('От новых к старым',False);bar.addWidget(self.order);button(bar,'Применить даты',self.refresh);button(bar,'Сбросить фильтры',self.reset_filters)
        self.grid=Grid([('number','Ремонт'),('received_at','Дата'),('client','Клиент этого ремонта'),('status','Статус'),('total','Стоимость'),('financial_status','Расчёты')]);self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);layout.addWidget(self.grid)
        self.empty_hint=QLabel();self.empty_hint.setWordWrap(True);layout.addWidget(self.empty_hint);self.selection_heading=text('Выберите обращение','section');layout.addWidget(self.selection_heading)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMinimumHeight(110);self.detail.setMaximumHeight(210);self.detail.setPlaceholderText('Выберите ремонт: здесь появятся жалоба, диагностика и выполненные работы.');layout.addWidget(self.detail)
        self.compare_hint=QLabel('Сравнение доступно для 2–6 обращений. Выделяйте строки с Ctrl или Shift.');self.compare_hint.setWordWrap(True);layout.addWidget(self.compare_hint)
        self.grid.selectionModel().currentRowChanged.connect(self.selected_detail);self.grid.openRequested.connect(self.open)
        self.search.textChanged.connect(self.grid.proxy.setFilterFixedString);self.order.currentIndexChanged.connect(self.refresh)
        bar=FlowLayout();outer.addLayout(bar);self.open_button=button(bar,'Открыть ремонт',self.open,primary=True);self.compare_button=button(bar,'Сравнить выбранные (2–6)',self.compare);self.new_button=button(bar,'Новое обращение',self.new);button(bar,'Закрыть',self.accept)
        self.compare_button.setToolTip('Выделите от двух до шести ремонтов одного аппарата с Ctrl или Shift.');self.compare_button.setEnabled(False)
        self.grid.selectionModel().selectionChanged.connect(self.update_selection);self.grid.proxy.modelReset.connect(self.update_selection);self.grid.proxy.rowsRemoved.connect(self.update_selection);self.search.textChanged.connect(self.update_selection);self.update_selection();self.refresh()
    def reset_filters(self):
        self.search.clear();self.since.set_date('');self.until.set_date('');self.refresh()
    def selected_rows(self):
        result=[]
        for index in self.grid.selectionModel().selectedRows():
            source=self.grid.proxy.mapToSource(index)
            if source.isValid() and 0<=source.row()<len(self.grid.records.rows):result.append(self.grid.records.rows[source.row()])
        return result
    def update_selection(self,*args):
        rows=self.selected_rows();valid=2<=len(rows)<=6 and all(r['equipment_id']==self.equipment['id'] for r in rows);self.compare_button.setEnabled(valid);self.open_button.setEnabled(bool(rows));self.empty_hint.setText('Обращений по текущим фильтрам нет. Сбросьте фильтры или создайте новое обращение.' if not self.grid.proxy.rowCount() else '');self.empty_hint.setVisible(not self.grid.proxy.rowCount());self.selected_detail()
    def selected_detail(self,*args):
        row=self.grid.selected()
        if row and self.selected_rows():
            self.selection_heading.setText('Ремонт №'+row['number']+' · '+date_text(row['received_at'])+' · '+row['client'])
            shown=repair_display(row)
            source_works=('\nРаботы из источника: '+shown['source_works']) if shown['source_works'] else ''
            self.detail.setPlainText('Приёмка: '+date_text(row['received_at'])+'\nЖалоба: '+shown['complaint']+'\nДиагностика: '+shown['defects']+'\nРаботы и материалы: '+readable_field(row['item_text'],'description').text+source_works+'\nОткройте ремонт для прежних DOCX, фото и подробностей.')
        else:self.selection_heading.setText('Выберите обращение');self.detail.clear()
    def refresh(self,*args):
        eq=self.equipment['id'];start=self.since.storage_text();end=self.until.storage_text();ascending=self.order.currentData()
        self.workspace.run(lambda:self.workspace.store.repairs(equipment_id=eq,date_from=start or None,date_to=end or None,ascending=ascending),self.grid.install)
    def open(self):
        row=self.grid.selected()
        if row and self.selected_rows():self.accept();self.workspace.open_repair(row['id'],'Документы')
    def new(self):self.accept();self.workspace.start_intake(self.equipment)
    def compare(self):
        rows=self.selected_rows();keys=[r['id'] for r in rows]
        if not 2<=len(keys)<=6 or any(r['equipment_id']!=self.equipment['id'] for r in rows):return
        self.workspace.run(lambda:self.workspace.store.compare_repairs(keys),self.show_comparison)
    def show_comparison(self,snapshots):
        d=QDialog(self);d.setWindowTitle('Сравнение ремонтов одного аппарата');fit_dialog(d,1060,650);outer=QVBoxLayout(d);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();layout=QHBoxLayout(body);scroll.setWidget(body);outer.addWidget(scroll,1)
        for s in snapshots:
            r=repair_display(s['repair']);box=QPlainTextEdit();box.setMinimumWidth(280);box.setReadOnly(True);lines=[r['number']+' · '+date_text(r['received_at']),s['client']['name'],'Жалоба: '+r['complaint'],'Диагностика: '+r['defects'],'План: '+r['plan']]
            if r['source_works']:lines.append('Работы из источника: '+r['source_works'])
            for x in s['repair_items']:lines.append(KINDS_DISPLAY[x['kind']]+': '+readable_field(x['name'],'name').text+' · '+x['quantity']+' '+x['unit']+' · '+rub(x['total_cents'])+'\n'+readable_field(x['description'],'description').text)
            lines.extend(['Стоимость '+rub(s['totals']['total']),'Остаток '+rub(s['totals']['balance']),'Вложения: '+str(len(s['attachments'])),'DOCX: '+str(len(s['generated_documents'])),'Примечания: '+r['notes']]);box.setPlainText('\n\n'.join(lines));layout.addWidget(box)
        button(outer,'Закрыть',d.accept);d.exec()
    def closeEvent(self,event):
        if self.workspace.worker:event.ignore()
        else:event.accept()
