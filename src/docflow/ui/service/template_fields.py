"""Configure scalar Word variables through labelled fields, never JSON editing."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QScrollArea,QWidget,QFormLayout,QComboBox,QCheckBox
from ...service.document_fields import FIELDS,propose_fields
from ...service.documents import ITEM_FIELDS,HISTORY_FIELDS
from ...templates import Template
from ..flow import FlowLayout
from .forms import fit_dialog
from .widgets import button


class TemplateFieldsDialog(QDialog):
    def __init__(self,variables,profile,kind,parent=None):
        super().__init__(parent);self.setWindowTitle('Поля Word-шаблона');fit_dialog(self,820,620)
        outer=QVBoxLayout(self);label=QLabel('Укажите, откуда брать каждое общее поле документа. Необязательное поле можно явно оставить пустым. Работы и детали используют готовые повторяющиеся строки шаблона.');label.setWordWrap(True);outer.addWidget(label)
        scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();form=QFormLayout(body);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);scroll.setWidget(body);outer.addWidget(scroll,1)
        self.mapping_widgets={};self.required_widgets={};scalar=sorted(set(variables)-ITEM_FIELDS-HISTORY_FIELDS)
        proposals=propose_fields(scalar);saved=profile.get('template_field_mapping',{}).get(kind,{});required=profile.get('template_required_fields',{}).get(kind,[])
        for variable in scalar:
            combo=QComboBox();combo.setAccessibleName('Источник поля '+variable);combo.setMinimumContentsLength(12);combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.addItem('Выберите поле программы',None);combo.addItem('Оставить пустым (необязательное поле)','')
            for key,label in FIELDS.items():combo.addItem(label,key)
            chosen=variable if variable in FIELDS else saved.get(variable,proposals.get(variable))
            combo.setCurrentIndex(max(0,combo.findData(chosen)))
            if variable in FIELDS:combo.setEnabled(False);combo.setToolTip('Стандартное поле программы сохраняет своё значение')
            form.addRow('{{'+variable+'}}',combo);self.mapping_widgets[variable]=combo
            check=QCheckBox('Обязательно заполнить');check.setAccessibleName('Обязательное поле '+variable);check.setChecked(variable in required);form.addRow('',check);self.required_widgets[variable]=check
        self.error=QLabel();self.error.setWordWrap(True);self.error.setTextFormat(Qt.TextFormat.PlainText);outer.addWidget(self.error)
        actions=FlowLayout();outer.addLayout(actions);button(actions,'Сохранить поля',self.accept,primary=True);button(actions,'Отмена',self.reject)
    def values(self):
        return ({key:w.currentData() for key,w in self.mapping_widgets.items() if w.currentData() is not None},[key for key,w in self.required_widgets.items() if w.isChecked()])
    def accept(self):
        missing=[key for key,w in self.mapping_widgets.items() if w.currentData() is None]
        if missing:self.error.setText('Выберите источник или «Оставить пустым»: '+', '.join(missing));return
        super().accept()


def configure_template(workspace,parent,path,kind,profile,callback):
    """Validate bytes on the existing worker, then ask only about field choices."""
    def loaded(template):
        dialog=TemplateFieldsDialog(template.fields,profile,kind,parent)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        aliases,required=dialog.values()
        updated={**profile,'template_field_mapping':{**profile.get('template_field_mapping',{}),kind:aliases},
                 'template_required_fields':{**profile.get('template_required_fields',{}),kind:required}}
        callback(updated)
    return workspace.run(lambda:Template.load(path),loaded,'Проверяю Word-шаблон перед настройкой полей…')
