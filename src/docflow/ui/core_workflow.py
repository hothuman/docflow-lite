"""Core document steps and the in-window data review."""
import hashlib
from html import escape
import json
from math import ceil
from pathlib import Path

from PySide6.QtCore import QModelIndex, QStringListModel, Qt, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLineEdit, QListView,
    QProgressBar, QStyle, QStyleOptionComboBox, QStylePainter, QTabWidget,
    QTextBrowser, QVBoxLayout, QWidget,
)
from .widgets import DataModel, DataView, RecordModel, labeled_input, paper, section, text
from .flow import ActionBar
from .settings import load_widths, save_widths
from .theme import COLORS
from ..safety import safe_name


class CoreCounts(QWidget):
    """A compact row of explicitly named values, shared by check and output."""

    def __init__(self, labels):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.values = []
        for label, tone in labels:
            panel, body = section(role='coreCount')
            body.setSpacing(2)
            value = text('—', tone)
            value.setAccessibleName(label)
            body.addWidget(value)
            body.addWidget(text(label, 'coreCountCaption'))
            layout.addWidget(panel, 1)
            self.values.append(value)

    def update_counts(self, *values):
        for field, value in zip(self.values, values, strict=True):
            field.setText(str(value))
            field.setAccessibleDescription(str(value))


class ColumnChoice(QComboBox):
    """Show a readable prompt for the existing empty mapping value."""

    def paintEvent(self, event):
        if self.currentText():
            super().paintEvent(event)
            return
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = 'Выберите столбец'
        option.palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS['error']))
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)


class ReviewedSourceModel(DataModel):
    """Mark actual source rows after a full check, retaining original row numbers."""

    checked = False

    def set_review(self, issues, mapping, *, checked):
        self.set_issues(issues, mapping)
        self.checked = checked
        if self.rowCount():
            self.headerDataChanged.emit(Qt.Orientation.Vertical, 0, self.rowCount() - 1)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if self.checked and orientation == Qt.Orientation.Vertical and self.table and 0 <= section < self.rowCount():
            row = self.table.records[section].row_number
            rejected = bool(self.issues_for(section))
            if role == Qt.ItemDataRole.DisplayRole:
                return f'{"!" if rejected else "✓"} {row}'
            if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
                return f'Строка {row} · ' + ('с ошибками, будет пропущена' if rejected else 'готова')
        return super().headerData(section, orientation, role)


def issue_text(issue, mapping):
    column = mapping.get(issue.field)
    field = f'{column} ({issue.field})' if column and column != issue.field else issue.field or 'Документ'
    return f'Строка {issue.row} · {field}: {issue.message}'


def issue_summary(issues, mapping, *, limit=50):
    lines = [issue_text(issue, mapping) for issue in issues[:limit]]
    if len(issues) > limit:
        lines.append(f'И ещё замечаний: {len(issues) - limit}. Полный список доступен в отчёте.')
    return '\n'.join(lines)


