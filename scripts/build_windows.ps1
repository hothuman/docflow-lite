param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& $Python -c "import sys; assert sys.version_info[:3] == (3,13,16), 'Use CPython 3.13.16 x64 for this release'"
if ($LASTEXITCODE -ne 0) { throw 'Unexpected build interpreter' }
& $Python -m pip install --require-hashes -r requirements/windows-x64.lock
if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency installation failed' }
& $Python -m pip install --no-deps --no-build-isolation -e .
if ($LASTEXITCODE -ne 0) { throw 'Project installation failed' }
New-Item -ItemType Directory -Force artifacts | Out-Null
$previousQtPlatform = $env:QT_QPA_PLATFORM
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    & $Python -m pytest -q tests site/tests --junitxml=artifacts/windows-tests.xml
    if ($LASTEXITCODE -ne 0) { throw 'Source tests failed' }
} finally {
    if ($null -eq $previousQtPlatform) { Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue }
    else { $env:QT_QPA_PLATFORM = $previousQtPlatform }
}
& $Python -m PyInstaller --noconfirm --clean packaging/windows.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
& $Python scripts/collect_release_licenses.py --bundle dist/DocFlow-Lite --sources build/third-party-sources
if ($LASTEXITCODE -ne 0) { throw 'License/source collection failed' }
& $Python scripts/package_windows.py
if ($LASTEXITCODE -ne 0) { throw 'Portable packaging failed' }
& $Python scripts/verify_windows_bundle.py --archive release/DocFlow-Lite-0.1.1-Windows-x64-Portable.zip
if ($LASTEXITCODE -ne 0) { throw 'Compiled Windows EXE runtime check failed' }
& $Python scripts/package_windows.py --checksums-only
if ($LASTEXITCODE -ne 0) { throw 'Checksums failed' }
Write-Host 'Portable ZIP extracted and EXE executed twice on native Windows.'
Write-Host 'Manual Windows 10/11 acceptance remains separate; see WINDOWS-CI-RESULTS.json.'

