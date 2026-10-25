"""One shared theme for the workspace and top-level Qt dialogs."""
from pathlib import Path
import os,sys
from PySide6.QtGui import QFontDatabase,QPalette,QColor
from functools import lru_cache
from PySide6.QtWidgets import QApplication
COLORS={'background': '#081C20', 'rail': '#0B2226', 'surface': '#102B2F', 'raised': '#17363A', 'input': '#0B2226', 'table': '#102B2F', 'alternate': '#123035', 'border': '#3C5B59', 'text': '#E5EEE5', 'muted': '#A7BDB5', 'accent': '#C2EF92', 'accentText': '#12241A', 'accentHover': '#D2F5AE', 'focus': '#EFBF73', 'error': '#FFABA0', 'success': '#A9E4BB', 'warning': '#EFBF73', 'info': '#A9D8DA', 'selection': '#284C43', 'disabled': '#829B93'}
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
 if app and app.property('docflow_shared_theme')!=stylesheet():
  palette=QPalette()
  for role,key in [('Window','background'),('WindowText','text'),('Base','input'),('AlternateBase','alternate'),('Text','text'),('Button','raised'),('ButtonText','text'),('Highlight','selection'),('HighlightedText','text'),('ToolTipBase','raised'),('ToolTipText','text'),('PlaceholderText','muted'),('Link','accent')]:
   palette.setColor(getattr(QPalette.ColorRole,role),QColor(COLORS[key]))
  palette.setColor(QPalette.ColorGroup.Disabled,QPalette.ColorRole.Text,QColor(COLORS['disabled']))
  palette.setColor(QPalette.ColorGroup.Disabled,QPalette.ColorRole.ButtonText,QColor(COLORS['disabled']))
  app.setPalette(palette);app.setStyleSheet(stylesheet());app.setProperty('docflow_shared_theme',stylesheet())
