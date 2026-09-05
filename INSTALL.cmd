@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title KBC REBOT - Install
set "PYTHONUTF8=1"
set "KBC_NO_PAUSE="
if /i "%~1"=="--check" set "KBC_NO_PAUSE=1"
echo KBC REBOT - Windows setup
echo Extract this folder first. Internet access is needed for installation.
if exist ".venv-windows\Scripts\python.exe" goto install_dependencies
call :find_python
if defined KBC_PY goto create_environment
where winget >nul 2>&1
if errorlevel 1 goto missing_python
echo Installing Python 3.13 for your Windows user using WinGet...
winget install --id Python.Python.3.13 --exact --source winget --scope user --architecture x64 --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
if errorlevel 1 goto missing_python
call :find_python
if not defined KBC_PY goto missing_python

:create_environment
%KBC_PY% -m venv ".venv-windows"
if errorlevel 1 goto failed

:install_dependencies
".venv-windows\Scripts\python.exe" -c "import sys,struct; sys.exit(0 if sys.version_info[:2] in [(3,12),(3,13)] and struct.calcsize('P')==8 else 1)"
if errorlevel 1 goto wrong_python
".venv-windows\Scripts\python.exe" -m pip install --disable-pip-version-check --timeout 60 --retries 3 -r requirements.txt
if errorlevel 1 goto failed
".venv-windows\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
".venv-windows\Scripts\python.exe" -m unittest discover -s tests -q
if errorlevel 1 goto failed
echo Installation and local tests passed.
if defined KBC_NO_PAUSE exit /b 0
".venv-windows\Scripts\python.exe" -m app.configure
if errorlevel 1 goto failed
echo Next: CHECK.cmd, then START.cmd. Keep credentials on this laptop.
pause
exit /b 0

:find_python
set "KBC_PY="
py -3.13 -c "import struct; assert struct.calcsize('P')==8" >nul 2>&1
if not errorlevel 1 set "KBC_PY=py -3.13"
if defined KBC_PY exit /b 0
py -3.12 -c "import struct; assert struct.calcsize('P')==8" >nul 2>&1
if not errorlevel 1 set "KBC_PY=py -3.12"
if defined KBC_PY exit /b 0
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set KBC_PY="%LocalAppData%\Programs\Python\Python313\python.exe"
if defined KBC_PY exit /b 0
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set KBC_PY="%LocalAppData%\Programs\Python\Python312\python.exe"
if defined KBC_PY exit /b 0
python -c "import sys,struct; assert sys.version_info[:2] in [(3,12),(3,13)] and struct.calcsize('P')==8" >nul 2>&1
if not errorlevel 1 set "KBC_PY=python"
exit /b 0

:missing_python
echo Python installation was unavailable. Install Python 3.13 64-bit from:
echo https://www.python.org/downloads/windows/
echo Include tkinter and pip, then run INSTALL.cmd again.
goto failed

:wrong_python
echo This environment needs Python 3.12 or 3.13 64-bit.
echo Rename the .venv-windows folder and run INSTALL.cmd again.

:failed
echo Setup stopped. Read the error above; your settings were not deleted.
if not defined KBC_NO_PAUSE pause
exit /b 1
