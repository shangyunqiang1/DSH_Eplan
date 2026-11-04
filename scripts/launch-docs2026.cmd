@echo off
setlocal
set "ROOT=%~dp0.."
set "PY=python"
if exist "%ROOT%\runtime\python-path.txt" set /p PY=<"%ROOT%\runtime\python-path.txt"
"%PY%" "%ROOT%\server\docs\server.py" --docset 2026 %*
