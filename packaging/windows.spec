# Windows x64, onedir: Qt DLLs remain replaceable next to the application.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

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
pyz = PYZ(a.pure)
exe = EXE(
    pyz,a.scripts,[],exclude_binaries=True,name='DocFlow-Lite',
    debug=False,bootloader_ignore_signals=False,strip=False,upx=False,
    console=False,disable_windowed_traceback=False,
    icon=str(root/'src/docflow/ui/app.ico'),
)
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='DocFlow-Lite')
