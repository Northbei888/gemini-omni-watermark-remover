@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo === Gemini watermark remover: CPU setup ===
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10-3.12, then run this again.
  echo Download: https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo Node.js/npm was not found. Install Node.js LTS, then run this again.
  echo Download: https://nodejs.org/
  echo.
  pause
  exit /b 1
)

if not exist ".venv-cpu\Scripts\python.exe" (
  echo Creating local CPU Python environment...
  python -m venv .venv-cpu
  if errorlevel 1 goto failed
)

echo Installing Python packages...
".venv-cpu\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv-cpu\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv-cpu\Scripts\python.exe" -m pip install future requests timm yapf
if errorlevel 1 goto failed

echo Installing local ffmpeg/ffprobe...
if not exist "node_modules\ffmpeg-static\ffmpeg.exe" npm install ffmpeg-static ffprobe-static
if errorlevel 1 goto failed

if not exist "ProPainter\inference_propainter.py" (
  where git >nul 2>nul
  if errorlevel 1 (
    echo Git was not found. Install Git, then run this again.
    echo Download: https://git-scm.com/downloads
    echo.
    pause
    exit /b 1
  )
  echo Cloning ProPainter...
  git clone https://github.com/sczhou/ProPainter.git ProPainter
  if errorlevel 1 goto failed
)

echo Applying ProPainter compatibility patch if needed...
git -C ProPainter apply --check ..\propainter.patch >nul 2>nul
if not errorlevel 1 git -C ProPainter apply ..\propainter.patch

echo.
echo CPU setup is complete.
echo Use remove_watermark_cpu_drag.bat by dragging videos onto it.
echo.
pause
exit /b 0

:failed
echo.
echo Setup failed. Check the message above, then run this file again.
echo.
pause
exit /b 1
