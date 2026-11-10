"""Five-step historical import with explicit identities and atomic confirmation."""
import json
from pathlib import Path
from threading import Event
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (QWizard,QWizardPage,QVBoxLayout,QFormLayout,QLineEdit,QComboBox,QLabel,QFileDialog,QScrollArea,QWidget,QTableWidget,QTableWidgetItem,QCheckBox,QPlainTextEdit,QDialog,QStyledItemDelegate)
from ...service.history_import import HISTORY_FIELDS,workbook_sheets,_load,preview_history,import_history
from ...service.import_mapping import propose_history
from ...service.statuses import STATUSES
from ...validation import Issue
from .forms import FieldsDialog,fit_dialog
from ..flow import FlowLayout
from ..theme import COLORS
from ..widgets import DataModel, DataView, text
from .models import RowsModel
from .presentation import IMPORT_STATES
from .widgets import Grid,button

_MONEY_FIELDS=('work_cost','parts_cost','delivery_cost','other_cost','discount','final_total','paid_amount','price')
_FLAG_FIELDS=('status','cost_state','payment_state')


class ImportCellDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.data(Qt.ItemDataRole.AccessibleDescriptionRole):
            painter.save()
            painter.setPen(QPen(QColor(COLORS['error'])))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(option.rect.adjusted(0,0,-1,-1))
            painter.restore()


class ImportCheckRows(RowsModel):
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and self.rows[index.row()]['status'] in ('error','conflict'):
            if role==Qt.ItemDataRole.ForegroundRole and self.columns[index.column()][0] in ('status','issues'):
                return QColor(COLORS['error'])
            if role==Qt.ItemDataRole.BackgroundRole:
                color=QColor(COLORS['error'])
                color.setAlpha(28)
                return color
        return super().data(index,role)


