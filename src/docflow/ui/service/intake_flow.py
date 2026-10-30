"""Mutually exclusive intake choices with one atomic domain operation."""
from uuid import uuid4
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QComboBox,QCheckBox,QRadioButton,QButtonGroup,QLineEdit,QPlainTextEdit,QLabel,QScrollArea,QWidget)
from .forms import fit_dialog
from .widgets import button
from ..flow import FlowLayout

class IntakeDialog(QDialog):
    @property
    def dirty(self):return bool(self.complaint.toPlainText() or self.name.text() or self.number.text() or self.model.text() or self.phone.text() or self.other_client.isChecked())
    def __init__(self,workspace,equipment=None):
        super().__init__(workspace);self.workspace=workspace;self.request_id=uuid4().hex;self.setWindowTitle('Принять оборудование в ремонт');fit_dialog(self,720,680)
        out=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();form=QFormLayout(body);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);scroll.setWidget(body);out.addWidget(scroll,1)
        hint=QLabel('Аппарат уже бывал в мастерской? Найдите его в списке — новое обращение сохранится в его истории.');hint.setWordWrap(True);form.addRow(hint)
        self.equipment_choice=QWidget();choice=FlowLayout(self.equipment_choice);self.equipment_group=QButtonGroup(self)
        self.existing_equipment=QRadioButton('Из списка');self.new_equipment=QRadioButton('Новый аппарат')
        for b in (self.existing_equipment,self.new_equipment):self.equipment_group.addButton(b);choice.addWidget(b)
        form.addRow('Какой аппарат?',self.equipment_choice);has_equipment=bool(workspace.cache.get('active_equipment'));self.existing_equipment.setEnabled(has_equipment);(self.existing_equipment if has_equipment else self.new_equipment).setChecked(True)
        self.equipment=self.selector(workspace.cache.get('active_equipment',[]),lambda r:r['number']+' · '+r['model'],'Найти существующий аппарат');form.addRow('Аппарат *',self.equipment)
        self.equipment_info=QLabel();self.equipment_info.setWordWrap(True);form.addRow(self.equipment_info)
        self.other_client=QCheckBox('У этого ремонта другой заказчик');self.other_client.setToolTip('Выберите существующего клиента этого обращения. Собственник аппарата не меняется.');form.addRow(self.other_client)
        self.repair_client=self.selector(workspace.cache.get('active_clients',[]),lambda r:r['name'],'Заказчик этого обращения');form.addRow('Заказчик ремонта *',self.repair_client)
        self.device_body=QWidget();df=QFormLayout(self.device_body);self.device_form=df;df.setContentsMargins(0,0,0,0);df.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);df.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.number=QLineEdit();self.number.setAccessibleName('Постоянный номер аппарата');self.number.setPlaceholderText('Номер, нанесённый на сам аппарат');df.addRow('Постоянный № аппарата *',self.number)
        self.model=QLineEdit();self.model.setAccessibleName('Модель аппарата');df.addRow('Модель *',self.model)
        self.client_choice=QWidget();cc=FlowLayout(self.client_choice);self.client_group=QButtonGroup(self);self.existing_client=QRadioButton('Из списка');self.new_client=QRadioButton('Новый клиент')
        for b in (self.existing_client,self.new_client):self.client_group.addButton(b);cc.addWidget(b)
        has_clients=bool(workspace.cache.get('active_clients'));self.existing_client.setEnabled(has_clients);(self.existing_client if has_clients else self.new_client).setChecked(True);df.addRow('Кому принадлежит аппарат?',self.client_choice)
        self.client=self.selector(workspace.cache.get('active_clients',[]),lambda r:r['name'],'Существующий собственник');df.addRow('Клиент *',self.client)
        self.name=QLineEdit();self.name.setAccessibleName('Имя нового клиента');df.addRow('Имя / организация *',self.name);self.phone=QLineEdit();self.phone.setAccessibleName('Телефон клиента');df.addRow('Телефон (необязательно)',self.phone);form.addRow(self.device_body)
        self.complaint=QPlainTextEdit();self.complaint.setMaximumHeight(100);self.complaint.setAccessibleName('Что сломалось');form.addRow('Что сломалось?',self.complaint)
        self.more=QCheckBox('Дополнительно: свой номер ремонта');form.addRow(self.more);self.repair_number=QLineEdit();self.repair_number.setAccessibleName('Номер ремонта');self.repair_number.setPlaceholderText('Автоматически: '+workspace.cache.get('next_repair_number',''));form.addRow('№ ремонта',self.repair_number)
        self.confirmation=QLabel();self.confirmation.setObjectName('intakeSummary');self.confirmation.setWordWrap(True);self.confirmation.setAccessibleName('Что будет создано');form.addRow('Проверьте перед приёмкой',self.confirmation)
        self.note=QLabel();self.note.setWordWrap(True);out.addWidget(self.note);bar=FlowLayout();out.addLayout(bar);self.submit=button(bar,'Принять в ремонт',self.save,primary=True);self.submit.setDefault(True);button(bar,'Отмена',self.reject)
        for b in (self.existing_equipment,self.new_equipment,self.existing_client,self.new_client,self.more,self.other_client):b.toggled.connect(self.arrange)
        for field in (self.name,self.model,self.number,self.repair_number):field.textChanged.connect(self.summarize)
        for combo in (self.equipment,self.client,self.repair_client):combo.currentTextChanged.connect(self.summarize)
        if equipment:self.existing_equipment.setChecked(True);self.equipment.setCurrentIndex(self.equipment.findData(equipment['id']))
        for label in self.findChildren(QLabel):label.setTextFormat(Qt.TextFormat.PlainText)
        self.form=form;self.arrange()
    @staticmethod
    def selector(rows,label,name):
        combo=QComboBox();combo.setEditable(True);combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert);combo.setMinimumWidth(0);combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);combo.setMinimumContentsLength(12);combo.setAccessibleName(name)
        for r in rows:combo.addItem(label(r),r['id'])
        combo.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive);return combo
    @staticmethod
    def selected(combo):return combo.currentData() if combo.currentIndex()>=0 and combo.currentText()==combo.itemText(combo.currentIndex()) else None
    def arrange(self,*args):
        if not hasattr(self,'form'):return
        new=self.new_equipment.isChecked();client=self.new_client.isChecked();self.form.setRowVisible(self.equipment,not new);self.form.setRowVisible(self.equipment_info,not new);self.device_body.setVisible(new)
        self.form.setRowVisible(self.other_client,not new);self.form.setRowVisible(self.repair_client,not new and self.other_client.isChecked());self.device_form.setRowVisible(self.client,not client)
        for field in (self.name,self.phone):self.device_form.setRowVisible(field,client)
        self.form.setRowVisible(self.repair_number,self.more.isChecked());self.summarize()
    def summarize(self,*args):
        if not hasattr(self,'confirmation'):return
        new=self.new_equipment.isChecked();eq=next((r for r in self.workspace.cache.get('active_equipment',[]) if r['id']==self.selected(self.equipment)),None)
        if new:
            owner=self.name.text().strip() if self.new_client.isChecked() else self.client.currentText();device=(self.number.text().strip() or 'номер не указан')+' · '+(self.model.text().strip() or 'модель не указана');what='Новый аппарат'+(' и новый клиент' if self.new_client.isChecked() else '')
        else:owner=eq.get('owner','') if eq else 'выберите аппарат';device=self.equipment.currentText();what='Новое обращение существующего аппарата — история сохраняется'
        requester=self.repair_client.currentText() if not new and self.other_client.isChecked() else owner
        history=[r for r in self.workspace.cache.get('finance',[]) if eq and r['equipment_id']==eq['id']]
        self.equipment_info.setText(('Постоянный № '+eq['number']+' · '+eq['model']+'\nСобственник: '+owner+f' · Обращений в истории: {len(history)}') if eq else 'Выберите аппарат из списка. Поиск не создаёт новую запись.')
        number=self.repair_number.text().strip() if self.more.isChecked() else self.workspace.cache.get('next_repair_number','автоматически');self.confirmation.setText(f'{what}.\nРемонт №{number or "укажите номер"}. Аппарат: {device}.\nСобственник: {owner or "не указан"}. Заказчик ремонта: {requester or "не указан"}.')
    def save(self):
        new=self.new_equipment.isChecked();nc=self.new_client.isChecked();store=self.workspace.store;payload={'request_id':self.request_id,'complaint':self.complaint.toPlainText(),'number':self.repair_number.text() if self.more.isChecked() else ''}
        if new:
            payload['equipment']={'number':self.number.text(),'model':self.model.text()}
            if nc:payload['client']={'name':self.name.text(),'phone':self.phone.text()}
            else:payload['client_id']=self.selected(self.client)
        else:
            payload['equipment_id']=self.selected(self.equipment)
            if self.other_client.isChecked():payload['client_id']=self.selected(self.repair_client)
        invalid=(not new and (not payload['equipment_id'] or self.other_client.isChecked() and not payload.get('client_id'))) or (new and (not self.number.text().strip() or not self.model.text().strip() or (nc and not self.name.text().strip()) or (not nc and not payload.get('client_id'))))
        if invalid:self.note.setText('Заполните обязательные поля и выберите существующие записи именно из списка.');return
        def saved(key):self.created_key=key;self.accept()
        self.workspace.run(lambda:store.intake(**payload),saved,'Сохраняю приёмку…',on_error=lambda error:self.note.setText('Приёмка не сохранена. '+error))
    def reject(self):
        if self.workspace.worker:return
        filled=bool(self.complaint.toPlainText() or self.name.text() or self.number.text() or self.model.text())
        from .widgets import confirm
        if filled and not confirm(self,'Закрыть незавершённую приёмку? Введённые данные ещё не сохранены.'):return
        super().reject()
    def closeEvent(self,event):event.ignore();self.reject()
