"""Backup and restore choices within the workshop."""
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFileDialog, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from ...safety import safe_name
from ...service.backup import create_backup, inspect_backup, restore_backup
from ...service.validation import ServiceError
from ..flow import ActionBar
from ..settings import preferences
from ..theme import COLORS
from ..widgets import card, text
from .widgets import button, confirm


class BackupPage(QWidget):
    def __init__(self, workspace, title, heading, description):
        super().__init__(workspace)
        self.workspace = workspace
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll)
        body = QWidget()
        self.scroll.setWidget(body)
        self.content = QVBoxLayout(body)
        self.panel, self.controls = card(heading, description)
        self.add_panel(self.panel)
        self.error = text('', 'error')
        self.error.setStyleSheet(f'border: 1px solid {COLORS["error"]}; border-radius: 5px; padding: 6px;')
        self.error.setAccessibleName('Ошибка резервного копирования')
        self.add_panel(self.error)
        self.error.hide()

    def add_panel(self, widget):
        widget.setMaximumWidth(760)
        self.content.addWidget(widget)

    def show_error(self, message):
        self.error.setText('Ошибка. ' + message)
        self.error.show()
        QTimer.singleShot(0,self,lambda:self.scroll.ensureWidgetVisible(self.error))

    def run(self, action, done, label, *, on_error=None):
        self.error.hide()
        return self.workspace.run(action, done, label, on_error=on_error or self.show_error, inline_error=True)


class CreateBackupPage(BackupPage):
    def __init__(self, workspace):
        super().__init__(workspace, 'Создать резервную копию', 'Место и имя файла',
                         'Выберите, куда сохранить ZIP, и проверьте точное имя файла.')
        self.folder = workspace.backup_directory()
        self.folder_label = text(str(self.folder), 'muted')
        self.folder_label.setAccessibleName('Папка назначения')
        self.controls.addWidget(self.folder_label)
        actions = ActionBar()
        self.controls.addWidget(actions)
        button(actions, 'Выбрать папку назначения', self.choose_folder)
        self.controls.addWidget(text('Имя ZIP', 'section'))
        self.filename = QLineEdit(f'DocFlow-{datetime.now():%Y%m%d-%H%M%S}.service-backup.zip')
        self.filename.setAccessibleName('Имя резервного ZIP')
        self.controls.addWidget(self.filename)
        self.target_label = text('', 'muted')
        self.controls.addWidget(self.target_label)
        self.filename.textChanged.connect(self.update_target)
        self.update_target()
        actions = ActionBar()
        self.controls.addWidget(actions)
        self.create_button = button(actions, 'Создать ZIP', self.create, primary=True)
        result, actions = card('Резервная копия создана')
        self.result = result
        self.result_name = text('', 'section')
        actions.addWidget(self.result_name)
        self.result_details = text('', 'muted')
        actions.addWidget(self.result_details)
        bar = ActionBar()
        actions.addWidget(bar)
        button(bar, 'Открыть расположение', self.open_location)
        button(bar, 'Готово', workspace.back_page)
        self.add_panel(self.result)
        self.result.hide()
        self.content.addStretch()
        self.archive = None

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Выбрать папку назначения', str(self.folder))
        if folder:
            self.folder = Path(folder)
            self.folder_label.setText(str(self.folder))
            self.error.hide()
            self.update_target()

    def archive_name(self):
        raw = self.filename.text().strip()
        return raw if not raw or raw.lower().endswith('.zip') else raw + '.zip'

    def update_target(self):
        name = self.archive_name()
        self.target_label.setText('Файл будет сохранён как ' + name if name else 'Введите имя ZIP-файла.')
        self.filename.setStyleSheet('')
        self.error.hide()

    def create(self):
        name = self.archive_name()
        if not name or safe_name(name) != name or name.casefold() == '.zip':
            self.show_error('Введите имя файла без пути и недопустимых символов (до 64 знаков).')
            self.filename.setStyleSheet(f'border: 1px solid {COLORS["error"]};')
            self.filename.setFocus()
            return
        target = self.folder / name
        store = self.workspace.store

        def write():
            if not target.parent.is_dir():
                raise ServiceError('Выбранная папка недоступна. Выберите существующую папку.')
            if target.is_dir():
                raise ServiceError('С таким именем уже существует папка. Укажите другое имя ZIP.')
            created = create_backup(store, target)
            details = created.stat()
            return created, details.st_size, datetime.fromtimestamp(details.st_mtime)

        def saved(result):
            self.archive, size, date = result
            preferences().setValue('workspace/v2/backup/lastDirectory', str(self.archive.parent))
            self.result_name.setText(self.archive.name)
            size_label = f'{size:,}'.replace(',', ' ')
            self.result_details.setText(f'{size_label} Б · {date:%d.%m.%Y %H:%M:%S}\n{self.archive.parent}')
            self.result_name.setToolTip(str(self.archive))
            self.result.show()
            self.panel.hide()
            self.workspace.message.setText('ZIP создан. Проверяйте и восстанавливайте его из раздела «Резервные копии».')

        self.run(write, saved, 'Создаю резервный ZIP…')

    def open_location(self):
        if self.archive:
            self.workspace.open_local(self.archive.parent)