class ValidationPanel(QFrame):
    """One review surface for mapping problems and per-record validation."""

    page_size = 30

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName('coreValidation')
        self.setAccessibleName('Результаты проверки данных')
        self.signature = None
        self.mode = ''
        self.issues = ()
        self.mapping = {}
        self.offset = 0
        self.missing = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(7)
        self.heading = text('', 'section')
        layout.addWidget(self.heading)
        self.counts = CoreCounts((('Строки готовы', 'coreCountGood'),
                                  ('Строки с ошибками', 'coreCountBad')))
        self.counts.hide()
        layout.addWidget(self.counts)
        self.report = QTextBrowser()
        self.report.setAccessibleName('Результаты проверки всех строк')
        self.report.setOpenExternalLinks(False)
        self.report.setOpenLinks(False)
        self.report.setFixedHeight(82)
        self.report.document().documentLayout().documentSizeChanged.connect(
            lambda size: self.report.setFixedHeight(max(70, min(154, ceil(size.height()) + 8))))
        self.report.anchorClicked.connect(self._open_link)
        layout.addWidget(self.report)
        actions = ActionBar()
        self.first = window.button('К первой ошибке', self._first_issue)
        self.previous = window.button('Предыдущие ошибки', lambda: self._change_page(-1))
        self.following = window.button('Следующие ошибки', lambda: self._change_page(1))
        for button in (self.first, self.previous, self.following):
            actions.addWidget(button)
        layout.addWidget(actions)
        self.hide()

    def _appearance(self, severity):
        self.setProperty('severity', severity)
        self.setAccessibleDescription(self.heading.text())
        self.heading.setObjectName('error' if severity == 'error' else 'section')
        for widget in (self, self.heading):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.show()

    def sync_context(self, signature, valid, message):
        if signature != self.signature:
            self.signature = signature
            self.mode = ''
            self.issues = ()
            self.mapping = {}
            self.window.data_model.set_review((), {}, checked=False)
            self.window.source_issue.hide()
            self.hide()
        if self.mode in ('rows', 'operation'):
            return
        if not valid and self.window.table and self.window.active_templates():
            missing = tuple(row for row in range(self.window.mapping_table.rowCount())
                            if not self.window.mapping_table.cellWidget(row, 1).currentText())
            if self.mode == 'mapping' and self.missing == missing and self.report.toPlainText() == message:
                return
            self.mode, self.missing = 'mapping', missing
            self.counts.hide()
            self.heading.setText(f'⚠ Проверьте сопоставление · полей без столбца: {len(missing)}')
            self.report.setPlainText(message)
            self.report.show()
            self.first.setVisible(bool(missing))
            self.first.setText('К первому полю без столбца')
            self.first.setAccessibleName(self.first.text())
            self.first.setAccessibleDescription('Выбрать столбец для указанного поля')
            self.previous.hide()
            self.following.hide()
            self._appearance('error')

    def set_error(self, message, signature):
        self.signature, self.mode = signature, 'operation'
        self.counts.hide()
        self.heading.setText('⚠ Не удалось выполнить действие')
        self.report.setPlainText(message)
        self.report.show()
        self.first.hide()
        self.previous.hide()
        self.following.hide()
        self._appearance('error')

    def set_results(self, signature, issues, mapping, total, rejected):
        self.signature, self.mode = signature, 'rows'
        self.issues, self.mapping, self.offset = tuple(issues), mapping, 0
        self.window.data_model.set_review(issues, mapping, checked=True)
        self.window.update_source_issue()
        self.counts.update_counts(total - rejected, rejected)
        self.counts.show()
        if issues:
            self.heading.setText('Строки с ошибками будут пропущены. Откройте замечание, чтобы найти ячейку.')
            self.first.setText('К первой ошибке')
            self.first.setAccessibleName(self.first.text())
            self.first.setAccessibleDescription(issue_text(self.issues[0], mapping))
            self.first.show()
            self.report.show()
            self._show_issue_page()
            self._appearance('error')
        else:
            self.heading.setText('Все строки готовы к созданию документов')
            self.report.setPlainText('Ошибок данных не обнаружено')
            self.report.hide()
            self.first.hide()
            self.previous.hide()
            self.following.hide()
            self._appearance('success')

    def _show_issue_page(self):
        stop = min(self.offset + self.page_size, len(self.issues))
        links = [f'<li><a style="color:{COLORS["error"]}" href="issue:{index}">'
                 f'{escape(issue_text(self.issues[index], self.mapping))}</a></li>'
                 for index in range(self.offset, stop)]
        self.report.setHtml(f'<p>Замечания {self.offset + 1}–{stop} из {len(self.issues)}. '
                            '</p>'
                            f'<ul>{"".join(links)}</ul>')
        pageable = len(self.issues) > self.page_size
        self.previous.setVisible(pageable)
        self.following.setVisible(pageable)
        self.previous.setEnabled(self.offset > 0)
        self.following.setEnabled(stop < len(self.issues))

    def _change_page(self, direction):
        self.offset += direction * self.page_size
        self._show_issue_page()

    def _open_link(self, link):
        index = link.path()
        if link.scheme() == 'issue' and index.isascii() and index.isdecimal() and int(index) < len(self.issues):
            self.window.go_to_source_issue(self.issues[int(index)], self.mapping)

    def _first_issue(self):
        if self.mode == 'mapping' and self.missing:
            row = self.missing[0]
            table = self.window.mapping_table
            table.setCurrentCell(row, 1)
            table.scrollToItem(table.item(row, 0))
            table.cellWidget(row, 1).setFocus(Qt.FocusReason.OtherFocusReason)
            self.window.pages.widget(2).ensureWidgetVisible(table, 6, 6)
        elif self.issues:
            self.window.go_to_source_issue(self.issues[0], self.mapping)


