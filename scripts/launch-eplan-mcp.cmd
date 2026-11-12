@echo off
rem Launch the bundled EPLAN MCP server over stdio (called by dsh-mcp-client).
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "ROOT=%~dp0.."
rem The EPLAN install path chosen in the plugin settings (runtime\eplan-platform-root.txt).
rem The MCP server reads EPLAN_PLATFORM_ROOT once at start-up, so it must be set here,
rem before python imports the module - a value saved later only applies after a reload.
set "EPLAN_ROOT_FILE=%ROOT%\runtime\eplan-platform-root.txt"
if not exist "%EPLAN_ROOT_FILE%" goto :noroot
for /f "usebackq delims=" %%L in ("%EPLAN_ROOT_FILE%") do set "EPLAN_PLATFORM_ROOT=%%L"
if not defined EPLAN_PLATFORM_ROOT goto :noroot
if not exist "%EPLAN_PLATFORM_ROOT%" goto :badroot
goto :noroot
:badroot
echo [dsh-eplan] ignoring missing EPLAN platform root 1>&2
set "EPLAN_PLATFORM_ROOT="
:noroot
rem --- Strip HTTP proxy variables before starting the MCP server -------------
rem EPLAN's Remote Client talks gRPC over a native (C-core) channel. That stack
rem honours HTTP_PROXY/HTTPS_PROXY/ALL_PROXY even for LAN and loopback targets and
rem tunnels through the proxy, where the CONNECT tunnel to EPLAN's remoting port
rem is dropped -> "failed to connect to all addresses" (grpc_status 14), while a
rem plain TCP/h2c test to the same host:port succeeds. gRPC reads the variables
rem from the real process environment, so they must be cleared here, before
rem python starts; clearing os.environ from inside the server is too late.
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "ALL_PROXY="
set "http_proxy="
set "https_proxy="
set "all_proxy="
set "GRPC_PROXY="
set "grpc_proxy="
set "NODE_USE_ENV_PROXY="
rem ---------------------------------------------------------------------------
set "PY="
if exist "%ROOT%\runtime\python-path.txt" set /p PY=<"%ROOT%\runtime\python-path.txt"
if not defined PY set "PY=python"
cd /d "%ROOT%\vendor\eplan-mcp\eplan-p8-mcp-server\mcp_server"
"%PY%" "%ROOT%\vendor\eplan-mcp\eplan-p8-mcp-server\mcp_server\server.py" %*
