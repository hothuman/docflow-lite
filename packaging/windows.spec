# Windows x64, onedir: Qt DLLs remain replaceable next to the application.
from pathlib import Path
import os, sys
from PyInstaller.utils.hooks import collect_data_files

# Build tools may inject Poppler/ICU/OpenSSL into PATH. Never package those
# unrelated DLLs as dependencies of Qt: their ABI can differ from Windows ICU.
allowed_dll_roots = [Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(),
                     Path(os.environ['SYSTEMROOT']).resolve()]
os.environ['PATH'] = os.pathsep.join(str(p) for p in (
    Path(sys.prefix)/'Scripts', Path(sys.base_prefix), Path(sys.base_prefix)/'DLLs',
    Path(os.environ['SYSTEMROOT'])/'System32', Path(os.environ['SYSTEMROOT'])))
root = Path(SPECPATH).parent
a = Analysis(
    [str(root/'launch.py')],
    pathex=[str(root/'src')],
    binaries=[],
    datas=collect_data_files('docflow') + collect_data_files('docx'),
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest','tkinter','PySide6.QtQml','PySide6.QtQuick',
              'PySide6.QtQuickWidgets','PySide6.QtWebEngineCore'],
    noarchive=False,
)
foreign_binaries = [(name, source) for name, source, kind in a.binaries
                    if kind == 'BINARY' and not any(
                        Path(source).resolve().is_relative_to(base) for base in allowed_dll_roots)]
if foreign_binaries:
    raise RuntimeError('Unapproved binary origin; use the pinned build environment: '+repr(foreign_binaries))
pyz = PYZ(a.pure)
exe = EXE(
    pyz,a.scripts,[],exclude_binaries=True,name='DocFlow-Lite',
    debug=False,bootloader_ignore_signals=False,strip=False,upx=False,
    console=False,disable_windowed_traceback=False,
    icon=str(root/'src/docflow/ui/app.ico'),
)
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='DocFlow-Lite')
