@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv-cpu\Scripts\python.exe"

if "%~1"=="" (
  echo Drag one or more 1280x720 or 720x1280 video files onto this BAT file.
  echo Supported sizes: 1280x720 and 720x1280.
  echo.
  pause
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo CPU environment was not found.
  echo Run setup_cpu.bat first.
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
echo Processing on CPU:
echo %INPUT%
echo.
echo Output:
echo %OUTPUT%
echo.

"%PYTHON_EXE%" dewatermark.py "%INPUT%" --omni-box -o "%OUTPUT%"
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
