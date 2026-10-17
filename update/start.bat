@echo off
cd /d "%~dp0"
title Eme PC Remote v0.3
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 EmePCRemote.py
) else (
  python EmePCRemote.py
)
pause