class HistoryWizard(QWizard):
    def __init__(self,workspace):
        super().__init__(workspace);self.workspace=workspace;self.store=workspace.store;self.setWindowTitle('Импорт журнала ремонтов из Excel / выгрузки 1С');fit_dialog(self,1020,720)
        # Windows defaults to Aero, which paints a white native footer outside
        # the shared application QSS. Classic uses the same themed controls as Linux.
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        self.plan=None;self.table=None;self.ready_page=-1;self.applied=False;self.decisions={'equipment_decisions':{},'client_decisions':{},'current_owners':{},'owner_decisions':{}};self.mappings={};self.statuses={}
        self.cancel_event=Event();self._operation_active=False;self._source_signature=None;self._mapping_undo=None;self._status_signature=None
        self.clients=workspace.cache.get('active_clients',[]);self.equipment=workspace.cache.get('active_equipment',[])
        self._layouts=[];self._errors=[];self._issues={};self._mapping_errors={};self._mapping_candidates={}
        for role,label in [(QWizard.WizardButton.BackButton,'Назад'),(QWizard.WizardButton.NextButton,'Далее'),(QWizard.WizardButton.CancelButton,'Отмена'),(QWizard.WizardButton.FinishButton,'Закрыть')]:self.setButtonText(role,label)
        for title in ('1. Файл','2. Соответствие столбцов','3. Проверка строк и связей','4. Подтверждение','5. Результат'):
            p=QWizardPage();p.setTitle(title);outer=QVBoxLayout(p);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();inner=QVBoxLayout(body);inner.setAlignment(Qt.AlignmentFlag.AlignTop);scroll.setWidget(body);outer.addWidget(scroll);self._layouts.append(inner);self.addPage(p)
            error=text('','error');error.setAccessibleName('Ошибка шага импорта');error.setStyleSheet(f'border:1px solid {COLORS["error"]};border-radius:5px;padding:6px;');error.hide();inner.addWidget(error);self._errors.append(error)
        l=self._layouts[0];note=text('Выберите Excel или CSV, сохранённый на компьютере. Для журнала из 1С сначала выгрузите файл.\nСтарый номер ремонта и постоянный номер аппарата выбираются отдельно. Записи будут добавлены после подтверждения.');l.addWidget(note)
        self.path=QLineEdit();self.path.setAccessibleName('Файл исторического журнала');l.addWidget(self.path);button(l,'Выбрать XLSX / CSV',self.choose)
        self.sheet=QComboBox();self.sheet.setAccessibleName('Лист Excel');l.addWidget(self.sheet);button(l,'Прочитать список листов',self.inspect)
        self.encoding=QComboBox();self.encoding.setAccessibleName('Кодировка журнала CSV')
        for label,value in [('Автоматически (UTF-8 / Windows-1251)','auto'),('UTF-8','utf-8'),('UTF-8 с BOM','utf-8-sig'),('Windows-1251 (CP1251)','cp1251')]:self.encoding.addItem(label,value)
        l.addWidget(self.encoding)
        self.path.textChanged.connect(self.update_source_controls)
        self.update_source_controls()
        self.source_label=QLineEdit();self.source_label.setPlaceholderText('Необязательный постоянный ID источника для сверки обновлённого журнала');l.addWidget(self.source_label)
        self.copy_documents=QCheckBox('Скопировать указанные локальные документы в проект');l.addWidget(self.copy_documents);self.document_root=QLineEdit();self.document_root.setReadOnly(True);l.addWidget(self.document_root);button(l,'Разрешённая папка исходных документов',self.choose_root)
        l=self._layouts[1];self.count=text();l.addWidget(self.count)
        self.preview=DataView();self.preview.setAccessibleName('Ячейки исходного файла');self.preview.setAlternatingRowColors(True)
        self.preview.setEditTriggers(DataView.EditTrigger.NoEditTriggers);self.preview.setMinimumHeight(135)
        self.preview.horizontalHeader().setDefaultSectionSize(155);self.preview.horizontalHeader().setMinimumSectionSize(75)
        self.source_model=DataModel(self.preview);self.preview.setModel(self.source_model)
        self.preview.setItemDelegate(ImportCellDelegate(self.preview));l.addWidget(self.preview,1)
        tools=FlowLayout();l.addLayout(tools);self.suggest_button=button(tools,'Предложить связи',self.propose)
        self.undo_button=button(tools,'Вернуть прежние связи',self.undo_mapping);self.undo_button.setEnabled(False)
        self.mapping_hint=text('Проверьте автоматически предложенные связи. Неоднозначные столбцы выберите вручную.');l.addWidget(self.mapping_hint)
        self.mapping_warning=text('','error');self.mapping_warning.setStyleSheet(f'border:1px solid {COLORS["error"]};border-radius:5px;padding:6px;')
        self.mapping_warning.hide();l.addWidget(self.mapping_warning)
        self.mapping_scroll=QScrollArea();self.mapping_scroll.setWidgetResizable(True);body=QWidget();self.mapping_form=QFormLayout(body);self.mapping_form.setFormAlignment(Qt.AlignmentFlag.AlignTop);self.mapping_scroll.setWidget(body);l.addWidget(self.mapping_scroll,2)
        self.default_status=QComboBox();self.default_status.addItem('Выберите статус пустых значений',None)
        for k,v in STATUSES.items():self.default_status.addItem(v[0],k)
        self.mapping_form.addRow('Пустой производственный статус',self.default_status)
        self.mapping_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        l=self._layouts[2];note=QLabel('Выберите строку и задайте решения. Для нового аппарата с разными заказчиками отдельно выберите текущего владельца. Одноимённых клиентов проверяйте вручную.');note.setWordWrap(True);l.addWidget(note)
        self.summary=text('','section');l.addWidget(self.summary)
        self.identity=Grid([('number','Ремонт'),('equipment','Постоянный №'),('model','Модель'),('client','Исторический клиент'),('equipment_decision','Решение по аппарату'),('client_decision','Решение по клиенту'),('status','Результат'),('issues','Проблемы / предупреждения')],model_type=ImportCheckRows);l.addWidget(self.identity)
        bar=FlowLayout();l.addLayout(bar);button(bar,'Связать / создать / отложить выбранную строку',self.decide);button(bar,'Подтвердить создание новых записей',self.confirm_new);button(bar,'Проверить повторно',self.refresh_plan)
        self.identity.doubleClicked.connect(self.decide)
        self.issue_detail=QPlainTextEdit()
        self.issue_detail.setReadOnly(True)
        self.issue_detail.setAccessibleName('Ошибки и предупреждения выбранной строки')
        self.issue_detail.setPlaceholderText('Выберите строку, чтобы увидеть сведения о проверке.')
        self.issue_detail.setMaximumHeight(95)
        l.addWidget(self.issue_detail)
        self.identity.selectionModel().currentRowChanged.connect(self.show_row_issues)
        button(bar,'К первой проблемной строке',self.focus_first_issue)
        self.source_issue_button=button(bar,'Показать исходную ячейку',self.focus_source_issue)
        self.source_issue_button.setEnabled(False)
        self.status_container=QWidget();self.status_form=QFormLayout(self.status_container);self.status_form.setFormAlignment(Qt.AlignmentFlag.AlignTop);self.status_scroll=QScrollArea();self.status_scroll.setWidgetResizable(True);self.status_scroll.setMaximumHeight(160);self.status_scroll.setWidget(self.status_container);l.addWidget(self.status_scroll)
        l=self._layouts[3];self.selection=QTableWidget(0,4);self.selection.setHorizontalHeaderLabels(['Выбрать','Ремонт / строки','Результат','Проблемы и предупреждения']);self.selection.horizontalHeader().setStretchLastSection(True);l.addWidget(self.selection)
        self.selection.setColumnWidth(1,180);self.selection.setColumnWidth(2,150)
        self.confirmed=QCheckBox('Я проверил аппарат, заказчика, даты, статусы, позиции и суммы.\nПрименить выбранные ремонты одной транзакцией; остальные строки отложить.');l.addWidget(self.confirmed)
        l=self._layouts[4];self.report=QPlainTextEdit();self.report.setReadOnly(True);l.addWidget(self.report);button(l,'Сохранить отчёт JSON',self.save_report)
        for label in self.findChildren(QLabel):label.setTextFormat(Qt.TextFormat.PlainText)
    def update_source_controls(self):
        self.encoding.setVisible(Path(self.path.text()).suffix.lower()=='.csv')

    def show_error(self, message):
        if self.currentId()>=0:
            error=self._errors[self.currentId()]
            error.setText('Ошибка. '+message)
            error.show()

    def review_mapping(self,*_):
        # Header vocabulary provides a targeted warning before the dry run.
        # The existing parser still validates the actual source values.
        flags={header for key in _FLAG_FIELDS for header in self._mapping_candidates.get(key,())}
        flags.update(self.mapping().get(key) for key in _FLAG_FIELDS)
        self._mapping_errors={key:combo.currentData() for key in _MONEY_FIELDS
                              if (combo:=self.mappings.get(key)) and combo.currentData() and combo.currentData() in flags}
        for key,combo in self.mappings.items():
            issue=self._mapping_errors.get(key)
            style=f'border:1px solid {COLORS["error"]};' if issue else ''
            if style!=combo.styleSheet():combo.setStyleSheet(style)
            combo.setAccessibleDescription(f'Проверьте связь. Колонка «{issue}» предназначена для отметок, здесь нужны суммы.' if issue else '')
        notice='Проверьте соответствие столбцов: '
        self.mapping_warning.setText(notice+'; '.join(f'«{HISTORY_FIELDS[key]}» ← «{header}»' for key,header in self._mapping_errors.items())+
                                     '. Укажите колонку с суммами или выберите «Не использовать».')
        self.mapping_warning.setVisible(bool(self._mapping_errors))
        self._issues={}
        self.source_model.set_issues([], {})

    def show_row_issues(self,*_):
        row=self.identity.selected()
        self.issue_detail.setPlainText(row.get('issues','') if row else '')
        is_error=bool(row and row['status'] in ('error','conflict'))
        self.issue_detail.setStyleSheet(f'color:{COLORS["error"]};border:1px solid {COLORS["error"]};' if is_error else '')
        self.source_issue_button.setEnabled(self.source_issue(row,self.mapping()) is not None)

    def source_issue(self, row, mapping):
        issues=self._issues.get(row['id'],()) if row else ()
        return next((issue for issue in issues if issue.field in mapping),None)

    def focus_source_issue(self):
        mapping=self.mapping()
        issue=self.source_issue(self.identity.selected(),mapping)
        if not issue:return
        index=self.source_model.index_for_issue(issue,mapping)
        if not index.isValid():return
        self.back()
        self.preview.setCurrentIndex(index)
        self.preview.scrollTo(index)
        self.preview.setFocus()

    def focus_first_issue(self):
        for i in range(self.identity.proxy.rowCount()):
            index=self.identity.proxy.index(i,0)
            row=self.identity.records.rows[self.identity.proxy.mapToSource(index).row()]
            if row['status'] in ('error','conflict','needs_confirmation'):
                self.identity.selectRow(i)
                self.identity.scrollTo(index)
                self.issue_detail.setFocus()
                return

    def run_operation(self,fn,callback=None,message='Проверяю журнал…'):
        if self.workspace.worker:return False
        self.cancel_event.clear();self._operation_active=True
        if self.currentId()>=0:self._errors[self.currentId()].hide()
        embedded=not self.isWindow()
        if not self.workspace.run(fn,callback,message,on_error=self.show_error,inline_error=embedded,keep_page_enabled=embedded):
            self._operation_active=False
            return False
        job=self.workspace.worker
        self.setEnabled(True)
        for index in self.pageIds():self.page(index).setEnabled(False)
        for role in (QWizard.WizardButton.BackButton,QWizard.WizardButton.NextButton,QWizard.WizardButton.FinishButton):self.button(role).setEnabled(False)
        self.button(QWizard.WizardButton.CancelButton).setEnabled(True);self.setButtonText(QWizard.WizardButton.CancelButton,'Остановить операцию')
        def finished():
            self._operation_active=False
            for index in self.pageIds():self.page(index).setEnabled(True)
            self.setButtonText(QWizard.WizardButton.CancelButton,'Отмена')
            self.button(QWizard.WizardButton.BackButton).setEnabled(self.currentId()>0 and not self.applied)
            self.button(QWizard.WizardButton.NextButton).setEnabled(self.currentId()<4)
            self.button(QWizard.WizardButton.FinishButton).setEnabled(self.currentId()==4)
        job.finished.connect(finished);return True
    def propose(self):
        if not self.table or self.workspace.worker:return
        self._mapping_undo={key:combo.currentData() for key,combo in self.mappings.items()}
        choices,candidates=propose_history(self.table.headers)
        for key,header in choices.items():
            if not self.mappings[key].currentData():self.mappings[key].setCurrentIndex(self.mappings[key].findData(header))
        ambiguous=[HISTORY_FIELDS[key].rstrip(' *') for key,values in candidates.items() if len(values)>1 and not self.mappings[key].currentData()]
        self.mapping_hint.setText('Проверьте предложения. '+('Несколько совпадений: '+', '.join(ambiguous)+'.' if ambiguous else 'Ранее выбранные связи сохранены.'))
        self.undo_button.setEnabled(True)
    def undo_mapping(self):
        if self._mapping_undo is None or self.workspace.worker:return
        current={key:combo.currentData() for key,combo in self.mappings.items()}
        for key,header in self._mapping_undo.items():self.mappings[key].setCurrentIndex(self.mappings[key].findData(header))
        self._mapping_undo=current;self.mapping_hint.setText('Прежние связи возвращены. Проверьте данные перед импортом.')
    def choose(self):
        p,_=QFileDialog.getOpenFileName(self,'Выбрать файл журнала ремонтов','','Таблицы (*.xlsx *.csv)')
        if p:self.path.setText(p);self.inspect()
    def choose_root(self):
        p=QFileDialog.getExistingDirectory(self,'Разрешённая локальная папка')
        if p:self.document_root.setText(p)
    def inspect(self):
        p=self.path.text()
        def installed(names):
            self.sheet.clear()
            for name in names:self.sheet.addItem(name,name)
        self.run_operation(lambda:workbook_sheets(p),installed,'Читаю листы без импорта…')
    def mapping(self):return {k:w.currentData() for k,w in self.mappings.items() if w.currentData()}
    def load_source(self):
        path=self.path.text();sheet=self.sheet.currentData();encoding=self.encoding.currentData()
        prior={key:combo.currentData() for key,combo in self.mappings.items()}
        if Path(path).suffix.lower()=='.xlsx' and not sheet:
            self.show_error('Сначала прочитайте список листов Excel и выберите нужный лист.');return
        def installed(data):
            signature=(str(Path(path).absolute()),sheet,encoding,data[1]);same=signature==self._source_signature
            self.table=data[0];self._source_signature=signature
            if not same:self.decisions={'equipment_decisions':{},'client_decisions':{},'current_owners':{},'owner_decisions':{}};self._mapping_undo=None;self.undo_button.setEnabled(False)
            self.source_model.set_table(self.table)
            self.count.setText(f'Строк в файле: {len(self.table.records)}. Слева указаны номера строк исходной таблицы.')
            for widget in self.mappings.values():self.mapping_form.removeRow(widget)
            self.mappings={}
            proposals,self._mapping_candidates=propose_history(self.table.headers)
            for key,label in HISTORY_FIELDS.items():
                combo=QComboBox();combo.addItem('Не использовать',None)
                for header in self.table.headers:combo.addItem(header,header)
                chosen=prior.get(key) if same else proposals.get(key)
                if chosen in self.table.headers:combo.setCurrentIndex(combo.findData(chosen))
                combo.setAccessibleName(label);self.mapping_form.addRow(label,combo);self.mappings[key]=combo
                combo.currentIndexChanged.connect(self.review_mapping)
            self.review_mapping()
            self.ready_page=0;self.next()
        self.run_operation(lambda:_load(path,sheet,encoding,self.cancel_event),installed,'Читаю ограниченный исходный файл…')
    def options(self):
        return {**self.decisions,'sheet':self.sheet.currentData(),'default_status':self.default_status.currentData(),
                'status_map':{raw:widget.currentData() for raw,widget in self.statuses.items() if widget.currentData()},
                'source_label':self.source_label.text(),'copy_documents':self.copy_documents.isChecked(),'document_root':self.document_root.text() or None,
                'encoding':self.encoding.currentData(),'separate_clients':True}
    def build_statuses(self):
        header=self.mapping().get('status');signature=(self._source_signature,header)
        chosen={raw:widget.currentData() for raw,widget in self.statuses.items()} if signature==self._status_signature else {}
        for w in self.statuses.values():self.status_form.removeRow(w)
        self.statuses={};self._status_signature=signature
        raw=sorted({str(r.values.get(header,'')) for r in self.table.records if header and r.values.get(header,'')})
        if len(raw)>100:raise ValueError('Больше 100 различных статусов: проверьте выбранную колонку')
        for value in raw:
            combo=QComboBox();combo.addItem('Выберите статус DocFlow',None)
            for k,v in STATUSES.items():combo.addItem(v[0],k)
            combo.setCurrentIndex(max(0,combo.findData(chosen.get(value))))
            self.status_form.addRow(value,combo);self.statuses[value]=combo
    def refresh_plan(self,after=None):
        mapping=self.mapping();options=self.options();path=self.path.text()
        def installed(plan):
            self.plan=plan
            self._issues={g['key']:[Issue(**item) for item in g['field_issues']]
                          for g in plan['groups'] if g.get('field_issues')}
            self.source_model.set_issues([issue for issues in self._issues.values() for issue in issues],mapping)
            counts=plan['counts'];self.summary.setText(f"Готово новых: {counts['ready']} · Уже импортировано: {counts['already_imported']} · Конфликты: {counts['conflict']} · Ошибки: {counts['error']} · Нужны решения: {counts['needs_confirmation']} · Отложено: {counts['deferred']}. База пока не изменена.")
            self.identity.install([{'id':g['key'],'number':g['data'].get('repair_number',''),'equipment':g['data'].get('equipment_number',''),'model':g['data'].get('model',''),'client':g['data'].get('client_name',''),'equipment_decision':g['equipment_decision'] or 'не выбрано','client_decision':g['client_decision'] or 'не выбрано','status':g['status'],'issues':'; '.join(g['errors']+g['warnings'])} for g in plan['groups']])
            self.show_row_issues()
            if counts['error'] or counts['conflict']:self.focus_first_issue()
            if callable(after):after()
        self.run_operation(lambda:preview_history(self.store,path,mapping,**options,cancel=self.cancel_event),installed,'Проверяю все строки без изменения базы…')
    def decide(self,*args):
        row=self.identity.selected()
        if not row or not self.plan:return
        g=next(g for g in self.plan['groups'] if g['key']==row['id']);data=g['data'];eqkey=data['equipment_key'];ckey=data['client_key']
        owner_choices=[('', 'Не выбран')]+list(dict((x['data']['client_key'],x['data'].get('client_name') or x['data']['client_key']) for x in self.plan['groups'] if x['data']['equipment_key']==eqkey).items())
        owner_choices+=list(dict((x['owner_person']['client_key'],x['owner_person'].get('client_name') or x['owner_person']['client_key']) for x in self.plan['groups'] if x['data']['equipment_key']==eqkey and x.get('owner_person')).items())
        fields=[('equipment','Физический аппарат',[('', 'Решение не принято'),('new','Создать новый'),('defer','Отложить')]+[(x['id'],x['number']+' · '+x['model']) for x in self.equipment]),('client','Заказчик этого ремонта',[('', 'Решение не принято'),('new','Создать нового'),('defer','Отложить')]+[(x['id'],x['name']) for x in self.clients]),('owner','Текущий владелец нового аппарата',owner_choices)]
        person=g.get('owner_person');values={'equipment':self.decisions['equipment_decisions'].get(eqkey,''),'client':self.decisions['client_decisions'].get(ckey,''),'owner':self.decisions['current_owners'].get(eqkey,'')}
        if person:
            fields.append(('owner_record','Собственник из отдельной колонки',[('', 'Решение не принято'),('new','Создать отдельного собственника'),('defer','Пока не выбирать')]+[(x['id'],x['name']) for x in self.clients]));values['owner_record']=self.decisions['owner_decisions'].get(person['client_key'],'')
        d=FieldsDialog('Явные решения по исходным идентификаторам',fields,values,self)
        def apply(v):
            for bucket,key,value in [('equipment_decisions',eqkey,v['equipment']),('client_decisions',ckey,v['client']),('current_owners',eqkey,v['owner'])]:
                if value:self.decisions[bucket][key]=value
                else:self.decisions[bucket].pop(key,None)
            if person:
                if v['owner_record']:self.decisions['owner_decisions'][person['client_key']]=v['owner_record']
                else:self.decisions['owner_decisions'].pop(person['client_key'],None)
            self.refresh_plan()
        if self.isWindow():
            if d.exec()==QDialog.DialogCode.Accepted:apply(d.values())
        else:
            self.workspace.embed_form(d,apply)
    def confirm_new(self):
        if not self.plan:return
        from .widgets import confirm
        if not confirm(self,'Явно создать новых заказчиков и собственников по проверенным ключам и аппараты с незанятыми постоянными номерами? Без внешнего ID одноимённые люди разных обращений останутся отдельными. Совпадающие номера аппаратов и существующие клиенты требуют ручного выбора.'):return
        for g in self.plan['groups']:
            d=g['data']
            if len(g['source_client_ids'])==1:self.decisions['client_decisions'].setdefault(d['client_key'],g['source_client_ids'][0])
            elif not g['client_candidates'] and not g['source_client_ids']:self.decisions['client_decisions'].setdefault(d['client_key'],'new')
            if g.get('owner_person'):
                if len(g['source_owner_ids'])==1:self.decisions['owner_decisions'].setdefault(g['owner_person']['client_key'],g['source_owner_ids'][0])
                elif not g['owner_candidates'] and not g['source_owner_ids']:self.decisions['owner_decisions'].setdefault(g['owner_person']['client_key'],'new')
            if d.get('equipment_number') and not g['equipment_candidates']:self.decisions['equipment_decisions'].setdefault(d['equipment_key'],'new')
        self.refresh_plan()
    def selection_page(self):
        groups=self.plan['groups'];self.selection.setRowCount(len(groups));self.confirmed.setChecked(False)
        for i,g in enumerate(groups):
            item=QTableWidgetItem();item.setData(Qt.ItemDataRole.UserRole,g['key']);item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if g['status'] in ('ready','already_imported') else Qt.CheckState.Unchecked)
            if g['status'] not in ('ready','already_imported'):item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.selection.setItem(i,0,item)
            for j,value in enumerate([g['data'].get('repair_number','')+' / '+','.join(str(r['row']) for r in g['rows']),IMPORT_STATES.get(g['status'],g['status']),'; '.join(g['errors']+g['warnings'])],1):
                cell=QTableWidgetItem(value);cell.setToolTip(value);cell.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
                if g['status'] in ('error','conflict'):cell.setForeground(QColor(COLORS['error']))
                self.selection.setItem(i,j,cell)
        self.ready_page=2;self.next()
    def validateCurrentPage(self):
        page=self.currentId()
        if self.workspace.worker:return False
        if self.ready_page==page:self.ready_page=-1;return True
        if page==0:self.load_source();return False
        if page==1:
            try:self.build_statuses()
            except ValueError as exc:self.show_error(str(exc));return False
            self.refresh_plan(lambda:(setattr(self,'ready_page',1),self.next()));return False
        if page==2:self.refresh_plan(self.selection_page);return False
        if page==3:
            if self.applied:return True
            keys=[self.selection.item(i,0).data(Qt.ItemDataRole.UserRole) for i in range(self.selection.rowCount()) if self.selection.item(i,0).checkState()==Qt.CheckState.Checked]
            if not self.confirmed.isChecked() or not keys:
                self.show_error('Выберите проверенные строки и подтвердите изменения.');return False
            plan=self.plan
            def applied(report):
                self.result_report=report
                lines=['Импорт завершён. Изменения выбранных ремонтов сохранены одной транзакцией.',f"Импортировано: {report['imported']} · Уже было: {report['already_imported']} · Отложено: {report['deferred']}",'']
                for row in report['rows'][:200]:
                    lines.append('Исходные строки '+', '.join(str(x['row']) for x in row['rows'])+': '+{'imported':'импортировано','already_imported':'уже импортировано','deferred':'отложено'}[row['result']]);lines.extend(row.get('warnings',[])+row.get('issues',[]))
                if len(report['rows'])>200:lines.append('Остальные записи доступны в полном отчёте JSON.')
                self.report.setPlainText('\n'.join(lines));self.applied=True;self.next();self.button(QWizard.WizardButton.BackButton).setEnabled(False)
            self.run_operation(lambda:import_history(self.store,plan,confirmed=True,selected_keys=keys,cancel=self.cancel_event),applied,'Атомарно импортирую выбранные ремонты…');return False
        return True
    def save_report(self):
        path,_=QFileDialog.getSaveFileName(self,'Новый отчёт JSON','history-import-report.json','JSON (*.json)')
        if path:
            content=json.dumps(self.result_report,ensure_ascii=False,indent=2)
            def save():
                with Path(path).open('x',encoding='utf-8') as f:f.write(content+'\n')
            self.workspace.run(save)
    def reject(self):
        if self._operation_active and self.workspace.worker:self.cancel_event.set();self.setButtonText(QWizard.WizardButton.CancelButton,'Отменяю…')
        elif not self.workspace.worker:super().reject()
    def closeEvent(self,event):
        if self.workspace.worker:
            if self._operation_active:self.cancel_event.set()
            event.ignore()
        else:event.accept()
