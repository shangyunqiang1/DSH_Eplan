@echo off
rem Launch the pure-local EPLAN 2025 platform help MCP server (stdio).
setlocal
set "ROOT=%~dp0.."
set "PY="
if exist "%ROOT%\runtime\python-path.txt" set /p PY=<"%ROOT%\runtime\python-path.txt"
if not defined PY set "PY=python"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%PY%" "%ROOT%\server\docs\server.py" --docset 2025guide %*
endlocal
