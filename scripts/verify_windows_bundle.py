"""Run the extracted EXE twice on native Windows, outside checkout/Python PATH."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import struct
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from docx import Document

ROOT=Path(__file__).resolve().parents[1]


def normal_start(exe,cwd,env):
    """Exercise the ordinary entrypoint/event loop, with no diagnostic flag."""
    import ctypes
    from ctypes import wintypes
    user32=ctypes.WinDLL('user32',use_last_error=True)
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user32.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes=[wintypes.HWND]
    user32.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user32.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    started=time.monotonic()
    process=subprocess.Popen([str(exe)],cwd=cwd,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    found=[]
    @callback_type
    def visit(hwnd,param):
        owner=wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==process.pid and user32.IsWindowVisible(hwnd):
            title=ctypes.create_unicode_buffer(1024)
            user32.GetWindowTextW(hwnd,title,len(title))
            if title.value.startswith('DocFlow Lite'):
                found.append((hwnd,title.value))
        return True
    try:
        deadline=time.monotonic()+25
        while not found and time.monotonic()<deadline:
            assert process.poll() is None, 'Normal EXE startup exited early'
            user32.EnumWindows(visit,0)
            time.sleep(0.1)
        assert found, 'Ordinary EXE did not expose its main window'
        startup=time.monotonic()-started
        time.sleep(.2)
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
                ('peakWorkingSet','workingSet','peakPaged','paged','peakNonPaged','nonPaged','pagefile','peakPagefile')]
        memory=Counters();memory.cb=ctypes.sizeof(memory)
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        psapi=ctypes.WinDLL('psapi',use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
        handle=kernel.OpenProcess(0x410,False,process.pid)
        try:
            assert handle and psapi.GetProcessMemoryInfo(handle,ctypes.byref(memory),memory.cb)
        finally:
            if handle:kernel.CloseHandle(handle)
        assert user32.PostMessageW(found[0][0],0x0010,0,0), 'WM_CLOSE failed'
        code=process.wait(timeout=20)
        assert code==0, f'Normal EXE close returned {code}'
        return {'visible_main_window':True,'title':found[0][1],'exit_code':code,'diagnostic_flag':False,
                'startup_to_visible_s':startup,'working_set_bytes':memory.workingSet,'peak_working_set_bytes':memory.peakWorkingSet}
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


def verify(archive,evidence,release):
    assert os.name=='nt', 'Run on native Windows; Wine is not a release check'
    evidence.mkdir(parents=True,exist_ok=True)
    result={'platform':platform.platform(),'manual_windows_10_11_test':False,
            'source_checkout_not_used_for_runtime':True,'runs':[]}
    with tempfile.TemporaryDirectory(prefix='DocFlow проверка ') as temp:
        testroot=Path(temp)/'Путь с пробелами'
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            z.extractall(testroot)
        bundle=testroot/'DocFlow-Lite'
        exe=bundle/'DocFlow-Lite.exe'
        raw=exe.read_bytes()
        assert raw[:2]==b'MZ'
        pe=struct.unpack_from('<I',raw,0x3c)[0]
        assert raw[pe:pe+4]==b'PE\0\0'
        assert struct.unpack_from('<H',raw,pe+4)[0]==0x8664
        result['exe_sha256']=hashlib.sha256(raw).hexdigest()
        result['portable_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
        hashes=json.loads((bundle/'BUNDLE-SHA256.json').read_text(encoding='utf-8'))
        for name,digest in hashes.items():
            assert hashlib.sha256((bundle/name).read_bytes()).hexdigest()==digest,name
        env=os.environ.copy()
        for name in list(env):
            if name.upper().startswith(('PYTHON','QT_','VIRTUAL_ENV')):env.pop(name)
        env['PATH']=str(Path(os.environ['SYSTEMROOT'])/'System32')
        result['runtime_path_contains_python']=False
        for attempt in (1,2):
            ordinary=normal_start(exe,testroot,env)
            output=evidence/f'Запуск {attempt}'
            completed=subprocess.run([str(exe),'--release-self-test','--require-windows',
                                      '--output',str(output)],cwd=testroot,env=env,
                                     capture_output=True,timeout=120)
            reportpath=output/'self-test.json'
            if not reportpath.is_file():
                raise RuntimeError(f'EXE produced no report; exit {completed.returncode}; stderr {completed.stderr[-1000:]!r}')
            report=json.loads(reportpath.read_text(encoding='utf-8'))
            assert completed.returncode==0, report
            assert report['status']=='passed' and report['frozen']
            assert report['qt_platform']=='windows' and all(x['passed'] for x in report['checks'])
            docs=[p for p in output.rglob('*.docx') if 'Исходные файлы с пробелами' not in p.parts]
            assert len(docs)==12
            for path in docs:
                with zipfile.ZipFile(path) as z:assert z.testzip() is None
                assert 'Демо' in '\n'.join(p.text for p in Document(path).paragraphs)
            result['runs'].append({'attempt':attempt,'exit_code':completed.returncode,
                                   'ordinary_start_and_close':ordinary,
                                   'frozen':report['frozen'],'qt_platform':report['qt_platform'],
                                   'checks':report['checks'],'generated_docx':len(docs)})
        service_output=evidence/'Service с пробелами'
        service_run=subprocess.run([str(exe),'--service-self-test','--require-windows','--output',str(service_output)],cwd=testroot.parent if testroot.exists() else evidence,env=env,capture_output=True,timeout=180)
        service=json.loads((service_output/'SERVICE-SELF-TEST.json').read_text(encoding='utf-8'))
        assert service_run.returncode==0 and service['status']=='passed',service
        assert service['frozen'] and service['qt_platform']=='windows'
        assert service['completion']['status']=='passed'
        assert len(service['completion']['checks'])==5 and all(c['passed'] for c in service['completion']['checks'])
        assert service['refinement']['status']=='passed'
        assert len(service['refinement']['checks'])==3 and all(c['passed'] for c in service['refinement']['checks'])
        layout=service['refinement']['layout']
        assert layout['status']=='passed' and len(layout['cases'])==90
        assert all(not case['failures'] for case in layout['cases'])
        result['service']=service
    result['status']='passed'
    result['limits']=['Automated native Windows runner, not manual Windows 10/11 acceptance',
                      'Native OS file-dialog interaction is not tested; selections supplied by harness',
                      'DOCX ZIP/XML and content verified; Word/LibreOffice visual rendering not tested']
    (evidence/'WINDOWS-CI-RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copy2(evidence/'WINDOWS-CI-RESULTS.json',release/'WINDOWS-CI-RESULTS.json')
    print(json.dumps({'status':result['status'],'runs':len(result['runs']),'docx_total':sum(x['generated_docx'] for x in result['runs'])}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,default=ROOT/'artifacts/windows')
    parser.add_argument('--release',type=Path,default=ROOT/'release')
    args=parser.parse_args()
    verify(args.archive.resolve(),args.evidence.resolve(),args.release.resolve())
