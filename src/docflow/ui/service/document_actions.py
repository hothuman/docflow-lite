"""Explicit system-editor handoff; opening a DOCX is not printer confirmation."""
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox


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
