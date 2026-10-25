"""Render actual Qt widgets at six client-area sizes and an externally set scale.

This is a virtual DPI/layout check, not physical-monitor or Windows shell testing.
"""
import argparse,json,os,shutil,tempfile,time
from pathlib import Path
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from docflow.gui import MainWindow, configure_app
from docflow.profile import Profile
from docflow.cli import demo_profile
from docflow.release_check import wait_idle

SIZES=((1280,720),(1366,768),(1600,900),(1920,1080),(2560,1440),(3840,2160))

def run(output):
    output.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion');app.setQuitOnLastWindowClosed(False)
    configure_app(app)
    window=MainWindow();window.show();scale=float(os.environ.get('QT_SCALE_FACTOR','1'));cases=[]
    with tempfile.TemporaryDirectory(prefix='DocFlow layout ') as temp:
        root=Path(temp);base=Profile.load(demo_profile())
        data=root/('Клиенты с длинным названием для проверки интерфейса '+ 'документы '*5+'.csv')
        shutil.copy2(base.data_file.with_suffix('.csv'),data)
        templates=[]
        for i,path in enumerate(base.templates):
            target=root/(str(i)+' Шаблон с длинным именем '+ 'документ '*5+'.docx');shutil.copy2(path,target);templates.append(target)
        window.apply_profile(Profile(data,templates,base.mapping,base.rules,base.name_column));wait_idle(window)
        for width,height in SIZES:
            logical=(round(width/scale),round(height/scale));window.resize(*logical);app.processEvents();time.sleep(.015);app.processEvents()
            for page in range(5):
                window.navigate(page);app.processEvents();scroll=window.pages.currentWidget()
                failures=[]
                if (window.width(),window.height())!=logical:failures.append('window exceeded requested logical size')
                if scroll.horizontalScrollBar().maximum():failures.append('unexpected page horizontal scrolling')
                if window._pinned_action:
                    primary=window.generate_btn;point=primary.mapTo(window,QPoint())
                    if not primary.isVisible() or not window.rect().contains(point) or not window.rect().contains(point+QPoint(primary.width()-1,primary.height()-1)):
                        failures.append('primary generation action clipped or hidden')
                for button in [window.demo_btn,window.folder_btn,window.mode_picker,*window.nav_buttons,*window.service_nav]:
                    if not button.isVisible():continue
                    point=button.mapTo(window,QPoint(0,0))
                    if not window.rect().contains(point) or not window.rect().contains(point+QPoint(button.width()-1,button.height()-1)):
                        failures.append('header/navigation clipped: '+button.accessibleName())
                for button in window.nav_buttons:
                    if button.isVisible() and button.text() and button.width()<button.sizeHint().width():
                        failures.append('navigation label truncated: '+button.text())
                case={'physical_client_size':[width,height],'scale_factor':scale,'device_pixel_ratio':window.devicePixelRatioF(),
                      'logical_size':[window.width(),window.height()],'page':page,'horizontal_scroll_max':scroll.horizontalScrollBar().maximum(),
                      'vertical_scroll_max':scroll.verticalScrollBar().maximum(),'failures':failures}
                cases.append(case)
            if (width,height) in ((1280,720),(1920,1080)):
                window.navigate(0);app.processEvents()
                assert window.grab().save(str(output/f'gui-{width}x{height}-{round(scale*100)}.png'))
        wait_idle(window);window.close();app.processEvents()
    report={'qt_platform':app.platformName(),'scope':'Virtual Qt client sizes and QT_SCALE_FACTOR; not physical Windows monitor/DPI acceptance',
            'cases':cases,'passed':not any(c['failures'] for c in cases)}
    (output/'layout.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'scale':scale,'cases':len(cases),'passed':report['passed'],'failed':[c for c in cases if c['failures']]}))
    return 0 if report['passed'] else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    raise SystemExit(run(args.output))
