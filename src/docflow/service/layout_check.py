"""Opt-in real Qt geometry checks, importable by the frozen diagnostic."""
import json,os
from pathlib import Path
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QPushButton,QScrollArea
from ..ui.service.widgets import Grid
from ..ui.theme import COLORS
from PySide6.QtGui import QColor
from ..ui.service.presentation import MONEY
from ..ui.service.repair_editor import RepairDialog
from ..ui.service.estimates import DraftDialog
from ..ui.service.import_wizard import HistoryWizard
from ..ui.service.profiles import ProfileDialog
from ..ui.service.images import ImagesDialog
from ..ui.service.history import HistoryDialog
from ..ui.service.forms import FieldsDialog
SIZES=((1280,720),(1366,768),(1600,900),(1920,1080),(2560,1440))
def assess(window,workspace,app,output,idle):
 output=Path(output);output.mkdir(parents=True,exist_ok=True);scale=float(os.environ.get('QT_SCALE_FACTOR','1'));cases=[];snapshot=workspace.store.snapshot(workspace.cache['finance'][0]['id']);equipment=next(x for x in workspace.cache['active_equipment'] if x['id']==snapshot['equipment']['id'])
 def pump():app.processEvents();app.processEvents()
 def inspect(widget,name,physical,logical,critical=()):
  pump();failures=[];paint={}
  if name=='import':
   capture=widget.grab();ratio=capture.devicePixelRatio();pixel=capture.toImage().pixelColor(round(8*ratio),round((widget.height()-8)*ratio));paint['wizard_footer_rgb']=pixel.name()
   expected=QColor(COLORS['background'])
   if max(abs(pixel.red()-expected.red()),abs(pixel.green()-expected.green()),abs(pixel.blue()-expected.blue()))>3:failures.append('wizard footer outside shared theme')
  if widget.width()>logical[0] or widget.height()>logical[1]:failures.append('window exceeds requested logical client size')
  for button in critical:
   if not button.isVisible():failures.append('confirmation/cancel hidden: '+button.text());continue
   point=button.mapTo(widget,QPoint())
   if not widget.rect().contains(point) or not widget.rect().contains(point+QPoint(button.width()-1,button.height()-1)):failures.append('confirmation/cancel clipped: '+button.text())
  controls=[b for b in widget.findChildren(QPushButton) if b.isVisible()]
  for i,a in enumerate(controls):
   for b in controls[i+1:]:
    if a.parentWidget() is b.parentWidget() and a.geometry().intersects(b.geometry()):failures.append('overlapping buttons: '+a.text()+' / '+b.text())
  for scroll in widget.findChildren(QScrollArea):
   if scroll.isVisible() and scroll.horizontalScrollBar().maximum():failures.append('horizontal page scrolling')
  for grid in widget.findChildren(Grid):
   if not grid.isVisible():continue
   grid.horizontalScrollBar().setValue(0);grid.fit_columns();pump()
   for col,(key,title) in enumerate(grid.records.columns):
    if key in MONEY and (grid.isColumnHidden(col) or grid.columnViewportPosition(col)<0 or grid.columnViewportPosition(col)+grid.columnWidth(col)>grid.viewport().width()):failures.append('monetary column outside viewport: '+title)
  cases.append({'view':name,'physical_client':list(physical),'logical_limit':list(logical),'actual_logical':[widget.width(),widget.height()],'failures':failures,**paint})
  if physical in ((1280,720),(1920,1080)):assert widget.grab().save(str(output/(name+'-'+str(physical[0])+'.png')))
 for physical in SIZES:
  logical=(round(physical[0]/scale),round(physical[1]/scale));window.resize(*logical);window.navigate(5);pump()
  for index,name in enumerate(('dashboard','equipment','repairs','clients','finance','documents','estimates','settings')):workspace.tabs.setCurrentIndex(index);pump();inspect(window,name,physical,logical,[b for b in window.nav_buttons if b.isVisible()])
  workspace.tabs.setCurrentIndex(0);editor=RepairDialog(workspace,snapshot);editor.resize(min(1060,logical[0]),min(740,logical[1]));editor.show();pump()
  for section,name in [('Приёмка','repair-basic'),('Сметы','repair-estimates'),('Документы','repair-documents'),('Вложения','repair-attachments')]:
   editor.tabs.show_section(section);pump();inspect(editor,name,physical,logical,[editor.save_button,editor.next_button,*[b for b in editor.findChildren(QPushButton) if b.isVisible() and b.text()=='Закрыть']])
  draft=DraftDialog(editor);draft.resize(min(960,logical[0]),min(640,logical[1]));draft.show();pump();inspect(draft,'draft',physical,logical,[b for b in draft.findChildren(QPushButton) if b.text() in ('Сохранить расчёт','Отмена')]);draft.reject()
  factories=[('import',lambda:HistoryWizard(workspace)),('profiles',lambda:ProfileDialog(workspace)),('images',lambda:ImagesDialog(snapshot['attachments'],workspace)),('equipment-history',lambda:HistoryDialog(workspace,equipment)),('input',lambda:FieldsDialog('Проверка размеров',[('name','Название *','text'),('notes','Примечания','long')],parent=workspace))]
  for name,factory in factories:
   dialog=factory();idle(workspace)
   if isinstance(dialog,HistoryDialog):assert dialog.grid.proxy.rowCount()>0
   dialog.resize(min(1020,logical[0]),min(680,logical[1]));dialog.show();pump();inspect(dialog,name,physical,logical,[b for b in dialog.findChildren(QPushButton) if b.isVisible() and b.text() in ('Сохранить','Отмена','Закрыть','Далее','Назад')]);dialog.reject();pump()
  editor.accept();pump()
 report={'status':'passed' if not any(c['failures'] for c in cases) else 'failed','qt_platform':app.platformName(),'scale_factor':scale,'device_pixel_ratio':window.devicePixelRatioF(),'scope':'Virtual Qt client sizes; not physical Windows monitor, OS DPI or Word acceptance','cases':cases};(output/'service-layout.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return report
