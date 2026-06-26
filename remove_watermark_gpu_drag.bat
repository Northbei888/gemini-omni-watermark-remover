@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "WATERMARK_BOX=1136,576,48,48"
set "PYTHON_EXE=%~dp0.venv-gpu\Scripts\python.exe"

if "%~1"=="" (
  echo Drag one or more 1280x720 video files onto this BAT file.
  echo Current watermark box: %WATERMARK_BOX%
  echo.
  pause
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo GPU environment was not found.
  echo Run setup_gpu_nvidia.bat first.
  echo.
  pause
  exit /b 1
)

set "PATH=%~dp0node_modules\ffmpeg-static;%~dp0node_modules\ffprobe-static\bin\win32\x64;%PATH%"
set "PYTHONIOENCODING=utf-8"

:process_next
if "%~1"=="" goto done

set "INPUT=%~1"
set "OUTPUT=%~dpn1_clean.mp4"

echo.
echo Processing on NVIDIA GPU:
echo %INPUT%
echo.
echo Output:
echo %OUTPUT%
echo.

"%PYTHON_EXE%" dewatermark.py "%INPUT%" --box %WATERMARK_BOX% --device cuda -o "%OUTPUT%"
if errorlevel 1 (
  echo.
  echo Failed:
  echo %INPUT%
  echo.
) else (
  echo.
  echo Done:
  echo %OUTPUT%
  echo.
)

shift
goto process_next

:done
echo All done.
echo.
pause
