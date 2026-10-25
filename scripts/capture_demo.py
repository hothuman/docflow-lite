"""Capture current Core/Service widgets on synthetic data for a demo sequence.

Frames show real application states, not an elapsed-time benchmark. An optional
external encoder can assemble frames.txt. Qt and the existing demo are enough.
"""
import argparse,json,os,time
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QRect
from PySide6.QtGui import QImage,QPainter,QColor,QFont
from PySide6.QtWidgets import QApplication
from docflow.gui import MainWindow,configure_app
from docflow.release_check import wait_idle
from docflow.service.demo import seed_demo
from docflow.service.repository import ServiceStore
from docflow.ui.service.repair_editor import RepairDialog
from docflow import __version__


def capture(output):
    output.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([]);configure_app(app)
    app.setQuitOnLastWindowClosed(False)
    root=output/'Synthetic project';seed_demo(root)
    window=MainWindow(service_root=root);window.resize(1366,768);window.show()
    window.load_demo();wait_idle(window);frames=[]
    def pump():
        end=time.monotonic()+30
        while window.service_workspace.worker or window.service_workspace._pending_refresh:
            app.processEvents();time.sleep(.005);assert time.monotonic()<end
        app.processEvents()
    def frame(widget,title,detail):
        app.processEvents();number=len(frames)+1
        raw=widget.grab();raw.save(str(output/f'raw-{number}.png'))
        image=QImage(1600,1000,QImage.Format.Format_RGB32);image.fill(QColor('#081c20'))
        painter=QPainter(image);painter.setPen(QColor('#b8e875'));painter.setFont(QFont('Segoe UI',24))
        painter.drawText(QRect(48,20,1500,55),Qt.AlignmentFlag.AlignLeft,title)
        painter.setPen(QColor('#c9d8d7'));painter.setFont(QFont('Segoe UI',13))
        painter.drawText(QRect(48,75,1500,50),Qt.AlignmentFlag.AlignLeft,detail)
        scaled=raw.toImage().scaled(1504,800,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        painter.drawImage((1600-scaled.width())//2,140,scaled)
        painter.setFont(QFont('Segoe UI',11));painter.drawText(48,974,f'DocFlow {__version__} / реальные экраны / вымышленные данные / последовательность, не хронометраж')
        painter.end();path=output/f'frame-{number}.png';assert image.save(str(path));frames.append(path)
    window.navigate(0);frame(window,'Core / таблица и шаблоны','Встроенный пример: XLSX, три записи, два DOCX-шаблона')
    window.navigate(2);frame(window,'Core / поля и проверки','Сопоставление значений и контроль до генерации')
    window.output_path.setText(str(output/'Core results'));window.start_generation();wait_idle(window)
    assert window.last_result.documents==4
    window.navigate(3);frame(window,'Core / четыре готовых DOCX','Две записи приняты; одна пропущена с диагностикой')
    window.navigate(5);pump();ui=window.service_workspace;ui.tabs.setCurrentIndex(0)
    frame(window,'Service / обзор мастерской','Аппараты, обращения и следующий шаг в локальном проекте')
    ui.tabs.setCurrentIndex(2);frame(window,'Service / журнал ремонтов','Отдельный номер аппарата и отдельный номер обращения')
    store=ServiceStore(root);repair=ui.cache['repairs'][0];snapshot=store.snapshot(repair['id'])
    editor=RepairDialog(ui,snapshot);editor.resize(1180,740);editor.show();app.processEvents()
    editor.tabs.show_section('Приёмка');frame(editor,'Service / карточка ремонта','Данные обращения и действия с понятными подписями')
    editor.tabs.show_section('Сметы');frame(editor,'Service / расчёт и версии','Предварительные сметы и внутренние финансовые записи')
    editor.reject();ui.tabs.setCurrentIndex(7);frame(window,'Service / настройки и копии','Резервирование и восстановление в отдельную папку')
    window.close();app.processEvents()
    (output/'frames.txt').write_text(''.join(f"file '{p.as_posix()}'\nduration 5\n" for p in frames)+f"file '{frames[-1].as_posix()}'\n",encoding='utf-8')
    result={'version':__version__,'frames':len(frames),'frame_duration_seconds':5,'scope':'Actual source-mode Qt states; synthetic data; not frozen EXE or elapsed-time recording','core_documents':4}
    (output/'capture-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('artifacts/demo-current'));args=p.parse_args();capture(args.output.resolve())
