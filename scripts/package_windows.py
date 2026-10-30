"""Package the verified Windows onedir bundle and corresponding source files."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import tomllib
import zipfile
from pathlib import Path

from generate_sbom import generate as generate_sbom
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from docflow.versioning import stage,is_prerelease

ROOT=Path(__file__).resolve().parents[1]
VERSION=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
INSTRUCTIONS=ROOT/'docs'/'README-WINDOWS-SERVICE.txt'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def archive_tree(path, folder, prefix):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for source in sorted(folder.rglob('*')):
            if source.is_file():
                assert not source.is_symlink()
                archive.write(source,str(Path(prefix)/source.relative_to(folder)))
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist())==len(set(archive.namelist()))


def package(bundle,out,sources):
    assert os.name=='nt' and platform.machine().lower() in {'amd64','x86_64'}
    assert (bundle/'DocFlow-Lite.exe').is_file() and (bundle/'_internal').is_dir()
    assert (bundle/'THIRD-PARTY-LICENSES.json').is_file()
    out.mkdir(parents=True,exist_ok=True)
    instruction_lines=INSTRUCTIONS.read_text(encoding='utf-8').splitlines()
    instruction_lines[0]=f'DocFlow Lite {VERSION} — Core + Service · {stage(VERSION)}'
    instruction_lines[2]=('Кандидат стабильной версии. Это ещё не стабильный выпуск.' if stage(VERSION)=='RC' else 'Предварительный выпуск.' if is_prerelease(VERSION) else 'Стабильный выпуск с ограничениями, указанными в документации.')
    (bundle/'README-WINDOWS.txt').write_text('\n'.join(instruction_lines)+'\n',encoding='utf-8')
    shutil.copy2(ROOT/'THIRD_PARTY.md',bundle/'THIRD_PARTY.md')
    shutil.copy2(ROOT/'LICENSE.txt',bundle/'LICENSE.txt')
    shutil.copytree(ROOT/'src/docflow/examples',bundle/'examples',dirs_exist_ok=True)
    if (ROOT/'examples/catalog').is_dir():shutil.copytree(ROOT/'examples/catalog',bundle/'examples/catalog',dirs_exist_ok=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    sbom=generate_sbom(bundle,VERSION,commit)
    (bundle/'SBOM.cdx.json').write_bytes((json.dumps(sbom,ensure_ascii=False,indent=2)+'\n').encode())
    shutil.copy2(bundle/'SBOM.cdx.json',out/'SBOM.cdx.json')
    manifest={str(p.relative_to(bundle)).replace('\\','/'):sha256(p)
              for p in sorted(bundle.rglob('*')) if p.is_file() and p.name!='BUNDLE-SHA256.json'}
    assert not any(p.endswith(('.pem','.key')) for p in manifest)
    (bundle/'BUNDLE-SHA256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    portable=out/f'DocFlow-Lite-{VERSION}-Windows-x64-Portable.zip'
    archive_tree(portable,bundle,'DocFlow-Lite')
    source_zip=out/f'DocFlow-Lite-{VERSION}-Source.zip'
    hashes=json.loads((ROOT/'FILE_HASHES.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(source_zip,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,digest in sorted(hashes.items()):
            source=ROOT/name
            assert sha256(source)==digest, 'Source manifest mismatch: '+name
            archive.write(source,'docflow-lite/'+name)
        archive.write(ROOT/'FILE_HASHES.json','docflow-lite/FILE_HASHES.json')
    with zipfile.ZipFile(source_zip) as archive:assert archive.testzip() is None
    library_zip=out/f'DocFlow-Lite-{VERSION}-ThirdParty-Sources.zip'
    archive_tree(library_zip,sources,'ThirdParty-Sources')
    info={'version':VERSION,'python':platform.python_version(),'platform':platform.platform(),
          'architecture':platform.machine(),
          'commit':commit,
          'runner_os':os.environ.get('RUNNER_OS'),'runner_image':os.environ.get('ImageOS'),
          'runner_image_version':os.environ.get('ImageVersion'),
          'dependencies':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
          'exe_sha256':sha256(bundle/'DocFlow-Lite.exe'),
          'procedure':'Pinned Windows wheels with SHA256, PyInstaller onedir; byte-for-byte reproducibility is not claimed'}
    (out/'BUILD-INFO.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    shutil.copy2(bundle/'README-WINDOWS.txt',out/'README-WINDOWS.txt')
    shutil.copy2(ROOT/'LICENSE.txt',out/'LICENSE.txt')
    print(json.dumps({'portable':str(portable),'source':str(source_zip),'third_party_sources':str(library_zip)}))


def checksums(out,bundle):
    files=sorted(p for p in out.iterdir() if p.is_file() and p.name!='SHA256SUMS.txt')
    lines=[f'{sha256(path)}  {path.name}' for path in files]
    lines.append(f'{sha256(bundle/"DocFlow-Lite.exe")}  DocFlow-Lite/DocFlow-Lite.exe')
    (out/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--bundle',type=Path,default=ROOT/'dist/DocFlow-Lite')
    parser.add_argument('--out',type=Path,default=ROOT/'release')
    parser.add_argument('--sources',type=Path,default=ROOT/'build/third-party-sources')
    parser.add_argument('--checksums-only',action='store_true')
    args=parser.parse_args()
    if args.checksums_only:checksums(args.out,args.bundle)
    else:package(args.bundle,args.out,args.sources)
