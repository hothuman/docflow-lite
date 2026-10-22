"""Qt Widgets workspace. File loading and preview never execute in the UI thread."""
import copy
import time
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, QUrl, Qt, Signal, Slot, QSize
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout, QWidget,
)
from .. import __version__
from ..batch import BatchResult, Prepared, generate, prepare
from ..cli import demo_profile
from ..data import Record, Table, load_table
from ..errors import DocFlowError
from ..profile import Profile
from ..templates import Template
from ..validation import Rule, values_for, validate_mapping
from .widgets import DataModel, DataView, RecordModel, card, icon, text

KINDS = {"Текст":"text", "Число ≥ 0":"number", "Email":"email", "Дата ГГГГ-ММ-ДД":"date"}


class TaskWorker(QThread):
    completed=Signal(object)
    failed=Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent);self.function=function

    def run(self):
        try:self.completed.emit(self.function())
        except (DocFlowError,OSError) as exc:self.failed.emit(str(exc))
        except Exception:self.failed.emit('Не удалось обработать файл. Исходные файлы не изменены')
        finally:self.function=None


class GenerationWorker(QThread):
    advanced=Signal(int,int)
    completed=Signal(object)
    failed=Signal(str)

    def __init__(self, prepared:Prepared, output:Path, parent=None):
        super().__init__(parent);self.prepared=prepared;self.output=output

    def run(self):
        last=0.0
        def progress(current,total):
            nonlocal last
            now=time.monotonic()
            if current==total or now-last>=.05:
                self.advanced.emit(current,total);last=now
        try:self.completed.emit(generate(self.prepared,self.output,progress))
        except (DocFlowError,OSError) as exc:self.failed.emit(str(exc))
        except Exception:self.failed.emit('Неожиданная ошибка генерации. Исходные файлы не изменены')