class ResultFilesModel(QStringListModel):
    """Friendly labels with the original package-relative path in a separate role."""

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole,
                    Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.UserRole):
            relative = super().data(index, Qt.ItemDataRole.DisplayRole)
            if relative is None or role in (Qt.ItemDataRole.UserRole, Qt.ItemDataRole.ToolTipRole):
                return relative
            folder, _, filename = relative.rpartition('/')
            row = folder.split('_', 2)[1] if folder.startswith('row_') and '_' in folder else ''
            return f'{filename}   ·   строка {int(row)}' if row.isdecimal() else filename
        return super().data(index, role)


def restore_source_columns(w):
    if not w.table:
        w.source_widths_key = ''
        return
    headers = w.table.headers
    digest = hashlib.sha256(json.dumps(headers, ensure_ascii=False).encode('utf-8')).hexdigest()
    w.source_widths_key = ''  # Do not persist programmatic column sizing.
    w.source_widths = load_widths('core/source/' + digest)
    for column, title in enumerate(headers):
        width = w.source_widths.get(column, max(144, min(320, w.source_table.fontMetrics().horizontalAdvance(title) + 30)))
        w.source_table.setColumnWidth(column, width)
    w.source_widths_key = 'core/source/' + digest


def save_source_column(w, section, _old_width, width):
    if w.source_widths_key:
        w.source_widths[section] = width
        save_widths(w.source_widths_key, w.source_widths)


