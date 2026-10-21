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
import zipfile
from pathlib import Path
from docx import Document

ROOT=Path(__file__).resolve().parents[1]


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
        env['PATH']=str(Path(env['SystemRoot'])/'System32')
        result['runtime_path_contains_python']=False
        for attempt in (1,2):
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
                                   'frozen':report['frozen'],'qt_platform':report['qt_platform'],
                                   'checks':report['checks'],'generated_docx':len(docs)})
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
