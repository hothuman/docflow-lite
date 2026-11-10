"""Explicit system-editor handoff; opening a DOCX is not printer confirmation."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from docx import Document
from docx.text.paragraph import Paragraph
from PySide6.QtCore import QSignalBlocker, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QLineEdit, QMessageBox, QPlainTextEdit,
                               QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from ...service.attachments import attachment_path, export_file
from ...service.document_fields import FIELDS
from ...service.document_readiness import assess
from ...service.documents import KINDS, prepare_document, save_prepared_document
from ...templates import Template
from ..flow import ActionBar
from ..widgets import card, text
from .images import ImagesPanel
from .presentation import date_text
from .widgets import Grid, button


def open_for_printing(parent, path):
    """Return whether the OS accepted the file, retaining it on every failure."""
    path = Path(path)
    if not path.is_file():
        QMessageBox.warning(parent, 'Документ не найден',
                            'Файл документа отсутствует. Сформируйте новую версию '
                            'или восстановите проект из резервной копии.\n\n' + str(path))
        return False
    try:
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    except (OSError, RuntimeError):
        opened = False
    if not opened:
        QMessageBox.warning(parent, 'Открытие документа',
                            'DOCX сохранён, но Windows не смогла открыть его. '
                            'Проверьте установленный Word или LibreOffice и доступ к файлу. '
                            'Нажмите «Показать папку документа» и откройте файл вручную.\n\n' + str(path))
        return False
    return True


_PURPOSE = {
    'intake': 'Фиксирует, от кого приняли оборудование, жалобу и комплектацию.',
    'completion': 'Показывает выполненные работы, использованные материалы и суммы.',
    'combined': 'Собирает приёмку и результаты ремонта в одном документе.',
    'defects': 'Фиксирует результаты диагностики и план работ.',
    'handover': 'Оформляет сведения о передаче оборудования. Сам документ не отмечает выдачу.',
    'estimate_preliminary': 'Показывает позиции и сумму сохранённой предварительной сметы.',
    'estimate_final': 'Показывает позиции и сумму сохранённой окончательной сметы.',
    'warranty': 'Готовит форму с гарантийными условиями из настроек организации.',
}


class _DocumentPages(QStackedWidget):
    def sizeHint(self):
        return self.currentWidget().sizeHint() if self.currentWidget() else super().sizeHint()

    def minimumSizeHint(self):
        return self.currentWidget().minimumSizeHint() if self.currentWidget() else super().minimumSizeHint()


def _paragraphs(container):
    for block in container.iter_inner_content():
        if isinstance(block, Paragraph):
            if block.text.strip():
                yield block.text
        else:
            for row in block.rows:
                yield '  │  '.join(' / '.join(_paragraphs(cell)) for cell in row.cells)


def _content_preview(prepared):
    document = Document(BytesIO(prepared.rendered))

    def lines_with_headers():
        yield from _paragraphs(document)
        for section in document.sections:
            for heading, story in (('Верхний колонтитул', section.header), ('Нижний колонтитул', section.footer)):
                if not story.is_linked_to_previous:
                    yield heading
                    yield from _paragraphs(story)

    lines = []
    remaining = 64_000
    for line in lines_with_headers():
        if len(line) >= remaining:
            lines.extend((line[:remaining], 'Полное содержимое доступно в разметке DOCX.'))
            break
        lines.append(line)
        remaining -= len(line) + 1
    return '\n'.join(lines)


class ServiceDocumentWizard(QWidget):
    """Create a version only after the user has seen the rendered candidate."""

    steps = ('Тип документа', 'Проверка данных', 'Предпросмотр', 'Создание', 'Результат', 'Созданные документы')

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.workspace = editor.workspace
        self.store = editor.store
        self.snapshot = editor.snapshot
        self.estimate_id = None
        self._kind_chosen = False
        self.prepared = None
        self._preview_copy = None
        self._last_document = None
        self._photo_panel = None
        self._photos_source = ()
        self.setAccessibleName('Мастер создания документа')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        self.step = text('', 'muted')
        layout.addWidget(self.step)
        self.heading = text('', 'section')
        layout.addWidget(self.heading)
        self.document_status = text('', 'status')
        self.document_status.setAccessibleName('Состояние документа')
        layout.addWidget(self.document_status)
        self.pages = _DocumentPages()
        self.pages.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.pages.currentChanged.connect(self.pages.updateGeometry)
        layout.addWidget(self.pages)
        self._type_page()
        self._check_page()
        self._preview_page()
        self._create_page()
        self._result_page()
        self._history_page()
        layout.addStretch(1)
        self.doc_kind.currentIndexChanged.connect(self._type_changed)
        self.doc_kind.activated.connect(self._mark_kind_chosen)
        self.template_path.textChanged.connect(self._refresh_check)
        self.install(self.snapshot)
        self.start()

    def _page(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)
        self.pages.addWidget(panel)
        return layout

    def _actions(self, layout):
        bar = ActionBar()
        layout.addWidget(bar)
        return bar

    def _type_page(self):
        layout = self._page()
        self.doc_kind = QComboBox()
        self.doc_kind.setAccessibleName('Тип документа')
        for kind, name in KINDS.items():
            self.doc_kind.addItem(name, kind)
        self.doc_kind.setMaximumWidth(520)
        layout.addWidget(self.doc_kind)
        self.purpose = text('', 'muted')
        layout.addWidget(self.purpose)
        actions = self._actions(layout)
        button(actions, 'Проверить данные', self.check_document, primary=True)
        button(actions, 'Созданные документы', lambda: self._show(5))
        layout.addStretch()

    def _check_page(self):
        layout = self._page()
        self.source = text('')
        self.profile_banner = text('', 'status')
        self.profile_banner.setAccessibleName('Проверка данных документа')
        layout.addWidget(self.source)
        layout.addWidget(self.profile_banner)
        self.check_handover_warning=text('','documentWarning')
        layout.addWidget(self.check_handover_warning)
        organization = self._actions(layout)
        button(organization, 'Настроить организацию', self._configure_organization)
        self.template_path = QLineEdit()
        self.template_path.setReadOnly(True)
        self.template_path.hide()
        self.template_name = text('', 'muted')
        layout.addWidget(self.template_name)
        templates = self._actions(layout)
        button(templates, 'Выбрать свой DOCX', self.pick_template)
        self.clear_template = button(templates, 'Вернуть форму профиля', self.template_path.clear)
        self.images = QCheckBox('Выбрать фотографии для документа')
        self.images.toggled.connect(self._toggle_photos)
        layout.addWidget(self.images)
        self.photos = QVBoxLayout()
        layout.addLayout(self.photos)
        actions = self._actions(layout)
        self.preview_button = button(actions, 'Посмотреть документ', lambda: self.editor.with_saved(self.preview), primary=True)
        button(actions, 'Назад к типу документа', lambda: self._show(0))
        layout.addStretch()

    def _preview_page(self):
        layout = self._page()
        layout.addWidget(text('Это текстовый предпросмотр содержания. Для проверки страниц и печати откройте DOCX в редакторе.', 'muted'))
        actions = self._actions(layout)
        self.preview_continue = button(actions, 'Продолжить к созданию', lambda: self._show(3), primary=True)
        button(actions, 'Посмотреть разметку DOCX', self.open_preview)
        button(actions, 'Назад к проверке', lambda: self._show(1))
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setAccessibleName('Содержимое DOCX перед созданием')
        self.preview_text.setMinimumHeight(100)
        self.preview_text.setMaximumHeight(235)
        layout.addWidget(self.preview_text)

    def _handover_warning(self):
        if self.doc_kind.currentData()!='handover':
            return ''
        repair=self.snapshot['repair']
        missing=[]
        if repair['status'] not in ('issued','closed'):missing.append('фактическая выдача')
        if not repair.get('issued_at'):missing.append('дата выдачи')
        if not repair.get('handover','').strip():missing.append('сведения о получателе')
        if not missing:
            return ''
        return ('Черновик передачи. Требуют проверки: '+', '.join(missing)+'. '
                'Создание DOCX не подтверждает выдачу оборудования.')

    def _create_page(self):
        layout = self._page()
        self.confirm_text = text('')
        layout.addWidget(self.confirm_text)
        self.create_handover_warning=text('','documentWarning')
        layout.addWidget(self.create_handover_warning)
        layout.addWidget(text('Будет создана новая версия. Ранее созданные документы останутся в журнале.', 'muted'))
        actions = self._actions(layout)
        self.generate_button = button(actions, 'Создать DOCX', self.create, primary=True)
        button(actions, 'Назад к предпросмотру', lambda: self._show(2))

    def _result_page(self):
        layout = self._page()
        frame, content = card('Документ создан')
        self.result_name = text('', 'section')
        self.result_info = text('')
        self.result_name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content.addWidget(self.result_name)
        content.addWidget(self.result_info)
        self._result_actions(content, self._result)
        layout.addWidget(frame)
        actions = self._actions(layout)
        button(actions, 'Создать другой документ', self.start)
        button(actions, 'Созданные документы', lambda: self._show(5))
        self.result_row = None

    def _history_page(self):
        layout = self._page()
        self.empty_history = text('У этого ремонта пока нет созданных документов.', 'empty')
        layout.addWidget(self.empty_history)
        self.grid = Grid([('kind','Тип'),('version','Версия'),('created_at','Создано'),('path','Файл')],
                         settings_key='documents/repair-versions')
        self.grid.setAccessibleName('Созданные документы ремонта')
        self.grid.setMaximumHeight(205)
        layout.addWidget(self.grid)
        self._result_actions(layout, self.grid.selected)
        self.grid.openRequested.connect(self.open_document)
        self.grid.doubleClicked.connect(lambda _: self.open_document())
        button(self._actions(layout), 'К выбору типа документа', lambda: self._show(0))

    def _result_actions(self, layout, row):
        actions = self._actions(layout)
        buttons = [
            button(actions, 'Открыть', lambda: self._open(row()), primary=True),
            button(actions, 'Показать в папке', lambda: self._show_folder(row())),
            button(actions, 'Сохранить копию', lambda: self._export(row())),
            button(actions, 'Подготовить к печати', lambda: self._open(row(), for_print=True)),
        ]
        if self.pages.count() == 6:
            def sync(*_):
                for control in buttons:
                    control.setEnabled(row() is not None)
            self.grid.selectionModel().currentChanged.connect(sync)
            self.grid.records.modelReset.connect(sync)
            sync()

    def _show(self, index):
        self.pages.setCurrentIndex(index)
        self.step.setText(f'Шаг {index + 1} из 5' if index < 5 else 'Журнал документов')
        self.heading.setText(self.steps[index])
        self.document_status.clear()
        self.document_status.hide()
        if index == 1:
            self._refresh_check()
        if index == 3:
            self._update_handover_warnings()

    def _notice(self, message):
        self._message(message, 'status')

    def _error(self, message):
        self._message(message, 'documentActionError')

    def _message(self, message, role):
        if self.document_status.objectName() != role:
            self.document_status.setObjectName(role)
            style = self.document_status.style()
            style.unpolish(self.document_status)
            style.polish(self.document_status)
        self.document_status.setText(message)
        self.document_status.setVisible(bool(message))

    def start(self, kind=None, estimate_id=None):
        self.estimate_id = None
        if kind in KINDS:
            self.doc_kind.setCurrentIndex(self.doc_kind.findData(kind))
            self._kind_chosen = True
        self.estimate_id = estimate_id
        self.prepared = None
        self._preview_copy = None
        self._refresh_check()
        self._show(0)
        self.doc_kind.setFocus()

    def suggest_kind(self, kind):
        if self.pages.currentIndex()==4 and self.doc_kind.currentData()!=kind:
            # A completed document has no pending selection or preview to preserve.
            self.start()
            self._kind_chosen = False
        if self._kind_chosen or self.pages.currentIndex()!=0 or self.doc_kind.currentData()==kind:
            return
        with QSignalBlocker(self.doc_kind):
            self.doc_kind.setCurrentIndex(self.doc_kind.findData(kind))
        self.prepared = None
        self._preview_copy = None
        self._refresh_check()

    def _mark_kind_chosen(self):
        self._kind_chosen = True

    def _type_changed(self):
        self._mark_kind_chosen()
        self.estimate_id = None
        self.prepared = None
        self._refresh_check()

    def _estimate(self):
        kind = self.doc_kind.currentData()
        if kind.startswith('estimate_'):
            return next((q for q in self.snapshot['estimates']
                         if q['kind'] == kind.removeprefix('estimate_') and (not self.estimate_id or q['id'] == self.estimate_id)), None)

    def _update_handover_warnings(self):
        warning=self._handover_warning()
        for label in (self.check_handover_warning,self.create_handover_warning):
            label.setText(warning)
            label.setAccessibleName(warning)
            label.setVisible(bool(warning))

    def _refresh_check(self, *_):
        kind = self.doc_kind.currentData()
        self.purpose.setText(_PURPOSE[kind])
        self._update_handover_warnings()
        quote = self._estimate()
        repair = self.snapshot['repair']
        snapshot = {**self.snapshot, 'estimates':[quote]} if quote else self.snapshot
        custom = self.template_path.text()
        check = assess(snapshot, kind, custom)
        self.template_name.setText('Выбран шаблон ' + Path(custom).name if custom else
                                   'Используется шаблон организации.' if check['template_selected'] else
                                   'Используется встроенная форма.')
        self.template_name.setToolTip(custom)
        self.clear_template.setVisible(bool(custom))
        self.source.setText(f"Данные ремонта № {repair['number']}" +
                            (f" · сохранённая версия сметы {quote['version']}" if quote else ''))
        problems = []
        if kind.startswith('estimate_') and not quote:
            problems.append('Сначала сохраните нужную версию в разделе «Смета».')
        if check['required_missing']:
            aliases = check['profile'].get('template_field_mapping',{}).get(kind,{})
            names = [FIELDS.get(aliases.get(key,key),key) for key in check['required_missing']]
            problems.append('Заполните обязательные поля: ' + ', '.join(names) + '.')
        if check['blocked'] and check['missing']:
            problems.append('Добавьте в настройках организации: ' + ', '.join(check['missing']) + '.')
        self.profile_banner.setText('\n'.join(problems) if problems else
                                    'Будет создана нейтральная форма без данных исполнителя.' if check['neutral'] else
                                    'Будут использованы сохранённые данные исполнителя.')
        role = 'documentReadinessError' if problems else 'status'
        if self.profile_banner.objectName() != role:
            self.profile_banner.setObjectName(role)
            style = self.profile_banner.style()
            style.unpolish(self.profile_banner)
            style.polish(self.profile_banner)
        self.preview_button.setEnabled(not problems)

    def _configure_organization(self):
        self.editor.with_saved(self.editor.setup_organization)

    def check_document(self):
        self.prepared = None
        self._preview_copy = None
        self._show(1)

    def pick_template(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Выбрать свой шаблон', '', 'Word (*.docx)')
        if path:
            self.workspace.run(lambda: Template.load(path), lambda _: self.template_path.setText(path),
                               'Проверяю шаблон…', on_error=self._error, inline_error=True)

    def install(self, snapshot):
        self.snapshot = snapshot
        rows = snapshot['generated_documents']
        self.grid.install(rows)
        self.grid.setVisible(bool(rows))
        self.empty_history.setVisible(not rows)
        attachments = tuple(row for row in snapshot['attachments'] if row['kind'] == 'image')
        if attachments != self._photos_source:
            chosen = self.image_choices
            if self._photo_panel:
                self.photos.removeWidget(self._photo_panel)
                self._photo_panel.deleteLater()
                self._photo_panel = None
            if attachments:
                self._photo_panel = ImagesPanel(attachments, self, chosen)
                self.photos.addWidget(self._photo_panel)
                self._toggle_photos(self.images.isChecked())
            self._photos_source = attachments
        self.images.setVisible(bool(attachments))
        self._refresh_check()

    @property
    def image_choices(self):
        return self._photo_panel.values() if self._photo_panel else []

    def _toggle_photos(self, checked):
        if self._photo_panel:
            self._photo_panel.setVisible(checked)

    def preview(self):
        self._refresh_check()
        if not self.preview_button.isEnabled():
            return
        choices = self.image_choices if self.images.isChecked() else []
        if len(choices) > 10:
            self._error('Выберите не более десяти фотографий.')
            return
        kind, template = self.doc_kind.currentData(), self.template_path.text() or None
        quote = self._estimate()
        estimate_id = quote['id'] if quote else None
        cancelled = Event()

        def work():
            if cancelled.is_set():
                return None
            prepared = prepare_document(self.store, self.editor.key, kind, template,
                                        estimate_id=estimate_id, image_choices=choices)
            return None if cancelled.is_set() else (prepared, _content_preview(prepared))

        def done(result):
            if cancelled.is_set():
                self._notice('Предпросмотр отменён. Документ не создан.')
                return
            self.prepared, content = result
            self.preview_text.setPlainText(content)
            self.confirm_text.setText(KINDS[kind] + f" · ремонт № {self.snapshot['repair']['number']}")
            self._show(2)
            self.preview_text.setFocus()
            QTimer.singleShot(0, self, self._reveal_preview_action)

        def cancel():
            cancelled.set()
            self._notice('Предпросмотр отменён. Завершается чтение шаблона…')

        def failed(error):
            if cancelled.is_set():
                done(None)
            else:
                self._error(error)

        self.prepared = None
        self._preview_copy = None
        self._notice('Готовлю предпросмотр…')
        self.workspace.run(work, done, 'Готовлю документ для проверки…', on_error=failed,
                           inline_error=True, cancel=cancel)

    def _reveal_preview_action(self):
        if self.preview_continue.isVisible():
            self.editor.body_scroll.ensureWidgetVisible(self.preview_continue, 6, 6)

    def open_preview(self):
        if not self.prepared:
            return
        if self._preview_copy:
            self._open_editor(self._preview_copy[1])
            return
        rendered = self.prepared.rendered
        def write():
            folder = TemporaryDirectory(prefix='docflow-preview-', ignore_cleanup_errors=True)
            file = Path(folder.name)/'Предпросмотр.docx'
            file.write_bytes(rendered)
            return folder, file
        def done(copy):
            self._preview_copy = copy
            self._open_editor(copy[1])
        self.workspace.run(write, done, 'Открываю временный DOCX…', on_error=self._error, inline_error=True)

    def create(self):
        prepared = self.prepared
        if not prepared:
            return
        if self.editor.dirty:
            self._show(1)
            self._error('Сохраните изменения ремонта и обновите предпросмотр.')
            return
        def work():
            path = save_prepared_document(self.store, prepared)
            return path, self.store.snapshot(self.editor.key)
        def done(result):
            path, snapshot = result
            self.editor.install(snapshot)
            self._last_document = path
            self.result_row = next(row for row in snapshot['generated_documents'] if Path(row['path']).name == path.name)
            row = self.result_row
            self.result_name.setText(KINDS[row['kind']])
            self.result_info.setText(f"Версия {row['version']} · {date_text(row['created_at'])}")
            self.prepared = None
            self._preview_copy = None
            self._show(4)
        def failed(error):
            self.prepared = None
            self._preview_copy = None
            self._show(1)
            self._error(error)
        self._notice('Сохраняю новую версию DOCX…')
        self.workspace.run(work, done, 'Создаю новую версию DOCX…', on_error=failed, inline_error=True)

    def _result(self):
        return self.result_row

    def _current(self):
        return self.result_row if self.pages.currentIndex() == 4 else self.grid.selected()

    def open_document(self):
        self._open(self._current())

    def show_document_folder(self):
        self._show_folder(self._current())

    def export_document(self):
        self._export(self._current())

    def _open_editor(self, path, for_print=False):
        try:
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except (OSError, RuntimeError):
            opened = False
        if opened:
            if for_print:
                self._notice('Документ открыт в редакторе. Проверьте страницы и выберите «Печать» или Ctrl+P.')
        else:
            self._error('Не удалось открыть редактор DOCX. Установите совместимый редактор или откройте файл из папки.')

    def _open(self, row, for_print=False):
        if row:
            self.workspace.run(lambda: attachment_path(self.store,row['id'],True),
                               lambda path: self._open_editor(path, for_print),
                               on_error=self._error, inline_error=True)

    def _show_folder(self, row):
        if row:
            self.workspace.run(lambda: attachment_path(self.store,row['id'],True),
                               lambda path: self.workspace.open_local(path.parent),
                               on_error=self._error, inline_error=True)

    def _export(self, row):
        if not row:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Сохранить отдельную копию', Path(row['path']).name, 'Word (*.docx)')
        if path:
            self.workspace.run(lambda: export_file(self.store,row['id'],path,True),
                               lambda result: self._notice('Копия сохранена: ' + result.name),
                               on_error=self._error, inline_error=True)
