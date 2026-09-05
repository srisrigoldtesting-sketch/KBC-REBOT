@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv-windows\Scripts\python.exe" goto missing
if "%~1"=="start" goto start
if "%~1"=="configure" goto configure
if "%~1"=="check" goto check
if "%~1"=="session" goto session
if "%~1"=="test" goto test
echo Use INSTALL.cmd, CONFIGURE.cmd, CHECK.cmd or START.cmd.
exit /b 1
:start
".venv-windows\Scripts\python.exe" -m app.main
goto complete
:configure
".venv-windows\Scripts\python.exe" -m app.configure
goto complete
:check
".venv-windows\Scripts\python.exe" -m app.diagnostics
goto complete
:session
".venv-windows\Scripts\python.exe" -m app.generate_session
goto complete
:test
".venv-windows\Scripts\python.exe" -m unittest discover -s tests -q
goto complete
:complete
set "KBC_EXIT=%errorlevel%"
if not "%KBC_EXIT%"=="0" echo The operation stopped. Read the message above.
if /i not "%~2"=="--no-pause" pause
exit /b %KBC_EXIT%
:missing
echo First extract the ZIP and run INSTALL.cmd.
if /i not "%~2"=="--no-pause" pause
exit /b 1
