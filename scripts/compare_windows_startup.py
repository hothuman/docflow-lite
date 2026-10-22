"""Read-only comparison with the immutable public 0.1.1 portable, on Windows CI.

Only the expected SHA256 is executed. No release, tag, site or source is modified.
"""
import argparse,hashlib,json,os,statistics,tempfile,zipfile
from pathlib import Path, PurePosixPath
from urllib.request import Request,urlopen
from verify_windows_bundle import normal_start

URL='https://github.com/hothuman/docflow-lite/releases/download/v0.1.1/DocFlow-Lite-0.1.1-Windows-x64-Portable.zip'
EXPECTED='c0cac130ec4b39d7d42f0ea6ea1d5f128ff6402c89cc4cb8518bc60403f2a034'

def run(exe,output):
    assert os.name=='nt'
    env=os.environ.copy()
    for key in list(env):
        if key.upper().startswith(('PYTHON','QT_','VIRTUAL_ENV')):env.pop(key)
    env['PATH']=str(Path(os.environ['SYSTEMROOT'])/'System32')
    with tempfile.TemporaryDirectory(prefix='DocFlow before after ') as temp:
        root=Path(temp);archive=root/'baseline.zip'
        with urlopen(Request(URL,headers={'User-Agent':'DocFlow-Lite-RC-QA'}),timeout=120) as response:
            with archive.open('wb') as stream:
                while data:=response.read(1024*1024):stream.write(data)
        assert hashlib.sha256(archive.read_bytes()).hexdigest()==EXPECTED,'Unexpected baseline archive; will not execute'
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            for name in z.namelist():
                path=PurePosixPath(name)
                assert not path.is_absolute() and '..' not in path.parts and '\\' not in name
                assert path.parts[0]=='DocFlow-Lite'
            z.extractall(root/'before')
        baseline=root/'before/DocFlow-Lite/DocFlow-Lite.exe'
        # Interleave samples to reduce ordering/cache bias; no Python on child PATH.
        before=[];after=[]
        for _ in range(3):
            before.append(normal_start(baseline,root,env));after.append(normal_start(exe,root,env))
        report={'status':'passed','baseline_release':'v0.1.1','baseline_zip_sha256':EXPECTED,
                'before':before,'after':after,'manual_windows_test':False,
                'startup_before_median_s':statistics.median(v['startup_to_visible_s'] for v in before),
                'startup_after_median_s':statistics.median(v['startup_to_visible_s'] for v in after),
                'scope':'Three interleaved native Windows CI startup/working-set samples; no document workload. 100 ms window polling. Not a physical Windows 10/11 test.'}
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:report[k] for k in ['status','startup_before_median_s','startup_after_median_s']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--exe',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.exe.resolve(),args.output.resolve())
