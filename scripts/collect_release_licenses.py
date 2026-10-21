"""Collect real distribution notices and verified corresponding Qt sources."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
import platform
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ['python-docx','openpyxl','defusedxml','lxml','PySide6-Essentials',
           'shiboken6','et_xmlfile','typing_extensions','pyinstaller']
QTBASE = {'Qt6Core','Qt6Gui','Qt6Widgets','Qt6Test','Qt6Network','Qt6OpenGL',
          'Qt6PrintSupport','Qt6Concurrent','Qt6DBus','Qt6Sql','Qt6Xml'}


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def fetch_source(item, sources):
    target=sources/Path(item['url']).name
    if not target.is_file() or sha256(target)!=item['sha256']:
        request=urllib.request.Request(item['url'],headers={'User-Agent':'DocFlow-Lite-Release/0.1.1'})
        temporary=target.with_suffix(target.suffix+'.partial')
        with urllib.request.urlopen(request,timeout=120) as response, temporary.open('wb') as dest:
            shutil.copyfileobj(response,dest)
        if sha256(temporary)!=item['sha256']:
            raise RuntimeError('Official source SHA256 mismatch: '+target.name)
        temporary.replace(target)
    return target


def collect(bundle, sources):
    notices=bundle/'licenses'
    notices.mkdir(parents=True,exist_ok=True)
    sources.mkdir(parents=True,exist_ok=True)
    distributions=[]
    for name in RUNTIME:
        dist=metadata.distribution(name)
        copied=[]
        for item in dist.files or []:
            if any(word in item.name.lower() for word in ('license','copying','notice','copyright')):
                source=Path(dist.locate_file(item))
                if source.is_file() and source.stat().st_size<2*1024*1024:
                    relative=Path(str(item).replace('..','_'))
                    dest=notices/name/relative
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,dest)
                    copied.append(str(dest.relative_to(bundle)).replace('\\','/'))
        if not copied:
            raise RuntimeError('No wheel license text found for '+name)
        distributions.append({'name':name,'version':dist.version,'license_files':copied})
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('Python installation LICENSE.txt is required')
    shutil.copy2(python_license,notices/'CPython-LICENSE.txt')

    source_items=json.loads((ROOT/'packaging/third-party-sources.json').read_text(encoding='utf-8'))
    license_count=0
    for item in source_items:
        archive=fetch_source(item,sources)
        item['file']=archive.name
        item['bytes']=archive.stat().st_size
        # Read selected archive members without extracting paths, symlinks or code.
        with tarfile.open(archive,'r:xz') as tar:
            for member in tar:
                path=PurePosixPath(member.name)
                if not member.isfile() or member.size>2*1024*1024:
                    continue
                lower=path.name.lower()
                if ('LICENSES' not in path.parts and
                    not any(x in lower for x in ('license','copying','notice','copyright','qt_attribution'))):
                    continue
                if path.is_absolute() or '..' in path.parts:
                    raise RuntimeError('Unexpected source archive path')
                raw=tar.extractfile(member).read()
                dest=notices/'Qt-source-notices'/item['component']/Path(*path.parts[1:])
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(raw)
                license_count+=1
    assert list((notices/'Qt-source-notices').rglob('LGPL-3.0-only.txt')), 'LGPLv3 text missing'
    assert list((notices/'Qt-source-notices').rglob('GPL-3.0-only.txt')), 'GPLv3 text missing'
    qt_dlls=sorted(p.stem for p in bundle.rglob('Qt6*.dll'))
    unsupported=set(qt_dlls)-QTBASE-{'Qt6Svg','Qt6SvgWidgets'}
    if unsupported:
        raise RuntimeError('Review corresponding sources for additional Qt DLLs: '+repr(unsupported))
    assert {'Qt6Core','Qt6Gui','Qt6Widgets'}<=set(qt_dlls)
    notes='''Qt for Python / Qt 6.10.2

This portable application uses Qt and PySide6 under LGPLv3. Full LGPLv3,
GPLv3 and third-party license texts are provided in licenses/.

Qt/PySide6 libraries have not been modified by DocFlow Lite. The DLLs in
_internal/ remain dynamically replaceable. This distribution does not restrict
replacement of LGPL libraries or reverse engineering for debugging changes to
those libraries. Keep a compatible Qt/PySide6/Shiboken ABI and architecture.

Corresponding Qt and PySide6 source archives, build files and original notices
are supplied as the separate ThirdParty-Sources ZIP attached to the same
GitHub release. Source URLs and exact SHA256 are in THIRD-PARTY-SOURCES.json.
Qt build/configuration guidance: https://doc.qt.io/qt-6/build-sources.html
PySide build guidance: https://doc.qt.io/qtforpython-6/building_from_source/windows.html

The third-party licenses apply to their respective components. No new open
source license is granted for DocFlow Lite itself by this notice.
'''
    (bundle/'QT-LGPL-NOTICE.txt').write_text(notes,encoding='utf-8')
    (bundle/'THIRD-PARTY-SOURCES.json').write_text(json.dumps(source_items,indent=2),encoding='utf-8')
    manifest={'python':platform.python_version(),'distributions':distributions,
              'qt_dlls':qt_dlls,'source_notice_files':license_count,
              'source_archives':source_items,'method':'onedir, unmodified upstream wheels'}
    (bundle/'THIRD-PARTY-LICENSES.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'distributions':len(distributions),'source_notice_files':license_count,'qt_dlls':qt_dlls}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--sources',type=Path,required=True)
    args=parser.parse_args()
    collect(args.bundle.resolve(),args.sources.resolve())
