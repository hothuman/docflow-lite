"""Small validated input dialogs; persistence is handled by the parent worker."""
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLineEdit,QPlainTextEdit,QComboBox,QDialogButtonBox,QScrollArea,QWidget,QLabel

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
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();body_layout=QVBoxLayout(body);body_layout.setContentsMargins(0,0,0,0);form=QFormLayout();body_layout.addLayout(form);body_layout.addStretch(1);form.setFormAlignment(Qt.AlignmentFlag.AlignTop);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);scroll.setWidget(body);outer.addWidget(scroll)
        for key,label,kind in fields:
            if isinstance(kind,list):
                w=QComboBox()
                for value,name in kind:w.addItem(name,value)
                i=w.findData(values.get(key));w.setCurrentIndex(max(0,i))
            elif kind=='long':w=QPlainTextEdit(str(values.get(key,'')));w.setMinimumHeight(70);w.setMaximumHeight(115)
            elif kind=='date' or key in ('received_at','started_at','completed_at','issued_at','occurred_at'):w=DateField(values.get(key,''));label=label.replace('ГГГГ-ММ-ДД','ДД.ММ.ГГГГ')
            else:w=QLineEdit(str(values.get(key,'')))
            w.setAccessibleName(label);w.setMinimumWidth(0);form.addRow(label,w);self.fields[key]=w
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Save).setText('Сохранить');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Отмена');buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);outer.addWidget(buttons)
        for label in self.findChildren(QLabel):label.setTextFormat(Qt.TextFormat.PlainText)
    def values(self):
        return {k:(w.storage_text() if isinstance(w,DateField) else w.currentData() if isinstance(w,QComboBox) else w.toPlainText() if isinstance(w,QPlainTextEdit) else w.text()) for k,w in self.fields.items()}
