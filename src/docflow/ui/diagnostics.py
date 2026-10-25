"""Bounded local diagnostics, never an automatic upload."""
import logging,os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from ..errors import DocFlowError
def diagnostic_path():
 base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local')) if os.name=='nt' else Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))
 return base/'DocFlowLite'/'logs'/'diagnostic.log'
def record_exception(context,exc):
 logger=logging.getLogger('docflow.local')
 try:
  if not logger.handlers:
   path=diagnostic_path();path.parent.mkdir(parents=True,exist_ok=True);handler=RotatingFileHandler(path,maxBytes=2*1024**2,backupCount=2,encoding='utf-8');handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'));logger.addHandler(handler);logger.setLevel(logging.INFO);logger.propagate=False
  logger.error('%s: %s',context,type(exc).__name__,exc_info=(type(exc),exc,exc.__traceback__))
 except OSError:pass
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