class RestoreBackupPage(BackupPage):
    def __init__(self, workspace):
        super().__init__(workspace, 'Восстановить резервную копию', '1. Проверить архив',
                         'Сначала проверьте архив. Затем выберите место для отдельного проекта.')
        self.archive = None
        self.checked = None
        self.target = None
        self.source = text('ZIP-файл ещё не выбран.', 'muted')
        self.source.setAccessibleName('Выбранная резервная копия')
        self.controls.addWidget(self.source)
        bar = ActionBar()
        self.controls.addWidget(bar)
        button(bar, 'Выбрать ZIP-файл', self.choose_archive)
        self.check_button = button(bar, 'Проверить целостность', self.check, primary=True)
        self.check_button.setEnabled(False)
        verified, steps = card('2. Выбрать место восстановления')
        self.verified = verified
        self.verification = text('', 'muted')
        self.verification.setAccessibleName('Результат проверки архива')
        steps.addWidget(self.verification)
        self.folder_label = text('Папка назначения ещё не выбрана.', 'muted')
        self.folder_label.setAccessibleName('Новая папка проекта')
        steps.addWidget(self.folder_label)
        bar = ActionBar()
        steps.addWidget(bar)
        self.folder_button = button(bar, 'Выбрать место для новой папки', self.choose_folder)
        self.restore_button = button(bar, 'Восстановить копию', self.restore, primary=True)
        self.restore_button.setEnabled(False)
        self.add_panel(self.verified)
        self.verified.hide()
        self.content.addStretch()

    def clear_verification(self):
        self.checked = None
        self.target = None
        self.folder_label.setText('Папка назначения ещё не выбрана.')
        self.restore_button.setEnabled(False)
        self.verified.hide()

    def choose_archive(self):
        archive, _ = QFileDialog.getOpenFileName(self, 'Выбрать ZIP для проверки',
                                                 str(self.workspace.backup_directory()), 'ZIP (*.zip)')
        if archive:
            self.archive = Path(archive)
            self.source.setText(self.archive.name)
            self.source.setToolTip(str(self.archive))
            self.clear_verification()
            self.check_button.setEnabled(True)
            self.error.hide()

    def check(self):
        if not self.archive:
            return
        self.clear_verification()

        def verified(info):
            self.checked = info
            self.verification.setText(f"Целостность подтверждена. Проверены SHA-256 и SQLite (схема {info['schema']}). "
                                      f"Файлов проверено: {info['files']}.")
            self.verified.show()
            self.folder_button.setFocus(Qt.FocusReason.OtherFocusReason)
            QTimer.singleShot(0,self,lambda:self.scroll.ensureWidgetVisible(self.verified,8,8))
            self.workspace.message.setText('Архив проверен. Выберите папку для отдельного проекта.')

        self.run(lambda: inspect_backup(self.archive), verified, 'Проверяю архив и целостность базы…')

    def choose_folder(self):
        if not self.checked:
            return
        folder = QFileDialog.getExistingDirectory(self, 'Выбрать место для новой папки проекта',
                                                   str(self.workspace.backup_directory()))
        if folder:
            unique_name = f'DocFlow-Restored-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}'
            self.target = Path(folder) / unique_name
            self.folder_label.setText(str(self.target))
            self.restore_button.setEnabled(True)

    def restore(self):
        if not self.checked or not self.target:
            return
        archive, target, expected_hash = self.archive, self.target, self.checked['sha256']
        if not confirm(self, f'Восстановить «{archive.name}» в новую папку?\n{target}\n'
                             'Активный проект сменится после успешной проверки копии.',
                       'Восстановить копию', cancel='Вернуться'):
            return

        def finished(root):
            preferences().setValue('workspace/v2/backup/lastDirectory', str(archive.parent))
            self.workspace._restored_target = root
            self.workspace.open_project(root)

        def failed(message):
            self.clear_verification()
            self.show_error(message)

        self.run(lambda: restore_backup(archive, target, expected_sha256=expected_hash),
                 finished, 'Восстанавливаю в отдельную папку…', on_error=failed)
