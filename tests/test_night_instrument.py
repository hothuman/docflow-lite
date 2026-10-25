"""Night Instrument usability: navigation, readiness and truthful repair context."""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from docflow.gui import MainWindow,configure_app
from docflow.release_check import wait_idle
from docflow.service.demo import seed_demo
from docflow.ui.service.repair_editor import RepairDialog
from docflow.ui.theme import COLORS

def contrast(a,b):
 def light(h):
  c=[int(h[i:i+2],16)/255 for i in (1,3,5)];c=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in c]
  return sum(v*w for v,w in zip(c,(.2126,.7152,.0722)))
 a,b=sorted((light(a),light(b)));return (b+.05)/(a+.05)

def test_night_semantic_text_is_legible_on_actual_surfaces():
 for surface in ('background','surface','table','raised','selection'):
  for text in ('text','muted','error','success','warning','info'):
   assert contrast(COLORS[text],COLORS[surface])>=4.5,(text,surface)
 assert contrast(COLORS['accentText'],COLORS['accent'])>=4.5
 assert contrast(COLORS['accentText'],COLORS['accentHover'])>=4.5

@pytest.mark.parametrize('size',[(900,600),(640,360)])
def test_small_window_keeps_navigation_text(size,tmp_path):
 app=QApplication.instance() or QApplication([]);configure_app(app);w=MainWindow(service_root=tmp_path/'Empty');w.resize(*size);w.show();app.processEvents()
 assert all(b.text().strip() for b in w.nav_buttons[:5])
 for b in w.nav_buttons[:5]:assert b.width()>=b.sizeHint().width(),b.text()
 w.navigate(5)
 # Service operations complete through the normal event loop.
 import time
 end=time.monotonic()+20
 while w.service_workspace.worker or w.service_workspace._pending_refresh:
  app.processEvents();time.sleep(.005);assert time.monotonic()<end
 for b in w.service_nav:assert b.text().strip() and b.width()>=b.sizeHint().width(),b.text()
 w.close();app.processEvents()

def test_core_route_reflects_real_mapping_and_blocks_during_work(tmp_path):
 app=QApplication.instance() or QApplication([]);configure_app(app);w=MainWindow();w.show();w.load_demo();wait_idle(w)
 assert [b.property('complete') for b in w.route_buttons]==[True,True,True,False]
 w.mapping_table.cellWidget(0,1).setCurrentText('');app.processEvents()
 assert not w.route_buttons[2].property('complete') and not w.generate_btn.isEnabled()
 w.set_busy(True);assert all(not b.isEnabled() for b in w.route_buttons)
 w.set_busy(False);wait_idle(w);w.close();app.processEvents()

def test_repair_context_uses_actual_status_and_only_navigates(tmp_path):
 import time
 app=QApplication.instance() or QApplication([]);configure_app(app);ids=seed_demo(tmp_path/'Demo');w=MainWindow(service_root=tmp_path/'Demo');w.show();w.navigate(5);ui=w.service_workspace
 end=time.monotonic()+20
 while ui.worker or ui._pending_refresh:
  app.processEvents();time.sleep(.005);assert time.monotonic()<end
 editor=RepairDialog(ui,ui.store.snapshot(ids['repair']));editor.resize(1080,760);editor.show();app.processEvents()
 before=editor.revision
 assert 'Ожидает запчастей' in editor.state_hint.text()
 assert 'Аппарат №DEMO-001' in editor.identity.text() and 'Обращение №DEMO-R-002' in editor.identity.text()
 editor.status_action.click();app.processEvents();g,index,_=editor.tabs.sections['Статус и история']
 assert editor.tabs.currentIndex()==g and editor.tabs.groups[g][0].currentIndex()==index
 assert editor.fields['status'].hasFocus() and not editor.dirty
 assert ui.store.snapshot(ids['repair'])['repair']['revision']==before
 editor.accept();w.close();app.processEvents()
