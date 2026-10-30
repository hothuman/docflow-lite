"""Optional predefined actions in user INI. No executable configuration."""
import json
from ..settings import preferences

DEFAULT=['new','search','continue','documents']
LABELS={'new':'Новый ремонт','search':'Найти оборудование / ремонт','continue':'Продолжить работу','documents':'Документы','catalog':'Каталог','backup':'Резервная копия'}
PRESETS={'По умолчанию':DEFAULT,'Простой':['new','search','documents'],'Сервисный':['new','continue','search','documents'],'Расширенный':[*DEFAULT,'catalog','backup']}

def validate(value):
    return isinstance(value,list) and 2<=len(value)<=len(LABELS) and all(isinstance(x,str) and x in LABELS for x in value) and len(set(value))==len(value) and all(x in value for x in ('new','documents'))

def load_actions():
    settings=preferences();raw=settings.value('dashboard/actions')
    if raw is None:return DEFAULT[:],''
    try:value=json.loads(raw) if isinstance(raw,str) else raw
    except (ValueError,TypeError):value=None
    if not validate(value):return DEFAULT[:],'Настройка повреждена. Используется безопасный стандартный экран; можно выполнить сброс.'
    return value[:],''

def save_actions(value):
    if not validate(value):raise ValueError('Новый ремонт и Документы должны оставаться; выбирайте только штатные действия')
    settings=preferences();settings.setValue('dashboard/actions',json.dumps(value));settings.sync()
    return settings.status()==settings.Status.NoError

def reset_actions():return save_actions(DEFAULT)

def show_editor(workspace):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QComboBox,QListWidget,QListWidgetItem,QMessageBox
    from .forms import fit_dialog
    from .widgets import button
    from ..flow import FlowLayout
    dialog=QDialog(workspace);dialog.setWindowTitle('Настроить стартовые действия');fit_dialog(dialog,620,560);layout=QVBoxLayout(dialog)
    text=QLabel('Необязательная настройка для этого пользователя на компьютере. Проекты и суммы не меняются. Новый ремонт и Документы остаются; Настройки всегда в боковом меню.');text.setWordWrap(True);layout.addWidget(text)
    order,warning=load_actions();note=QLabel(warning);note.setWordWrap(True);layout.addWidget(note)
    preset=QComboBox();preset.addItem('Выбрать набор…');preset.addItems(PRESETS);layout.addWidget(preset);items=QListWidget();items.setAccessibleName('Порядок и видимость действий');layout.addWidget(items)
    def install(keys):
        items.clear()
        for key in keys+[k for k in LABELS if k not in keys]:
            item=QListWidgetItem(LABELS[key]);item.setData(Qt.ItemDataRole.UserRole,key);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if key in keys else Qt.CheckState.Unchecked)
            if key in ('new','documents'):item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsUserCheckable)
            items.addItem(item)
    def move(delta):
        index=items.currentRow();target=index+delta
        if index>=0 and 0<=target<items.count():item=items.takeItem(index);items.insertItem(target,item);items.setCurrentRow(target)
    def apply():
        keys=[items.item(i).data(Qt.ItemDataRole.UserRole) for i in range(items.count()) if items.item(i).checkState()==Qt.CheckState.Checked]
        if save_actions(keys):workspace.dashboard.apply_actions();dialog.accept()
        else:note.setText('Не удалось сохранить настройки. Проверьте доступ к папке конфигурации.')
    def reset():
        if reset_actions():install(DEFAULT[:]);workspace.dashboard.apply_actions();note.setText('Стандартный вид восстановлен.')
        else:note.setText('Не удалось сохранить сброс; проверьте доступ.')
    preset.currentTextChanged.connect(lambda name:install(PRESETS[name][:]) if name in PRESETS else None)
    bar=FlowLayout();layout.addLayout(bar);button(bar,'Выше',lambda:move(-1));button(bar,'Ниже',lambda:move(1));button(bar,'Вернуть по умолчанию',reset)
    bar=FlowLayout();layout.addLayout(bar);button(bar,'Сохранить',apply,primary=True);button(bar,'Отмена',dialog.reject);install(order);dialog.exec()
