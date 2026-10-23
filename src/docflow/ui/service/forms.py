"""Small validated input dialogs; persistence is handled by the parent worker."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLineEdit,QPlainTextEdit,QComboBox,QDialogButtonBox,QScrollArea,QWidget,QLabel

class FieldsDialog(QDialog):
    def __init__(self,title,fields,values=None,parent=None):
        super().__init__(parent);self.setWindowTitle(title);self.resize(580,520);self.fields={};values=values or {}
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();form=QFormLayout(body);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);scroll.setWidget(body);outer.addWidget(scroll)
        for key,label,kind in fields:
            if isinstance(kind,list):
                w=QComboBox()
                for value,name in kind:w.addItem(name,value)
                i=w.findData(values.get(key));w.setCurrentIndex(max(0,i))
            elif kind=='long':w=QPlainTextEdit(str(values.get(key,'')));w.setMinimumHeight(90)
            else:w=QLineEdit(str(values.get(key,'')))
            w.setAccessibleName(label);w.setMinimumWidth(0);form.addRow(label,w);self.fields[key]=w
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);outer.addWidget(buttons)
    def values(self):
        return {k:(w.currentData() if isinstance(w,QComboBox) else w.toPlainText() if isinstance(w,QPlainTextEdit) else w.text()) for k,w in self.fields.items()}
