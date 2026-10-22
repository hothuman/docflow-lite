"""Explicit, local release diagnostic; normal startup does not run this code.

The frozen executable exercises its own GUI, resources and generation engine.
File-dialog choices are supplied by the harness; native file-dialog interaction
and manual Windows 10/11 acceptance are outside this automated check.
"""
import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import sys
import time
import traceback
import zipfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def dialog_choice(dialog, method, value):
    previous = getattr(dialog, method)
    setattr(dialog, method, staticmethod(lambda *args, **kwargs: value))
    try:
        yield
    finally:
        setattr(dialog, method, previous)


def wait_idle(window, timeout=15):
    """Pump Qt events while allowing Python worker threads to acquire the GIL."""
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance()
    deadline=time.monotonic()+timeout
    while True:
        app.processEvents()
        running=any(worker and worker.isRunning() for worker in
                    (window.worker,getattr(window,'task_worker',None),getattr(window,'preview_worker',None)))
        timer=getattr(window,'_preview_timer',None)
        if not running and not getattr(window,'_busy',False) and not (timer and timer.isActive()) and not getattr(window,'_pending_preview',None):
            app.processEvents();return
        if time.monotonic()>deadline:raise RuntimeError('GUI operation timed out: '+window.status.text())
        time.sleep(.005)


