@echo off
rem Launch the offline EPLAN 2025 documentation MCP server over stdio.
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "ROOT=%~dp0.."
set "PY="
if exist "%ROOT%\runtime\python-path.txt" set /p PY=<"%ROOT%\runtime\python-path.txt"
if not defined PY set "PY=python"
cd /d "%ROOT%\server\docs2025"
"%PY%" "%ROOT%\server\docs2025\server.py" %*
