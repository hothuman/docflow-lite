@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -c "import docflow, PySide6, defusedxml" >nul 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -e ".[gui]"
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" launch.py
if errorlevel 1 goto fail
exit /b 0
:fail
echo DocFlow could not start. Install Python 3.12 and check the error above.
echo First setup requires an internet connection to download dependencies.
pause
exit /b 1

