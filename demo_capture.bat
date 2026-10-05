@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*") do for /d %%B in ("%%D\ffmpeg-*") do set "PATH=%PATH%;%%B\bin"
if not exist eval_out mkdir eval_out
echo Recording real Gnani responses for the demo video...
.venv\Scripts\python scripts\demo_capture.py > eval_out\demo_log.txt 2>&1
echo ==== DONE ==== >> eval_out\demo_log.txt
type eval_out\demo_log.txt
pause
