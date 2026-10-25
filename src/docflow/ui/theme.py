"""One shared theme for the workspace and top-level Qt dialogs."""
from pathlib import Path
import os,sys
from PySide6.QtGui import QFontDatabase
from functools import lru_cache
from PySide6.QtWidgets import QApplication
COLORS={'background':'#F4F7FC','rail':'#FFFFFF','surface':'#FFFFFF','input':'#FFFFFF','table':'#FFFFFF','alternate':'#F5F8FC','border':'#CED8E6','text':'#172B4D','muted':'#52647A','accent':'#1556D9','focus':'#1556D9','error':'#B42318','success':'#00776B','selection':'#E9F0FF'}
@lru_cache(maxsize=1)
def stylesheet():
 result=Path(__file__).with_name('theme.qss').read_text(encoding='utf-8')
 for key,value in COLORS.items():result=result.replace('@'+key+'@',value)
 return result
def apply_theme(app=None):
 app=app or QApplication.instance()
 # Qt's Windows offscreen plugin starts with no system font database.
 # Load installed fonts for meaningful automated geometry; do not bundle fonts.
 if app and sys.platform=='win32' and app.platformName()=='offscreen' and not QFontDatabase.families():
  folder=Path(os.environ.get('SYSTEMROOT','C:/Windows'))/'Fonts'
  for name in ('segoeui.ttf','segoeuib.ttf','arial.ttf'):
   if (folder/name).is_file():QFontDatabase.addApplicationFont(str(folder/name))
 if app and app.property('docflow_shared_theme')!=stylesheet():app.setStyleSheet(stylesheet());app.setProperty('docflow_shared_theme',stylesheet())
