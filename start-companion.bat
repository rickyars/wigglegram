@echo off
rem Double-click to start the wigglegram companion and open the app.
rem Leave this window open while you use the app; close it (or Ctrl+C) to stop.
rem Set WIGGLEGRAM_PYTHON to use a different Python (it needs ml-sharp + torch).
title wigglegram companion
cd /d "%~dp0"
set "PY=%WIGGLEGRAM_PYTHON%"
if "%PY%"=="" set "PY=D:\miniconda3\envs\comfyui\python.exe"
if not exist "%PY%" (
  echo Python not found at %PY%
  echo Set WIGGLEGRAM_PYTHON to the python.exe of the env that has ml-sharp installed.
  pause
  exit /b 1
)
"%PY%" wigglegram-companion.py --open
echo.
echo Companion stopped.
pause