def build_create(w):
    _, layout = w.page()
    w.empty_card, empty = section(role='coreStart')
    empty.setContentsMargins(20, 16, 20, 16)
    empty.setSpacing(10)
    empty.addWidget(text('Из таблицы в Word', 'coreHeroTitle'))
    empty.addWidget(text('Заполняйте договоры, акты и другие Word-документы данными из Excel или CSV.', 'coreLead'))
    w.select_first_table = w.button('Выбрать таблицу', w.select_data, 'folder', primary=True)
    actions = ActionBar()
    actions.addWidget(w.select_first_table)
    actions.addWidget(w.demo_btn)
    empty.addWidget(actions)
    empty.addWidget(text('Попробуйте путь от таблицы до DOCX на вымышленных данных.', 'muted'))
    start_tools = ActionBar()
    for control in (w.button('Открыть профиль', w.open_profile, 'folder'),
                    w.button('Настройки чтения', lambda: toggle_source_settings(w, not w.source_settings.isVisible()), 'gear')):
        control.setObjectName('coreQuiet')
        start_tools.addWidget(control)
    empty.addWidget(start_tools)
    layout.addWidget(w.empty_card)

    w.source_card, source = section()
    layout.addWidget(w.source_card, 1)
    w.source_heading = text('Файл с данными', 'coreSectionTitle')
    source.addWidget(w.source_heading)
    w.data_path = QLineEdit()
    w.data_path.setReadOnly(True)
    w.data_path.setAccessibleName('Выбранная таблица')
    file_row = QHBoxLayout()
    file_row.addWidget(w.data_path, 1)
    w.load_btn = w.button('Заменить таблицу', w.select_data, 'folder')
    file_row.addWidget(w.load_btn)
    source.addLayout(file_row)
    w.stats = text('Таблица ещё не выбрана', 'coreMeta')
    source.addWidget(w.stats)
    w.source_check = text('', 'muted')
    source.addWidget(w.source_check)

    w.source_issue = text('', 'error')
    w.source_issue.setAccessibleName('Ошибки выбранной строки')
    w.source_issue.hide()
    source.addWidget(w.source_issue)
    w.source_widths_key = ''
    w.source_widths = {}
    w.tabs = QTabWidget()
    w.tabs.setObjectName('coreSourceTabs')
    w.tabs.setMinimumHeight(210)
    source.addWidget(w.tabs, 1)
    w.source_table = DataView()
    w.source_table.setObjectName('coreSourceTable')
    w.source_table.setAccessibleName('Исходные строки таблицы')
    w.data_model = ReviewedSourceModel(w)
    w.source_table.setModel(w.data_model)
    w.source_table.setAlternatingRowColors(True)
    w.source_table.setShowGrid(False)
    w.source_table.setSelectionBehavior(DataView.SelectionBehavior.SelectRows)
    w.source_table.setSelectionMode(DataView.SelectionMode.SingleSelection)
    w.source_table.setWordWrap(False)
    w.source_table.horizontalHeader().setDefaultSectionSize(155)
    w.source_table.horizontalHeader().setMinimumSectionSize(75)
    w.source_table.selectionModel().currentRowChanged.connect(w._table_row_changed)
    w.source_table.horizontalHeader().sectionResized.connect(lambda *args: save_source_column(w, *args))
    w.tabs.addTab(w.source_table, 'Данные')

    preview = QWidget()
    body = QVBoxLayout(preview)
    w.row_selector = QComboBox()
    w.record_model = RecordModel(w)
    w.row_selector.setModel(w.record_model)
    w.template_selector = QComboBox()
    add_preview_selectors(body, w.row_selector, w.template_selector)
    for selector in (w.row_selector, w.template_selector):
        selector.currentIndexChanged.connect(w.update_preview)
    w.preview_text = paper('Текстовый предпросмотр документа')
    body.addWidget(w.preview_text, 1)
    w.tabs.addTab(preview, 'Текстовый пример')
    w.report_text = QTextBrowser()
    w.report_text.setAccessibleName('Подробности проверки строк')
    w.report_text.setOpenExternalLinks(False)
    w.tabs.addTab(w.report_text, 'Замечания')

    w.source_tools = ActionBar()
    w.source_settings_btn = w.button('Настройки чтения', lambda checked: toggle_source_settings(w, checked), 'gear')
    w.source_settings_btn.setCheckable(True)
    w.source_tools.addWidget(w.source_settings_btn)
    w.source_tools.addWidget(w.button('Открыть профиль', w.open_profile, 'folder'))
    source.addWidget(w.source_tools)

    w.source_settings, settings = section('Чтение таблицы', role='coreSubsection')
    w.encoding_selector = QComboBox()
    for label, value in (('Определить автоматически', 'auto'), ('UTF-8', 'utf-8-sig'), ('Windows-1251', 'cp1251')):
        w.encoding_selector.addItem(label, value)
    w.sheet_input = QLineEdit()
    w.sheet_input.setPlaceholderText('Пусто — активный лист')
    labeled_input(settings, 'Кодировка CSV', w.encoding_selector)
    labeled_input(settings, 'Лист XLSX', w.sheet_input)
    w.reload_btn = w.button('Перечитать таблицу', w.reload_data)
    settings.addWidget(w.reload_btn, alignment=Qt.AlignmentFlag.AlignLeft)
    layout.addWidget(w.source_settings)
    w.source_settings.hide()
    layout.addStretch()

    w.template_summary = text('Шаблон ещё не выбран', 'coreMeta')
    w.options_card, options = section('Папка и параметры', role='coreSubsection')
    w.options_layout = options
    w.output_path = QLineEdit(str(Path.home() / 'Documents' / 'DocFlow Lite'))
    labeled_input(options, 'Куда сохранить', w.output_path, accessible_name='Папка результатов')
    w.output_btn = w.button('Выбрать папку', w.select_output, 'folder')
    options.addWidget(w.output_btn, alignment=Qt.AlignmentFlag.AlignLeft)
    w.run_hint = text('Для каждого запуска создаётся отдельная папка.', 'muted')
    options.addWidget(w.run_hint)
    w.name_selector = QComboBox()
    labeled_input(options, 'Столбец для названий папок строк', w.name_selector)
    w.folder_preview = text('', 'muted')
    options.addWidget(w.folder_preview)
    w.name_selector.currentTextChanged.connect(lambda: update_folder_preview(w))
    w.open_after = QCheckBox('Открыть папку после завершения')
    options.addWidget(w.open_after)
    w.check_btn = w.button('Проверить все строки ещё раз', w.check_all, 'check')
    options.addWidget(w.check_btn, alignment=Qt.AlignmentFlag.AlignLeft)
    w.progress = QProgressBar()
    w.progress.setRange(0, 100)
    w.progress.setTextVisible(False)
    options.addWidget(w.progress)
    w.progress_label = text('Документы ещё не созданы', 'muted')
    options.addWidget(w.progress_label)
    w.generate_btn = w.button('Создать документы', w.start_generation, primary=True)
    w.ready_card = QFrame()
    w.readiness = text('', 'muted')
    w.ready_details = text('', 'muted')
    w.ready_details.hide()


