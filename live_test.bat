@echo off
REM One-click live test: installs deps, runs Gnani smoke test + noisy-phone benchmark.
REM Output is saved to eval_out\live_test_log.txt
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
if not exist eval_out mkdir eval_out
set LOG=eval_out\live_test_log.txt
echo ==== Kural live test %DATE% %TIME% ==== > %LOG%

where python >nul 2>&1 || (echo Python not found. Install from https://www.python.org/downloads/ ^(tick "Add to PATH"^) >> %LOG% & type %LOG% & pause & exit /b 1)

if not exist .venv (echo Creating virtual env... & python -m venv .venv)
echo Installing packages (first run takes a minute)...
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt >> %LOG% 2>&1

set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
where ffmpeg >nul 2>&1 || (
  echo Installing ffmpeg via winget...
  winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements >> %LOG% 2>&1
)
where ffmpeg >nul 2>&1 || (
  for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*") do (
    for /d %%B in ("%%D\ffmpeg-*") do set "PATH=%PATH%;%%B\bin"
  )
)
where ffmpeg >> %LOG% 2>&1

echo. >> %LOG%
echo ---- 1. Gnani smoke test ---- >> %LOG%
echo Running Gnani smoke test...
.venv\Scripts\python scripts\gnani_smoke.py >> %LOG% 2>&1

echo. >> %LOG%
echo ---- 2. Retrieval benchmark ---- >> %LOG%
.venv\Scripts\python scripts\eval_rag.py >> %LOG% 2>&1

echo. >> %LOG%
echo ---- 3. Noisy phone benchmark ---- >> %LOG%
echo Running noisy-phone benchmark (2-4 minutes)...
.venv\Scripts\python scripts\eval_noise.py >> %LOG% 2>&1

echo ==== DONE ==== >> %LOG%
type %LOG%
echo.
echo All done. You can close this window.
pause
