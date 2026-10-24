"""Synthetic actual GUI screenshots plus geometry, never customer data."""
import argparse,json,time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from docflow.gui import MainWindow,configure_app
from docflow.service.demo import seed_demo
from docflow.service.repository import ServiceStore
from docflow.service.profiles import save_profile
from docflow.service.attachments import add_attachment
from docflow.service.documents import generate_document
from docflow.service.layout_check import assess
from docflow.release_check import wait_idle
def run(output):
 output.mkdir(parents=True,exist_ok=True);app=QApplication.instance() or QApplication([]);configure_app(app);app.setQuitOnLastWindowClosed(False)
 def idle(ui):
  end=time.monotonic()+30
  while ui.worker or ui._pending_refresh:app.processEvents();time.sleep(.005);assert time.monotonic()<end
  app.processEvents()
 empty=MainWindow(service_root=output/'Empty synthetic project');empty.resize(1366,768);empty.show();empty.navigate(5);idle(empty.service_workspace);empty.grab().save(str(output/'dashboard-empty.png'));empty.close();app.processEvents()
 root=output/'Synthetic project';ids=seed_demo(root);store=ServiceStore(root);save_profile(store,{'name':'Учебная мастерская','organization_name':'Синтетическое предприятие'},activate=True)
 for n in range(2):
  path=output/f'Synthetic-photo-{n}.png';image=QImage(640,360,QImage.Format.Format_RGB32);image.fill(QColor('#781326'));assert image.save(str(path));add_attachment(store,ids['repair'],path,'Вымышленная схема '+str(n+1))
 generate_document(store,ids['repair'],'combined');w=MainWindow(service_root=root);w.show();w.navigate(5);ui=w.service_workspace;idle(ui);result=assess(w,ui,app,output,idle)
 w.resize(1366,768);w.navigate(0);w.load_demo();wait_idle(w);w.grab().save(str(output/'core-create.png'));w.output_path.setText(str(output/'Core generated'));w.start_generation();wait_idle(w);assert w.last_result.documents==4;w.grab().save(str(output/'core-result.png'));w.close();app.processEvents();print(json.dumps({'status':result['status'],'cases':len(result['cases']),'failed':[c for c in result['cases'] if c['failures']]},ensure_ascii=False));return 0 if result['status']=='passed' else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();raise SystemExit(run(args.output))
