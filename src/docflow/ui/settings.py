"""User interface preferences in a portable INI backend, with legacy read migration."""
import json
import os
from pathlib import Path
from PySide6.QtCore import QSettings, QStandardPaths


def preferences():
    folder = os.environ.get('DOCFLOW_SETTINGS_DIR')
    if not folder:
        folder = str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)) / 'DocFlowLite')
    return QSettings(str(Path(folder) / 'interface.ini'), QSettings.Format.IniFormat)


def load_widths(key):
    settings = preferences()
    raw = settings.value('columns/' + key)
    if raw is None:
        # Existing installations keep their choices. Read only; no registry writes.
        raw = QSettings('DocFlowLite', 'Interface').value('columns/' + key, {})
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return {}
    if not isinstance(raw, dict):
        return {}
    return {int(k): min(4096, max(48, int(v))) for k, v in raw.items()
            if str(k).isdigit() and str(v).isdigit()}


def save_widths(key, widths):
    settings = preferences()
    settings.setValue('columns/' + key, json.dumps({str(k): v for k, v in widths.items()}))
    settings.sync()
    return settings.status() == QSettings.Status.NoError
