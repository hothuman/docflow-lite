"""Asynchronous local workspace. Every DB/media/DOCX/backup operation runs off Qt's UI thread."""
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from functools import wraps
from PySide6.QtCore import QThread,Qt,QSortFilterProxyModel,QTimer,QUrl,QLockFile,Signal,QStandardPaths
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QTabWidget,QTableView,QHeaderView,QLineEdit,QComboBox,QCheckBox,QFileDialog,QInputDialog,QMessageBox,QDialog,QPlainTextEdit,QFormLayout,QScrollArea,QToolBar)
from ...service.repository import ServiceStore,default_root
from ...service.validation import ServiceError,rub
from ...service.statuses import APPROVALS
from ...service.documents import generate_document,KINDS
from ...service.attachments import add_attachment,attachment_path,remove_attachment,export_file
from ..settings import preferences
from ...service.demo import seed_demo
from .widgets import Grid,button,confirm
from .forms import FieldsDialog
from .journal import RepairJournal
from .pages import WorkspacePages
from ..flow import ActionBar, OperationNotice
from ..diagnostics import record_exception,record_project_event,friendly_error,diagnostic_path

def needs_project(function):
    @wraps(function)
    def guarded(self,*args,**kwargs):
        if not self.require_project():return False
        return function(self,*args,**kwargs)
    return guarded

class Job(QThread):
    def __init__(self,function,parent,project_operation=False):super().__init__(parent);self.function=function;self.value=None;self.error='';self.project_operation=project_operation
    def run(self):
        try:self.value=self.function()
        except Exception as exc:
            if self.project_operation:record_project_event('worker_error',exc)
            else:record_exception('Service worker',exc)
            self.error=friendly_error(exc)
        finally:self.function=None

