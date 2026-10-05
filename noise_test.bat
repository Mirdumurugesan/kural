@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*") do for /d %%B in ("%%D\ffmpeg-*") do set "PATH=%PATH%;%%B\bin"
if not exist eval_out mkdir eval_out
echo Running noisy-phone benchmark (2-4 minutes)...
.venv\Scripts\python scripts\eval_noise.py > eval_out\noise_log.txt 2>&1
type eval_out\noise_log.txt
echo ==== DONE ==== >> eval_out\noise_log.txt
pause
