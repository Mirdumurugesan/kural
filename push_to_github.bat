@echo off
REM Publishes this folder to https://github.com/Mirdumurugesan/kural (secrets in .env are git-ignored).
chcp 65001 >nul
cd /d "%~dp0"
if not exist eval_out mkdir eval_out
set LOG=eval_out\git_log.txt
echo ==== push %DATE% %TIME% ==== > %LOG%
where git >> %LOG% 2>&1 || (echo Git is not installed. Get it from https://git-scm.com/download/win >> %LOG% & type %LOG% & pause & exit /b 1)
if not exist .git (
  git init -b main >> %LOG% 2>&1
  git remote add origin https://github.com/Mirdumurugesan/kural.git >> %LOG% 2>&1
)
for /f "delims=" %%E in ('git config user.email') do set GEMAIL=%%E
if "%GEMAIL%"=="" git config user.email "mirdulamurugesan@gmail.com"
for /f "delims=" %%N in ('git config user.name') do set GNAME=%%N
if "%GNAME%"=="" git config user.name "Mirdula M"
git add -A >> %LOG% 2>&1
git status --short >> %LOG% 2>&1
git ls-files | findstr /i /c:".env" | findstr /v /i "example" >> %LOG% && (echo REFUSING: .env is staged >> %LOG% & type %LOG% & pause & exit /b 1)
git commit -q -F eval_out\commit_msg.txt >> %LOG% 2>&1
echo Pushing... a GitHub sign-in window may open: click Authorize / Sign in.
git push -u origin main >> %LOG% 2>&1
echo exit code %ERRORLEVEL% >> %LOG%
echo ==== DONE ==== >> %LOG%
type %LOG%
pause