def toggle_source_settings(w, expanded):
    w.source_settings_btn.setChecked(expanded)
    w.source_settings.setVisible(expanded)
    if expanded:
        page = w.pages.widget(0)
        w.encoding_selector.setFocus(Qt.FocusReason.OtherFocusReason)
        QTimer.singleShot(0, page, lambda: page.ensureWidgetVisible(w.encoding_selector, 8, 8)
                          if w.encoding_selector.hasFocus() else None)


def add_preview_selectors(layout, row, template):
    for caption, selector in (('Строка таблицы', row), ('Шаблон Word', template)):
        selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        selector.setMinimumContentsLength(12)
        labeled_input(layout, caption, selector)


def build_result(w):
    page,layout=w.page()
    w.result_card,body=section(role='coreResult')
    layout.addWidget(w.result_card)
    w.result_summary=text('Документы ещё не созданы','coreMeta')
    w.result_counts = CoreCounts((('Документы Word', 'coreCountValue'), ('Обработано строк', 'coreCountGood'),
                                    ('Пропущено строк', 'coreCountBad')))
    body.addWidget(w.result_counts)
    w.result_path=text('','muted')
    w.result_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
    w.result_path.setAccessibleName('Папка созданного комплекта')
    body.addWidget(w.result_path)
    w.result_empty = text('Документы не созданы. Откройте отчёт, чтобы узнать, какие строки нужно исправить.', 'muted')
    body.addWidget(w.result_empty)
    w.result_files=QListView()
    w.result_files.setObjectName('coreResultFiles')
    w.result_files.setAccessibleName('Созданные документы Word')
    w.result_files.setMinimumHeight(100)
    w.result_files.setUniformItemSizes(True)
    w.result_files.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
    w.result_files.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    w.result_files_model=ResultFilesModel(w.result_files)
    w.result_files.setModel(w.result_files_model)
    actions=ActionBar();body.addWidget(actions)
    w.result_file_btn=w.button('Открыть документ',lambda:open_primary_result(w),'document',primary=True)
    w.result_file_btn.setEnabled(False)
    w.result_open_btn=w.button('Показать в папке',w.open_result,'folder')
    w.result_open_btn.setEnabled(False);actions.addWidget(w.result_open_btn)
    w.report_btn=w.button('Открыть отчёт',w.open_report,'check')
    w.report_btn.setEnabled(False);actions.addWidget(w.report_btn)
    w.new_run_btn = w.button('Настройки нового запуска', lambda checked: toggle_new_run(w, checked))
    w.new_run_btn.setCheckable(True)
    actions.addWidget(w.new_run_btn)
    body.addWidget(w.result_files)
    w.result_report_btn = w.button('Обработанные и пропущенные строки',
                                   lambda checked: w.result_report.setVisible(checked))
    w.result_report_btn.setCheckable(True)
    body.addWidget(w.result_report_btn, alignment=Qt.AlignmentFlag.AlignLeft)
    w.result_files.selectionModel().currentChanged.connect(
        lambda current, _: sync_result_actions(w))
    w.result_files.activated.connect(lambda _:w.open_result_file())
    w.result_report=QTextBrowser();w.result_report.setMinimumHeight(100)
    w.result_report.setAccessibleName('Обработанные и пропущенные строки')
    w.result_report.setOpenExternalLinks(False);body.addWidget(w.result_report);w.result_report.hide()
    layout.addWidget(w.options_card)
    layout.addStretch()