def run(output, require_windows=False):
    from PySide6.QtCore import Qt, qVersion
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog, QScrollArea
    from docx import Document
    from . import __version__
    from .cli import demo_profile
    from .gui import MainWindow
    from .profile import Profile
    from .validation import Rule

    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    proof = {'version':__version__, 'os':platform.platform(),
             'python':platform.python_version(), 'qt':qVersion(),
             'executable':sys.executable, 'frozen':bool(getattr(sys,'frozen',False)),
             'qt_platform':app.platformName(), 'checks':[],
             'manual_test':False, 'file_dialogs':'choices supplied by harness'}

    def check(name, **details):
        proof['checks'].append({'name':name,'passed':True,**details})

    def click(widget):
        assert widget.isEnabled(), widget.text()
        parent=widget.parentWidget()
        while parent is not None:
            if isinstance(parent,QScrollArea):
                parent.ensureWidgetVisible(widget,12,12)
                app.processEvents()
                break
            parent=parent.parentWidget()
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
        app.processEvents()
        wait_idle(window)

    def wait_for_generation():
        deadline = time.monotonic()+30
        while window.worker.isRunning() or window.last_result is None:
            app.processEvents()
            if time.monotonic()>deadline:
                raise RuntimeError('Generation timed out: '+window.status.text())
            time.sleep(.01)
        assert window.worker.wait(2000)
        app.processEvents()
        result = window.last_result
        assert (result.total,result.accepted,result.rejected,result.documents)==(3,2,1,4)
        docs = sorted(result.directory.rglob('*.docx'))
        assert len(docs)==4
        for path in docs:
            with zipfile.ZipFile(path) as archive:
                assert archive.testzip() is None
            document = Document(path)
            text = '\n'.join(p.text for p in document.paragraphs)
            assert '{{' not in text
            assert 'Демо' in text
        report = json.loads((result.directory/'report.json').read_text(encoding='utf-8'))
        assert report['records'][2]['status']=='error'
        assert len(report['records'][2]['issues'])==2
        with (result.directory/'report.csv').open(encoding='utf-8-sig',newline='') as f:
            assert len(list(csv.reader(f,delimiter=';')))==5
        return result

    try:
        if require_windows:
            assert os.name=='nt' and proof['qt_platform']=='windows'
            assert proof['frozen'], 'Must test the compiled EXE'
        window.show()
        QTest.qWait(300)
        app.processEvents()
        assert window.isVisible() and int(window.winId())!=0
        if require_windows:
            assert window.windowHandle().isExposed(), 'Native window was not exposed'
        check('main_window_opened',native_handle=int(window.winId()))
        assert window.grab().save(str(output/'main-window.png'))
        click(window.demo_btn)
        assert window.source_table.rowCount()==3 and len(window.templates)==2
        assert 'Демо Клиент А' in window.preview_text.toPlainText()
        assert window.grab().save(str(output/'demo-loaded.png'))
        window.navigate(1);app.processEvents()
        assert window.grab().save(str(output/'templates.png'))
        window.navigate(2);app.processEvents()
        assert window.grab().save(str(output/'mapping.png'))
        window.navigate(0);app.processEvents()
        window.row_selector.setCurrentIndex(2)
        assert 'будет пропущена' in window.preview_text.toPlainText()
        click(window.check_btn)
        assert 'С ошибками: 1' in window.status.text()
        check('bundled_demo_and_validation')
        window.output_path.setText(str(output/'Встроенный пример'))
        click(window.generate_btn)
        result = wait_for_generation()
        check('bundled_demo_generation',directory=str(result.directory),documents=4)

        demo = Profile.load(demo_profile())
        inputs = output/'Исходные файлы с пробелами'
        inputs.mkdir()
        templates = []
        for index,path in enumerate(demo.templates,1):
            target = inputs/f'{index} Русский шаблон.docx'
            shutil.copy2(path,target)
            templates.append(target)
        for extension in ('xlsx','csv'):
            window.navigate(1);app.processEvents()
            while window.template_list.count():
                window.template_list.setCurrentRow(0)
                click(window.remove_btn)
            window.navigate(0);app.processEvents()
            data = inputs/('Демонстрационные клиенты.'+extension)
            shutil.copy2(demo.data_file.with_suffix('.'+extension),data)
            before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [data,*templates]}
            with dialog_choice(QFileDialog,'getOpenFileName',(str(data),'')):
                click(window.load_btn)
            assert window.source_table.rowCount()==3
            with dialog_choice(QFileDialog,'getOpenFileNames',([str(p) for p in templates],'')):
                click(window.add_btn)
            assert len(window.templates)==2
            for row in range(window.mapping_table.rowCount()):
                field = window.mapping_table.item(row,0).text()
                rule = demo.rules.get(field,Rule())
                window.mapping_table.cellWidget(row,1).setCurrentText(demo.mapping[field])
                kind = window.mapping_table.cellWidget(row,2)
                kind.setCurrentIndex(kind.findData(rule.kind))
                window.mapping_table.cellWidget(row,3).setChecked(rule.required)
            window.name_selector.setCurrentText(demo.name_column)
            window.navigate(2);app.processEvents()
            saved = inputs/f'Сохранённый профиль {extension}.json'
            with dialog_choice(QFileDialog,'getSaveFileName',(str(saved),'')):
                click(window.save_profile_btn)
            restored = Profile.load(saved)
            assert restored.data_file==data.resolve()
            with dialog_choice(QFileDialog,'getOpenFileName',(str(saved),'')):
                click(window.open_profile_btn)
            assert window.table.source==data.resolve()
            window.navigate(0);app.processEvents()
            with dialog_choice(QFileDialog,'getExistingDirectory',str(output/('Документы '+extension))):
                click(window.output_btn)
            window.last_result=None
            click(window.generate_btn)
            result=wait_for_generation()
            assert all(hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in before.items())
            check('unicode_spaces_'+extension,directory=str(result.directory),documents=4,
                  profile_saved_and_loaded=True,sources_unchanged=True)
        assert window.grab().save(str(output/'demo-generated.png'))
        window.close()
        app.processEvents()
        assert not window.isVisible()
        check('main_window_closed')
        proof['status']='passed'
    except Exception:
        proof['status']='failed'
        proof['traceback']=traceback.format_exc()
    finally:
        if window.worker and window.worker.isRunning():
            window.worker.wait(30000)
        window.close()
        app.processEvents()
        (output/'self-test.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if proof['status']=='passed' else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description='Local diagnostic for release verification')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--require-windows',action='store_true')
    args=parser.parse_args(argv)
    return run(args.output.resolve(),args.require_windows)
