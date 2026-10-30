"""Short explicit intake, with an atomic domain operation and no guessed links."""
from uuid import uuid4
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QComboBox,QCheckBox,QLineEdit,QPlainTextEdit,QLabel,QScrollArea,QWidget
from .forms import fit_dialog
from .widgets import button
from ..flow import FlowLayout

class IntakeDialog(QDialog):
    def __init__(self,workspace,equipment=None):
        super().__init__(workspace);self.workspace=workspace;self.request_id=uuid4().hex;self.setWindowTitle('Новый ремонт');fit_dialog(self,680,620)
        out=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();form=QFormLayout(body);scroll.setWidget(body);out.addWidget(scroll,1)
        hint=QLabel('Выберите уже известный аппарат или явно добавьте новый. Повторный ремонт сохраняет всю прежнюю историю.');hint.setWordWrap(True);form.addRow(hint)
        self.new_equipment=QCheckBox('Новый аппарат');self.new_equipment.setChecked(not workspace.cache.get('active_equipment'));form.addRow(self.new_equipment)
        self.equipment=QComboBox();self.equipment.setAccessibleName('Существующий аппарат')
        for row in workspace.cache.get('active_equipment',[]):self.equipment.addItem(row['number']+' · '+row['model'],row['id'])
        form.addRow('Аппарат *',self.equipment)
        self.other_client=QCheckBox('Другой заказчик этого ремонта (владелец аппарата не меняется)');form.addRow(self.other_client)
        self.repair_client=QComboBox();self.repair_client.setAccessibleName('Заказчик обращения')
        for row in workspace.cache.get('active_clients',[]):self.repair_client.addItem(row['name']+(' · '+row['phone'] if row.get('phone') else ''),row['id'])
        form.addRow(self.repair_client)
        self.device_body=QWidget();df=QFormLayout(self.device_body);self.device_form=df;df.setContentsMargins(0,0,0,0)
        self.number=QLineEdit();self.number.setAccessibleName('Постоянный номер аппарата');df.addRow('Постоянный № аппарата *',self.number)
        self.model=QLineEdit();self.model.setAccessibleName('Модель аппарата');df.addRow('Модель *',self.model)
        self.new_client=QCheckBox('Новый клиент');self.new_client.setChecked(not workspace.cache.get('active_clients'));df.addRow(self.new_client)
        self.client=QComboBox();self.client.setAccessibleName('Существующий клиент')
        for row in workspace.cache.get('active_clients',[]):self.client.addItem(row['name']+(' · '+row['phone'] if row.get('phone') else ''),row['id'])
        df.addRow('Клиент *',self.client)
        self.name=QLineEdit();self.name.setAccessibleName('Имя нового клиента');df.addRow('Имя / организация *',self.name)
        self.phone=QLineEdit();self.phone.setAccessibleName('Телефон клиента');df.addRow('Телефон (необязательно)',self.phone)
        form.addRow(self.device_body)
        self.complaint=QPlainTextEdit();self.complaint.setMaximumHeight(100);self.complaint.setAccessibleName('Жалоба при приёмке');form.addRow('Жалоба',self.complaint)
        self.more=QCheckBox('Указать номер ремонта вручную');form.addRow(self.more)
        self.repair_number=QLineEdit();self.repair_number.setAccessibleName('Номер ремонта');self.repair_number.setPlaceholderText('Автоматически: '+workspace.cache.get('next_repair_number',''));form.addRow(self.repair_number)
        self.note=QLabel('');self.note.setWordWrap(True);out.addWidget(self.note)
        bar=FlowLayout();out.addLayout(bar);self.submit=button(bar,'Принять в ремонт',self.save,primary=True);self.submit.setDefault(True);button(bar,'Отмена',self.reject)
        self.new_equipment.toggled.connect(self.arrange);self.new_client.toggled.connect(self.arrange);self.more.toggled.connect(self.arrange)
        self.other_client.toggled.connect(self.arrange)
        if equipment:
            self.new_equipment.setChecked(False);self.equipment.setCurrentIndex(self.equipment.findData(equipment['id']))
        self.arrange()
    def arrange(self):
        new=self.new_equipment.isChecked();client=self.new_client.isChecked()
        self.equipment.setEnabled(not new);self.device_body.setVisible(new);self.client.setEnabled(not client)
        self.other_client.setVisible(not new);self.repair_client.setVisible(not new and self.other_client.isChecked())
        for widget in (self.name,self.phone):self.device_form.setRowVisible(widget,client)
        self.repair_number.setVisible(self.more.isChecked())
    def save(self):
        new=self.new_equipment.isChecked();nc=self.new_client.isChecked();store=self.workspace.store
        payload={'request_id':self.request_id,'complaint':self.complaint.toPlainText(),'number':self.repair_number.text() if self.more.isChecked() else ''}
        if new:
            payload['equipment']={'number':self.number.text(),'model':self.model.text()}
            if nc:payload['client']={'name':self.name.text(),'phone':self.phone.text()}
            else:payload['client_id']=self.client.currentData()
        else:
            payload['equipment_id']=self.equipment.currentData()
            if self.other_client.isChecked():payload['client_id']=self.repair_client.currentData()
        if (not new and not payload['equipment_id']) or (new and (not self.number.text().strip() or not self.model.text().strip() or (nc and not self.name.text().strip()))):
            self.note.setText('Заполните поля со звёздочкой: аппарат, модель и клиент.');return
        def saved(key):self.created_key=key;self.accept()
        self.workspace.run(lambda:store.intake(**payload),saved,'Сохраняю приёмку…',on_error=lambda error:self.note.setText('Приёмка не сохранена. Данные не добавлены. '+error))
    def reject(self):
        if self.workspace.worker:return
        filled=bool(self.complaint.toPlainText() or self.name.text() or self.number.text() or self.model.text())
        from .widgets import confirm
        if filled and not confirm(self,'Закрыть незавершённую приёмку? Введённые данные ещё не сохранены.'):return
        super().reject()

    def closeEvent(self,event):
        event.ignore();self.reject()
