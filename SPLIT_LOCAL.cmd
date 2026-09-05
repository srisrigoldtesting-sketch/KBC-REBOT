@echo off
title KBC REBOT - Split a local file
call "%~dp0RUN.cmd" split
exit /b %errorlevel%