def toggle_new_run(w, expanded):
    w.update_readiness()
    if not expanded:
        w.new_run_btn.setFocus(Qt.FocusReason.OtherFocusReason)
        w.pages.widget(3).verticalScrollBar().setValue(0)
    if expanded:
        page = w.pages.currentWidget()
        field = w.output_path
        field.setFocus(Qt.FocusReason.OtherFocusReason)

        def reveal_field():
            if w.pages.currentWidget() is page and w.new_run_btn.isChecked() and w.focusWidget() is field:
                center = field.mapTo(page.widget(), field.rect().center())
                page.ensureVisible(center.x(), center.y(), 0, field.height() // 2 + 12)

        # The scroll area's range grows after the options card is laid out.
        QTimer.singleShot(0, page, reveal_field)


def sync_result_actions(w):
    has_file = w.result_files.currentIndex().isValid()
    available = bool(w.last_result) and not w._busy
    label = 'Открыть документ' if has_file else 'Открыть отчёт'
    hint = 'Открыть выбранный DOCX' if has_file else 'Посмотреть обработанные и пропущенные строки'
    w.result_file_btn.setText(label)
    w.result_file_btn.setAccessibleName(label)
    w.result_file_btn.setToolTip(hint)
    w.result_file_btn.setAccessibleDescription(hint)
    w.result_file_btn.setEnabled(available)
    w.result_file_btn.setVisible(w.pages.currentIndex() == 3 and available)
    w.report_btn.setVisible(has_file)
    w.result_empty.setVisible(bool(w.last_result) and not w.result_files_model.rowCount())


def open_primary_result(w):
    if not w.result_file_btn.isEnabled():
        return
    if w.result_files.currentIndex().isValid():
        w.open_result_file()
    else:
        w.open_report()


def update_folder_preview(w):
    if not w.table or not w.table.records:
        w.folder_preview.clear()
        return
    record=w.table.records[0]
    value=record.values.get(w.name_selector.currentText(),'')
    w.folder_preview.setText(f'Пример папки: row_{record.row_number:04d}_{safe_name(value)}')

def readiness(w,valid,message):
    loaded=bool(w.table);w.empty_card.setVisible(not loaded);w.source_card.setVisible(loaded);w.result_card.setVisible(bool(w.last_result))
    w.template_list.setVisible(bool(w.templates));w.mapping_table.setVisible(loaded and bool(w.active_templates()))
    w.templates_empty.setVisible(not w.templates)
    w.template_summary.setVisible(bool(w.templates))
    w.reload_btn.setVisible(loaded)
    checked=w._full_check is not None and w._full_check[0]==w.validation_signature()
    states=[loaded,bool(w.active_templates()),checked,bool(w.last_result)]
    page = w.pages.currentIndex()
    steps = ('1  Таблица', '2  Шаблоны', '3  Проверка', '4  Результат' if w.last_result else '4  Создание')
    for i, (button, complete) in enumerate(zip(w.route_buttons, states)):
        button.setProperty('complete', complete)
        button.setChecked(page == i)
        button.setEnabled(not w._busy)
        button.setText(steps[i])
        button.setAccessibleName(steps[i])
        status = 'Шаг завершён' if complete else 'Шаг не завершён'
        if page == i:
            status = 'Текущий шаг. ' + status
        button.setToolTip(status)
        button.setAccessibleDescription(status)
        button.style().unpolish(button)
        button.style().polish(button)
    w.source_check.setVisible(checked)
    if checked:
        w.source_check.setText(f'Готовы: {w._full_check[2] - w._full_check[1]} · с ошибками: {w._full_check[1]}')
    show_options = not w.last_result or w.new_run_btn.isChecked()
    w.run_hint.setText('Предыдущий комплект останется доступен, пока новый не создан.'
                       if w.last_result else 'Для каждого запуска создаётся отдельная папка.')
    w.progress.setVisible(w._busy or w.progress.value() > 0)
    w.progress_label.setVisible(w._busy or w.progress.value() > 0 or w.operation_notice.isVisible())
    for control in (w.result_open_btn, w.report_btn):
        control.setEnabled(bool(w.last_result) and not w._busy)
    w.options_card.setVisible(show_options)
    w.new_run_btn.setEnabled(not w._busy)
    w.new_run_btn.setText('Свернуть' if w.new_run_btn.isChecked() else 'Новый запуск')
    w.new_run_btn.setAccessibleName(w.new_run_btn.text())
    w.new_run_btn.setToolTip('Свернуть параметры нового запуска' if w.new_run_btn.isChecked()
                             else 'Подготовить новый комплект, сохранив предыдущий')
    w.select_first_table.setEnabled(not w._busy)
    w.core_back.setVisible(0 < page < 4 and not w._busy)
    w.core_next.setVisible(page in (1, 2) or page == 0 and loaded or page == 3 and not valid and show_options)
    w.generate_btn.setVisible(page == 3 and valid and show_options and w.cancel_btn.isHidden())
    generate_label = 'Создать новый комплект' if w.last_result else 'Создать документы'
    w.generate_btn.setText(generate_label)
    w.generate_btn.setAccessibleName(generate_label)
    generate_style = '' if w.last_result else 'primary'
    if w.generate_btn.objectName() != generate_style:
        w.generate_btn.setObjectName(generate_style)
        w.generate_btn.style().unpolish(w.generate_btn)
        w.generate_btn.style().polish(w.generate_btn)
    sync_result_actions(w)
    w._sync_footer_status()
    title=('Выбрать таблицу' if not loaded else 'К шаблонам →','Добавить шаблон Word' if not w.active_templates() else 'К проверке полей →','Проверить все строки' if not checked else 'К созданию документов →')[min(page,2)]
    if not loaded:title='Выбрать таблицу'
    elif not w.active_templates() and page != 0:title='Добавить шаблон Word'
    elif page==3 and not valid:title='Проверить связь полей →'
    if not loaded:hint='Откройте таблицу Excel или CSV для нового комплекта.'
    elif page==0:hint='Перейти к выбору шаблонов Word.'
    elif not w.active_templates():hint='Добавьте один или несколько Word-шаблонов для этой таблицы.'
    elif page==1:hint='Сопоставить поля шаблонов со столбцами таблицы.'
    elif page==3:hint='Вернуться к полям и исправить ошибки сопоставления.'
    elif checked:hint='Перейти к папке и созданию документов.'
    else:hint='Проверить все строки перед созданием документов.'
    if w._busy:hint='Дождитесь завершения операции. '+hint
    w.core_next.setText(title);w.core_next.setAccessibleName(title)
    w.core_next.setToolTip(hint);w.core_next.setAccessibleDescription(hint)
    w.core_next.setEnabled(not w._busy and (page!=2 or valid or not loaded or not w.active_templates()));w.generate_btn.setEnabled(valid and not w._busy)
    update_folder_preview(w)
    feedback=(f'Все {w._full_check[2]} строк проверены. С ошибками: {w._full_check[1]}.' if checked else 'Поля связаны. Все строки ещё не проверены.' if valid else message)
    w.mapping_feedback.setText(feedback);w.readiness.setText(feedback)

def next_step(w):
    page=w.pages.currentIndex()
    if not w.table:w.navigate(0);w.select_data();return
    if page==0:
        w.navigate(1)
        return
    if not w.active_templates():w.navigate(1);w.select_templates();return
    if page==1:
        if w.active_templates():w.navigate(2)
        else:w.select_templates()
    elif page==2:
        if w._full_check and w._full_check[0]==w.validation_signature():w.navigate(3)
        else:w.check_all()
    elif page==3:w.navigate(2)
