"""Local organization profile management; selected files stay in the local project."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QFileDialog,QCheckBox,QComboBox
from ...service.profiles import profiles,save_profile,activate_profile,NEUTRAL,profile
from ...service.documents import KINDS
from ...service.statuses import STATUSES
from .forms import FieldsDialog
from ..flow import FlowLayout
from .forms import fit_dialog
from .widgets import Grid,button

class ProfileDialog(QDialog):
    def __init__(self,workspace):
        super().__init__(workspace);self.workspace=workspace;self.setWindowTitle('Локальные профили организаций');fit_dialog(self,900,600)
        layout=QVBoxLayout(self);label=QLabel('Активный профиль применяется к новым ремонтам. Старые ремонты сохраняют связь со своим профилем, сохранённые сметы — снимок реквизитов. Пустые реквизиты не заполняются автоматически.');label.setWordWrap(True);layout.addWidget(label)
        self.empty=QLabel('Организация ещё не настроена. Встроенные документы будут явно обозначены как нейтральные. Начните с «Настроить организацию».');self.empty.setWordWrap(True);layout.addWidget(self.empty)
        self.grid=Grid([('name','Профиль'),('active_label','Состояние'),('organization_name','Исполнитель'),('number_prefix','Префикс'),('contact','Контакт'),('logo_path','Логотип')]);layout.addWidget(self.grid)
        bar=FlowLayout();layout.addLayout(bar)
        button(bar,'Настроить организацию',self.setup,primary=True)
        self.selection_tools=[]
        for title,fn in [('Дополнительные поля',lambda:self.edit(True)),('Сделать активным',self.activate),('Выбрать шаблон',self.template),('Логотип',self.logo)]:self.selection_tools.append(button(bar,title,fn))
        button(bar,'Нейтральный профиль',lambda:self.activate(True));self.grid.selectionModel().currentRowChanged.connect(self.update_tools)
        button(layout,'Закрыть',self.accept);self.refresh()
    def refresh(self):
        store=self.workspace.store
        def query():
            with store.db.connection() as c:active=profile(c,active=True)['id']
            return [{**p,'active_label':'Активный' if p['id']==active else 'Сохранённый'} for p in profiles(store)]
        def installed(rows):self.grid.install(rows);self.empty.setVisible(not rows);self.grid.setVisible(bool(rows));self.update_tools()
        self.workspace.run(query,installed)
    def update_tools(self,*args):
        for control in self.selection_tools:control.setEnabled(self.grid.selected() is not None)
    def setup(self):
        from .organization_setup import OrganizationWizard
        self.workspace.modal(OrganizationWizard(self.workspace));self.refresh()
    def edit(self,existing=False):
        row=self.grid.selected() if existing else None
        if existing and not row:return
        fields=[('name','Название профиля *','text'),('organization_name','Наименование исполнителя','text'),('contact','Контакты','text'),('details','Реквизиты (только проверенные)','long'),('number_prefix','Префикс номера','text'),('number_start','Начальный номер','text'),('default_discount','Начальная скидка, ₽','text'),('warranty_terms','Утверждённые условия гарантии (можно оставить пустым)','long')]
        fields += [('status_'+k,'Название статуса «'+v[0]+'»','text') for k,v in STATUSES.items()]
        data=dict(row or NEUTRAL);data.update({'status_'+k:data.get('status_labels',{}).get(k,v[0]) for k,v in STATUSES.items()})
        d=FieldsDialog('Профиль организации',fields,data,self)
        if d.exec()==QDialog.DialogCode.Accepted:
            values=d.values();values['status_labels']={k:values.pop('status_'+k) for k in STATUSES};values={**data,**values};s=self.workspace.store
            self.workspace.run(lambda:save_profile(s,values,row['id'] if row else None),lambda _:self.refresh())
    def activate(self,neutral=False):
        row=self.grid.selected()
        if neutral or row:self.workspace.run(lambda:activate_profile(self.workspace.store,None if neutral else row['id']),lambda _:self.refresh())
    def template(self):
        row=self.grid.selected()
        if not row:return
        d=FieldsDialog('Назначение шаблона',[('kind','Вид документа',list(KINDS.items()))],parent=self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        kind=d.values()['kind'];path,_=QFileDialog.getOpenFileName(self,'Проверяемый шаблон','','Word (*.docx)')
        if path:self.workspace.run(lambda:save_profile(self.workspace.store,row,row['id'],assets={'templates':{kind:path}}),lambda _:self.refresh())
    def logo(self):
        row=self.grid.selected()
        if not row:return
        path,_=QFileDialog.getOpenFileName(self,'Логотип PNG / JPEG','','Изображения (*.png *.jpg *.jpeg)')
        if not path:return
        d=QDialog(self);d.setWindowTitle('Право использования логотипа');layout=QVBoxLayout(d);check=QCheckBox('Подтверждаю право использовать выбранный логотип в документах');layout.addWidget(check);ok=button(layout,'Сохранить',d.accept);ok.setEnabled(False);check.toggled.connect(ok.setEnabled);button(layout,'Отмена',d.reject)
        if d.exec()==QDialog.DialogCode.Accepted:
            confirmed=check.isChecked();store=self.workspace.store
            self.workspace.run(lambda:save_profile(store,row,row['id'],assets={'logo':path},logo_rights_confirmed=confirmed),lambda _:self.refresh())
    def closeEvent(self,event):
        if self.workspace.worker:event.ignore()
        else:event.accept()