class ServiceWorkspace(QWidget):
    page_changed = Signal()

    def __init__(self,parent=None,root=None,shell_navigation=False):
        super().__init__(parent);self.shell_navigation=shell_navigation;self.store=None;self.worker=None;self.project_lock=None;self.cache={};self._pending_refresh=False;self.dialogs=[];self._last_repairs={};self.project_state='not_open';self._project_busy=False;self._safe_project_buttons=[]
        out=QVBoxLayout(self);out.setContentsMargins(0,0,0,0)
        self.location=QLabel('Проект не открыт');self.location.setObjectName('projectLocation');self.location.setWordWrap(True);out.addWidget(self.location)
        self.project_actions=ActionBar();out.addWidget(self.project_actions)
        self.open_project_button=button(self.project_actions,'Открыть проект',self.choose_project,primary=True)
        self.new_project_button=button(self.project_actions,'Создать отдельный проект',self.new_project)
        self.restore_project_button=button(self.project_actions,'Восстановить копию',self.restore)
        self.section_picker=QComboBox();self.section_picker.setAccessibleName('Раздел мастерской');out.addWidget(self.section_picker)
        self.tabs=QTabWidget();self.tabs.setUsesScrollButtons(False);out.addWidget(self.tabs,1)
        self.pages = WorkspacePages(self)
        out.addWidget(self.pages, 1)
        self.pages.changed.connect(self._page_changed)
        self.section_picker.currentIndexChanged.connect(self.tabs.setCurrentIndex);self.tabs.currentChanged.connect(self.section_picker.setCurrentIndex)
        from .dashboard import Dashboard
        self.dashboard=Dashboard(self);self.tabs.addTab(self.dashboard,'Обзор')
        self.searches={};self.empty_labels={};self.archive_hints={};self.archive_buttons={};self.reset_filter_buttons={}
        self.views={};self.toolbars={}
        definitions={
        'equipment':('Оборудование',[('number','Постоянный №'),('model','Модель'),('owner','Владелец'),('serial','Серийный №')]),
        'repairs':('Ремонты',[('number','Ремонт №'),('equipment_label','Аппарат'),('client','Клиент'),('received_at','Приёмка'),('status','Статус'),('total','Стоимость'),('balance','Остаток')]),
        'clients':('Клиенты',[('name','Клиент'),('kind','Тип'),('contact','Контактное лицо'),('phone','Телефон'),('email','Email'),('archived','Состояние')]),
        'finance':('Финансы',[('number','Ремонт №'),('client','Клиент'),('status','Статус'),('total','Стоимость'),('paid','Учтено оплат'),('balance','Остаток к оплате'),('financial_status','Расчёты')]),
        'documents':('Документы',[('number','Ремонт №'),('kind','Тип'),('version','Версия'),('created_at','Создано'),('path','Файл')]),
        'estimates':('Сметы',[('number','Ремонт №'),('client','Клиент'),('kind','Смета'),('version','Версия'),('state','Ручная отметка'),('total','Итог')])}
        for key,(name,cols) in definitions.items():
            if key=='repairs':
                self.journal=RepairJournal(cols,self.start_intake,
                    lambda:self.open_selected('repairs'),self.open_journal_history)
                self.views[key]=self.journal.grid
                self.searches[key]=self.journal.search
                self.status_filter=self.journal.status_filter
                self.tabs.addTab(self.journal,name)
                continue
            page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(0,6,0,0);layout.setSpacing(8)
            from ..widgets import text
            help_text={
                'equipment':'Постоянный номер идентифицирует аппарат. Карточка покажет владельца и отдельные обращения.',
                'clients':'Карточка клиента хранит контакты. Заказчик ремонта и текущий владелец аппарата могут различаться.',
                'finance':'Здесь учтены только сохранённые оплаты и возвраты. Неизвестный остаток требует сверки источника.',
                'documents':'Найдите акт, смету или гарантию. Проверьте номер ремонта и версию перед открытием.',
                'estimates':'Открывайте сохранённые версии расчёта. Черновик и ручные отметки доступны в карточке ремонта.',
            }
            layout.addWidget(text(help_text[key],'muted'))
            bar=ActionBar();layout.addWidget(bar);self.toolbars[key]=bar
            search=QLineEdit()
            search.setPlaceholderText({'equipment':'Номер аппарата, серийный номер или модель',
                'clients':'Клиент, контакт, телефон или email','finance':'Ремонт, заказчик или статус',
                'documents':'Номер ремонта, вид документа или имя файла','estimates':'Номер ремонта, заказчик или вид сметы'}[key])
            search.setAccessibleName('Поиск '+name);layout.addWidget(search)
            self.searches[key]=search
            empty=QLabel({'equipment':'Пока нет оборудования. Добавьте первый аппарат или импортируйте журнал.','clients':'Клиентов пока нет. Добавьте первого клиента.','finance':'Финансовых записей пока нет. Откройте ремонт для учёта расчётов.','documents':'Документы ещё не создавались.','estimates':'Нет сохранённых смет. Откройте ремонт и подготовьте расчёт.'}[key]);empty.setObjectName('empty');empty.setWordWrap(True);layout.addWidget(empty);self.empty_labels[key]=empty
            reset=QPushButton('Сбросить фильтры');reset.setVisible(False);reset.clicked.connect(lambda _,k=key:self.reset_list_filters(k));layout.addWidget(reset);self.reset_filter_buttons[key]=reset
            if key in ('clients','equipment'):
                hint=QLabel();hint.setWordWrap(True);hint.setObjectName('muted');hint.hide();layout.addWidget(hint);self.archive_hints[key]=hint
                show_archive=QPushButton('Показать архив');show_archive.hide();show_archive.clicked.connect(lambda _,k=key:self.show_archived(k));layout.addWidget(show_archive);self.archive_buttons[key]=show_archive
            view=Grid(cols,settings_key='workspace/'+key);view.setAccessibleName(name)
            layout.addWidget(view,1);search.textChanged.connect(view.proxy.setFilterFixedString);search.textChanged.connect(lambda _,k=key:self.update_list_state(k));self.views[key]=view;self.tabs.addTab(page,name)
        button(self.toolbars['clients'],'Добавить',self.new_client);button(self.toolbars['clients'],'Изменить',self.edit_client);button(self.toolbars['clients'],'Архив / вернуть',lambda:self.archive('clients'))
        button(self.toolbars['equipment'],'Добавить',self.new_equipment);button(self.toolbars['equipment'],'Карточка / история',self.equipment_card);button(self.toolbars['equipment'],'Изменить',self.edit_equipment);button(self.toolbars['equipment'],'Архив / вернуть',lambda:self.archive('equipment'))
        self.archived=QCheckBox('Архив');self.toolbars['equipment'].addWidget(self.archived);self.archived.toggled.connect(self.refresh)
        self.clients_archived=QCheckBox('Архивные клиенты');self.toolbars['clients'].addWidget(self.clients_archived);self.clients_archived.toggled.connect(self.refresh)
        self.active_only=QCheckBox('Активные');self.toolbars['equipment'].addWidget(self.active_only);self.active_only.toggled.connect(self.refresh)
        button(self.toolbars['finance'],'Карточка и платежи',lambda:self.open_selected('finance'))
        button(self.toolbars['finance'],'Найти ремонты с долгом',self.show_repair_debt)
        button(self.toolbars['estimates'],'Открыть ремонт и сметы',lambda:self.open_selected('estimates'))
        self.views['estimates'].doubleClicked.connect(lambda _:self.open_selected('estimates'))
        button(self.toolbars['documents'],'Открыть DOCX',lambda:self.open_file(True));button(self.toolbars['documents'],'Экспортировать',self.export_document)
        self.views['finance'].doubleClicked.connect(lambda _:self.open_selected('finance'))
        self.views['equipment'].doubleClicked.connect(self.equipment_card)
        self.views['equipment'].openRequested.connect(self.equipment_card)
        for key in ('finance','estimates'):self.views[key].openRequested.connect(lambda k=key:self.open_selected(k))
        self.views['documents'].openRequested.connect(lambda:self.open_file(True))
        from .settings_page import SettingsPage
        self.settings_page=SettingsPage(self)
        self.tabs.addTab(self.settings_page,'Настройки')
        self.section_picker.addItems([self.tabs.tabText(i) for i in range(self.tabs.count())]);self.section_picker.setCurrentIndex(0)
        if self.shell_navigation:self.tabs.tabBar().hide();self.section_picker.hide()
        self.message=OperationNotice();out.addWidget(self.message)
        self.operation_cancel=QPushButton('Отменить операцию')
        self.operation_cancel.setAccessibleName('Отменить фоновую операцию')
        self.operation_cancel.hide()
        out.addWidget(self.operation_cancel,0,Qt.AlignmentFlag.AlignLeft)
        self.operation_cancel.clicked.connect(self._cancel_operation)
        self._operation_cancel_callback=None
        from ..widgets import card,text
        self.backup_result_panel,backup_result=card('Восстановление завершено')
        self.backup_result_folder=text('','muted');backup_result.addWidget(self.backup_result_folder)
        self.backup_result_actions=ActionBar();backup_result.addWidget(self.backup_result_actions);out.addWidget(self.backup_result_panel)
        self._backup_result=None
        button(self.backup_result_actions,'Открыть расположение',lambda:self.open_local(self._backup_result) if self._backup_result else None)
        button(self.backup_result_actions,'К журналу ремонтов',self.finish_backup_notice)
        self.backup_result_panel.hide()
        self._restored_target=None
        self.history_window=None
        self._repair_sections={}
        for label in self.findChildren(QLabel):label.setTextFormat(Qt.TextFormat.PlainText)
        self._sync_project_controls()
        self.open_project(root or default_root())
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if not self.shell_navigation:
            compact=self.width()<920
            self.tabs.tabBar().setVisible(not compact)
            self.section_picker.setVisible(compact and self.current_page is None)

    @property
    def current_page(self):
        return self.pages.current

    def _page_changed(self):
        self.tabs.setVisible(self.current_page is None)
        self.location.setVisible(self.current_page is None)
        self.section_picker.setVisible(not self.shell_navigation and self.width()<920 and self.current_page is None)
        self.page_changed.emit()

    def push_page(self,widget,title,**options):
        if self.current_page is None and self.tabs.currentWidget() is self.journal and not options.get('on_close'):
            context=self.journal.view_context()
            options['on_close']=lambda:self.journal.restore_view(context)
        return self.pages.push(widget,title,**options)

    def back_page(self):
        self.pages.back()

    def go_to_section(self,index):
        if self.tabs.currentIndex()==index and self.current_page is None:
            self.page_changed.emit()
            return
        was_editing=self.current_page is not None
        def open_section():
            self.tabs.setCurrentIndex(index)
            self._page_changed()
            if was_editing and self.store:self.refresh()
        self.pages.clear(open_section)

    def embed_form(self,dialog,on_accept=None,**options):
        self.push_page(dialog,dialog.windowTitle(),**options)
        if on_accept:
            dialog.accepted.connect(lambda:on_accept(dialog.values()))
        return dialog
    def show_repair_debt(self):
        self.journal.reset_filters()
        self.journal.finance_filter.setCurrentIndex(self.journal.finance_filter.findData('debt'))
        self.tabs.setCurrentWidget(self.journal)
        self.journal.finance_filter.setFocus()

    def set_short_journal(self,short):
        self.layout().setSpacing(4 if short else 6)
        self.message.set_compact(short)

    def _sync_project_controls(self):
        ready=self.store is not None and not self._project_busy and not self.worker
        available=not self._project_busy and not self.worker
        for control in self.tabs.findChildren(QPushButton):
            control.setEnabled(available if control in self._safe_project_buttons else ready)
        for control in (*self.searches.values(),*self.views.values(),self.status_filter,self.archived,self.clients_archived,self.active_only):control.setEnabled(ready)
        for control in (self.open_project_button,self.new_project_button,self.restore_project_button):control.setEnabled(available)
        self.journal.project_state(self.store is not None,ready)
        self.project_actions.setVisible(self.store is None or self.project_state in ('cancelled','error','locked'))
        if self.store is None:
            for key in self.views:self.update_list_state(key)
            self.dashboard.empty.setText('Проект не открыт. Откройте локальную папку, создайте отдельный проект или восстановите копию.')
            for value in self.dashboard.values.values():value.setText('—')
            self.dashboard.recent.install([]);self.dashboard.recent.hide();self.dashboard.empty.show();self.dashboard.finance_hint.hide()
        else:self.dashboard.empty.setText('Обращений пока нет. Добавьте клиента и оборудование, затем оформите первый ремонт.')
    def _project_status(self,state,message):
        self.project_state=state;self._project_busy=state in ('opening','copy_required')
        labels={'opening':'Открываю проект…','copy_required':'Нужна отдельная обновлённая копия','cancelled':'Открытие отменено','error':'Ошибка открытия','locked':'Проект занят другим процессом','not_open':'Проект не открыт'}
        if self.store:
            title='Проект: '+self.store.root.name
            if state!='opened':title+=' · '+labels.get(state,'')
            self.location.setToolTip(str(self.store.root))
            if state in ('cancelled','error','locked'):message+=' Текущий проект остаётся открыт.'
        else:
            title=labels.get(state,'Проект не открыт')
            if state not in ('opening','not_open'):title='Проект не открыт · '+title
            self.location.setToolTip('')
        self.location.setText(title);self.message.setText(message)
        record_project_event(state);self._sync_project_controls()
    def require_project(self):
        if self.store is not None and not self._project_busy and not self.worker:return True
        if self.store is None:self.message.setText('Проект не открыт. Откройте локальную папку, создайте отдельный проект или восстановите копию.')
        elif not self.worker:self.message.setText('Дождитесь завершения открытия проекта.')
        return False
    def _cancel_operation(self):
        if self._operation_cancel_callback:
            self._operation_cancel_callback()
            self.operation_cancel.setEnabled(False)
            self.message.setText('Отмена запрошена. Завершаю чтение…')

    def run(self,fn,callback=None,message='Выполняю операцию…',on_error=None,project_operation=False,*,inline_error=False,keep_page_enabled=False,cancel=None):
        if self.worker:return False
        self.tabs.setEnabled(False)
        if keep_page_enabled:self.pages.back_button.setEnabled(False)
        else:self.pages.setEnabled(False)
        self._operation_cancel_callback=cancel
        self.operation_cancel.setEnabled(bool(cancel))
        self.operation_cancel.setVisible(bool(cancel))
        for d in self.dialogs:d.setEnabled(False)
        self.message.setText(message);job=Job(fn,self,project_operation);self.worker=job;self._sync_project_controls()
        def failed(error):
            self.message.setText('Ошибка: '+error)
            if on_error:
                try:on_error(error)
                except Exception as exc:
                    record_project_event('error_handler_error',exc)
                    if project_operation:self._project_status('error','Ошибка завершения открытия. Повторите выбор проекта.')
            if not inline_error:QMessageBox.warning(self,'Мастерская',error)
        def done():
            self._operation_cancel_callback=None;self.operation_cancel.hide()
            self.worker=None;self.tabs.setEnabled(True);self.pages.setEnabled(True);self.pages.back_button.setEnabled(True)
            for d in self.dialogs:d.setEnabled(True)
            error=job.error;value=job.value;job.deleteLater()
            if error:
                failed(error)
            else:
                try:
                    if callback:callback(value)
                    if not self.worker and self.message.text()==message:self.message.setText('Операция выполнена')
                except Exception as exc:
                    if project_operation:record_project_event('callback_error',exc)
                    else:record_exception('Service callback',exc)
                    failed(friendly_error(exc))
            self._sync_project_controls()
            if self._pending_refresh and not self.worker and not self._project_busy:self._pending_refresh=False;self.refresh()
        def slow():
            if project_operation and self.worker is job and job.isRunning():
                record_project_event('worker_still_running')
                self.message.setText('Открытие ещё выполняется. Не закрывайте программу; дождитесь результата проверки диска и базы.')
        QTimer.singleShot(15000,self,slow)
        job.finished.connect(done);job.start();return True
    def open_project(self,root):
        self.journal.persist_context()
        if self.worker or self._project_busy:return False
        if self.current_page is not None:
            self.pages.clear(lambda:self.open_project(root))
            return
        if self.history_window:self.history_window.close()
        if self.dialogs:return False
        root=Path(root).absolute()
        if self.store and root.resolve()==self.store.root.resolve():self._project_status('opened','Проект уже открыт.');self.refresh();return
        if str(root).startswith('\\\\'):
            self._project_status('error','SQLite-проект должен находиться на локальном диске. Выберите другую папку.');return False
        from ...service.database import Database
        self._pending_refresh=False;self._project_status('opening','Проверяю версию проекта без изменений…')
        def failed(error):self._project_status('error','Не удалось открыть проект: '+error)
        def inspected(version):
            if version is None:self._open_current_project(root);return
            self._project_status('copy_required','Для старой схемы нужна отдельная обновлённая копия. Исходный проект не меняется.')
            if not confirm(self,f'Проект использует схему {version}. Создать обновлённую копию в новой папке? Исходный проект, документы и история останутся без изменений. Без подтверждения проект не обновляется.'):
                self._project_status('cancelled','Открытие отменено. Исходный проект не изменён.');return
            parent=QFileDialog.getExistingDirectory(self,'Папка для новой обновлённой копии')
            if not parent:self._project_status('cancelled','Копия не создана. Исходный проект не изменён.');return
            target=Path(parent)/('DocFlow-Updated-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:6])
            from ...service.project_upgrade import copy_project_for_upgrade
            source_lock=QLockFile(str(root/'.docflow-service.lock'));source_lock.setStaleLockTime(30000)
            if not source_lock.tryLock(0):self._project_status('locked','Закройте другой экземпляр программы и повторите открытие. Копия не создана.');return
            def copy():
                try:return copy_project_for_upgrade(root,target)
                finally:source_lock.unlock()
            self._project_status('opening','Создаю отдельную обновлённую копию…')
            if not self.run(copy,self._open_current_project,'Проверяю и обновляю отдельную копию; исходный проект не меняется…',on_error=failed,project_operation=True):source_lock.unlock();failed('Операция не запущена. Повторите открытие.')
        return self.run(lambda:Database.migration_required(root/'service.db'),inspected,'Проверяю версию проекта без изменений…',on_error=failed,project_operation=True)
    def _open_current_project(self,root):
        root.mkdir(parents=True,exist_ok=True);lock=QLockFile(str(root/'.docflow-service.lock'));lock.setStaleLockTime(30000)
        if not lock.tryLock(0):self._project_status('locked','Этот проект уже открыт другим экземпляром приложения. Закройте его и повторите открытие.');return
        def failed(error):
            lock.unlock();self._project_status('error','Не удалось открыть проект: '+error)
        def installed(result):
            store,data=result;previous=self.cache;previous_store=self.store
            controls=(*(value for key,value in self.searches.items() if key!='repairs'),self.archived,self.clients_archived,self.active_only)
            prior=[(c,c.text() if isinstance(c,QLineEdit) else c.currentIndex() if isinstance(c,QComboBox) else c.isChecked()) for c in controls]
            def set_filters(values):
                for control,value in values:
                    blocked=control.blockSignals(True)
                    if isinstance(control,QLineEdit):control.setText(value)
                    elif isinstance(control,QComboBox):control.setCurrentIndex(value)
                    else:control.setChecked(value)
                    control.blockSignals(blocked)
            try:
                self._install_project_data(data);self.store=store
                set_filters([(c,'' if isinstance(c,QLineEdit) else 0 if isinstance(c,QComboBox) else False) for c in controls])
                self.journal.project_changed(store.root)
                if self._restored_target==store.root:
                    self._project_status('opened','Восстановленная копия открыта как активный проект: '+store.root.name)
                    self._restored_target=None
                    self.show_backup_location(store.root)
                else:
                    self._project_status('opened','Проект открыт. Можно продолжать работу.')
                for key in self.views:self.update_list_state(key)
            except Exception:
                self.store=previous_store;self.cache=previous;set_filters(prior)
                if previous:self._install_project_data(previous)
                else:
                    self.cache={}
                    for view in self.views.values():view.install([])
                raise
            if self.project_lock:self.project_lock.unlock()
            self.project_lock=lock
        def open_store():
            try:
                store=ServiceStore(root,allow_upgrade=False)
                return store,self._query_project_data(store)
            except Exception:lock.unlock();raise
        if not self.run(open_store,installed,'Проверяю SQLite и версию схемы…',on_error=failed,project_operation=True):failed('Операция не запущена. Повторите открытие.')
    def _query_project_data(self,s,archived=False,active=False,clients_archived=False):
        from ...service.estimates import estimate_summaries
        from ...service.link_audit import audit_links
        docs=s.documents();rows=[{**r,'equipment_label':r['equipment_number']+' · '+r['model']} for r in s.repairs()]
        current_equipment=s.equipment()
        archived_equipment=s.equipment(archived=True)
        journal_equipment={row['id']:row for row in (*current_equipment,*archived_equipment)}
        equipment=s.equipment(archived=archived,active=True) if active else (
            archived_equipment if archived else current_equipment)
        return {'clients':s.clients(archived=clients_archived),'equipment':equipment,'repairs':rows,'finance':rows,'documents':docs,'estimates':estimate_summaries(s),'dashboard':s.dashboard(rows),'active_clients':s.clients(),'active_equipment':current_equipment,'journal_equipment':journal_equipment,'link_audit':audit_links(s),'next_repair_number':s.preview_repair_number()}
    def _install_project_data(self,data):
        for key,view in self.views.items():
            if key=='repairs':self.journal.install(data[key],data['journal_equipment'])
            else:view.install(data[key])
        self.dashboard.install(data['dashboard']);self.cache=data
    def refresh(self,*args,journal_context=None,on_complete=None):
        if not self.store or self._project_busy:return
        if self.worker:self._pending_refresh=True;return
        s=self.store;archived=self.archived.isChecked();active=self.active_only.isChecked();clients_archived=self.clients_archived.isChecked()
        def install(data):
            self._install_project_data(data)
            for key in self.views:self.update_list_state(key)
            if journal_context and self.tabs.currentWidget() is self.journal:
                self._sync_project_controls()
                self.journal.restore_view(journal_context)
            if on_complete:
                if self.shell_navigation:on_complete()
                else:QTimer.singleShot(0,self,on_complete)
        self.run(lambda:self._query_project_data(s,archived,active,clients_archived),install,'Обновляю журнал…')
    def reset_list_filters(self,key):
        if key=='repairs':
            self.journal.reset_filters()
            return
        self.searches[key].clear()
        if key=='equipment':self.active_only.setChecked(False)
        self.update_list_state(key)
    def show_archived(self,key):
        self.reset_list_filters(key)
        (self.clients_archived if key=='clients' else self.archived).setChecked(True)
    def update_list_state(self,key):
        if key not in self.views or key=='repairs':return
        if self.store is None:
            self.empty_labels[key].setText('Проект не открыт. Выберите локальную папку или создайте отдельный проект.');self.empty_labels[key].show();self.reset_filter_buttons[key].hide();return
        query=bool(self.searches[key].text().strip());filtered=query or (key=='equipment' and self.active_only.isChecked())
        visible=self.views[key].proxy.rowCount()
        self.reset_filter_buttons[key].setVisible(filtered)
        label=self.empty_labels[key]
        label.setVisible(not visible)
        if filtered and not visible:label.setText('По выбранным фильтрам записей нет. Сбросьте фильтры или измените поиск.')
        elif key in ('clients','equipment'):
            archived=(self.clients_archived if key=='clients' else self.archived).isChecked()
            counts=self.cache.get('link_audit',{}).get('counts',{}).get(key,{})
            archive_count=counts.get('archived',0);current_count=counts.get('current',0)
            archived_empty='Архивных клиентов пока нет.' if key=='clients' else 'Архивного оборудования пока нет.'
            current_empty='Список действующих клиентов пуст.' if key=='clients' else 'Список действующего оборудования пуст.'
            label.setText(archived_empty if archived else (current_empty if archive_count else ('Клиентов пока нет. Добавьте первого клиента.' if key=='clients' else 'Пока нет оборудования. Добавьте первый аппарат или импортируйте журнал.')))
            hint=self.archive_hints[key];hint.setVisible(bool(archive_count))
            hint.setText(('Действующих' if key=='clients' else 'Действующего')+f': {current_count}. В архиве: {archive_count}. '+('Показаны архивные записи.' if archived else 'Архивные записи скрыты; связанные обращения и история сохранены.'))
            self.archive_buttons[key].setText(f'Показать архив ({archive_count})');self.archive_buttons[key].setVisible(bool(archive_count) and not archived)
        elif not visible:
            label.setText({'finance':'Финансовых записей пока нет. Откройте ремонт для учёта расчётов.','documents':'Документы ещё не создавались.','estimates':'Нет сохранённых смет. Откройте ремонт и подготовьте расчёт.'}[key])
    @needs_project
    def open_catalog(self):
        from .catalog import CatalogDialog
        self.modal(CatalogDialog(self))
    def customize_dashboard(self):
        from .dashboard_preferences import show_editor
        show_editor(self)
    @needs_project
    def start_intake(self,equipment=None):
        from .intake import IntakeDialog
        if isinstance(equipment,bool):equipment=None
        dialog=IntakeDialog(self,equipment)
        if self.shell_navigation:
            from .history import HistoryPage
            previous=self.current_page
            self.embed_form(dialog)
            def finished(_):
                if getattr(dialog,'created_key',None):
                    key=dialog.created_key
                    self.refresh(on_complete=lambda:self.open_repair(key,
                        return_to=previous.refresh if isinstance(previous,HistoryPage) else None))
            dialog.finished.connect(finished)
            return dialog
        self.dialogs.append(dialog)
        try:dialog.exec()
        finally:self.dialogs.remove(dialog)
        if getattr(dialog,'created_key',None):self.open_repair(dialog.created_key)
        else:self.refresh()
    @needs_project
    def search_all(self):
        from .search import SearchDialog
        if self.shell_navigation:
            page=self.embed_form(SearchDialog(self,embedded=True))
            page.query.setFocus()
            return page
        self.modal(SearchDialog(self))
    @needs_project
    def continue_repair(self):
        key=self._last_repairs.get(str(self.store.root))
        if key and any(r['id']==key for r in self.cache.get('finance',[])):self.open_repair(key)
        else:
            self.tabs.setCurrentIndex(2);self.searches['repairs'].setFocus()
            self.message.setText('Выберите ремонт, чтобы продолжить. После открытия он запомнится в этом проекте.')
    def quick_help(self):
        dialog=QDialog(self);dialog.setWindowTitle('Ремонт за 5 минут');box=QVBoxLayout(dialog)
        label=QLabel('1. Новый ремонт — выберите известный аппарат или добавьте новый с клиентом.\n2. Приёмка — жалоба и комплектность. Диагностика — причина и план.\n3. Согласование — расчёт, версия сметы и фактический ответ заказчика.\n4. Работы — выполненные позиции, запчасти, фото и расчёты.\n5. Выдача — сформируйте акт, откройте для печати и отметьте передачу.\nИстория аппарата всегда доступна из карточки. Состояние ремонта и оплата учитываются отдельно.');label.setWordWrap(True);box.addWidget(label);button(box,'Понятно',dialog.accept);dialog.resize(580,420);dialog.exec()
    @needs_project
    def diagnose_links(self):
        from ...service.link_audit import audit_links,audit_summary
        store=self.store
        def show(report):
            dialog=QDialog(self);dialog.setWindowTitle('Проверка связей');layout=QVBoxLayout(dialog);box=QPlainTextEdit();box.setReadOnly(True);box.setPlainText(audit_summary(report));layout.addWidget(box)
            bar=QHBoxLayout();layout.addLayout(bar)
            def save():
                import json
                path,_=QFileDialog.getSaveFileName(dialog,'Новый отчёт без персональных данных','relationship-check.json','JSON (*.json)')
                if not path:return
                def write():
                    with Path(path).open('x',encoding='utf-8') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
                self.run(write,lambda _:self.message.setText('Сохранён агрегированный отчёт связей без персональных данных.'))
            button(bar,'Сохранить отчёт JSON',save);button(bar,'Закрыть',dialog.accept);dialog.resize(720,540);self.modal(dialog)
        self.run(lambda:audit_links(store),show,'Проверяю связи без изменения данных…')
    @needs_project
    def find_equipment(self):
        self.tabs.setCurrentIndex(1)
        def focus():self.window().activateWindow();self.searches['equipment'].setFocus(Qt.FocusReason.ShortcutFocusReason)
        QTimer.singleShot(0,focus)
    @needs_project
    def dashboard_history(self):
        rows=self.cache.get('active_equipment',[])
        if not rows:QMessageBox.information(self,'История','Добавьте оборудование или импортируйте журнал.');return
        if len(rows)==1:
            self.show_history(rows[0])
        else:self.find_equipment();self.message.setText('Найдите аппарат, выберите строку и нажмите «Карточка / история» или Enter.')
    def open_local(self,path):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.message.setText('Не удалось открыть файл или папку. Скопируйте путь: '+str(path));QMessageBox.warning(self,'Открытие','Система не смогла открыть файл или папку. Проверьте установленное приложение и доступ к файлу.');return False
        return True
    @needs_project
    def diagnostics(self):
        store=self.store
        def query():
            with store.db.connection() as c:rows=[dict(r) for r in c.execute('SELECT * FROM operations ORDER BY id DESC LIMIT 200')]
            path=diagnostic_path();return rows,path.read_text(encoding='utf-8')[-100000:] if path.is_file() else ''
        def show(data):
            from .dashboard import DiagnosticsDialog
            self.modal(DiagnosticsDialog(self,data[0],{r['id']:r['number'] for r in self.cache.get('finance',[])},data[1]))
        self.run(query,show,'Открываю локальную диагностику…')
    @needs_project
    def selection(self,key):
        row=self.views[key].selected()
        if not row:QMessageBox.information(self,'Service','Сначала выберите запись в таблице')
        return row
    def _client_fields(self):return [('kind','Тип',[('organization','Организация'),('individual','Физическое лицо'),('entrepreneur','ИП')]),('name','Отображаемое название *','text'),('legal_name','ФИО / наименование','text'),('contact','Контактное лицо','text'),('phone','Телефон (необязательно)','text'),('email','Email (необязательно)','text'),('notes','Примечания','long')]
    def new_client(self):self._client_dialog()
    def edit_client(self):
        r=self.selection('clients')
        if r:self._client_dialog(r)
    @needs_project
    def _client_dialog(self,row=None):
        d=FieldsDialog('Клиент',self._client_fields(),row,self)
        key=row['id'] if row else None;s=self.store;d.persist_with(self,lambda data:s.save_client(data,key))
        if self.shell_navigation:return self.embed_form(d,on_close=self.refresh)
        self.modal(d)
    @needs_project
    def _equipment_dialog(self,row=None):
        clients=[(x['id'],x['name']) for x in self.cache.get('active_clients',[])]
        if not clients:
            has_archive=self.cache.get('link_audit',{}).get('counts',{}).get('clients',{}).get('archived',0)
            QMessageBox.information(self,'Клиенты','Действующих клиентов нет. Откройте архив и проверьте нужную карточку либо создайте нового клиента. Архивные связи не удалены.' if has_archive else 'Сначала добавьте клиента');return
        fields=[('number','Постоянный номер *','text'),('model','Модель *','text'),('manufacturer','Производитель','text'),('kind','Тип','text'),('serial','Серийный номер','text'),('owner_id','Текущий владелец',clients),('identifiers','Другие идентификаторы','text'),('notes','Примечания','long')]
        d=FieldsDialog('Оборудование',fields,row,self)
        key=row['id'] if row else None;s=self.store;d.persist_with(self,lambda data:s.save_equipment(data,key))
        if self.shell_navigation:return self.embed_form(d,on_close=self.refresh)
        self.modal(d)
    def new_equipment(self):self._equipment_dialog()
    def edit_equipment(self):
        r=self.selection('equipment')
        if r:self._equipment_dialog(r)
    @needs_project
    def archive(self,table):
        r=self.selection(table)
        if r and confirm(self,('Вернуть из архива' if r['archived'] else 'Архивировать')+'? История не удаляется.'):
            s=self.store;self.run(lambda:s.archive(table,r['id'],not r['archived']),lambda _:self.refresh())
    @needs_project
    def equipment_card(self,*args):
        row=self.selection('equipment')
        if not row:return
        self.show_history(row)
    @needs_project
    def open_journal_history(self):
        equipment=self.journal.selected_equipment()
        if equipment:self.show_history(equipment)

    @needs_project
    def show_history(self,equipment,view=None):
        if self.shell_navigation:
            from .history import HistoryPage
            for route in self.pages.routes:
                if isinstance(route.widget,HistoryPage) and route.widget.equipment['id']==equipment['id']:
                    self.pages.return_to(route.widget,route.widget.refresh)
                    return route.widget
            page=HistoryPage(self,equipment,view,on_back=self.back_page,on_new=self.start_intake)
            return self.push_page(page,'История аппарата',back_label='К предыдущему экрану')
        from .history import HistoryDialog
        if self.history_window:self.history_window.close()
        window=HistoryDialog(self,equipment,view,workspace_view=True)
        self.history_window=window
        self.dialogs.append(window)
        def closed(_):
            self.dialogs.remove(window)
            self.history_window=None
            window.deleteLater()
        window.finished.connect(closed)
        window.setEnabled(not self.worker)
        window.show()

    @needs_project
    def new_repair(self):
        eq=[(x['id'],x['number']+' · '+x['model']) for x in self.cache.get('active_equipment',[])]
        if not eq:
            has_archive=self.cache.get('link_audit',{}).get('counts',{}).get('equipment',{}).get('archived',0)
            QMessageBox.information(self,'Оборудование','Действующего оборудования нет. Откройте архив и проверьте постоянный номер и владельца перед возвратом карточки в работу. Новый аппарат создавайте только для другого оборудования.' if has_archive else 'Сначала добавьте оборудование');return
        self._repair_create([('equipment_id','Оборудование',eq),('number','№ ремонта (не номер аппарата)','text'),('complaint','Жалоба','long')])
    @needs_project
    def new_repair_for(self,row):self._repair_create([('equipment_id','Оборудование',[(row['id'],row['number'])]),('number','№ ремонта (не номер аппарата)','text'),('complaint','Жалоба','long')])
    @needs_project
    def _repair_create(self,fields):
        fields=fields+[('client_id','Заказчик',[(None,'Текущий владелец оборудования')]+[(x['id'],x['name']) for x in self.cache.get('active_clients',[])])]
        d=FieldsDialog('Приёмка оборудования',fields,parent=self)
        d.fields['number'].setPlaceholderText('Автоматически: '+self.cache.get('next_repair_number',''))
        s=self.store;request=uuid4().hex
        def create(v):return s.create_repair(v['equipment_id'],v['number'],v['complaint'],request,client_id=v['client_id'])
        if self.shell_navigation:
            created=[]
            def persist(v):created.append(create(v))
            d.persist_with(self,persist)
            self.embed_form(d)
            d.finished.connect(lambda _:self.open_repair(created[0]) if created else None)
            return d
        if d.exec()==QDialog.DialogCode.Accepted:
            values=d.values()
            self.run(lambda:create(values),self.open_repair)
    @needs_project
    def open_selected(self,key):
        r=self.selection(key)
        if r:self.open_repair(r['repair_id'] if key=='estimates' else r['id'],'Сметы' if key=='estimates' else 'Финансы' if key=='finance' else None)
    def modal(self,dialog):
        self.dialogs.append(dialog)
        if self.worker:dialog.setEnabled(False)
        try:return dialog.exec()
        finally:self.dialogs.remove(dialog);dialog.deleteLater();self.refresh()
    @needs_project
    def import_history(self):
        from .import_wizard import HistoryWizard
        if self.shell_navigation:return self.embed_form(HistoryWizard(self),on_close=self.refresh)
        self.modal(HistoryWizard(self))
    @needs_project
    def organization_profiles(self):
        from .profiles import ProfileDialog
        if self.shell_navigation:return self.embed_form(ProfileDialog(self),on_close=self.refresh)
        self.modal(ProfileDialog(self))
    @needs_project
    def review_docx(self):
        from ...service.docx_extract import export_review_csv
        source,_=QFileDialog.getOpenFileName(self,'Таблицы Word для ручной проверки','','Word (*.docx)')
        if not source:return
        target,_=QFileDialog.getSaveFileName(self,'Новый проверочный CSV','word-review.csv','CSV (*.csv)')
        if target and confirm(self,'Сохранить текст таблиц с координатами источника? Это не импорт ремонтов: связи, колонки и суммы нужно проверить вручную.'):
            self.run(lambda:export_review_csv(source,target),lambda _:self.message.setText('CSV сохранён. Исправьте и сопоставьте колонки перед историческим импортом.'))
    @needs_project
    def open_repair(self,key,section=None,return_to=None):
        if self.shell_navigation:
            for route in self.pages.routes:
                if isinstance(route.widget,RepairPage) and route.widget.key==key:
                    page=route.widget
                    self.pages.return_to(page,lambda:page.tabs.show_section(section) if section else None)
                    return
        self._last_repairs[str(self.store.root)]=key
        s=self.store
        journal_context=self.journal.view_context() if self.tabs.currentWidget() is self.journal and self.current_page is None else None
        def show(snapshot):
            if self.shell_navigation:
                page=RepairPage(self,snapshot)
                context_key=(s.root,key)
                active=section or self._repair_sections.get(context_key)
                if active:page.tabs.show_section(active)
                page.tabs.sectionChanged.connect(lambda _:self._repair_sections.__setitem__(context_key,page.tabs.selected_section()))
                def closed():
                    if journal_context:self.journal.panels.return_to_list(restore=False)
                    self.refresh(journal_context=journal_context,on_complete=return_to)
                return self.push_page(page,page.windowTitle(),
                    back_label='Назад к журналу' if journal_context else 'Назад',
                    before_close=page.request_exit,on_close=closed)
            d=RepairDialog(self,snapshot)
            if section:d.tabs.show_section(section)
            self.dialogs.append(d)
            try:d.exec()
            finally:
                self.dialogs.remove(d);d.deleteLater()
                if journal_context:self.journal.panels.return_to_list(restore=False)
                self.refresh(journal_context=journal_context,on_complete=return_to)
        self.run(lambda:s.snapshot(key),show)
    @needs_project
    def open_file(self,document=False):
        r=self.selection('documents')
        if r:
            s=self.store;self.run(lambda:attachment_path(s,r['id'],True),self.open_local)
    @needs_project
    def export_document(self):
        row=self.selection('documents')
        if not row:return
        path,_=QFileDialog.getSaveFileName(self,'Копия DOCX',Path(row['path']).name,'Word (*.docx)')
        if not path:return
        s=self.store
        self.run(lambda:export_file(s,row['id'],path,True),lambda _:self.message.setText('Копия сохранена: '+path))
    def choose_project(self):
        if self.worker or self._project_busy:return False
        p=QFileDialog.getExistingDirectory(self,'Локальная папка проекта')
        if p:self.open_project(p)
    def new_project(self):
        if self.worker or self._project_busy:return False
        parent=QFileDialog.getExistingDirectory(self,'Папка для отдельного нового проекта')
        if not parent:return
        target=Path(parent)/('DocFlow-New-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:6])
        self.open_project(target)
    @needs_project
    def open_folder(self):
        if self.store:self.open_local(self.store.root)
    def demo(self):
        if self.worker or self._project_busy:return False
        p=default_root().with_name('Service-Synthetic-Demo-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
        if not confirm(self,'Создать отдельный вымышленный проект? Рабочая база не меняется.'):return
        self.run(lambda:seed_demo(p),lambda _:self.open_project(p),'Создаю отдельное синтетическое демо…')
    def backup_directory(self):
        fallback=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        saved=preferences().value('workspace/v2/backup/lastDirectory', fallback)
        path=Path(saved or Path.home()/'Documents')
        return path if path.is_dir() else Path(fallback or Path.home()/'Documents')

    def show_backup_location(self, path):
        self._backup_result=Path(path)
        self.backup_result_folder.setText('Открыт отдельный проект '+self._backup_result.name)
        self.backup_result_folder.setToolTip(str(self._backup_result))
        self.backup_result_panel.show()

    def finish_backup_notice(self):
        self.backup_result_panel.hide()
        self._backup_result=None
        self.tabs.setCurrentIndex(2)

    @needs_project
    def backup(self):
        from .backup_pages import CreateBackupPage
        self.backup_result_panel.hide()
        page=CreateBackupPage(self)
        return self.push_page(page,page.windowTitle())

    def restore(self):
        if self.worker or self._project_busy:return False
        from .backup_pages import RestoreBackupPage
        self.backup_result_panel.hide()
        page=RestoreBackupPage(self)
        return self.push_page(page,page.windowTitle())
    @needs_project
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

from .repair_editor import RepairDialog, RepairPage
