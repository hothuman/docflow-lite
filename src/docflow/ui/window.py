"""Qt Widgets workspace. File loading and preview never execute in the UI thread."""
import copy
import time
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, QUrl, Qt, Signal, Slot, QSize
from PySide6.QtGui import QDesktopServices, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout, QWidget,
)
from .. import __version__
from ..versioning import stage
from ..batch import BatchResult, Prepared, generate, prepare
from ..cli import demo_profile
from ..data import Record, Table, load_table
from ..errors import DocFlowError, GenerationCancelled
from ..profile import Profile
from ..templates import Template
from ..validation import Rule, values_for, validate_mapping
from .diagnostics import record_exception,friendly_error
from .theme import COLORS
from .flow import FlowLayout
from .widgets import DataModel, DataView, RecordModel, card, icon, text
from .mode_switch import ModeSwitch
from .settings import preferences

KINDS = {"Текст":"text", "Число ≥ 0":"number", "Email":"email", "Дата ГГГГ-ММ-ДД":"date"}


class TaskWorker(QThread):
    completed=Signal(object)
    failed=Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent);self.function=function

    def run(self):
        try:self.completed.emit(self.function())
        except (DocFlowError,OSError) as exc:record_exception('Core operation',exc);self.failed.emit(friendly_error(exc))
        except Exception as exc:record_exception('Core task',exc);self.failed.emit(friendly_error(exc))
        finally:self.function=None


class GenerationWorker(QThread):
    advanced=Signal(int,int)
    validated=Signal(object)
    completed=Signal(object)
    failed=Signal(str)
    cancelled=Signal()

    def __init__(self, prepared:Prepared, output:Path, parent=None):
        super().__init__(parent);self.prepared=prepared;self.output=output

    def run(self):
        last=0.0
        def progress(current,total):
            nonlocal last
            now=time.monotonic()
            if current==total or now-last>=.05:
                self.advanced.emit(current,total);last=now
        try:
            issues=[]
            for record in self.prepared.table.records:
                if self.isInterruptionRequested():raise GenerationCancelled()
                issues.extend(values_for(record,self.prepared.profile.mapping,self.prepared.profile.rules)[1])
            self.validated.emit(issues)
            self.completed.emit(generate(self.prepared,self.output,progress,cancelled=self.isInterruptionRequested))
        except GenerationCancelled:self.cancelled.emit()
        except (DocFlowError,OSError) as exc:record_exception('Core operation',exc);self.failed.emit(friendly_error(exc))
        except Exception as exc:record_exception('Core generation',exc);self.failed.emit(friendly_error(exc))


