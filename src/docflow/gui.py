import copy
import sys
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

from . import __version__
from .batch import BatchResult, Prepared, generate, prepare
from .cli import demo_profile
from .data import load_table
from .errors import DocFlowError
from .profile import Profile
from .templates import Template
from .validation import Rule, values_for, validate_mapping

KINDS = {"Текст": "text", "Число ≥ 0": "number", "Email": "email", "Дата ГГГГ-ММ-ДД": "date"}

STYLE = """
QWidget {font-family: 'Segoe UI', 'DejaVu Sans'; font-size: 13px; color:#162840;}
QMainWindow, #work {background:#f3f5f9;}
#rail {background:#122842; min-width:190px; max-width:190px;}
#rail QLabel {color:#aebed0;} #brand {color:white; font-size:23px; font-weight:700;}
#rail #active {color:white; background:#234362; border-radius:8px; padding:13px;}
#title {font-size:27px; font-weight:700;} #muted {color:#64758a;}
#section {font-size:16px; font-weight:600;}
QPushButton {background:white; border:1px solid #d6dfeb; border-radius:7px; padding:10px 15px;}
QPushButton:hover {background:#edf3ff; border-color:#81a6ed;}
QPushButton:disabled {color:#93a0b0; background:#eef1f5;}
QPushButton#primary {background:#285de5; color:white; border:0; font-weight:600;}
QPushButton#primary:disabled {background:#a3b8eb;}
QLineEdit, QComboBox {background:white; border:1px solid #d6dfeb; border-radius:5px; padding:7px;}
QTableWidget, QTextBrowser, QListWidget {background:white; border:1px solid #dce3ed; border-radius:5px; gridline-color:#edf0f5;}
QHeaderView::section {background:#edf2fa; padding:9px; border:0; border-bottom:1px solid #dce3ed; font-weight:600;}
QTabWidget::pane {border:0; background:transparent;}
QTabBar::tab {padding:11px 16px; color:#6b7d92; background:#e8edf5; margin-right:3px; border-top-left-radius:6px; border-top-right-radius:6px;}
QTabBar::tab:selected {background:white; color:#2355d3;}
QProgressBar {border:0; background:#dfe7f4; height:7px; border-radius:3px; text-align:center;}
QProgressBar::chunk {background:#2a67e8; border-radius:3px;}
#status {background:#e8f3ed; color:#236047; border-radius:6px; padding:10px;}
"""


def label(text, name=None):
    obj = QLabel(text)
    obj.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        obj.setObjectName(name)
    obj.setWordWrap(True)
    return obj


