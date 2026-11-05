"""Small optional wizard, always creating an explicit profile copy."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWizard,QWizardPage,QVBoxLayout,QFormLayout,QLabel,QLineEdit,QPlainTextEdit,QCheckBox,QComboBox,QFileDialog,QScrollArea,QWidget)
from ...service.profiles import save_profile,NEUTRAL
from ...service.documents import KINDS
from .forms import fit_dialog
from .widgets import button

class IdentityPage(QWizardPage):
    def isComplete(self):
        return all(field.text().strip() for field in self.required_fields)

class OrganizationWizard(QWizard):
    def __init__(self,workspace,editor=None):
        super().__init__(editor or workspace);self.workspace=workspace;self.editor=editor;self.setWindowTitle('Организация для документов');fit_dialog(self,760,650);self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setButtonText(QWizard.WizardButton.NextButton,'Далее');self.setButtonText(QWizard.WizardButton.BackButton,'Назад');self.setButtonText(QWizard.WizardButton.CancelButton,'Отмена');self.setButtonText(QWizard.WizardButton.FinishButton,'Сохранить организацию')
        self.source=dict(editor.snapshot['profile'] if editor else NEUTRAL);self.saved_profile_id=None
        page=IdentityPage();page.setTitle('1. Кто выполняет ремонт?');layout=QVBoxLayout(page);note=QLabel('Заполните только реальные данные. Создаётся отдельный профиль; старые документы и версии смет сохранят свои сведения.');note.setWordWrap(True);layout.addWidget(note);form=QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);layout.addLayout(form)
        self.profile_name=QLineEdit('Профиль документов');self.organization=QLineEdit(self.source['organization_name']);self.organization.setAccessibleName('Название исполнителя');self.contact=QLineEdit(self.source['contact']);self.details=QPlainTextEdit(self.source['details']);self.details.setMaximumHeight(180)
        for label,w in [('Название настройки *',self.profile_name),('Исполнитель *',self.organization),('Контакты',self.contact),('Реквизиты',self.details)]:form.addRow(label,w)
        # QWizard's mandatory-field baseline treats an unchanged nonempty default
        # as incomplete. Validate actual trimmed values, including existing data.
        page.required_fields=(self.profile_name,self.organization)
        for field in page.required_fields:field.textChanged.connect(page.completeChanged)
        self.addPage(page)
        page=QWizardPage();page.setTitle('2. Оформление (необязательно)');layout=QVBoxLayout(page);note=QLabel('Можно сохранить встроенную нейтральную форму. Фирменный DOCX и логотип выбирайте только при наличии права использования.');note.setWordWrap(True);layout.addWidget(note)
        self.logo=QLineEdit();self.logo.setReadOnly(True);layout.addWidget(self.logo);button(layout,'Выбрать логотип PNG / JPEG',self.choose_logo);button(layout,'Убрать логотип',self.logo.clear);self.logo_rights=QCheckBox('Подтверждаю право использования логотипа');layout.addWidget(self.logo_rights)
        self.kind=QComboBox()
        for key,label in KINDS.items():self.kind.addItem(label,key)
        layout.addWidget(self.kind);self.template=QLineEdit();self.template.setReadOnly(True);layout.addWidget(self.template);button(layout,'Выбрать фирменный DOCX',self.choose_template);button(layout,'Убрать выбранный шаблон',self.template.clear);self.kind.currentIndexChanged.connect(self.template.clear);self.addPage(page)
        page=QWizardPage();page.setTitle('3. Где использовать профиль?');layout=QVBoxLayout(page);self.apply_repair=QCheckBox('Для новых документов этого ремонта');self.apply_repair.setChecked(bool(editor));self.apply_repair.setVisible(bool(editor));layout.addWidget(self.apply_repair);self.activate=QCheckBox('Для новых ремонтов мастерской');self.activate.setChecked(True);layout.addWidget(self.activate);note=QLabel('Существующие версии смет и уже выданные DOCX не меняются. Для сметы с новыми реквизитами сохраните новую версию. Исходный профиль остаётся доступен.');note.setWordWrap(True);layout.addWidget(note);self.result_note=QLabel();self.result_note.setWordWrap(True);layout.addWidget(self.result_note);self.addPage(page)
        for label in self.findChildren(QLabel):label.setTextFormat(Qt.TextFormat.PlainText)
        for index in self.pageIds():
            page=self.page(index);body=QWidget();body.setLayout(page.layout());scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body);QVBoxLayout(page).addWidget(scroll)
    def choose_logo(self):
        path,_=QFileDialog.getOpenFileName(self,'Ваш логотип','','PNG / JPEG (*.png *.jpg *.jpeg)')
        if path:self.logo.setText(path)
    def choose_template(self):
        path,_=QFileDialog.getOpenFileName(self,'Фирменный шаблон','','Word (*.docx)')
        if path:self.template.setText(path)
    def accept(self):
        if self.workspace.worker:return
        if not self.organization.text().strip() or not self.profile_name.text().strip():self.result_note.setText('Укажите реальное название исполнителя и название настройки.');return
        if self.logo.text() and not self.logo_rights.isChecked():self.result_note.setText('Подтвердите право использования логотипа на предыдущем шаге или уберите файл.');return
        values={**self.source,'name':self.profile_name.text(),'organization_name':self.organization.text(),'contact':self.contact.text(),'details':self.details.toPlainText()};assets={}
        if self.logo.text():assets['logo']=self.logo.text()
        if self.template.text():assets['templates']={self.kind.currentData():self.template.text()}
        editor=self.editor;repair_id=editor.key if editor and self.apply_repair.isChecked() else None;revision=editor.revision if repair_id else None;activate=self.activate.isChecked();rights=self.logo_rights.isChecked()
        def work():
            key=save_profile(self.workspace.store,values,assets=assets,logo_rights_confirmed=rights,activate=activate,repair_id=repair_id,expected_revision=revision)
            return key,self.workspace.store.snapshot(editor.key) if editor else None
        def saved(result):
            self.saved_profile_id=result[0]
            if editor:editor.install(result[1])
            super(OrganizationWizard,self).accept()
        self.workspace.run(work,saved,'Сохраняю организацию и проверенные файлы…',on_error=lambda error:self.result_note.setText(error))
    def reject(self):
        if not self.workspace.worker:super().reject()
    def closeEvent(self,event):
        if self.workspace.worker:event.ignore()
        else:event.accept()
