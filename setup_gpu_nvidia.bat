@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo === Gemini watermark remover: NVIDIA GPU setup ===
echo.

where nvidia-smi >nul 2>nul
if errorlevel 1 (
  echo NVIDIA GPU driver was not detected.
  echo Install the NVIDIA driver first, or use setup_cpu.bat instead.
  echo.
  pause
  exit /b 1
)

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

if not exist ".venv-gpu\Scripts\python.exe" (
  echo Creating local GPU Python environment...
  python -m venv .venv-gpu
  if errorlevel 1 goto failed
)

echo Installing CUDA PyTorch. This download is large and may take a while...
".venv-gpu\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv-gpu\Scripts\python.exe" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
if errorlevel 1 goto failed

echo Installing remaining Python packages...
".venv-gpu\Scripts\python.exe" -m pip install numpy opencv-python scipy scikit-image einops av imageio imageio-ffmpeg tqdm matplotlib addict pyyaml future requests timm yapf
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

echo Verifying CUDA...
".venv-gpu\Scripts\python.exe" -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
if errorlevel 1 goto failed

echo.
echo NVIDIA GPU setup is complete.
echo Use remove_watermark_gpu_drag.bat by dragging videos onto it.
echo.
pause
exit /b 0

:failed
echo.
echo Setup failed. Check the message above, then run this file again.
echo.
pause
exit /b 1
