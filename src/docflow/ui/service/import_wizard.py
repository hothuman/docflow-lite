"""Five-step historical import with explicit identities and atomic confirmation."""
import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWizard,QWizardPage,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QComboBox,QLabel,QFileDialog,QScrollArea,QWidget,QTableWidget,QTableWidgetItem,QCheckBox,QPlainTextEdit,QDialog,QMessageBox)
from ...service.history_import import HISTORY_FIELDS,workbook_sheets,_load,preview_history,import_history
from ...service.statuses import STATUSES
from .forms import FieldsDialog,fit_dialog
from ..flow import FlowLayout
from .presentation import IMPORT_STATES
from .widgets import Grid,button

class HistoryWizard(QWizard):
    def __init__(self,workspace):
        super().__init__(workspace);self.workspace=workspace;self.store=workspace.store;self.setWindowTitle('Исторический импорт XLSX / CSV');fit_dialog(self,1020,720)
        self.plan=None;self.table=None;self.ready_page=-1;self.applied=False;self.decisions={'equipment_decisions':{},'client_decisions':{},'current_owners':{}};self.mappings={};self.statuses={}
        self.clients=workspace.cache.get('active_clients',[]);self.equipment=workspace.cache.get('active_equipment',[])
        self._layouts=[]
        for role,label in [(QWizard.WizardButton.BackButton,'Назад'),(QWizard.WizardButton.NextButton,'Далее'),(QWizard.WizardButton.CancelButton,'Отмена'),(QWizard.WizardButton.FinishButton,'Закрыть')]:self.setButtonText(role,label)
        for title in ('Источник и лист','Колонки и исходные строки','Аппараты и клиенты','Проверка и подтверждение','Отчёт'):
            p=QWizardPage();p.setTitle(title);outer=QVBoxLayout(p);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();inner=QVBoxLayout(body);inner.setAlignment(Qt.AlignmentFlag.AlignTop);scroll.setWidget(body);outer.addWidget(scroll);self._layouts.append(inner);self.addPage(p)
        l=self._layouts[0];note=QLabel('Старый номер ремонта не определяет аппарат. Программа не угадывает связи по модели или фамилии. Рабочая база изменится только после последнего подтверждения.');note.setWordWrap(True);l.addWidget(note)
        self.path=QLineEdit();self.path.setAccessibleName('Файл исторического журнала');l.addWidget(self.path);button(l,'Выбрать XLSX / CSV',self.choose)
        self.sheet=QComboBox();self.sheet.setAccessibleName('Лист Excel');l.addWidget(self.sheet);button(l,'Прочитать список листов',self.inspect)
        self.source_label=QLineEdit();self.source_label.setPlaceholderText('Необязательный постоянный ID источника для сверки обновлённого журнала');l.addWidget(self.source_label)
        self.copy_documents=QCheckBox('Скопировать указанные локальные документы в проект');l.addWidget(self.copy_documents);self.document_root=QLineEdit();self.document_root.setReadOnly(True);l.addWidget(self.document_root);button(l,'Разрешённая папка исходных документов',self.choose_root)
        l=self._layouts[1];self.count=QLabel();l.addWidget(self.count);self.preview=Grid([]);l.addWidget(self.preview,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();self.mapping_form=QFormLayout(body);self.mapping_form.setFormAlignment(Qt.AlignmentFlag.AlignTop);scroll.setWidget(body);l.addWidget(scroll,2)
        self.default_status=QComboBox();self.default_status.addItem('Выберите статус пустых значений',None)
        for k,v in STATUSES.items():self.default_status.addItem(v[0],k)
        self.mapping_form.addRow('Пустой производственный статус',self.default_status)
        l=self._layouts[2];note=QLabel('Выберите строку и задайте решения. Для нового аппарата с разными заказчиками отдельно выберите текущего владельца. Одноимённых клиентов проверяйте вручную.');note.setWordWrap(True);l.addWidget(note)
        self.identity=Grid([('number','Ремонт'),('equipment','Постоянный №'),('model','Модель'),('client','Исторический клиент'),('equipment_decision','Решение по аппарату'),('client_decision','Решение по клиенту'),('status','Результат'),('issues','Проблемы / предупреждения')]);l.addWidget(self.identity)
        bar=FlowLayout();l.addLayout(bar);button(bar,'Связать / создать / отложить выбранную строку',self.decide);button(bar,'Подтвердить создание новых записей',self.confirm_new);button(bar,'Проверить повторно',self.refresh_plan)
        self.identity.doubleClicked.connect(self.decide)
        self.status_container=QWidget();self.status_form=QFormLayout(self.status_container);self.status_form.setFormAlignment(Qt.AlignmentFlag.AlignTop);self.status_scroll=QScrollArea();self.status_scroll.setWidgetResizable(True);self.status_scroll.setMaximumHeight(160);self.status_scroll.setWidget(self.status_container);l.addWidget(self.status_scroll)
        l=self._layouts[3];self.selection=QTableWidget(0,4);self.selection.setHorizontalHeaderLabels(['Выбрать','Ремонт / строки','Результат','Проблемы и предупреждения']);self.selection.horizontalHeader().setStretchLastSection(True);l.addWidget(self.selection)
        self.confirmed=QCheckBox('Я проверил аппарат, заказчика, даты, статусы, позиции и суммы.\nПрименить выбранные ремонты одной транзакцией; остальные строки отложить.');l.addWidget(self.confirmed)
        l=self._layouts[4];self.report=QPlainTextEdit();self.report.setReadOnly(True);l.addWidget(self.report);button(l,'Сохранить отчёт JSON',self.save_report)
        for label in self.findChildren(QLabel):label.setTextFormat(Qt.TextFormat.PlainText)
    def choose(self):
        p,_=QFileDialog.getOpenFileName(self,'Исторический журнал','','Таблицы (*.xlsx *.csv)')
        if p:self.path.setText(p);self.inspect()
    def choose_root(self):
        p=QFileDialog.getExistingDirectory(self,'Разрешённая локальная папка')
        if p:self.document_root.setText(p)
    def inspect(self):
        p=self.path.text()
        def installed(names):
            self.sheet.clear()
            for name in names:self.sheet.addItem(name,name)
        self.workspace.run(lambda:workbook_sheets(p),installed,'Читаю листы без импорта…')
    def mapping(self):return {k:w.currentData() for k,w in self.mappings.items() if w.currentData()}
    def load_source(self):
        path=self.path.text();sheet=self.sheet.currentData()
        if Path(path).suffix.lower()=='.xlsx' and not sheet:
            QMessageBox.information(self,'Импорт','Сначала прочитайте и выберите лист Excel');return
        def installed(data):
            self.table=data[0];self.decisions={'equipment_decisions':{},'client_decisions':{},'current_owners':{}}
            self.preview.records.columns=[(h,h) for h in self.table.headers];self.preview.install([r.values for r in self.table.records[:100]])
            self.count.setText(f'Всего {len(self.table.records)} строк. На экране первые 100; проверка и импорт используют все строки.')
            for widget in self.mappings.values():self.mapping_form.removeRow(widget)
            self.mappings={}
            for key,label in HISTORY_FIELDS.items():
                combo=QComboBox();combo.addItem('Не использовать',None)
                for header in self.table.headers:combo.addItem(header,header)
                for header in self.table.headers:
                    if header.casefold() in (key.casefold(),label.rstrip(' *').casefold()):combo.setCurrentIndex(combo.findData(header));break
                combo.setAccessibleName(label);self.mapping_form.addRow(label,combo);self.mappings[key]=combo
            self.ready_page=0;self.next()
        self.workspace.run(lambda:_load(path,sheet),installed,'Читаю ограниченный исходный файл…')
    def options(self):
        return {**self.decisions,'sheet':self.sheet.currentData(),'default_status':self.default_status.currentData(),
                'status_map':{raw:widget.currentData() for raw,widget in self.statuses.items() if widget.currentData()},
                'source_label':self.source_label.text(),'copy_documents':self.copy_documents.isChecked(),'document_root':self.document_root.text() or None}
    def build_statuses(self):
        for w in self.statuses.values():self.status_form.removeRow(w)
        self.statuses={};header=self.mapping().get('status')
        raw=sorted({str(r.values.get(header,'')) for r in self.table.records if header and r.values.get(header,'')})
        if len(raw)>100:raise ValueError('Больше 100 различных статусов: проверьте выбранную колонку')
        for value in raw:
            combo=QComboBox();combo.addItem('Сопоставьте явно',None)
            for k,v in STATUSES.items():combo.addItem(v[0],k)
            self.status_form.addRow(value,combo);self.statuses[value]=combo
    def refresh_plan(self,after=None):
        mapping=self.mapping();options=self.options();path=self.path.text()
        def installed(plan):
            self.plan=plan
            self.identity.install([{'id':g['key'],'number':g['data'].get('repair_number',''),'equipment':g['data'].get('equipment_number',''),'model':g['data'].get('model',''),'client':g['data'].get('client_name',''),'equipment_decision':g['equipment_decision'] or 'не выбрано','client_decision':g['client_decision'] or 'не выбрано','status':g['status'],'issues':'; '.join(g['errors']+g['warnings'])} for g in plan['groups']])
            if callable(after):after()
        self.workspace.run(lambda:preview_history(self.store,path,mapping,**options),installed,'Проверяю все строки без изменения базы…')
    def decide(self,*args):
        row=self.identity.selected()
        if not row or not self.plan:return
        g=next(g for g in self.plan['groups'] if g['key']==row['id']);data=g['data'];eqkey=data['equipment_key'];ckey=data['client_key']
        owner_choices=[('', 'Не выбран')]+list(dict((x['data']['client_key'],x['data'].get('client_name') or x['data']['client_key']) for x in self.plan['groups'] if x['data']['equipment_key']==eqkey).items())
        fields=[('equipment','Физический аппарат',[('', 'Решение не принято'),('new','Создать новый'),('defer','Отложить')]+[(x['id'],x['number']+' · '+x['model']) for x in self.equipment]),('client','Заказчик этого ремонта',[('', 'Решение не принято'),('new','Создать нового'),('defer','Отложить')]+[(x['id'],x['name']) for x in self.clients]),('owner','Текущий владелец нового аппарата',owner_choices)]
        d=FieldsDialog('Явные решения по исходным идентификаторам',fields,{'equipment':self.decisions['equipment_decisions'].get(eqkey,''),'client':self.decisions['client_decisions'].get(ckey,''),'owner':self.decisions['current_owners'].get(eqkey,'')},self)
        if d.exec()==QDialog.DialogCode.Accepted:
            v=d.values()
            for bucket,key,value in [('equipment_decisions',eqkey,v['equipment']),('client_decisions',ckey,v['client']),('current_owners',eqkey,v['owner'])]:
                if value:self.decisions[bucket][key]=value
                else:self.decisions[bucket].pop(key,None)
            self.refresh_plan()
    def confirm_new(self):
        if not self.plan:return
        from .widgets import confirm
        if not confirm(self,'Явно создать новых клиентов по исходным ключам и новые аппараты с незанятыми постоянными номерами? Совпадающие номера аппаратов потребуют ручного выбора; сведения и текущих владельцев нужно проверить.'):return
        for g in self.plan['groups']:
            d=g['data'];self.decisions['client_decisions'].setdefault(d['client_key'],'new')
            if d.get('equipment_number') and not g['equipment_candidates']:self.decisions['equipment_decisions'].setdefault(d['equipment_key'],'new')
        self.refresh_plan()
    def selection_page(self):
        groups=self.plan['groups'];self.selection.setRowCount(len(groups));self.confirmed.setChecked(False)
        for i,g in enumerate(groups):
            item=QTableWidgetItem();item.setData(Qt.ItemDataRole.UserRole,g['key']);item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if g['status'] in ('ready','already_imported') else Qt.CheckState.Unchecked)
            if g['status'] not in ('ready','already_imported'):item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.selection.setItem(i,0,item)
            for j,value in enumerate([g['data'].get('repair_number','')+' / '+','.join(str(r['row']) for r in g['rows']),IMPORT_STATES.get(g['status'],g['status']),'; '.join(g['errors']+g['warnings'])],1):
                cell=QTableWidgetItem(value);cell.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);self.selection.setItem(i,j,cell)
        self.ready_page=2;self.next()
    def validateCurrentPage(self):
        page=self.currentId()
        if self.workspace.worker:return False
        if self.ready_page==page:self.ready_page=-1;return True
        if page==0:self.load_source();return False
        if page==1:
            try:self.build_statuses()
            except Exception as exc:QMessageBox.warning(self,'Импорт',str(exc));return False
            self.refresh_plan(lambda:(setattr(self,'ready_page',1),self.next()));return False
        if page==2:self.refresh_plan(self.selection_page);return False
        if page==3:
            if self.applied:return True
            keys=[self.selection.item(i,0).data(Qt.ItemDataRole.UserRole) for i in range(self.selection.rowCount()) if self.selection.item(i,0).checkState()==Qt.CheckState.Checked]
            if not self.confirmed.isChecked() or not keys:QMessageBox.information(self,'Импорт','Выберите проверенные строки и подтвердите изменения');return False
            plan=self.plan
            def applied(report):
                self.result_report=report
                lines=['Импорт завершён. Изменения выбранных ремонтов сохранены одной транзакцией.',f"Импортировано: {report['imported']} · Уже было: {report['already_imported']} · Отложено: {report['deferred']}",'']
                for row in report['rows'][:200]:
                    lines.append('Исходные строки '+', '.join(str(x['row']) for x in row['rows'])+': '+{'imported':'импортировано','already_imported':'уже импортировано','deferred':'отложено'}[row['result']]);lines.extend(row.get('warnings',[])+row.get('issues',[]))
                if len(report['rows'])>200:lines.append('Остальные записи доступны в полном отчёте JSON.')
                self.report.setPlainText('\n'.join(lines));self.applied=True;self.next();self.button(QWizard.WizardButton.BackButton).setEnabled(False)
            self.workspace.run(lambda:import_history(self.store,plan,confirmed=True,selected_keys=keys),applied,'Атомарно импортирую выбранные ремонты…');return False
        return True
    def save_report(self):
        path,_=QFileDialog.getSaveFileName(self,'Новый отчёт JSON','history-import-report.json','JSON (*.json)')
        if path:
            content=json.dumps(self.result_report,ensure_ascii=False,indent=2)
            def save():
                with Path(path).open('x',encoding='utf-8') as f:f.write(content+'\n')
            self.workspace.run(save)
    def reject(self):
        if not self.workspace.worker:super().reject()
    def closeEvent(self,event):
        if self.workspace.worker:event.ignore()
        else:event.accept()
