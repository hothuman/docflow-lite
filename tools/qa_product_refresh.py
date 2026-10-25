"""Capture actual Qt views using synthetic data only."""
import argparse, json, time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from docflow.gui import MainWindow, configure_app
from docflow.release_check import wait_idle
from docflow.service.demo import seed_demo
from docflow.ui.service.repair_editor import RepairDialog

def capture(output):
 output.mkdir(parents=True,exist_ok=True)
 app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False)
 ids=seed_demo(output/'Synthetic project');w=MainWindow(service_root=output/'Synthetic project');w.resize(1440,900);w.show();w.load_demo();wait_idle(w);app.processEvents();assert w.grab().save(str(output/'core.png'))
 w.navigate(5);ui=w.service_workspace
 until=time.monotonic()+30
 while ui.worker or ui._pending_refresh:app.processEvents();time.sleep(.005);assert time.monotonic()<until
 for index,name in [(0,'overview'),(2,'repairs'),(6,'estimates'),(7,'settings')]:
  ui.tabs.setCurrentIndex(index);app.processEvents();assert w.grab().save(str(output/(name+'.png')))
 editor=RepairDialog(ui,ui.store.snapshot(ids['repair']));editor.resize(1080,760);editor.show();app.processEvents();assert editor.grab().save(str(output/'repair-card.png'));editor.reject();w.close();app.processEvents()
 (output/'capture.json').write_text(json.dumps({'version':__import__('docflow').__version__,'platform':app.platformName(),'synthetic':True,'size':[1440,900],'scope':'Actual Qt capture; not physical monitor/Word acceptance'},indent=2),encoding='utf-8')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);capture(p.parse_args().output)
