$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create Python 3.12 environment' }
}
$docflowPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
& $docflowPython -m pip install -e '.[gui,dev,build]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $docflowPython -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
& $docflowPython -m PyInstaller --noconfirm --clean --onedir --windowed --name DocFlow-Lite --paths src --collect-data docflow launch.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
Copy-Item README.md,THIRD_PARTY.md dist\DocFlow-Lite\
Copy-Item -Recurse src dist\DocFlow-Lite\source
Write-Host 'Build created in dist\DocFlow-Lite. Launch the EXE on Windows and verify results.'
Write-Host 'Before distribution, complete the dependency-license review described in THIRD_PARTY.md.'

