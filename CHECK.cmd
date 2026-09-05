@echo off
title KBC REBOT - Connection checks
call "%~dp0RUN.cmd" check
exit /b %errorlevel%
