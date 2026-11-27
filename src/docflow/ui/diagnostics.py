"""Bounded local diagnostics, never an automatic upload."""
import logging
import os
import re
from pathlib import Path
from logging.handlers import RotatingFileHandler
from threading import RLock
from .. import __version__
from ..errors import DocFlowError
from ..versioning import local_state_namespace

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)
_logger.propagate = False
_lock = RLock()
_MAX_BYTES = 2 * 1024**2
_CONTEXTS = {
    'Core operation', 'Core task', 'Core generation', 'Service worker', 'Service callback',
}
_PROJECT_RESULTS = {
    'not_open', 'opening', 'opened', 'error', 'upgrade_available', 'copy_required',
    'cancelled', 'locked', 'worker_error', 'error_handler_error', 'callback_error',
    'worker_still_running',
}
_MODULE = re.compile(r'docflow(?:\.[a-z][a-z0-9_]{0,63}){1,6}\Z')
_ERROR_TYPES = (
    FileNotFoundError, PermissionError, FileExistsError, TimeoutError,
    OSError, DocFlowError, ValueError, TypeError, RuntimeError,
)


def diagnostic_path():
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    else:
        base = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
    # Older releases may have written raw tracebacks. Start a separate log.
    return base / local_state_namespace(__version__) / 'logs' / 'technical.log'


def _record(level, message, *args):
    with _lock:
        path = diagnostic_path().absolute()
        try:
            for handler in _logger.handlers[:]:
                if handler.baseFilename != str(path):
                    _logger.removeHandler(handler)
                    handler.close()
            if not _logger.handlers:
                path.parent.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(path, maxBytes=_MAX_BYTES, backupCount=2, encoding='utf-8')
                handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
                _logger.addHandler(handler)
            _logger.log(level, 'version=%s ' + message, __version__, *args)
        except OSError:
            # Logging must not replace the actual error presented to the user.
            pass


def _error_type(exc):
    if exc is None:
        return 'none'
    return next((kind.__name__ for kind in _ERROR_TYPES if isinstance(exc, kind)), 'OtherError')


def record_project_event(result, exc=None):
    result = result if result in _PROJECT_RESULTS else 'other'
    _record(logging.INFO, 'project result=%s error_type=%s', result, _error_type(exc))


def record_exception(context, exc):
    # Report package code locations only. Traceback text, paths, source text,
    # exception chains, exception identifiers and frame locals may include data.
    frames = []
    trace = exc.__traceback__
    while trace is not None:
        module = trace.tb_frame.f_globals.get('__name__', '')
        if _MODULE.fullmatch(module):
            frames.append(f'{module}:{trace.tb_lineno}')
        trace = trace.tb_next
    context = context if context in _CONTEXTS else 'other'
    _record(logging.ERROR, 'operation=%s error_type=%s frames=%s',
            context, _error_type(exc), ','.join(frames[-6:]) or '-')


def read_diagnostics():
    with _lock:
        try:
            return diagnostic_path().read_text(encoding='utf-8')[-100000:]
        except FileNotFoundError:
            return ''

def friendly_error(exc):
 if isinstance(exc,FileNotFoundError):return 'Файл или папка недоступны. Проверьте путь и наличие файла.'
 if isinstance(exc,PermissionError):return 'Нет доступа к файлу. Проверьте права и закройте его в другой программе.'
 if isinstance(exc,FileExistsError):return 'Файл или папка уже существуют. Выберите новое имя; данные не заменены.'
 if isinstance(exc,OSError):return 'Не удалось выполнить файловую операцию. Проверьте свободное место, путь и доступ.'
 if isinstance(exc,DocFlowError):
  message=str(exc)
  if message=='Дата должна иметь формат ГГГГ-ММ-ДД':return 'Проверьте дату: ДД.ММ.ГГГГ в форме или ГГГГ-ММ-ДД в исходной таблице.'
  if message.startswith('Ошибка локальной базы:'):return 'Не удалось сохранить данные в локальной базе. Проверьте диск и доступ; подробности в диагностике.'
  return message
 return 'Не удалось выполнить операцию. Подробности сохранены в локальной диагностике.'
