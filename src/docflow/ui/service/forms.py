"""Small validated input dialogs; persistence is handled by the parent worker."""
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLineEdit,QPlainTextEdit,QComboBox,QDialogButtonBox,QScrollArea,QWidget,QLabel,QSizePolicy

def fit_dialog(dialog,width,height):
    dialog.setMinimumSize(420,300)
    available=dialog.screen().availableGeometry()
    dialog.resize(min(width,max(420,available.width()-40)),min(height,max(300,available.height()-60)))

class DateField(QLineEdit):
    def __init__(self,value='',parent=None):super().__init__(parent);self.setPlaceholderText('ДД.ММ.ГГГГ');self.set_date(value)
    def set_date(self,value):
        try:value=datetime.fromisoformat(str(value)).strftime('%d.%m.%Y') if value else ''
        except ValueError:pass
        self.setText(str(value))
    def storage_text(self):
        value=self.text().strip()
        try:return datetime.strptime(value,'%d.%m.%Y').date().isoformat()
        except ValueError:return value

class FieldsDialog(QDialog):
    def __init__(self,title,fields,values=None,parent=None):
        super().__init__(parent);self.setWindowTitle(title);fit_dialog(self,580,520);self.fields={};values=values or {}
        self._persistence=None;self._saving=False;self.check_values=None;self.errors={};self._labels={};self._required=set()
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();body_layout=QVBoxLayout(body);body_layout.setContentsMargins(0,0,0,0);form=QFormLayout();body_layout.addLayout(form);body_layout.addStretch(1);form.setFormAlignment(Qt.AlignmentFlag.AlignTop);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);scroll.setWidget(body);outer.addWidget(scroll)
        for key,label,kind in fields:
            if isinstance(kind,list):
                w=QComboBox()
                for value,name in kind:w.addItem(name,value)
                i=w.findData(values.get(key));w.setCurrentIndex(max(0,i))
            elif kind=='long':w=QPlainTextEdit(str(values.get(key,'')));w.setMinimumHeight(70);w.setMaximumHeight(115)
            elif kind=='date' or key in ('received_at','started_at','completed_at','issued_at','occurred_at'):w=DateField(values.get(key,''));label=label.replace('ГГГГ-ММ-ДД','ДД.ММ.ГГГГ')
            else:w=QLineEdit(str(values.get(key,'')))
            w.setAccessibleName(label);w.setMinimumWidth(0);self.fields[key]=w;self._labels[key]=label
            if '*' in label:self._required.add(key)
            holder=QWidget();stack=QVBoxLayout(holder);stack.setContentsMargins(0,0,0,0);stack.addWidget(w)
            error=QLabel();error.setObjectName('fieldError');error.setWordWrap(True);error.setTextFormat(Qt.TextFormat.PlainText);error.setAccessibleName('Ошибка: '+label);error.hide();stack.addWidget(error);self.errors[key]=error;form.addRow(label,holder)
        self.error=QLabel();self.error.setObjectName('formError');self.error.setWordWrap(True);self.error.setTextFormat(Qt.TextFormat.PlainText);self.error.setAccessibleName('Ошибка сохранения');self.error.hide();outer.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);self.save_button=buttons.button(QDialogButtonBox.StandardButton.Save);self.save_button.setText('Сохранить');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Отмена');buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);outer.addWidget(buttons)
        for label in self.findChildren(QLabel):label.setTextFormat(Qt.TextFormat.PlainText)
        self._initial_values=self.values()
        self.form_scroll=scroll

    def compact_workspace_layout(self):
        self.setMaximumWidth(820)
        self.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.form_scroll.setSizeAdjustPolicy(QScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.form_scroll.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
    @property
    def dirty(self):
        return self.values()!=self._initial_values
    def values(self):
        return {k:(w.storage_text() if isinstance(w,DateField) else w.currentData() if isinstance(w,QComboBox) else w.toPlainText() if isinstance(w,QPlainTextEdit) else w.text()) for k,w in self.fields.items()}
    def persist_with(self,workspace,save):
        """Keep this exact form alive until the asynchronous transaction succeeds."""
        self._persistence=(workspace,save)
    def _field_error(self,key,visible):
        field=self.fields[key]
        field.setProperty('validationIssue',visible)
        field.style().unpolish(field);field.style().polish(field)
        self.errors[key].setVisible(visible)
    def show_error(self,message,field_key=None):
        self.error.setText('Ошибка · '+message);self.error.show()
        for key,label in self._labels.items():
            names=(label.replace('*','').strip(),{'name':'Название','number':'Постоянный номер','model':'Модель','amount':'Сумма','price':'Цена','occurred_at':'Дата'}.get(key,''))
            if key==field_key or (field_key is None and any(name and message.casefold().startswith(name.casefold()) for name in names)):
                self.errors[key].setText(message);self._field_error(key,True);self.fields[key].setFocus();break
    def accept(self):
        self.error.hide()
        for key in self.errors:self._field_error(key,False)
        if self.check_values and not self.check_values(self.values()):return
        if self._persistence is None:return super().accept()
        workspace,save=self._persistence
        if self._saving or workspace.worker:return
        values=self.values()
        for key in self._required:
            if values[key] is None or not str(values[key]).strip():self.show_error(self._labels[key].replace('*','').strip()+': заполните значение');return
        self._saving=True
        buttons=self.findChild(QDialogButtonBox);buttons.setEnabled(False)
        def failed(error):
            self._saving=False;buttons.setEnabled(True);self.show_error(error)
        def saved(_):
            self._saving=False;buttons.setEnabled(True);super(FieldsDialog,self).accept()
        if not workspace.run(lambda:save(values),saved,'Сохраняю…',on_error=failed,inline_error=not self.isWindow()):failed('Дождитесь завершения текущей операции и повторите сохранение.')
    def reject(self):
        if self._saving:return
        if not self.isWindow() and self.dirty:
            from .widgets import confirm
            if not confirm(self,'Введённые данные ещё не сохранены. Уйти из формы?',
                           'Уйти без сохранения',cancel='Остаться'):return
        super().reject()
    def closeEvent(self,event):
        if self._saving:event.ignore()
        else:super().closeEvent(event)
