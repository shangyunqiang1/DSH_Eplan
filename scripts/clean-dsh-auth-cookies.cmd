@echo off
rem ---------------------------------------------------------------------------
rem  Launch DeepSeek Harness after cleaning accumulated dsh-auth-* cookies.
rem
rem  Why: the desktop host hard-codes --port 0 (random port) and the session
rem  cookie is named "dsh-auth-" + base64url(sha256(host:port)). Every launch
rem  mints a NEW cookie name; the old ones are never replaced and stay valid for
rem  Max-Age days (client-connection cookieMaxAgeDays, default 30). The Cookie
rem  header grows with every launch past Node's 16 KB default limit, the welcome
rem  handshake comes back 431, and DSH dies with
rem  "desktop welcome: Web authentication failed".
rem
rem  This wrapper cleans the jar while DSH is closed, raises the header limit as a
rem  safety net, then starts DSH in its normal working directory.
rem  Exit codes from the cleaner: 0 ok, 2 DSH running (skip), 4 store unreadable.
rem  Reversible: the original Start Menu shortcut is kept as
rem  "DeepSeek Harness.lnk.bak-original".
rem ---------------------------------------------------------------------------
setlocal
chcp 65001 >nul

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "CLEANER=%~dp0clean-dsh-auth-cookies.ps1"
set "DSH=D:\Programs\DeepSeek Harness\DeepSeek Harness.exe"
set "DSHDIR=D:\Programs\DeepSeek Harness"

rem Safety net: leave room for accumulated cookies even if cleanup is skipped.
set "NODE_OPTIONS=--max-http-header-size=1048576"

if not exist "%CLEANER%" goto :launch
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%CLEANER%"
rem  `if errorlevel N` means "exit code >= N", so higher codes must be tested first.
if errorlevel 4 goto :cleanupfailed
if errorlevel 2 goto :alreadyrunning
if errorlevel 1 goto :cleanupfailed

echo.
echo Cookies cleaned. Starting DeepSeek Harness...
goto :launch

:cleanupfailed
echo.
echo WARNING: cookie cleanup did not complete - starting anyway.
echo          The header limit set above still protects this launch.
goto :launch

:alreadyrunning
echo.
echo DeepSeek Harness is already running - skipped cookie cleanup.

:launch
start "" /D "%DSHDIR%" "%DSH%"
exit /b 0
