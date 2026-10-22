"""Synthetic, reproducible local comparison. All generated outputs are temporary."""
import argparse,csv,json,os,platform,statistics,sys,tempfile,time,threading
from pathlib import Path
from openpyxl import Workbook
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from docflow.batch import prepare,generate
from docflow.cli import demo_profile
from docflow.data import load_table
from docflow.profile import Profile
from docflow.validation import values_for
from docflow.gui import MainWindow

def rss():
    if sys.platform.startswith("linux"):
        return int(next(line.split()[1] for line in Path("/proc/self/status").read_text().splitlines() if line.startswith("VmRSS:")))*1024
    if os.name=="nt":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[("cb",wintypes.DWORD),("faults",wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ("peakWorkingSet","workingSet","peakPaged","paged","peakNonPaged","nonPaged","pagefile","peakPagefile")]
        value=Counters();value.cb=ctypes.sizeof(value)
        kernel=ctypes.WinDLL("kernel32");kernel.GetCurrentProcess.restype=wintypes.HANDLE
        psapi=ctypes.WinDLL("psapi");psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(value),value.cb):return value.workingSet
    return 0

def idle(window,app):
    deadline=time.monotonic()+15
    while True:
        app.processEvents()
        workers=[getattr(window,n,None) for n in ("worker","task_worker","preview_worker")]
        timer=getattr(window,"_preview_timer",None)
        if not any(w and w.isRunning() for w in workers) and not getattr(window,"_busy",False) and not(timer and timer.isActive()) and not getattr(window,"_pending_preview",None):return
        if time.monotonic()>deadline:raise RuntimeError("GUI idle timed out")
        time.sleep(.005)


def measure(fn):
    start=time.perf_counter();value=fn();return value,time.perf_counter()-start

def run(output,counts,memory_only=False):
    peak=[rss()];stop=threading.Event()
    def sample():
        while not stop.wait(.025):peak[0]=max(peak[0],rss())
    sampler=threading.Thread(target=sample,daemon=True);sampler.start()
    app=QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window,startup=measure(MainWindow);window.show();app.processEvents()
    base=Profile.load(demo_profile());results=[]
    try:
        for n in counts:
            with tempfile.TemporaryDirectory(prefix='DocFlow bench ') as temp:
                p=Path(temp);csvpath=p/'Синтетические данные.csv';xlsx=p/'Синтетические данные.xlsx'
                headers=['Номер','Клиент','Email','Услуга','Сумма','Дата']
                rows=[[str(i).zfill(5),'Демо Клиент '+str(i),f'client{i}@example.com','Сервис',str(i+100),'2026-10-21'] for i in range(n)]
                with csvpath.open('w',encoding='utf-8-sig',newline='') as f:
                    writer=csv.writer(f,delimiter=';');writer.writerow(headers);writer.writerows(rows)
                wb=Workbook(write_only=True);ws=wb.create_sheet();ws.append(headers)
                for row in rows:ws.append(row)
                wb.save(xlsx)
                table,loadcsv=measure(lambda:load_table(csvpath))
                _,loadxlsx=measure(lambda:load_table(xlsx))
                profile=Profile(csvpath,base.templates,base.mapping,base.rules,base.name_column)
                prepared,preparation=measure(lambda:prepare(profile))
                _,validation=measure(lambda:[values_for(r,profile.mapping,profile.rules) for r in table.records])
                context,_=values_for(table.records[0],profile.mapping,profile.rules)
                preview=[]
                for _ in range(20):
                    _,elapsed=measure(lambda:prepared.templates[0].preview(context));preview.append(elapsed)
                _,gui_load=measure(lambda:window.apply_profile(profile));idle(window,app)
                _,snapshot=measure(window.snapshot)
                result,generation=(None,None) if memory_only else measure(lambda:generate(prepared,p/'Выход'))
                if result:
                    assert result.accepted==n and result.documents==n*2 and result.rejected==0
                    assert len(list(result.directory.rglob('*.docx')))==n*2
                # A separate 100-row GUI run exercises its real event loop and background worker.
                lag=[];last=[time.perf_counter()]
                timer=QTimer();timer.setInterval(10)
                timer.timeout.connect(lambda:(lag.append(time.perf_counter()-last[0]),last.__setitem__(0,time.perf_counter())))
                timer.start();window.output_path.setText(str(p/'GUI'));window.last_result=None
                if n==100 and not memory_only:
                    window.start_generation();deadline=time.monotonic()+90
                    while window.worker.isRunning() or window.last_result is None:
                        app.processEvents();time.sleep(.005)
                        if time.monotonic()>deadline:raise RuntimeError('GUI generation timeout')
                    window.worker.wait(2000);app.processEvents();assert window.last_result.documents==200
                timer.stop()
                record={'records':n,'templates':2,'csv_load_s':loadcsv,'xlsx_load_s':loadxlsx,
                    'prepare_s':preparation,'validation_s':validation,'preview_median_s':statistics.median(preview),
                    'gui_install_s':gui_load,'snapshot_s':snapshot,'generation_s':generation,'documents':result.documents if result else 0,
                    'gui_timer_max_interval_s':max(lag) if lag else None,'rss_peak_bytes':peak[0]}
                results.append(record);print(json.dumps(record),flush=True)
        report={'platform':platform.platform(),'python':platform.python_version(),'qt_platform':app.platformName(),
            'main_window_construction_s':startup,'rss_peak_bytes':peak[0],'memory_method':'/proc/self/status VmRSS on Linux; GetProcessMemoryInfo on Windows; 25 ms sampling','memory_only':memory_only,'results':results,
            'scope':'One local run per size, same synthetic six columns and bundled two templates; medians of 20 previews. '
                    'RSS sampled every 25 ms; GUI heartbeat only at 100 rows. Native Windows/physical DPI performance is not asserted.'}
        output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    finally:
        stop.set();sampler.join(1)
        for name in ('worker','task_worker','preview_worker'):
            worker=getattr(window,name,None)
            if worker and worker.isRunning():worker.wait(30000)
        window.close();app.processEvents()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--counts',default='10,100,1000,5000');p.add_argument('--memory-only',action='store_true')
    a=p.parse_args();run(a.output,[int(n) for n in a.counts.split(',')],a.memory_only)
