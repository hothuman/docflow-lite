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

REQUIRED_STAGE3_CHECKS=frozenset({'file_preview_apply_replay','catalog_to_quote_snapshot_docx','catalog_update_preserves_history','catalog_profiles_backup_restore','dashboard_presets_reset_restart','compact_catalog_layouts'})

def assert_stage3_checks(report):
    assert report['status']=='passed' and report['frozen'] and report['qt_platform']=='windows'
    assert len(report['checks'])==6 and {c['name'] for c in report['checks']}==REQUIRED_STAGE3_CHECKS
    assert all(c['passed'] is True for c in report['checks']) and report['backup_restore'] is True
    assert len(report['layout'])==3 and all(c['footer_visible'] for c in report['layout'])

REQUIRED_STAGE2_CHECKS=frozenset({'first_intake','repeat_intake','estimate_approval','act_without_excel','issue_payment_history'})

def assert_stage2_checks(report):
    assert report['status']=='passed' and report['frozen'] and report['qt_platform']=='windows'
    assert len(report['checks'])==5 and {c['name'] for c in report['checks']}==REQUIRED_STAGE2_CHECKS
    assert all(c['passed'] is True for c in report['checks']) and report['backup_restore'] is True

REQUIRED_PROJECT_CHECKS=frozenset({
    'native_folder_cancel_settles_without_touching_original',
    'no_store_navigation_and_recovery_actions_at_three_sizes',
    'business_entrypoints_guarded_without_store',
    'retry_opens_fresh_project_and_can_create_client',
    'cancel_switch_retains_current_project_name_and_data',
    'failed_switch_is_terminal_and_can_retry',
})


def assert_project_loading_checks(report):
    assert report['status']=='passed' and report['frozen'] and report['qt_platform']=='windows'
    assert report.get('native_folder_dialog_seen') is True and report.get('native_folder_dialog_close_sent') is True
    checks=report['checks']
    assert len(checks)==len(REQUIRED_PROJECT_CHECKS) and {c['name'] for c in checks}==REQUIRED_PROJECT_CHECKS
    assert all(c.get('passed') is True for c in checks)

REQUIRED_COMPLETION_CHECKS = frozenset({
    'native_profile_form_numbering_status_labels',
    'native_five_page_history_wizard_900_101_305_900_fourth_two_owners_and_replay',
    'native_draft_versions_manual_approval_actual_expenses_and_both_quote_docx',
    'native_individual_image_choice_order_captions_and_docx',
    'completion_backup_restore_profiles_history_quotes_and_selected_images',
    'native_historical_unknown_finance_and_explicit_reconciliation',
    'native_photo_append_without_english_heading_styles',
})


def assert_completion_checks(checks):
    assert isinstance(checks,list), 'Missing native completion results'
    assert len(checks)==len(REQUIRED_COMPLETION_CHECKS), 'Native completion suite count differs'
    assert {c.get('name') for c in checks}==REQUIRED_COMPLETION_CHECKS, 'Missing, duplicate or unexpected native completion scenario'
    assert all(c.get('passed') is True for c in checks), 'Native completion scenario failed'



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
        for variable,folder in [('LOCALAPPDATA','LocalAppData'),('APPDATA','Roaming'),('DOCFLOW_SETTINGS_DIR','Settings')]:
            target=testroot/folder;target.mkdir(parents=True,exist_ok=True);env[variable]=str(target)
        result['isolated_user_data_and_settings']=True
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
        assert_completion_checks(service['completion']['checks'])
        assert service['refinement']['status']=='passed'
        assert len(service['refinement']['checks'])==3 and all(c['passed'] for c in service['refinement']['checks'])
        layout=service['refinement']['layout']
        assert layout['status']=='passed' and len(layout['cases'])==90
        assert all(not case['failures'] for case in layout['cases'])
        result['service']=service
        result['project_loading']=[]
        for scale in ('1','2'):
            project_output=evidence/('Project-loading-'+scale)
            project_env={**env,'QT_SCALE_FACTOR':scale}
            project_run=subprocess.run([str(exe),'--project-loading-self-test','--require-windows','--output',str(project_output)],cwd=testroot,env=project_env,capture_output=True,timeout=120)
            project=json.loads((project_output/'PROJECT-LOADING-SELF-TEST.json').read_text(encoding='utf-8'))
            assert project_run.returncode==0,project
            assert_project_loading_checks(project)
            result['project_loading'].append({'scale':scale,**project})
        stage2_output=evidence/'Stage2-business-routes'
        stage2_run=subprocess.run([str(exe),'--stage2-self-test','--require-windows','--output',str(stage2_output)],cwd=testroot,env=env,capture_output=True,timeout=180)
        stage2=json.loads((stage2_output/'STAGE2-SELF-TEST.json').read_text(encoding='utf-8'))
        assert stage2_run.returncode==0,stage2
        assert_stage2_checks(stage2);result['stage2']=stage2
        result['stage3']=[]
        for scale in ('1','1.25','1.5','2'):
            stage3_output=evidence/('Stage3-'+scale)
            stage3_run=subprocess.run([str(exe),'--stage3-self-test','--require-windows','--output',str(stage3_output)],cwd=testroot,env={**env,'QT_SCALE_FACTOR':scale},capture_output=True,timeout=180)
            stage3=json.loads((stage3_output/'STAGE3-SELF-TEST.json').read_text(encoding='utf-8'))
            assert stage3_run.returncode==0,stage3
            assert_stage3_checks(stage3);result['stage3'].append({'scale':scale,**stage3})
    result['status']='passed'
    result['limits']=['Automated native Windows runner, not manual Windows 10/11 acceptance',
                      'Native folder picker cancellation tested at 100%/200%; other file selections supplied by harness',
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
