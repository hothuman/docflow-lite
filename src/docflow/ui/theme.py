"""One shared theme for the workspace and top-level Qt dialogs."""
from pathlib import Path
from functools import lru_cache
from PySide6.QtWidgets import QApplication
COLORS={'background':'#0D0F13','rail':'#101218','surface':'#171A21','input':'#20242D','table':'#12151B','alternate':'#191D25','border':'#30343E','text':'#F3F4F6','muted':'#A1A6B1','accent':'#A1162C','focus':'#C36172','error':'#FF9AA4','success':'#70D69E','selection':'#632033'}
@lru_cache(maxsize=1)
def stylesheet():
 result=Path(__file__).with_name('theme.qss').read_text(encoding='utf-8')
 for key,value in COLORS.items():result=result.replace('@'+key+'@',value)
 return result
def apply_theme(app=None):
 app=app or QApplication.instance()
 if app and app.property('docflow_shared_theme')!=stylesheet():app.setStyleSheet(stylesheet());app.setProperty('docflow_shared_theme',stylesheet())