class GenerationWorker(QThread):
    advanced = Signal(int, int)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, prepared: Prepared, output: Path):
        super().__init__()
        self.prepared = prepared
        self.output = output

    def run(self):
        try:
            result = generate(self.prepared, self.output, lambda a, b: self.advanced.emit(a, b))
            self.completed.emit(result)
        except (DocFlowError, OSError) as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("Неожиданная ошибка. Исходники не изменены; проверьте входные файлы")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"DocFlow Lite {__version__} — локальная генерация документов")
        self.resize(1360, 900)
        self.setMinimumSize(1050, 720)
        self.table = None
        self.templates = []
        self.worker = None
        self.last_result = None
        self.encoding = "auto"
        self.sheet = None
        self.setStyleSheet(STYLE)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        rail = QFrame()
        rail.setObjectName("rail")
        nav = QVBoxLayout(rail)
        nav.setContentsMargins(19, 29, 19, 24)
        nav.setSpacing(20)
        nav.addWidget(label("DocFlow\nLite", "brand"))
        nav.addWidget(label("ЛОКАЛЬНЫЙ ИНСТРУМЕНТ"))
        nav.addSpacing(26)
        nav.addWidget(label("01  Подготовка", "active"))
        nav.addWidget(label("02  Проверка данных"))
        nav.addWidget(label("03  Пакет Word"))
        nav.addStretch()
        nav.addWidget(label("Файлы обрабатываются\nна этом компьютере"))
        nav.addWidget(label(f"Бета {__version__} · Без телеметрии"))
        outer.addWidget(rail)
        self.work = QWidget()
        self.work.setObjectName("work")
        layout = QVBoxLayout(self.work)
        layout.setContentsMargins(28, 25, 28, 20)
        layout.setSpacing(13)
        titlebar = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label("Документы из вашей таблицы", "title"))
        titles.addWidget(label("Загрузите данные, сопоставьте поля и проверьте результат", "muted"))
        titlebar.addLayout(titles, 1)
        self.demo_btn = QPushButton("Открыть демопример")
        self.demo_btn.clicked.connect(self.load_demo)
        titlebar.addWidget(self.demo_btn)
        layout.addLayout(titlebar)
        inputs = QGridLayout()
        self.data_path = QLineEdit()
        self.data_path.setReadOnly(True)
        self.data_path.setPlaceholderText("XLSX или CSV с заголовками в первой строке")
        self.load_btn = QPushButton("Выбрать таблицу")
        self.load_btn.clicked.connect(self.select_data)
        self.add_btn = QPushButton("Добавить DOCX")
        self.add_btn.clicked.connect(self.select_templates)
        inputs.addWidget(self.data_path, 0, 0)
        inputs.addWidget(self.load_btn, 0, 1)
        inputs.addWidget(self.add_btn, 0, 2)
        self.template_list = QListWidget()
        self.template_list.setMaximumHeight(72)
        self.template_list.setMinimumHeight(55)
        inputs.addWidget(self.template_list, 1, 0)
        self.remove_btn = QPushButton("Убрать шаблон")
        self.remove_btn.clicked.connect(self.remove_template)
        inputs.addWidget(self.remove_btn, 1, 1)
        presets = QVBoxLayout()
        self.open_profile_btn = QPushButton("Открыть настройки")
        self.save_profile_btn = QPushButton("Сохранить настройки")
        self.open_profile_btn.clicked.connect(self.open_profile)
        self.save_profile_btn.clicked.connect(self.save_profile)
        presets.addWidget(self.open_profile_btn)
        presets.addWidget(self.save_profile_btn)
        inputs.addLayout(presets, 1, 2)
        inputs.setColumnStretch(0, 1)
        layout.addLayout(inputs)
        self.stats = label("Начните с демопримера или выберите свои файлы", "muted")
        layout.addWidget(self.stats)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tabs = QTabWidget()
        self.source_table = QTableWidget()
        self.source_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.source_table.setAlternatingRowColors(True)
        self.tabs.addTab(self.source_table, "Данные")
        preview_page = QWidget()
        pv = QVBoxLayout(preview_page)
        self.row_selector = QComboBox()
        self.template_selector = QComboBox()
        self.row_selector.currentIndexChanged.connect(self.update_preview)
        self.template_selector.currentIndexChanged.connect(self.update_preview)
        pv.addWidget(self.row_selector)
        pv.addWidget(self.template_selector)
        pv.addWidget(label("Текстовый просмотр. Вёрстку DOCX проверяйте в Word или LibreOffice", "muted"))
        self.preview_text = QTextBrowser()
        pv.addWidget(self.preview_text)
        self.tabs.addTab(preview_page, "Предпросмотр")
        self.report_text = QTextBrowser()
        self.report_text.setPlainText("После генерации здесь появится отчёт по каждой ошибке")
        self.tabs.addTab(self.report_text, "Отчёт")
        splitter.addWidget(self.tabs)
        mapping_page = QWidget()
        mp = QVBoxLayout(mapping_page)
        mp.setContentsMargins(10, 0, 0, 0)
        mp.addWidget(label("Сопоставление полей", "section"))
        mp.addWidget(label("Шаблон: {{client}} → столбец «Клиент»", "muted"))
        self.mapping_table = QTableWidget(0, 4)
        self.mapping_table.setHorizontalHeaderLabels(["Переменная", "Столбец", "Проверка", "Нужно"])
        self.mapping_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.mapping_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.mapping_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.mapping_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.mapping_table.verticalHeader().setVisible(False)
        mp.addWidget(self.mapping_table, 1)
        self.name_selector = QComboBox()
        mp.addWidget(label("Столбец для названий папок", "muted"))
        mp.addWidget(self.name_selector)
        self.check_btn = QPushButton("Проверить все записи")
        self.check_btn.clicked.connect(self.check_all)
        mp.addWidget(self.check_btn)
        splitter.addWidget(mapping_page)
        splitter.setSizes([550, 500])
        layout.addWidget(splitter, 1)
        output_row = QHBoxLayout()
        self.output_path = QLineEdit(str(Path.cwd() / "docflow-output"))
        self.output_btn = QPushButton("Папка результата")
        self.output_btn.clicked.connect(self.select_output)
        output_row.addWidget(self.output_path, 1)
        output_row.addWidget(self.output_btn)
        layout.addLayout(output_row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        bottom = QHBoxLayout()
        self.status = label("Исходная таблица и шаблоны не изменяются", "status")
        bottom.addWidget(self.status, 1)
        self.folder_btn = QPushButton("Открыть результат")
        self.folder_btn.setEnabled(False)
        self.folder_btn.clicked.connect(self.open_result)
        bottom.addWidget(self.folder_btn)
        self.generate_btn = QPushButton("Создать пакет документов")
        self.generate_btn.setObjectName("primary")
        self.generate_btn.clicked.connect(self.start_generation)
        bottom.addWidget(self.generate_btn)
        layout.addLayout(bottom)
        outer.addWidget(self.work, 1)

    def error(self, text):
        self.status.setText("Ошибка: " + str(text))
        self.report_text.setPlainText(str(text))
        self.tabs.setCurrentIndex(2)

    def load_demo(self):
        try:
            self.apply_profile(Profile.load(demo_profile()))
        except (DocFlowError, OSError) as exc:
            self.error(exc)

    def apply_profile(self, profile):
        try:
            prepared = prepare(profile)
            self.table, self.templates = prepared.table, list(prepared.templates)
            self.encoding, self.sheet = profile.encoding, profile.sheet
            self.refresh(profile.mapping, profile.rules, profile.name_column)
            self.status.setText("Файлы загружены. Проверьте предпросмотр перед генерацией")
        except (DocFlowError, OSError) as exc:
            self.error(exc)

    def select_data(self):
        path, _ = QFileDialog.getOpenFileName(self, "Открыть таблицу", "", "Таблицы (*.xlsx *.csv)")
        if path:
            try:
                table = load_table(path)
                self.table, self.encoding, self.sheet = table, "auto", None
                self.refresh()
            except (DocFlowError, OSError) as exc:
                self.error(exc)

    def select_templates(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "DOCX с переменными {{поле}}", "", "Word (*.docx)")
        if paths:
            try:
                added = [Template.load(p) for p in paths]
                templates = {t.path: t for t in self.templates + added}
                if len(templates) > 20:
                    raise DocFlowError("Не более 20 шаблонов")
                old_mapping, old_rules = self.mapping()
                self.templates = list(templates.values())
                self.refresh(old_mapping, old_rules)
            except (DocFlowError, OSError) as exc:
                self.error(exc)

    def remove_template(self):
        index = self.template_list.currentRow()
        if index >= 0:
            mapping, rules = self.mapping()
            del self.templates[index]
            self.refresh(mapping, rules)

    def mapping(self):
        mapping, rules = {}, {}
        for row in range(self.mapping_table.rowCount()):
            field = self.mapping_table.item(row, 0).text()
            column = self.mapping_table.cellWidget(row, 1).currentText()
            if column:
                mapping[field] = column
                rules[field] = Rule(self.mapping_table.cellWidget(row, 3).isChecked(), self.mapping_table.cellWidget(row, 2).currentData())
        return mapping, rules

    def refresh(self, saved=None, rules=None, name_column=""):
        saved, rules = saved or {}, rules or {}
        self.row_selector.blockSignals(True)
        self.template_selector.blockSignals(True)
        self.row_selector.clear()
        self.template_selector.clear()
        self.template_list.clear()
        self.name_selector.clear()
        for t in self.templates:
            self.template_list.addItem(t.path.name + "  ·  " + ", ".join(sorted(t.fields)))
            self.template_selector.addItem(t.path.name)
        fields = sorted(set().union(*(t.fields for t in self.templates)))
        self.mapping_table.setRowCount(len(fields))
        headers = self.table.headers if self.table else ()
        for row, field in enumerate(fields):
            item = QTableWidgetItem(field)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.mapping_table.setItem(row, 0, item)
            column = QComboBox()
            column.addItem("")
            column.addItems(list(headers))
            candidate = saved.get(field, field if field in headers else "")
            column.setCurrentText(candidate if candidate in headers else "")
            kind = QComboBox()
            for title, value in KINDS.items():
                kind.addItem(title, value)
            rule = rules.get(field, Rule())
            kind.setCurrentIndex(kind.findData(rule.kind))
            required = QCheckBox()
            required.setChecked(rule.required)
            self.mapping_table.setCellWidget(row, 1, column)
            self.mapping_table.setCellWidget(row, 2, kind)
            self.mapping_table.setCellWidget(row, 3, required)
            column.currentTextChanged.connect(self.update_preview)
            kind.currentIndexChanged.connect(self.update_preview)
            required.stateChanged.connect(self.update_preview)
            self.mapping_table.setRowHeight(row, 42)
        self.source_table.clear()
        self.source_table.setColumnCount(len(headers))
        self.source_table.setHorizontalHeaderLabels(list(headers))
        if self.table:
            self.data_path.setText(str(self.table.source))
            shown = self.table.records[:100]
            self.source_table.setRowCount(len(shown))
            self.source_table.setVerticalHeaderLabels([str(r.row_number) for r in shown])
            for row, record in enumerate(shown):
                for col, header in enumerate(headers):
                    self.source_table.setItem(row, col, QTableWidgetItem(record.values[header][:250]))
            self.source_table.resizeColumnsToContents()
            self.source_table.horizontalHeader().setStretchLastSection(True)
            self.name_selector.addItems(list(headers))
            if name_column in headers:
                self.name_selector.setCurrentText(name_column)
            for n, record in enumerate(self.table.records):
                self.row_selector.addItem(f"Запись {n + 1} · строка {record.row_number}")
            self.stats.setText(f"Записей: {len(self.table.records)}   ·   Шаблонов: {len(self.templates)}   ·   Показаны первые {len(shown)} строк   ·   Все данные демонстрационные" if self.table.source.parent == demo_profile().parent else f"Записей: {len(self.table.records)}   ·   Шаблонов: {len(self.templates)}   ·   Показаны первые {len(shown)} строк")
        self.row_selector.blockSignals(False)
        self.template_selector.blockSignals(False)
        self.update_preview()

    def profile(self):
        if not self.table or not self.templates:
            raise DocFlowError("Сначала выберите таблицу и DOCX-шаблоны")
        mapping, rules = self.mapping()
        return Profile(self.table.source, [t.path for t in self.templates], mapping, rules, self.name_selector.currentText(), self.encoding, self.sheet)

    def snapshot(self):
        profile = copy.deepcopy(self.profile())
        fields = set().union(*(t.fields for t in self.templates))
        validate_mapping(self.table, fields, profile.mapping, profile.rules)
        if profile.name_column and profile.name_column not in self.table.headers:
            raise DocFlowError("Не найден столбец для имени папки")
        return Prepared(profile, copy.deepcopy(self.table), tuple(self.templates))

    def update_preview(self, *_):
        if not self.table or not self.templates or self.row_selector.currentIndex() < 0:
            return
        try:
            profile = self.profile()
            from .validation import validate_mapping
            validate_mapping(self.table, set().union(*(t.fields for t in self.templates)), profile.mapping, profile.rules)
            record = self.table.records[self.row_selector.currentIndex()]
            values, issues = values_for(record, profile.mapping, profile.rules)
            if issues:
                self.preview_text.setPlainText("Запись будет пропущена:\n\n" + "\n".join(f"{x.field}: {x.message}" for x in issues))
            else:
                self.preview_text.setPlainText(self.templates[max(0, self.template_selector.currentIndex())].preview(values))
        except (DocFlowError, OSError) as exc:
            self.preview_text.setPlainText(str(exc))

    def check_all(self):
        try:
            prepared = self.snapshot()
            issues = [x for record in prepared.table.records for x in values_for(record, prepared.profile.mapping, prepared.profile.rules)[1]]
            rejected = len({x.row for x in issues})
            self.status.setText(f"Проверено: {len(prepared.table.records)} записей. Без ошибок: {len(prepared.table.records) - rejected}. С ошибками: {rejected}")
            self.report_text.setPlainText("\n".join(f"Строка {x.row} · {x.field}: {x.message}" for x in issues) if issues else "Ошибок данных не обнаружено")
            self.tabs.setCurrentIndex(2)
        except (DocFlowError, OSError) as exc:
            self.error(exc)

    def open_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Открыть настройки", "", "Настройки (*.json)")
        if path:
            try:
                self.apply_profile(Profile.load(path))
            except (DocFlowError, OSError) as exc:
                self.error(exc)

    def save_profile(self):
        try:
            profile = self.profile()
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить настройки", "docflow-profile.json", "Настройки (*.json)")
            if path:
                profile.save(path)
                self.status.setText("Сопоставление и проверки сохранены в JSON")
        except (DocFlowError, OSError) as exc:
            self.error(exc)

    def select_output(self):
        path = QFileDialog.getExistingDirectory(self, "Папка для результатов", self.output_path.text())
        if path:
            self.output_path.setText(path)

    def start_generation(self):
        if self.worker and self.worker.isRunning():
            return
        try:
            prepared = self.snapshot()
            if not self.output_path.text().strip():
                raise DocFlowError("Выберите папку результата")
            self.worker = GenerationWorker(prepared, Path(self.output_path.text()))
            self.worker.advanced.connect(lambda a, b: self.progress.setValue(int(a * 100 / b)))
            self.worker.completed.connect(self.on_result)
            self.worker.failed.connect(self.error)
            self.worker.finished.connect(lambda: self.set_busy(False))
            self.set_busy(True)
            self.progress.setValue(0)
            self.status.setText("Создаю пакет из загруженных данных и шаблонов…")
            self.worker.start()
        except (DocFlowError, OSError) as exc:
            self.error(exc)

    def set_busy(self, busy):
        for widget in (self.demo_btn, self.load_btn, self.add_btn, self.remove_btn, self.open_profile_btn, self.save_profile_btn, self.mapping_table, self.name_selector, self.check_btn, self.generate_btn, self.output_btn, self.output_path):
            widget.setEnabled(not busy)

    def on_result(self, result: BatchResult):
        self.last_result = result
        self.folder_btn.setEnabled(True)
        self.progress.setValue(100)
        self.status.setText(f"Готово: {result.documents} DOCX · {result.accepted} записей обработано · {result.rejected} пропущено")
        self.report_text.setPlainText(f"Папка результата: {result.directory}\n\nСоздано DOCX: {result.documents}\nЗаписей с ошибками: {result.rejected}\n\n" + "\n".join(f"Строка {x.row} · {x.field}: {x.message}" for x in result.issues) + "\n\nПолный отчёт сохранён в report.json и report.csv")
        self.tabs.setCurrentIndex(2)

    def open_result(self):
        if self.last_result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_result.directory)))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Генерация продолжается", "Дождитесь завершения текущего пакета перед закрытием")
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

