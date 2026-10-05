@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
if not exist eval_out mkdir eval_out
.venv\Scripts\python scripts\tts_probe.py > eval_out\tts_probe_log.txt 2>&1
echo ==== DONE ==== >> eval_out\tts_probe_log.txt
type eval_out\tts_probe_log.txt
pause
