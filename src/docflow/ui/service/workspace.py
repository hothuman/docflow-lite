"""Asynchronous local workspace. Every DB/media/DOCX/backup operation runs off Qt's UI thread."""
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from PySide6.QtCore import QThread,Qt,QSortFilterProxyModel,QTimer,QUrl,QLockFile,Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QTabWidget,QTableView,QHeaderView,QLineEdit,QComboBox,QCheckBox,QFileDialog,QInputDialog,QMessageBox,QDialog,QPlainTextEdit,QFormLayout,QScrollArea,QToolBar)
from ...service.repository import ServiceStore,default_root
from ...service.validation import ServiceError,rub
from ...service.statuses import STATUSES,APPROVALS
from ...service.documents import generate_document,KINDS
from ...service.attachments import add_attachment,attachment_path,remove_attachment
from ...service.backup import create_backup,restore_backup
from ...service.demo import seed_demo
from .widgets import Grid,button,confirm
from .forms import FieldsDialog

class Job(QThread):
    def __init__(self,function,parent):super().__init__(parent);self.function=function;self.value=None;self.error=''
    def run(self):
        try:self.value=self.function()
        except Exception as exc:self.error=str(exc) or 'Не удалось выполнить операцию'
        finally:self.function=None

class ServiceWorkspace(QWidget):
    def __init__(self,parent=None,root=None):
        super().__init__(parent);self.store=None;self.worker=None;self.project_lock=None;self.cache={};self._pending_refresh=False;self.dialogs=[]
        out=QVBoxLayout(self);out.setContentsMargins(0,0,0,0)
        self.location=QLabel('Service · один локальный пользователь · подготовительная версия');self.location.setWordWrap(True);out.addWidget(self.location)
        self.tabs=QTabWidget();self.tabs.setUsesScrollButtons(True);out.addWidget(self.tabs,1)
        dash=QWidget();dl=QVBoxLayout(dash);self.metrics=QLabel('Открываю локальный проект…');self.metrics.setWordWrap(True);self.metrics.setObjectName('title');dl.addWidget(self.metrics);self.recent=QPlainTextEdit();self.recent.setReadOnly(True);dl.addWidget(self.recent);self.tabs.addTab(dash,'Обзор')
        self.views={};self.toolbars={}
        definitions={
        'equipment':('Оборудование',[('number','Постоянный №'),('model','Модель'),('owner','Владелец'),('serial','Серийный №')]),
        'repairs':('Ремонты',[('number','Ремонт №'),('received_at','Приёмка'),('equipment_number','Оборудование №'),('model','Модель'),('client','Клиент'),('complaint','Жалоба'),('status','Производство'),('total','Стоимость'),('paid','Оплачено'),('balance','Остаток'),('financial_status','Расчёты')]),
        'clients':('Клиенты',[('name','Название'),('legal_name','ФИО / наименование'),('contact','Контактное лицо'),('phone','Телефон'),('email','Email')]),
        'finance':('Финансы',[('number','Ремонт №'),('client','Клиент'),('status','Производство'),('total','Стоимость'),('paid','Учтено оплат'),('balance','Остаток'),('financial_status','Расчёты')]),
        'documents':('Документы',[('number','Ремонт №'),('kind','Тип'),('version','Версия'),('created_at','Создано'),('path','Файл')]),
        'estimates':('Сметы',[('number','Ремонт №'),('client','Клиент'),('kind','Смета'),('version','Версия'),('state','Ручная отметка'),('total','Итог')])}
        for key,(name,cols) in definitions.items():
            page=QWidget();layout=QVBoxLayout(page);bar=QToolBar();bar.setMovable(False);layout.addWidget(bar);self.toolbars[key]=bar
            search=QLineEdit();search.setPlaceholderText('Поиск по всем столбцам');search.setAccessibleName('Поиск '+name);layout.addWidget(search)
            view=Grid(cols);layout.addWidget(view,1);search.textChanged.connect(view.proxy.setFilterFixedString);self.views[key]=view;self.tabs.addTab(page,name)
        button(self.toolbars['clients'],'Добавить',self.new_client);button(self.toolbars['clients'],'Изменить',self.edit_client);button(self.toolbars['clients'],'Архив / вернуть',lambda:self.archive('clients'))
        button(self.toolbars['equipment'],'Добавить',self.new_equipment);button(self.toolbars['equipment'],'Карточка / история',self.equipment_card);button(self.toolbars['equipment'],'Изменить',self.edit_equipment);button(self.toolbars['equipment'],'Архив / вернуть',lambda:self.archive('equipment'))
        button(self.toolbars['repairs'],'Новый ремонт',self.new_repair);button(self.toolbars['repairs'],'Открыть',lambda:self.open_selected('repairs'))
        self.status_filter=QComboBox();self.status_filter.addItem('Все статусы','')
        for k,(name,_) in STATUSES.items():self.status_filter.addItem(name,k)
        self.toolbars['repairs'].addWidget(self.status_filter);self.status_filter.currentIndexChanged.connect(self.refresh)
        self.archived=QCheckBox('Архив');self.toolbars['equipment'].addWidget(self.archived);self.archived.toggled.connect(self.refresh)
        self.active_only=QCheckBox('Активные');self.toolbars['equipment'].addWidget(self.active_only);self.active_only.toggled.connect(self.refresh)
        button(self.toolbars['finance'],'Карточка и платежи',lambda:self.open_selected('finance'))
        button(self.toolbars['estimates'],'Открыть ремонт и сметы',lambda:self.open_selected('estimates'))
        self.views['estimates'].doubleClicked.connect(lambda _:self.open_selected('estimates'))
        button(self.toolbars['documents'],'Открыть DOCX',lambda:self.open_file(True));button(self.toolbars['documents'],'Экспортировать',self.export_document)
        for k in ('repairs','finance'):self.views[k].doubleClicked.connect(lambda _,key=k:self.open_selected(key))
        self.views['equipment'].doubleClicked.connect(self.equipment_card)
        settings=QWidget();sl=QVBoxLayout(settings);note=QLabel('Рабочая база находится в пользовательском каталоге, отдельно от EXE. Резервные копии не зашифрованы. Восстановление выполняется в новую папку; действующий проект не заменяется.');note.setWordWrap(True);sl.addWidget(note)
        for label,fn in [('Открыть другой локальный проект',self.choose_project),('Открыть папку проекта',self.open_folder),('Создать отдельное синтетическое демо',self.demo),('Резервная копия',self.backup),('Восстановить в новую папку',self.restore),('Импорт оборудования XLSX / CSV',self.import_equipment),('Исторический импорт XLSX / CSV',self.import_history),('Word → проверочный CSV',self.review_docx),('Профили организаций',self.organization_profiles)]:button(sl,label,fn)
        sl.addStretch();self.tabs.addTab(settings,'Настройки')
        self.message=QLabel('');self.message.setWordWrap(True);out.addWidget(self.message)
        for label in self.findChildren(QLabel):label.setTextFormat(Qt.TextFormat.PlainText)
        self.open_project(root or default_root())
    def run(self,fn,callback=None,message='Выполняю операцию…'):
        if self.worker:return False
        self.tabs.setEnabled(False)
        for d in self.dialogs:d.setEnabled(False)
        self.message.setText(message);job=Job(fn,self);self.worker=job
        def done():
            self.worker=None;self.tabs.setEnabled(True)
            for d in self.dialogs:d.setEnabled(True)
            error=job.error;value=job.value;job.deleteLater()
            if error:self.message.setText('Ошибка: '+error);QMessageBox.warning(self,'Service',error)
            else:
                self.message.setText('Готово')
                if callback:callback(value)
            if self._pending_refresh and not self.worker:self._pending_refresh=False;self.refresh()
        job.finished.connect(done);job.start();return True
    def open_project(self,root):
        root=Path(root).absolute()
        if self.store and root.resolve()==self.store.root.resolve():self.refresh();return
        if str(root).startswith('\\\\'):raise ServiceError('SQLite-проект должен находиться на локальном диске')
        root.mkdir(parents=True,exist_ok=True);lock=QLockFile(str(root/'.docflow-service.lock'));lock.setStaleLockTime(30000)
        if not lock.tryLock(0):QMessageBox.warning(self,'Service','Этот проект уже открыт другим экземпляром приложения');return
        def installed(store):
            if self.project_lock:self.project_lock.unlock()
            self.project_lock=lock;self.store=store;self.location.setText('Service · '+str(root)+' · один пользователь');self.refresh()
        def open_store():
            try:return ServiceStore(root)
            except Exception:lock.unlock();raise
        self.run(open_store,installed,'Проверяю SQLite и версию схемы…')
    def refresh(self,*args):
        if not self.store:return
        if self.worker:self._pending_refresh=True;return
        s=self.store;archived=self.archived.isChecked();active=self.active_only.isChecked();status=self.status_filter.currentData()
        def query():
            from ...service.estimates import estimate_summaries
            docs=s.documents()
            return {'clients':s.clients(archived=archived),'equipment':s.equipment(archived=archived,active=active),'repairs':s.repairs(status=status),'finance':s.repairs(),'documents':docs,'estimates':estimate_summaries(s),'dashboard':s.dashboard(),'active_clients':s.clients(),'active_equipment':s.equipment()}
        def install(data):
            self.cache=data
            for k,v in self.views.items():v.install(data[k])
            d=data['dashboard'];self.metrics.setText(f"Оборудование: {d['equipment']}   Активные ремонты: {d['active']}\nСогласование: {d['approval']}   Запчасти: {d['parts']}   Готово: {d['ready']}\nЗадолженность: {rub(d['debt'])}")
            self.recent.setPlainText('Недавние локальные операции\n'+'\n'.join(f"{r['created_at']} · {r['entity']} · {r['action']} · {r['detail']}" for r in d['recent']))
        self.run(query,install,'Обновляю журнал…')
    def selection(self,key):
        row=self.views[key].selected()
        if not row:QMessageBox.information(self,'Service','Сначала выберите запись в таблице')
        return row
    def _client_fields(self):return [('kind','Тип',[('organization','Организация'),('individual','Физическое лицо'),('entrepreneur','ИП')]),('name','Отображаемое название *','text'),('legal_name','ФИО / наименование','text'),('contact','Контактное лицо','text'),('phone','Телефон (необязательно)','text'),('email','Email (необязательно)','text'),('notes','Примечания','long')]
    def new_client(self):self._client_dialog()
    def edit_client(self):
        r=self.selection('clients')
        if r:self._client_dialog(r)
    def _client_dialog(self,row=None):
        d=FieldsDialog('Клиент',self._client_fields(),row,self)
        if d.exec()==QDialog.DialogCode.Accepted:
            data=d.values();key=row['id'] if row else None;s=self.store;self.run(lambda:s.save_client(data,key),lambda _:self.refresh())
    def _equipment_dialog(self,row=None):
        clients=[(x['id'],x['name']) for x in self.cache.get('active_clients',[])]
        if not clients:QMessageBox.information(self,'Клиенты','Сначала добавьте клиента');return
        fields=[('number','Постоянный номер *','text'),('model','Модель *','text'),('manufacturer','Производитель','text'),('kind','Тип','text'),('serial','Серийный номер','text'),('owner_id','Текущий владелец',clients),('identifiers','Другие идентификаторы','text'),('notes','Примечания','long')]
        d=FieldsDialog('Оборудование',fields,row,self)
        if d.exec()==QDialog.DialogCode.Accepted:
            data=d.values();key=row['id'] if row else None;s=self.store;self.run(lambda:s.save_equipment(data,key),lambda _:self.refresh())
    def new_equipment(self):self._equipment_dialog()
    def edit_equipment(self):
        r=self.selection('equipment')
        if r:self._equipment_dialog(r)
    def archive(self,table):
        r=self.selection(table)
        if r and confirm(self,('Вернуть из архива' if r['archived'] else 'Архивировать')+'? История не удаляется.'):
            s=self.store;self.run(lambda:s.archive(table,r['id'],not r['archived']),lambda _:self.refresh())
    def equipment_card(self,*args):
        row=self.selection('equipment')
        if not row:return
        from .history import HistoryDialog
        self.modal(HistoryDialog(self,row));return
    def new_repair(self):
        eq=[(x['id'],x['number']+' · '+x['model']) for x in self.cache.get('active_equipment',[])]
        if not eq:QMessageBox.information(self,'Оборудование','Сначала добавьте оборудование');return
        self._repair_create([('equipment_id','Оборудование',eq),('number','Номер обращения (пусто — автоматически)','text'),('complaint','Жалоба','long')])
    def new_repair_for(self,row):self._repair_create([('equipment_id','Оборудование',[(row['id'],row['number'])]),('number','Номер обращения (не номер оборудования)','text'),('complaint','Жалоба','long')])
    def _repair_create(self,fields):
        fields=fields+[('client_id','Заказчик',[(None,'Текущий владелец оборудования')]+[(x['id'],x['name']) for x in self.cache.get('active_clients',[])])]
        d=FieldsDialog('Приёмка оборудования',fields,parent=self)
        if d.exec()==QDialog.DialogCode.Accepted:
            v=d.values();s=self.store;request=uuid4().hex
            self.run(lambda:s.create_repair(v['equipment_id'],v['number'],v['complaint'],request,client_id=v['client_id']),self.open_repair)
    def open_selected(self,key):
        r=self.selection(key)
        if r:self.open_repair(r['repair_id'] if key=='estimates' else r['id'])
    def modal(self,dialog):
        self.dialogs.append(dialog)
        if self.worker:dialog.setEnabled(False)
        try:return dialog.exec()
        finally:self.dialogs.remove(dialog);self.refresh()
    def import_history(self):
        from .import_wizard import HistoryWizard
        self.modal(HistoryWizard(self))
    def organization_profiles(self):
        from .profiles import ProfileDialog
        self.modal(ProfileDialog(self))
    def review_docx(self):
        from ...service.docx_extract import export_review_csv
        source,_=QFileDialog.getOpenFileName(self,'Таблицы Word для ручной проверки','','Word (*.docx)')
        if not source:return
        target,_=QFileDialog.getSaveFileName(self,'Новый проверочный CSV','word-review.csv','CSV (*.csv)')
        if target and confirm(self,'Сохранить текст таблиц с координатами источника? Это не импорт ремонтов: связи, колонки и суммы нужно проверить вручную.'):
            self.run(lambda:export_review_csv(source,target),lambda _:self.message.setText('CSV сохранён. Исправьте и сопоставьте колонки перед историческим импортом.'))
    def open_repair(self,key):
        s=self.store
        def show(snapshot):
            d=RepairDialog(self,snapshot);self.dialogs.append(d);d.exec();self.dialogs.remove(d);self.refresh()
        self.run(lambda:s.snapshot(key),show)
    def open_file(self,document=False):
        r=self.selection('documents')
        if r:
            s=self.store;self.run(lambda:attachment_path(s,r['id'],True),lambda p:QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))))
    def export_document(self):
        row=self.selection('documents')
        if not row:return
        path,_=QFileDialog.getSaveFileName(self,'Копия DOCX',Path(row['path']).name,'Word (*.docx)')
        if not path:return
        s=self.store
        def copy():
            import shutil
            source=attachment_path(s,row['id'],True)
            with source.open('rb') as a,Path(path).open('xb') as b:shutil.copyfileobj(a,b)
            return path
        self.run(copy,lambda _:self.message.setText('Копия сохранена: '+path))
    def choose_project(self):
        p=QFileDialog.getExistingDirectory(self,'Локальная папка проекта')
        if p:self.open_project(p)
    def open_folder(self):
        if self.store:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root)))
    def demo(self):
        p=default_root().with_name('Service-Synthetic-Demo-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
        if not confirm(self,'Создать отдельный вымышленный проект? Рабочая база не меняется.'):return
        self.run(lambda:seed_demo(p),lambda _:self.open_project(p),'Создаю отдельное синтетическое демо…')
    def backup(self):
        path,_=QFileDialog.getSaveFileName(self,'Новая резервная копия',f'DocFlow-{datetime.now():%Y%m%d-%H%M%S}.service-backup.zip','ZIP (*.zip)')
        if path:
            s=self.store;self.run(lambda:create_backup(s,path),lambda _:self.message.setText('Копия создана: '+path),'Резервирую SQLite и вложения…')
    def restore(self):
        archive,_=QFileDialog.getOpenFileName(self,'Проверенная резервная копия','','ZIP (*.zip)')
        if not archive:return
        parent=QFileDialog.getExistingDirectory(self,'Родительская папка восстановления')
        if not parent:return
        target=Path(parent)/('DocFlow-Restored-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
        if confirm(self,'Проверить и восстановить копию в новую папку '+str(target)+'? Текущие данные не заменяются.'):
            self.run(lambda:restore_backup(archive,target),lambda p:self.open_project(p),'Проверяю манифест и восстанавливаю новую папку…')
    def import_equipment(self):
        path,_=QFileDialog.getOpenFileName(self,'Таблица оборудования','','Таблицы (*.xlsx *.csv)')
        if not path:return
        from ...data import load_table
        from ...service.importers import preview_equipment,import_equipment
        s=self.store
        def mapping(table):
            options=[(h,h) for h in table.headers]
            clients=[(x['id'],x['name']) for x in self.cache.get('active_clients',[])]
            if not clients:QMessageBox.information(self,'Импорт','Сначала создайте владельца оборудования');return
            d=FieldsDialog('Явное сопоставление (новое оборудование)',[('number','Постоянный номер',options),('model','Модель',options),('owner_id','Владелец',clients)],parent=self)
            if d.exec()!=QDialog.DialogCode.Accepted:return
            v=d.values();m={k:v[k] for k in ('number','model')}
            def preview(rows):
                if confirm(self,f"Проверено записей: {len(rows)}. Первые номера: "+', '.join(x['number'] for x in rows[:5])+'. Импортировать всё одной транзакцией?'):
                    self.run(lambda:import_equipment(s,rows,v['owner_id']),lambda _:self.refresh(),'Импортирую без объединения исторических номеров…')
            self.run(lambda:preview_equipment(path,m),preview,'Проверяю таблицу…')
        self.run(lambda:load_table(Path(path)),mapping,'Открываю таблицу в фоновом потоке…')

from .repair_editor import RepairDialog