class MainWindow(QMainWindow):
    PAGE_NAMES=('1. Выберите таблицу','2. Добавьте шаблоны Word','3. Проверьте поля и данные','4. Создайте документы','О программе','Обзор мастерской')
    NAV_NAMES=('Документы','Шаблоны Word','Поля и проверка','Создание','О программе','Мастерская')

    def __init__(self,service_root=None):
        super().__init__()
        self._service_root=service_root;self.service_workspace=None;self._full_check=None
        settings=preferences()
        def page_setting(key,maximum):
            try:return max(0,min(maximum,int(settings.value(key,0))))
            except (TypeError,ValueError):return 0
        self._saved_mode=page_setting('workspace/mode',1);self._last_core_page=page_setting('workspace/documents',3);self._last_service_page=page_setting('workspace/workshop',7)
        self.setWindowTitle(f'DocFlow Lite {__version__}')
        self.setWindowIcon(QIcon(str(Path(__file__).with_name('app.ico'))))
        self.resize(1400,860);self.setMinimumSize(560,320)
        self.table=None;self.templates=[];self.worker=None;self.task_worker=None;self.preview_worker=None
        self.last_result=None;self.encoding='auto';self.sheet=None;self._busy=False
        self._mapping_cache={};self._rules_cache={};self._active_paths=set()
        self._preview_revision=0;self._pending_preview=None;self._preview_job=None
        self._preview_timer=QTimer(self);self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._start_preview)
        from .theme import apply_theme
        apply_theme()
        root=QWidget();root.setObjectName('root');self.setCentralWidget(root)
        outer=QHBoxLayout(root);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        self.rail=QFrame();self.rail.setObjectName('rail');self.rail.setFixedWidth(224)
        nav=QVBoxLayout(self.rail);nav.setContentsMargins(14,22,14,18);nav.setSpacing(8)
        self.brand=text('d/ DocFlow','brand');nav.addWidget(self.brand)
        self.version_label=text(f'v{__version__} · {stage(__version__)}','version');nav.addWidget(self.version_label)
        self.mode_picker=ModeSwitch();self.mode_picker.setAccessibleName('Документы или Мастерская')
        self.mode_picker.currentIndexChanged.connect(lambda i:self.navigate(5 if i else getattr(self,'_last_core_page',0)))
        self.nav_caption=text('ДОКУМЕНТЫ','eyebrow');nav.addWidget(self.nav_caption)
        nav.addSpacing(8);self.nav_buttons=[]
        for index,kind in enumerate(('document','templates','fields','check','info','templates')):
            button=QPushButton(self.NAV_NAMES[index]);button.setObjectName('nav')
            button.setCheckable(True);button.setIcon(icon(kind));button.setIconSize(QSize(21,21))
            button.setToolTip(self.NAV_NAMES[index]);button.setAccessibleName(self.NAV_NAMES[index])
            button.clicked.connect(lambda checked=False,i=index:self.navigate(i))
            nav.addWidget(button);self.nav_buttons.append(button)
        self.service_nav=[]
        for i,(label,kind) in enumerate(zip(('Обзор','Оборудование','Ремонты','Клиенты','Финансы','Документы','Сметы','Настройки'),('check','tool','history','people','money','document','document','folder'))):
            button=QPushButton(label);button.setObjectName('nav');button.setCheckable(True);button.setIcon(icon(kind));button.setToolTip(label);button.setAccessibleName('Service: '+label)
            button.clicked.connect(lambda checked=False,index=i:self._navigate_service(index))
            button.hide();self.service_nav.append(button)
        for i in (0,2,1,3,5):nav.addWidget(self.service_nav[i])
        self.account_caption=text('УЧЁТ И НАСТРОЙКИ','eyebrow');self.account_caption.hide();nav.addWidget(self.account_caption)
        for i in (4,6,7):nav.addWidget(self.service_nav[i])
        ordered=[self.service_nav[i] for i in (0,2,1,3,5,4,6,7)]
        for a,b in zip(ordered,ordered[1:]):QWidget.setTabOrder(a,b)
        nav.addStretch()
        self.local_note=text('Локальная обработка\nБез сети и телеметрии','muted');nav.addWidget(self.local_note)
        outer.addWidget(self.rail)
        self.work=QWidget();self.work.setObjectName('work');outer.addWidget(self.work,1)
        work=QVBoxLayout(self.work);work.setContentsMargins(22,20,22,12);work.setSpacing(10)
        mode_row=QHBoxLayout();mode_row.addWidget(self.mode_picker,1);self.about_button=self.button('О программе',lambda:self.navigate(4));mode_row.addWidget(self.about_button);work.addLayout(mode_row)
        self.mode_help=text('Документы: таблица → Word. Мастерская: клиенты, аппараты и ремонты.','muted');work.addWidget(self.mode_help)
        header=QHBoxLayout();titles=QVBoxLayout();titles.setSpacing(5)
        self.breadcrumb=text('CORE / LITE · ДОКУМЕНТЫ','eyebrow');titles.addWidget(self.breadcrumb)
        self.title=text(self.PAGE_NAMES[0],'title');titles.addWidget(self.title)
        self.subtitle=text('Таблица → ваши шаблоны Word → комплект документов','muted');titles.addWidget(self.subtitle)
        header.addLayout(titles,1)
        self.demo_btn=self.button('Открыть демопример',self.load_demo);self.demo_btn.setToolTip('Открыть встроенные вымышленные данные и два DOCX-шаблона')
        self.folder_btn=self.button('Открыть папку',self.open_result,'folder');self.folder_btn.setEnabled(False)
        self.folder_btn.hide();work.addLayout(header)
        self.operation_notice=text('','status');self.operation_notice.setAccessibleName('Сообщение о действии');self.operation_notice.setMaximumHeight(64);self.operation_notice.hide();work.addWidget(self.operation_notice)
        self.core_route=QFrame();self.core_route.setObjectName('routeBar');route=FlowLayout(self.core_route);self.route_buttons=[]
        for i,label in enumerate(('1  Таблица','2  Шаблоны','3  Проверка','4  Создание')):
            b=self.button(label,lambda checked=False,index=i:self.navigate(index));b.setObjectName('journey');b.setCheckable(True);route.addWidget(b);self.route_buttons.append(b)
        work.addWidget(self.core_route);self.core_state=text('','muted');work.addWidget(self.core_state)
        self.pages=QStackedWidget();work.addWidget(self.pages,1)
        self._build_create();self._build_templates();self._build_mapping();self._build_result();self._build_about();self.pages.addWidget(QWidget())
        self.status=text('Откройте демопример или выберите свои файлы','status');self.status.setAccessibleName('Текущий статус')
        self.footer_layout=QHBoxLayout();self.footer_layout.setSpacing(12);self.footer_layout.addWidget(self.status,1)
        self.cancel_btn=self.button('Отменить генерацию',self.cancel_generation)
        self.cancel_btn.setToolTip('Дождаться текущего документа и удалить незавершённый новый пакет')
        self.cancel_btn.hide();self.footer_layout.addWidget(self.cancel_btn)
        self.core_next=self.button('Выбрать таблицу',self.core_next_step,primary=True);self.footer_layout.addWidget(self.core_next)
        self._pinned_action=None;work.addLayout(self.footer_layout)
        self.navigate(5 if self._saved_mode else self._last_core_page);self._responsive();self.update_readiness()
        from PySide6.QtGui import QShortcut,QKeySequence
        self.profile_shortcut=QShortcut(QKeySequence.StandardKey.Save,self);self.profile_shortcut.activated.connect(lambda:self.save_profile(background=True) if self.pages.currentIndex()<4 and self.table and not self._busy else None)

    def button(self,title,callback,kind=None,primary=False):
        button=QPushButton(title)
        if kind:button.setIcon(icon(kind,COLORS['accentText'] if primary else COLORS['muted']))
        if primary:button.setObjectName('primary')
        button.clicked.connect(callback);button.setAccessibleName(title)
        return button

    def page(self):
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        page=QWidget();page.setObjectName('page');scroll.setWidget(page)
        self.pages.addWidget(scroll);layout=QVBoxLayout(page);layout.setContentsMargins(0,0,2,0);layout.setSpacing(14)
        return page,layout

    def _build_create(self):
        from .core_workflow import build_create
        build_create(self)

    def _build_templates(self):
        page,layout=self.page();box,body=card('Word-шаблоны','Отметьте шаблоны для текущего комплекта. Поддерживаются переменные {{поле}} в тексте, таблицах и колонтитулах.')
        layout.addWidget(box);body.addWidget(self.template_summary);self.template_list=QListWidget();self.template_list.setMinimumHeight(240)
        self.template_list.setTextElideMode(Qt.TextElideMode.ElideMiddle);self.template_list.setAccessibleName('Шаблоны, выбранные для генерации')
        self.template_list.itemChanged.connect(self._template_toggled);body.addWidget(self.template_list,1)
        row=FlowLayout();self.template_add_btn=self.button('Добавить шаблоны',self.select_templates,'plus');row.addWidget(self.template_add_btn)
        self.add_btn=self.template_add_btn
        self.remove_btn=self.button('Убрать из списка',self.remove_template);row.addWidget(self.remove_btn);body.addLayout(row)
        body.addWidget(text('Удаление из списка не удаляет исходный файл. PDF, макросы и сложные выражения шаблонов не поддерживаются.','muted'));layout.addStretch()

    def _build_mapping(self):
        page,layout=self.page();box,body=card('Сопоставление полей','Выберите столбец для каждой переменной. Имя переменной и заголовок таблицы могут различаться.')
        layout.addWidget(box)
        self.mapping_table=QTableWidget(0,4);self.mapping_table.setMinimumHeight(260)
        self.mapping_table.setHorizontalHeaderLabels(['Переменная','Столбец таблицы','Проверка','Обязательно'])
        self.mapping_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.mapping_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        for col in (2,3):self.mapping_table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.ResizeToContents)
        self.mapping_table.horizontalHeader().setMinimumSectionSize(100);self.mapping_table.verticalHeader().hide();body.addWidget(self.mapping_table,1)
        self.mapping_feedback=text('Сначала загрузите файлы','muted');body.addWidget(self.mapping_feedback)
        self.validation_report=QTextBrowser();self.validation_report.setOpenExternalLinks(False);self.validation_report.setMinimumHeight(120);self.validation_report.setAccessibleName('Результаты проверки всех строк');self.validation_report.hide();body.addWidget(self.validation_report)
        row=FlowLayout();self.open_profile_btn=self.button('Открыть сохранённую настройку',self.open_profile,'folder')
        self.save_profile_btn=self.button('Сохранить настройку',lambda:self.save_profile(background=True))
        row.addWidget(self.open_profile_btn);row.addWidget(self.save_profile_btn);body.addLayout(row)
        formatbox,settings=card('Чтение таблицы','CSV: auto определяет UTF-8 или Windows-1251. Для XLSX можно указать имя листа; пустое поле означает активный лист.')
        layout.addWidget(formatbox)
        self.encoding_selector=QComboBox();self.encoding_selector.addItems(['auto','utf-8-sig','cp1251']);self.encoding_selector.setAccessibleName('Кодировка CSV')
        self.sheet_input=QLineEdit();self.sheet_input.setPlaceholderText('Имя листа XLSX (необязательно)');self.sheet_input.setAccessibleName('Лист XLSX')
        settings.addWidget(self.encoding_selector);settings.addWidget(self.sheet_input)
        self.reload_btn=self.button('Перечитать выбранную таблицу',self.reload_data);settings.addWidget(self.reload_btn)
        layout.addStretch()

    def _build_result(self):
        from .core_workflow import build_result
        build_result(self)

    def _build_about(self):
        page,layout=self.page();box,body=card('DocFlow Lite',f'Версия {__version__} · Core + Service · {stage(__version__)}')
        layout.addWidget(box)
        body.addWidget(text('Локальная генерация Word-документов из XLSX/CSV. Данные и шаблоны не отправляются на сервер.'))
        body.addWidget(text('До 5 000 записей, 100 столбцов и 20 DOCX-шаблонов за запуск. Исходники не перезаписываются.'))
        body.addWidget(text('Поддерживаются простые переменные {{поле}}. В Core нет PDF-экспорта, циклов и истории. Service отдельно ведёт ремонты и поддерживает ограниченное повторение строк. Текстовый предпросмотр не заменяет проверку оформления в Word/LibreOffice.','muted'))
        body.addWidget(text('Предварительная версия Core + Service. Проверяйте готовые документы в своей версии Word/LibreOffice.','muted'))
        body.addWidget(text('© 2026 Гапоненко Ростислав Дмитриевич. Бесплатное личное и деловое использование по условиям поставки.'))
        body.addWidget(text('Используются Qt / PySide6 / Shiboken под LGPLv3 и другие сторонние библиотеки. Их лицензии сохраняются; совместимая замена LGPL-библиотек допускается.','muted'))
        from pathlib import Path
        license_path=Path(__file__).resolve().parents[1]/'resources'/'LICENSE.txt'
        license_button=QPushButton('Условия использования')
        license_button.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(license_path))))
        body.addWidget(license_button)
        layout.addStretch()

    def navigate(self,index,*,internal=False):
        previous=self.pages.currentIndex()
        if not internal and index!=previous:
            busy=self._busy or (self.service_workspace and self.service_workspace.worker)
            dirty=self.service_workspace and any(getattr(d,'dirty',False) for d in self.service_workspace.dialogs)
            if busy or dirty:
                message='Дождитесь завершения операции перед переходом.' if busy else 'Сначала сохраните или закройте открытую форму ремонта.'
                self.status.setText(message);self.mode_picker.setToolTip(message)
                self.operation_notice.setText(message);self.operation_notice.show()
                self.mode_picker.blockSignals(True);self.mode_picker.setCurrentIndex(1 if previous==5 else 0);self.mode_picker.blockSignals(False);return
        if index==5 and self.service_workspace is None:
            from .service.workspace import ServiceWorkspace
            self.service_workspace=ServiceWorkspace(self,self._service_root,shell_navigation=True)
            self.service_workspace.tabs.currentChanged.connect(self._service_section_changed)
            old=self.pages.widget(5);self.pages.removeWidget(old);old.deleteLater();self.pages.addWidget(self.service_workspace)
            self.service_workspace.tabs.setCurrentIndex(self._last_service_page)
        if (index==5)!=(previous==5):self._clear_notice()
        self.pages.setCurrentIndex(index);self.title.setText(self.PAGE_NAMES[index])
        if index<4:self._last_core_page=index
        self.mode_picker.blockSignals(True);self.mode_picker.setCurrentIndex(1 if index==5 else 0);self.mode_picker.blockSignals(False)
        self.nav_caption.setText('МАСТЕРСКАЯ' if index==5 else 'ДОКУМЕНТЫ')
        self.breadcrumb.setText('МАСТЕРСКАЯ' if index==5 else 'ДОКУМЕНТЫ')
        for i,b in enumerate(self.nav_buttons):b.setVisible(index!=5 and i in (0,4))
        for b in self.service_nav:b.setVisible(index==5)
        if index==5:self._service_section_changed(self.service_workspace.tabs.currentIndex())
        self.demo_btn.setVisible(index!=5);self.folder_btn.hide()
        self.generate_btn.setVisible(index==3 and self.cancel_btn.isHidden())
        if index==5:
            if not hasattr(self,'_core_status'):self._core_status=self.status.text()
            self.status.setText('Найдите аппарат или начните новый ремонт')
        elif hasattr(self,'_core_status'):
            self.status.setText(self._core_status);del self._core_status
        self.subtitle.setText(self._service_subtitle(self.service_workspace.tabs.currentIndex()) if index==5 else 'Из таблицы — в готовый комплект документов')
        for i,button in enumerate(self.nav_buttons):button.setChecked(i==index or i==0 and index<4)
        self._responsive();self.update_readiness();self.remember_location()

    def remember_location(self):
        settings=preferences();settings.setValue('workspace/mode',1 if self.pages.currentIndex()==5 else 0);settings.setValue('workspace/documents',self._last_core_page);settings.setValue('workspace/workshop',self._last_service_page);settings.sync()

    def _navigate_service(self,index):
        self.service_workspace.tabs.setCurrentIndex(index)
        self._service_section_changed(index)

    def _service_subtitle(self,index):
        return ('Всё, что нужно для работы мастерской','Каждый аппарат и вся история обращений','Текущие обращения и этапы выполнения','Контакты и история работы с заказчиками','Стоимость, учтённые оплаты и остатки','Созданные формы и версии документов','Предварительные и окончательные расчёты','Проект, импорт и сохранность данных')[index]

    def _service_section_changed(self,index):
        self._last_service_page=index
        for i,b in enumerate(self.service_nav):b.setChecked(i==index)
        if self.pages.currentIndex()==5:
            self.title.setText(('Обзор мастерской','Оборудование','Журнал ремонтов','Клиенты','Финансы','Документы','Сметы','Настройки мастерской')[index])
            self.subtitle.setText(self._service_subtitle(index))
            self.remember_location()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'core_route'):self._responsive()

    def _responsive(self):
        service=self.pages.currentIndex()==5
        compact=self.width()<760 or self.height()<600
        self.rail.setVisible(not compact);self.rail.setFixedWidth(204)
        self.mode_help.setVisible(self.height()>=600)
        self.version_label.setVisible(self.height()>=650);self.local_note.setVisible(self.height()>=700)
        self.breadcrumb.hide();self.subtitle.setVisible(self.height()>=600)
        self.work.layout().setContentsMargins(12 if compact else 22,10,12 if compact else 22,10)
        if self.service_workspace:
            self.service_workspace.location.setVisible(True)
            self.service_workspace.section_picker.setVisible(service and compact)
        self.account_caption.setVisible(service and self.height()>=600)
        self.nav_caption.setVisible(self.height()>=600)
        self.core_route.setVisible(self.pages.currentIndex()<4)
        self.core_state.setVisible(self.pages.currentIndex()<4 and self.height()>=500)
        self.status.setVisible(not service and self.height()>=500)
        self.about_button.setVisible(compact)
        if hasattr(self,'core_next'):
            if self._pinned_action is None:self.footer_layout.addWidget(self.generate_btn);self._pinned_action=True

    def active_templates(self):return [t for t in self.templates if t.path in self._active_paths]

    def error(self,message):
        self.status.setText('Ошибка: '+str(message));self.report_text.setPlainText(str(message));self.result_report.setPlainText(str(message))
        self.operation_notice.setText('Ошибка: '+str(message));self.operation_notice.setToolTip(str(message));self.operation_notice.show()
        self.validation_report.setPlainText(str(message));self.validation_report.show()
        self.tabs.setCurrentIndex(2)
    def _clear_notice(self):
        self.operation_notice.hide();self.operation_notice.clear();self.operation_notice.setToolTip('')

    def _task(self,function,success,message):
        if self._busy:return
        self._task_success=success;self.set_busy(True);self.status.setText(message)
        self.operation_notice.setText(message);self.operation_notice.show()
        self.task_worker=TaskWorker(function,self)
        self.task_worker.completed.connect(self._task_result);self.task_worker.failed.connect(self.error)
        self.task_worker.finished.connect(self._task_finished);self.task_worker.start()

    @Slot(object)
    def _task_result(self,value):
        try:self._task_success(value)
        except (DocFlowError,OSError) as exc:self.error(exc)

    @Slot()
    def _task_finished(self):
        self.task_worker.deleteLater();self.task_worker=None;self._task_success=None
        self.set_busy(False)
        if not self.status.text().startswith('Ошибка:'):self.operation_notice.hide()

    def load_demo(self):
        self._task(lambda:prepare(Profile.load(demo_profile())),self._install_prepared,'Загружаю встроенный демопример…')

    def apply_profile(self,profile):
        """Synchronous installation API for tests/tools; interactive actions use _task."""
        try:self._install_prepared(prepare(profile))
        except (DocFlowError,OSError) as exc:self.error(exc)

    def _install_prepared(self,prepared):
        self.table=prepared.table;self.templates=list(prepared.templates);self._active_paths={t.path for t in self.templates}
        self.encoding=prepared.profile.encoding;self.sheet=prepared.profile.sheet
        self.encoding_selector.setCurrentText(self.encoding);self.sheet_input.setText(self.sheet or '')
        self._mapping_cache={};self._rules_cache={}
        self.refresh(prepared.profile.mapping,prepared.profile.rules,prepared.profile.name_column)
        self.status.setText('Файлы загружены. Проверьте данные и предпросмотр перед генерацией')

    def select_data(self):
        if self._busy:return
        path,_=QFileDialog.getOpenFileName(self,'Открыть таблицу','','Таблицы (*.xlsx *.csv)')
        if path:self._load_data(path)

    def reload_data(self):
        if self.table:self._load_data(self.table.source)
        else:self.error('Сначала выберите таблицу')

    def _load_data(self,path):
        encoding=self.encoding_selector.currentText();sheet=self.sheet_input.text().strip() or None
        def install(table):
            mapping,rules=self.mapping();self.table=table;self.encoding=encoding;self.sheet=sheet
            self.refresh(mapping,rules);self.status.setText(f'Таблица загружена: {len(table.records)} записей')
        self._task(lambda:load_table(path,encoding=encoding,sheet=sheet),install,'Читаю и проверяю таблицу…')

    def select_templates(self):
        if self._busy:return
        paths,_=QFileDialog.getOpenFileNames(self,'DOCX с переменными {{поле}}','','Word (*.docx)')
        if not paths:return
        if len(set([t.path for t in self.templates]+[Path(p).resolve() for p in paths]))>20:
            self.error('Не более 20 шаблонов');return
        def install(added):
            mapping,rules=self.mapping()
            self.templates=list({t.path:t for t in self.templates+added}.values())
            self._active_paths.update(t.path for t in added);self.refresh(mapping,rules)
            self.status.setText(f'Загружено шаблонов: {len(self.templates)}')
        self._task(lambda:[Template.load(path) for path in paths],install,'Проверяю шаблоны Word…')

    def remove_template(self):
        if self._busy:return
        index=self.template_list.currentRow()
        if index>=0:
            mapping,rules=self.mapping();self._active_paths.discard(self.templates[index].path)
            del self.templates[index];self.refresh(mapping,rules)

    def _template_toggled(self,item):
        if self._busy:return
        path=Path(item.data(Qt.ItemDataRole.UserRole))
        if item.checkState()==Qt.CheckState.Checked:self._active_paths.add(path)
        else:self._active_paths.discard(path)
        mapping,rules=self.mapping();self.refresh(mapping,rules)

    def mapping(self):
        mapping,rules={},{}
        for row in range(self.mapping_table.rowCount()):
            field=self.mapping_table.item(row,0).text();column=self.mapping_table.cellWidget(row,1).currentText()
            if column:
                mapping[field]=column;rules[field]=Rule(self.mapping_table.cellWidget(row,3).isChecked(),self.mapping_table.cellWidget(row,2).currentData())
        return mapping,rules

    def refresh(self,saved=None,rules=None,name_column=None):
        saved,rules=saved or {},rules or {}
        self._mapping_cache.update(saved);self._rules_cache.update(rules)
        name_column=self.name_selector.currentText() if name_column is None else name_column
        previous_row=self.row_selector.currentIndex();previous_template=self.template_selector.currentText()
        selected=self.template_list.currentItem()
        selected_path=selected.data(Qt.ItemDataRole.UserRole) if selected else None
        for widget in (self.row_selector,self.template_selector,self.template_list):widget.blockSignals(True)
        self.template_list.clear();self.template_selector.clear();self.name_selector.clear()
        active=self.active_templates()
        for template in self.templates:
            item=QListWidgetItem(icon('document',COLORS['accent']),template.path.name+'\n'+f'{len(template.raw)/1024:.1f} КБ · {len(template.fields)} полей · {template.path.parent}')
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.ItemDataRole.UserRole,str(template.path));item.setToolTip(str(template.path)+'\nПоля: '+', '.join(sorted(template.fields)))
            item.setCheckState(Qt.CheckState.Checked if template.path in self._active_paths else Qt.CheckState.Unchecked);self.template_list.addItem(item)
            if str(template.path)==selected_path:self.template_list.setCurrentItem(item)
        if self.template_list.currentRow()<0 and self.templates:self.template_list.setCurrentRow(0)
        self.template_selector.addItems([t.path.name for t in active])
        if previous_template in [t.path.name for t in active]:self.template_selector.setCurrentText(previous_template)
        fields=sorted(set().union(*(t.fields for t in active)));headers=self.table.headers if self.table else ()
        self.mapping_table.setRowCount(0);self.mapping_table.setRowCount(len(fields))
        for row,field in enumerate(fields):
            item=QTableWidgetItem(field);item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);item.setToolTip('{{'+field+'}}');self.mapping_table.setItem(row,0,item)
            column=QComboBox();column.addItem('');column.addItems(list(headers));column.setAccessibleName('Столбец для '+field)
            candidate=self._mapping_cache.get(field,field if field in headers else '')
            column.setCurrentText(candidate if candidate in headers else '')
            kind=QComboBox();kind.setAccessibleName('Правило для '+field)
            for title,value in KINDS.items():kind.addItem(title,value)
            rule=self._rules_cache.get(field,Rule());kind.setCurrentIndex(kind.findData(rule.kind))
            required=QCheckBox();required.setAccessibleName('Обязательное поле '+field);required.setChecked(rule.required)
            for col,widget in enumerate((column,kind,required),1):self.mapping_table.setCellWidget(row,col,widget)
            self.mapping_table.setRowHeight(row,46)
            column.currentTextChanged.connect(self.update_preview);kind.currentIndexChanged.connect(self.update_preview);required.stateChanged.connect(self.update_preview)
        self.data_model.set_table(self.table);self.record_model.set_table(self.table)
        self.name_selector.addItem('');self.name_selector.addItems(list(headers))
        if name_column in headers:self.name_selector.setCurrentText(name_column)
        if self.table:
            self.data_path.setText(str(self.table.source));self.data_path.setToolTip(str(self.table.source))
            self.row_selector.setCurrentIndex(max(0,min(previous_row,len(self.table.records)-1)))
            self.stats.setText(f'{len(self.table.records)} записей · {len(headers)} столбцов · все строки доступны в таблице')
        else:self.data_path.clear();self.stats.setText('Данные ещё не загружены')
        self.template_summary.setText(f'Выбрано {len(active)} из {len(self.templates)} шаблонов'+ ('\n'+'\n'.join(t.path.name for t in active[:3]) if active else ''))
        self.template_summary.setToolTip('\n'.join(str(t.path) for t in active))
        for widget in (self.row_selector,self.template_selector,self.template_list):widget.blockSignals(False)
        self.update_preview()

    def profile(self):
        active=self.active_templates()
        if not self.table or not active:raise DocFlowError('Сначала выберите таблицу и DOCX-шаблоны')
        mapping,rules=self.mapping()
        return Profile(self.table.source,[t.path for t in active],mapping,rules,self.name_selector.currentText(),self.encoding,self.sheet)

    def snapshot(self):
        profile=copy.deepcopy(self.profile());active=self.active_templates()
        fields=set().union(*(t.fields for t in active));validate_mapping(self.table,fields,profile.mapping,profile.rules)
        if profile.name_column and profile.name_column not in self.table.headers:raise DocFlowError('Не найден столбец для имени папки')
        # Values are validated immutable strings. Copy only mutable row dictionaries;
        # sharing paths/header tuples/strings is safe and avoids generic deepcopy overhead.
        table=Table(self.table.source,self.table.headers,
                    tuple(Record(r.row_number,r.values.copy()) for r in self.table.records))
        return Prepared(profile,table,tuple(active))

    def update_readiness(self):
        valid=False
        try:
            profile=self.profile();validate_mapping(self.table,set().union(*(t.fields for t in self.active_templates())),profile.mapping,profile.rules)
            valid=True;message='Готово к генерации'
        except DocFlowError as exc:message=str(exc)
        self.readiness.setText(message);self.readiness.setObjectName('ready' if valid else 'muted')
        self.readiness.style().unpolish(self.readiness);self.readiness.style().polish(self.readiness)
        self.mapping_feedback.setText('Поля связаны; все строки ещё не проверены' if valid else message)
        self.ready_details.setText(f'Таблица: {len(self.table.records) if self.table else 0} записей\nШаблоны: {len(self.active_templates())} выбрано\nФормат: DOCX\nОтчёты: JSON и CSV')
        self.generate_btn.setEnabled(valid and not self._busy)
        states=[bool(self.table),bool(self.active_templates()),valid,bool(self.last_result)]
        for b,complete in zip(self.route_buttons,states):
            b.setProperty('complete',complete);b.setEnabled(not self._busy);b.style().unpolish(b);b.style().polish(b)
        next_step='Выберите таблицу XLSX или CSV.' if not self.table else 'Добавьте шаблон DOCX.' if not self.active_templates() else 'Откройте «Поля и проверки» и сопоставьте переменные.' if not valid else 'Проверьте записи, затем нажмите «Сгенерировать документы».'
        self.readiness.setToolTip(next_step)
        self.ready_details.setText(next_step+'\n'+self.ready_details.text())
        for row in range(self.mapping_table.rowCount()):
            missing=not self.mapping_table.cellWidget(row,1).currentText()
            self.mapping_table.item(row,0).setForeground(QColor(COLORS['error'] if missing else COLORS['text']))
        if hasattr(self,'core_next'):
            from .core_workflow import readiness
            readiness(self,valid,message)

    def core_next_step(self):
        from .core_workflow import next_step
        next_step(self)

    def validation_signature(self):
        try:
            mapping,rules=self.mapping()
            return (id(self.table),tuple(id(t) for t in self.active_templates()),tuple(sorted(mapping.items())),tuple(sorted((k,v.required,v.kind) for k,v in rules.items())))
        except (AttributeError,TypeError):return None

    def _table_row_changed(self,current,previous):
        if current.isValid():self.row_selector.setCurrentIndex(current.row())

    def update_preview(self,*_):
        # Remember explicit blank mappings as well as configured fields when templates toggle.
        for row in range(self.mapping_table.rowCount()):
            field=self.mapping_table.item(row,0).text()
            self._mapping_cache[field]=self.mapping_table.cellWidget(row,1).currentText()
            self._rules_cache[field]=Rule(self.mapping_table.cellWidget(row,3).isChecked(),self.mapping_table.cellWidget(row,2).currentData())
        self._preview_revision+=1;revision=self._preview_revision
        self._preview_timer.stop();self._pending_preview=None;self.update_readiness()
        if not self.table or not self.active_templates() or self.row_selector.currentIndex()<0:
            self.preview_text.setPlainText('Загрузите таблицу и выберите шаблон для текстового предпросмотра');return
        try:
            profile=self.profile();active=self.active_templates()
            validate_mapping(self.table,set().union(*(t.fields for t in active)),profile.mapping,profile.rules)
            record=self.table.records[self.row_selector.currentIndex()];values,issues=values_for(record,profile.mapping,profile.rules)
            if issues:
                self.preview_text.setPlainText('Запись будет пропущена:\n\n'+'\n'.join(f'{x.field}: {x.message}' for x in issues));return
            template=active[max(0,self.template_selector.currentIndex())]
            self._pending_preview=(revision,template,values);self.preview_text.setPlainText('Подготавливаю текстовый предпросмотр…');self._preview_timer.start(60)
        except (DocFlowError,OSError) as exc:self.preview_text.setPlainText(str(exc))

    def _start_preview(self):
        if self.preview_worker and self.preview_worker.isRunning():return
        if not self._pending_preview:return
        revision,template,values=self._pending_preview;self._pending_preview=None
        def render():
            try:return revision,template.preview(values)
            except (DocFlowError,OSError) as exc:return revision,str(exc)
            except Exception:return revision,'Не удалось создать текстовый предпросмотр'
        self.preview_worker=TaskWorker(render,self);self.preview_worker.completed.connect(self._preview_result)
        self.preview_worker.finished.connect(self._preview_finished);self.preview_worker.start()

    @Slot(object)
    def _preview_result(self,result):
        revision,message=result
        if revision==self._preview_revision:self.preview_text.setPlainText(message)

    @Slot()
    def _preview_finished(self):
        self.preview_worker.deleteLater();self.preview_worker=None
        if self._pending_preview:self._preview_timer.start(0)

    def check_all(self):
        if self._busy:return
        try:
            prepared=self.snapshot()
            def validate():return [x for record in prepared.table.records for x in values_for(record,prepared.profile.mapping,prepared.profile.rules)[1]]
            def show(issues):
                rejected=len({x.row for x in issues});total=len(prepared.table.records)
                self._full_check=(self.validation_signature(),rejected,total)
                self.status.setText(f'Проверено: {total} записей. Без ошибок: {total-rejected}. С ошибками: {rejected}')
                message='\n'.join(f'Строка {x.row} · {x.field}: {x.message}' for x in issues) if issues else 'Ошибок данных не обнаружено'
                self.report_text.setPlainText(message);self.result_report.setPlainText(message);self.validation_report.setPlainText(message);self.validation_report.show();self.tabs.setCurrentIndex(2)
            self._task(validate,show,'Проверяю все записи…')
        except (DocFlowError,OSError) as exc:self.error(exc)

    def open_profile(self):
        if self._busy:return
        path,_=QFileDialog.getOpenFileName(self,'Открыть настройки','','Настройки (*.json)')
        if path:self._task(lambda:prepare(Profile.load(path)),self._install_prepared,'Читаю JSON-профиль и файлы…')

    def save_profile(self,background=False):
        if self._busy:return
        try:
            profile=self.snapshot().profile
            path,_=QFileDialog.getSaveFileName(self,'Сохранить настройки','docflow-profile.json','Настройки (*.json)')
            if path:
                if background:
                    self._task(lambda:profile.save(path),lambda _:self.status.setText('JSON-профиль сохранён'),'Сохраняю JSON-профиль…')
                else:
                    # Keep the synchronous automation API; interactive buttons use a worker.
                    profile.save(path);self.status.setText('JSON-профиль сохранён')
        except (DocFlowError,OSError) as exc:self.error(exc)

    def select_output(self):
        if self._busy:return
        path=QFileDialog.getExistingDirectory(self,'Папка результата',self.output_path.text())
        if path:self.output_path.setText(path);self.output_path.setToolTip(path)

    def start_generation(self):
        if self._busy or (self.worker and self.worker.isRunning()):return
        try:self._begin_generation(self.snapshot())
        except (DocFlowError,OSError) as exc:self.error(exc)

    def _preflight_results(self,issues,signature,total):
        rejected=len({x.row for x in issues});self._full_check=(signature,rejected,total)
        message='\n'.join(f'Строка {x.row} · {x.field}: {x.message}' for x in issues) or 'Все строки проверены. Ошибок не обнаружено.'
        self.validation_report.setPlainText(message);self.validation_report.show()
        self.progress_label.setText(f'Проверено {total} строк. Будут пропущены строки с ошибками: {rejected}.')
        self.update_readiness()

    def _begin_generation(self,prepared):
        try:
            if not self.output_path.text().strip():raise DocFlowError('Выберите папку результата')
            self.last_result=None
            for control in (self.folder_btn,self.result_open_btn,self.report_btn):control.setEnabled(False)
            self.result_summary.setText('Новый запуск: документы ещё не созданы')
            self.result_path.setText('Предыдущие файлы остаются в своих папках. Здесь появится результат нового запуска.')
            self.result_report.clear()
            self.set_busy(True);self.progress.setValue(0);self.progress_label.setText('Подготовка пакета…')
            self.status.setText('Создаю документы из загруженного снимка данных…')
            if self.worker:self.worker.deleteLater()
            self.worker=GenerationWorker(prepared,Path(self.output_path.text()),self)
            self.worker.validated.connect(lambda issues:self._preflight_results(issues,self.validation_signature(),len(prepared.table.records)))
            self.worker.advanced.connect(self._progress);self.worker.completed.connect(self.on_result)
            self.worker.failed.connect(self.error);self.worker.cancelled.connect(self._generation_cancelled)
            self.worker.finished.connect(self._generation_finished)
            self.generate_btn.hide();self.cancel_btn.setEnabled(True);self.cancel_btn.show();self.worker.start()
        except (DocFlowError,OSError) as exc:self.error(exc)

    @Slot()
    def cancel_generation(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption();self.cancel_btn.setEnabled(False)
            self.progress_label.setText('Отмена после текущего документа…')
            self.status.setText('Отменяю генерацию и очищаю временный пакет…')

    @Slot()
    def _generation_cancelled(self):
        self.progress.setValue(0)
        self.progress_label.setText('Генерация отменена')
        self.status.setText('Генерация отменена. Измените настройки или запустите снова.')
        self.result_summary.setText('Генерация отменена; новый пакет не сохранён')
        self.result_path.setText('Ранее созданные результаты остаются в своих папках.')

    @Slot(int,int)
    def _progress(self,current,total):
        if self.worker and self.worker.isInterruptionRequested():return
        self.progress.setValue(round(current/total*100) if total else 0)
        self.progress_label.setText(f'Обработано записей: {current} / {total}')
        self.status.setText(f'Генерация: {current} / {total} записей')

    @Slot()
    def _generation_finished(self):
        self.worker.prepared=None
        self.cancel_btn.hide();self.generate_btn.setVisible(self.pages.currentIndex()==3)
        self.set_busy(False)

    def set_busy(self,busy):
        self._busy=busy
        self.mode_picker.setEnabled(not busy);self.core_next.setEnabled(not busy)
        for widget in (self.demo_btn,self.load_btn,self.add_btn,self.remove_btn,self.open_profile_btn,self.save_profile_btn,
                       self.mapping_table,self.name_selector,self.check_btn,self.output_btn,self.output_path,self.template_list,
                       self.reload_btn,self.encoding_selector,self.sheet_input,self.open_after,self.template_add_btn):widget.setEnabled(not busy)
        self.update_readiness()

    @Slot(object)
    def on_result(self,result:BatchResult):
        self._clear_notice()
        self.last_result=result;self.folder_btn.setEnabled(True);self.result_open_btn.setEnabled(True);self.report_btn.setEnabled(True)
        self.progress.setValue(100);self.progress_label.setText(f'Завершено: {result.total} / {result.total} записей')
        summary=f'Готово: {result.documents} DOCX · {result.accepted} записей обработано · {result.rejected} пропущено'
        self.status.setText(summary);self.result_summary.setText(summary)
        self.result_path.setText(str(result.directory));self.result_path.setToolTip(str(result.directory))
        message=f'Всего записей: {result.total}\nСоздано DOCX: {result.documents}\nОбработано: {result.accepted}\nПропущено: {result.rejected}\n\n'+'\n'.join(f'Строка {x.row} · {x.field}: {x.message}' for x in result.issues)+'\n\nПолные отчёты: report.json и report.csv'
        self.report_text.setPlainText(message);self.result_report.setPlainText(message);self.tabs.setCurrentIndex(2);self.navigate(3,internal=True)
        # Bring the completed package and its folder action into view, rather
        # than leaving the user above the fold at the generation settings.
        QTimer.singleShot(0,self,lambda:self.pages.widget(3).ensureWidgetVisible(self.result_open_btn,12,12))
        if self.open_after.isChecked():self.open_result()

    def open_result(self):
        if self.last_result and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_result.directory))):self.error('Система не смогла открыть папку. Скопируйте путь из раздела «Результат»')

    def open_report(self):
        if self.last_result and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_result.directory/'report.json'))):self.error('Система не смогла открыть отчёт. Он сохранён в папке результата')

    def closeEvent(self,event):
        if (self.service_workspace and self.service_workspace.worker) or self._busy or any(w and w.isRunning() for w in (self.worker,self.task_worker,self.preview_worker)):
            QMessageBox.information(self,'Обработка продолжается','Дождитесь завершения текущей операции перед закрытием')
            event.ignore()
        else:
            if self.service_workspace and self.service_workspace.project_lock:self.service_workspace.project_lock.unlock()
            self._preview_timer.stop();event.accept()
