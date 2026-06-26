@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "WATERMARK_BOX=1136,576,48,48"
set "PYTHON_EXE=%~dp0.venv-cpu\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0.venv-gpu\Scripts\python.exe"

if "%~1"=="" (
  echo Drag one video file onto this BAT file to preview the watermark box.
  echo Current watermark box: %WATERMARK_BOX%
  echo.
  pause
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo No local environment was found.
  echo Run setup_cpu.bat or setup_gpu_nvidia.bat first.
  echo.
  pause
  exit /b 1
)

set "PATH=%~dp0node_modules\ffmpeg-static;%~dp0node_modules\ffprobe-static\bin\win32\x64;%PATH%"
set "PYTHONIOENCODING=utf-8"

"%PYTHON_EXE%" dewatermark.py "%~1" --box %WATERMARK_BOX% --preview
echo.
pause