class MainWindow(QMainWindow):
    PAGE_NAMES=('Создание документов','Управление шаблонами','Поля и проверки','Результат работы','О программе')
    NAV_NAMES=('Создать DOCX','Шаблоны','Поля и проверки','Результат','О программе')

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'DocFlow Lite {__version__}')
        self.setWindowIcon(icon('document','#A1162C',32))
        self.resize(1400,860);self.setMinimumSize(560,320)
        self.table=None;self.templates=[];self.worker=None;self.task_worker=None;self.preview_worker=None
        self.last_result=None;self.encoding='auto';self.sheet=None;self._busy=False
        self._mapping_cache={};self._rules_cache={};self._active_paths=set()
        self._preview_revision=0;self._pending_preview=None;self._preview_job=None
        self._preview_timer=QTimer(self);self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._start_preview)
        self.setStyleSheet((Path(__file__).with_name('theme.qss')).read_text(encoding='utf-8'))
        root=QWidget();root.setObjectName('root');self.setCentralWidget(root)
        outer=QHBoxLayout(root);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        self.rail=QFrame();self.rail.setObjectName('rail');self.rail.setFixedWidth(202)
        nav=QVBoxLayout(self.rail);nav.setContentsMargins(14,22,14,18);nav.setSpacing(8)
        self.brand=text('DocFlow Lite','brand');nav.addWidget(self.brand)
        self.version_label=text(f'v{__version__} · RC','version');nav.addWidget(self.version_label)
        nav.addSpacing(20);self.nav_buttons=[]
        for index,kind in enumerate(('document','templates','fields','check','info')):
            button=QPushButton(self.NAV_NAMES[index]);button.setObjectName('nav')
            button.setCheckable(True);button.setIcon(icon(kind));button.setIconSize(QSize(21,21))
            button.setToolTip(self.NAV_NAMES[index]);button.setAccessibleName(self.NAV_NAMES[index])
            button.clicked.connect(lambda checked=False,i=index:self.navigate(i))
            nav.addWidget(button);self.nav_buttons.append(button)
        nav.addStretch()
        self.local_note=text('Локальная обработка\nБез сети и телеметрии','muted');nav.addWidget(self.local_note)
        outer.addWidget(self.rail)
        self.work=QWidget();self.work.setObjectName('work');outer.addWidget(self.work,1)
        work=QVBoxLayout(self.work);work.setContentsMargins(22,20,22,12);work.setSpacing(14)
        header=QHBoxLayout();titles=QVBoxLayout();titles.setSpacing(5)
        self.title=text(self.PAGE_NAMES[0],'title');titles.addWidget(self.title)
        self.subtitle=text('Таблица → ваши шаблоны Word → комплект документов','muted');titles.addWidget(self.subtitle)
        header.addLayout(titles,1)
        self.demo_btn=self.button('Открыть демопример',self.load_demo);self.demo_btn.setToolTip('Открыть встроенные вымышленные данные и два DOCX-шаблона')
        self.folder_btn=self.button('Открыть папку',self.open_result,'folder');self.folder_btn.setEnabled(False)
        header.addWidget(self.demo_btn);header.addWidget(self.folder_btn);work.addLayout(header)
        self.pages=QStackedWidget();work.addWidget(self.pages,1)
        self._build_create();self._build_templates();self._build_mapping();self._build_result();self._build_about()
        self.status=text('Откройте демопример или выберите свои файлы','status');self.status.setAccessibleName('Текущий статус')
        self.footer_layout=QHBoxLayout();self.footer_layout.setSpacing(12);self.footer_layout.addWidget(self.status,1)
        self._pinned_action=None;work.addLayout(self.footer_layout)
        self.navigate(0);self._responsive();self.update_readiness()

    def button(self,title,callback,kind=None,primary=False):
        button=QPushButton(title)
        if kind:button.setIcon(icon(kind,'#F3F4F6'))
        if primary:button.setObjectName('primary')
        button.clicked.connect(callback);button.setAccessibleName(title)
        return button

    def page(self):
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        page=QWidget();page.setObjectName('page');scroll.setWidget(page)
        self.pages.addWidget(scroll);layout=QVBoxLayout(page);layout.setContentsMargins(0,0,2,0);layout.setSpacing(14)
        return page,layout

    def _build_create(self):
        page,layout=self.page();self.create_grid=QGridLayout();self.create_grid.setSpacing(14)
        layout.addLayout(self.create_grid);layout.addStretch()
        self.source_card,source=card('1. Файлы для генерации','Исходники не перезаписываются. XLSX/CSV и от 1 до 20 DOCX.')
        self.template_summary=text('Шаблоны Word ещё не выбраны','muted');source.addWidget(self.template_summary)
        buttons=QHBoxLayout();self.add_btn=self.button('Добавить DOCX',self.select_templates,'plus');buttons.addWidget(self.add_btn)
        self.manage_btn=self.button('Управление',lambda:self.navigate(1));buttons.addWidget(self.manage_btn);source.addLayout(buttons)
        self.data_path=QLineEdit();self.data_path.setReadOnly(True);self.data_path.setPlaceholderText('Таблица Excel или CSV');self.data_path.setAccessibleName('Выбранная таблица')
        source.addWidget(self.data_path)
        self.load_btn=self.button('Выбрать XLSX / CSV',self.select_data,'folder');source.addWidget(self.load_btn)
        self.stats=text('Данные ещё не загружены','muted');source.addWidget(self.stats)
        self.tabs=QTabWidget();self.tabs.setMinimumHeight(265);source.addWidget(self.tabs,1)
        self.source_table=DataView();self.data_model=DataModel(self);self.source_table.setModel(self.data_model)
        self.source_table.setAlternatingRowColors(True);self.source_table.setSelectionBehavior(DataView.SelectionBehavior.SelectRows)
        self.source_table.setSelectionMode(DataView.SelectionMode.SingleSelection);self.source_table.setWordWrap(False)
        self.source_table.horizontalHeader().setDefaultSectionSize(155)
        self.source_table.horizontalHeader().setMinimumSectionSize(75)
        self.source_table.horizontalHeader().setStretchLastSection(True)
        self.source_table.selectionModel().currentRowChanged.connect(self._table_row_changed)
        self.tabs.addTab(self.source_table,'Данные')
        preview=QWidget();pv=QVBoxLayout(preview);pv.setContentsMargins(0,10,0,0)
        self.row_selector=QComboBox();self.record_model=RecordModel(self);self.row_selector.setModel(self.record_model)
        self.row_selector.setAccessibleName('Запись для предпросмотра')
        self.template_selector=QComboBox();self.template_selector.setAccessibleName('Шаблон для предпросмотра')
        for selector in (self.row_selector,self.template_selector):
            selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            selector.setMinimumContentsLength(12)
        self.row_selector.currentIndexChanged.connect(self.update_preview);self.template_selector.currentIndexChanged.connect(self.update_preview)
        pv.addWidget(self.row_selector);pv.addWidget(self.template_selector)
        pv.addWidget(text('Текстовый просмотр. Оформление проверяйте в Word или LibreOffice.','muted'))
        self.preview_text=QTextBrowser();self.preview_text.setOpenExternalLinks(False);self.preview_text.setAccessibleName('Текстовый предпросмотр документа');pv.addWidget(self.preview_text,1)
        self.tabs.addTab(preview,'Предпросмотр')
        self.report_text=QTextBrowser();self.report_text.setOpenExternalLinks(False);self.report_text.setPlainText('Здесь появятся результаты проверки и отчёт генерации')
        self.tabs.addTab(self.report_text,'Отчёт')
        self.options_card,options=card('2. Настройки генерации')
        self.options_layout=options
        options.addWidget(text('Формат результата','eyebrow'));options.addWidget(text('DOCX · отдельные файлы для каждой записи'))
        options.addWidget(text('Название папки записи','eyebrow'))
        self.name_selector=QComboBox();self.name_selector.setAccessibleName('Столбец для названий папок');options.addWidget(self.name_selector)
        self.output_path=QLineEdit(str(Path.home()/'Documents'/'DocFlow Lite'));self.output_path.setAccessibleName('Папка результатов')
        options.addWidget(text('Папка результатов','eyebrow'));options.addWidget(self.output_path)
        self.output_btn=self.button('Выбрать папку',self.select_output,'folder');options.addWidget(self.output_btn)
        self.open_after=QCheckBox('Открыть папку после завершения');options.addWidget(self.open_after)
        options.addWidget(self.button('Сопоставить поля и проверки',lambda:self.navigate(2),'fields'))
        self.check_btn=self.button('Проверить все записи',self.check_all,'check');options.addWidget(self.check_btn)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0);self.progress.setTextVisible(False);options.addWidget(self.progress)
        self.progress_label=text('Генерация ещё не запускалась','muted');options.addWidget(self.progress_label)
        self.generate_btn=self.button('Сгенерировать документы',self.start_generation,primary=True);options.addWidget(self.generate_btn)
        self.ready_card,ready=card('Состояние подготовки')
        self.readiness=text('Нужны таблица и шаблоны','muted');ready.addWidget(self.readiness)
        self.ready_details=text('Откройте встроенный демопример для первого запуска.','muted');ready.addWidget(self.ready_details)
        ready.addWidget(text('Проверки выполняются по вашим правилам. Ошибочные записи пропускаются и попадают в отчёт.','muted'))
        ready.addStretch();self.create_grid.addWidget(self.source_card,0,0);self.create_grid.addWidget(self.options_card,0,1);self.create_grid.addWidget(self.ready_card,0,2)

    def _build_templates(self):
        page,layout=self.page();box,body=card('Word-шаблоны','Отметьте шаблоны для текущего комплекта. Поддерживаются переменные {{поле}} в тексте, таблицах и колонтитулах.')
        layout.addWidget(box);self.template_list=QListWidget();self.template_list.setMinimumHeight(240)
        self.template_list.setTextElideMode(Qt.TextElideMode.ElideMiddle);self.template_list.setAccessibleName('Шаблоны, выбранные для генерации')
        self.template_list.itemChanged.connect(self._template_toggled);body.addWidget(self.template_list,1)
        row=QHBoxLayout();self.template_add_btn=self.button('Добавить шаблоны',self.select_templates,'plus');row.addWidget(self.template_add_btn)
        self.remove_btn=self.button('Удалить выбранный из списка',self.remove_template);row.addWidget(self.remove_btn);body.addLayout(row)
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
        row=QHBoxLayout();self.open_profile_btn=self.button('Открыть JSON-профиль',self.open_profile,'folder')
        self.save_profile_btn=self.button('Сохранить JSON-профиль',self.save_profile)
        row.addWidget(self.open_profile_btn);row.addWidget(self.save_profile_btn);body.addLayout(row)
        formatbox,settings=card('Чтение таблицы','CSV: auto определяет UTF-8 или Windows-1251. Для XLSX можно указать имя листа; пустое поле означает активный лист.')
        layout.addWidget(formatbox)
        self.encoding_selector=QComboBox();self.encoding_selector.addItems(['auto','utf-8-sig','cp1251']);self.encoding_selector.setAccessibleName('Кодировка CSV')
        self.sheet_input=QLineEdit();self.sheet_input.setPlaceholderText('Имя листа XLSX (необязательно)');self.sheet_input.setAccessibleName('Лист XLSX')
        settings.addWidget(self.encoding_selector);settings.addWidget(self.sheet_input)
        self.reload_btn=self.button('Перечитать выбранную таблицу',self.reload_data);settings.addWidget(self.reload_btn)
        layout.addStretch()

    def _build_result(self):
        page,layout=self.page();box,body=card('Результат последней генерации','Фактические числа из отчёта. Результаты каждого запуска сохраняются в отдельной папке.')
        layout.addWidget(box);self.result_summary=text('Документы ещё не созданы','section');body.addWidget(self.result_summary)
        self.result_path=text('После генерации здесь появится путь сохранения','muted');self.result_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);body.addWidget(self.result_path)
        self.result_open_btn=self.button('Открыть папку с документами',self.open_result,'folder',primary=True);self.result_open_btn.setEnabled(False);body.addWidget(self.result_open_btn)
        self.report_btn=self.button('Открыть report.json',self.open_report);self.report_btn.setEnabled(False);body.addWidget(self.report_btn)
        self.result_report=QTextBrowser();self.result_report.setMinimumHeight(200);self.result_report.setOpenExternalLinks(False);body.addWidget(self.result_report)
        layout.addStretch()

    def _build_about(self):
        page,layout=self.page();box,body=card('DocFlow Lite',f'Версия {__version__} · Release Candidate')
        layout.addWidget(box)
        body.addWidget(text('Локальная генерация Word-документов из XLSX/CSV. Данные и шаблоны не отправляются на сервер.'))
        body.addWidget(text('До 5 000 записей, 100 столбцов и 20 DOCX-шаблонов за запуск. Исходники не перезаписываются.'))
        body.addWidget(text('Поддерживаются простые переменные {{поле}}. PDF-экспорт, циклы, интеграции и история между запусками не реализованы. Текстовый предпросмотр не заменяет проверку оформления в Word/LibreOffice.','muted'))
        body.addWidget(text('Release Candidate требует ручной приёмки на Windows 10/11. Старый опубликованный выпуск 0.1.1 остаётся отдельным.','muted'))
        layout.addStretch()

    def navigate(self,index):
        self.pages.setCurrentIndex(index);self.title.setText(self.PAGE_NAMES[index])
        for i,button in enumerate(self.nav_buttons):button.setChecked(i==index)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'create_grid'):self._responsive()

    def _responsive(self):
        compact=self.width()<1050
        self.rail.layout().setContentsMargins(9 if compact else 14,12 if compact else 22,9 if compact else 14,12 if compact else 18)
        self.rail.layout().setSpacing(5 if compact else 8)
        self.brand.setText('DF' if compact else 'DocFlow Lite');self.version_label.setVisible(not compact);self.local_note.setVisible(not compact)
        for i,button in enumerate(self.nav_buttons):button.setText('' if compact else self.NAV_NAMES[i])
        self.rail.setFixedWidth(64 if compact else max(202,max(button.sizeHint().width() for button in self.nav_buttons)+28))
        self.demo_btn.setText('Демо' if compact else 'Открыть демопример');self.folder_btn.setText('Папка' if compact else 'Открыть папку')
        width=self.width()-self.rail.width()-48
        mode=3 if width>=1120 else 2 if width>=760 else 1
        pinned=self.height()<800 or compact
        if hasattr(self,'footer_layout') and self._pinned_action!=pinned:
            self.options_layout.removeWidget(self.generate_btn);self.footer_layout.removeWidget(self.generate_btn)
            (self.footer_layout if pinned else self.options_layout).addWidget(self.generate_btn)
            self.generate_btn.show();self._pinned_action=pinned
        if getattr(self,'_columns',None)==mode:return
        self._columns=mode
        for item in (self.source_card,self.options_card,self.ready_card):self.create_grid.removeWidget(item)
        for column in range(3):self.create_grid.setColumnStretch(column,0)
        self.create_grid.addWidget(self.source_card,0,0)
        self.create_grid.addWidget(self.options_card,0 if mode>1 else 1,1 if mode>1 else 0)
        self.create_grid.addWidget(self.ready_card,0 if mode==3 else 1 if mode==2 else 2,2 if mode==3 else 1 if mode==2 else 0,alignment=Qt.AlignmentFlag.AlignTop)
        self.create_grid.setColumnStretch(0,5)
        if mode>1:self.create_grid.setColumnStretch(1,3)
        if mode==3:self.create_grid.setColumnStretch(2,3)

    def active_templates(self):return [t for t in self.templates if t.path in self._active_paths]

    def error(self,message):
        self.status.setText('Ошибка: '+str(message));self.report_text.setPlainText(str(message));self.result_report.setPlainText(str(message))
        self.tabs.setCurrentIndex(2)

    def _task(self,function,success,message):
        if self._busy:return
        self._task_success=success;self.set_busy(True);self.status.setText(message)
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
            item=QListWidgetItem(icon('document','#C45468'),template.path.name+'\n'+f'{len(template.raw)/1024:.1f} КБ · {len(template.fields)} полей · {template.path.parent}')
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
        self.mapping_feedback.setText('Все переменные сопоставлены' if valid else message)
        self.ready_details.setText(f'Таблица: {len(self.table.records) if self.table else 0} записей\nШаблоны: {len(self.active_templates())} выбрано\nФормат: DOCX\nОтчёты: JSON и CSV')
        self.generate_btn.setEnabled(valid and not self._busy)
        for row in range(self.mapping_table.rowCount()):
            missing=not self.mapping_table.cellWidget(row,1).currentText()
            self.mapping_table.item(row,0).setForeground(QColor('#FF9AA4' if missing else '#F3F4F6'))

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
                self.status.setText(f'Проверено: {total} записей. Без ошибок: {total-rejected}. С ошибками: {rejected}')
                message='\n'.join(f'Строка {x.row} · {x.field}: {x.message}' for x in issues) if issues else 'Ошибок данных не обнаружено'
                self.report_text.setPlainText(message);self.result_report.setPlainText(message);self.tabs.setCurrentIndex(2)
            self._task(validate,show,'Проверяю все записи…')
        except (DocFlowError,OSError) as exc:self.error(exc)

    def open_profile(self):
        if self._busy:return
        path,_=QFileDialog.getOpenFileName(self,'Открыть настройки','','Настройки (*.json)')
        if path:self._task(lambda:prepare(Profile.load(path)),self._install_prepared,'Читаю JSON-профиль и файлы…')

    def save_profile(self):
        if self._busy:return
        try:
            profile=self.snapshot().profile
            path,_=QFileDialog.getSaveFileName(self,'Сохранить настройки','docflow-profile.json','Настройки (*.json)')
            if path:
                profile.save(path);self.status.setText('JSON-профиль сохранён')
        except (DocFlowError,OSError) as exc:self.error(exc)

    def select_output(self):
        if self._busy:return
        path=QFileDialog.getExistingDirectory(self,'Папка результата',self.output_path.text())
        if path:self.output_path.setText(path);self.output_path.setToolTip(path)

    def start_generation(self):
        if self._busy or (self.worker and self.worker.isRunning()):return
        try:
            prepared=self.snapshot()
            if not self.output_path.text().strip():raise DocFlowError('Выберите папку результата')
            self.set_busy(True);self.progress.setValue(0);self.progress_label.setText('Подготовка пакета…')
            self.status.setText('Создаю документы из загруженного снимка данных…')
            if self.worker:self.worker.deleteLater()
            self.worker=GenerationWorker(prepared,Path(self.output_path.text()),self)
            self.worker.advanced.connect(self._progress);self.worker.completed.connect(self.on_result)
            self.worker.failed.connect(self.error);self.worker.finished.connect(self._generation_finished);self.worker.start()
        except (DocFlowError,OSError) as exc:self.error(exc)

    @Slot(int,int)
    def _progress(self,current,total):
        self.progress.setValue(round(current/total*100) if total else 0)
        self.progress_label.setText(f'Обработано записей: {current} / {total}')
        self.status.setText(f'Генерация: {current} / {total} записей')

    @Slot()
    def _generation_finished(self):
        self.worker.prepared=None
        self.set_busy(False)

    def set_busy(self,busy):
        self._busy=busy
        for widget in (self.demo_btn,self.load_btn,self.add_btn,self.remove_btn,self.open_profile_btn,self.save_profile_btn,
                       self.mapping_table,self.name_selector,self.check_btn,self.output_btn,self.output_path,self.template_list,
                       self.reload_btn,self.encoding_selector,self.sheet_input,self.open_after,self.template_add_btn):widget.setEnabled(not busy)
        self.update_readiness()

    @Slot(object)
    def on_result(self,result:BatchResult):
        self.last_result=result;self.folder_btn.setEnabled(True);self.result_open_btn.setEnabled(True);self.report_btn.setEnabled(True)
        self.progress.setValue(100);self.progress_label.setText(f'Завершено: {result.total} / {result.total} записей')
        summary=f'Готово: {result.documents} DOCX · {result.accepted} записей обработано · {result.rejected} пропущено'
        self.status.setText(summary);self.result_summary.setText(summary)
        self.result_path.setText(str(result.directory));self.result_path.setToolTip(str(result.directory))
        message=f'Всего записей: {result.total}\nСоздано DOCX: {result.documents}\nОбработано: {result.accepted}\nПропущено: {result.rejected}\n\n'+'\n'.join(f'Строка {x.row} · {x.field}: {x.message}' for x in result.issues)+'\n\nПолные отчёты: report.json и report.csv'
        self.report_text.setPlainText(message);self.result_report.setPlainText(message);self.tabs.setCurrentIndex(2);self.navigate(3)
        if self.open_after.isChecked():self.open_result()

    def open_result(self):
        if self.last_result and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_result.directory))):self.error('Система не смогла открыть папку. Скопируйте путь из раздела «Результат»')

    def open_report(self):
        if self.last_result and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_result.directory/'report.json'))):self.error('Система не смогла открыть отчёт. Он сохранён в папке результата')

    def closeEvent(self,event):
        if self._busy or any(w and w.isRunning() for w in (self.worker,self.task_worker,self.preview_worker)):
            QMessageBox.information(self,'Обработка продолжается','Дождитесь завершения текущей операции перед закрытием')
            event.ignore()
        else:self._preview_timer.stop();event.accept()
