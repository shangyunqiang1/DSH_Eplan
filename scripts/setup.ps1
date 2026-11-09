# DSH_Eplan setup: resolve the Python runtime, normalize launchers, and build the
# offline EPLAN 2025 API index.
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -RebuildIndex
#
# The plugin needs a Python 3.12+ interpreter (3.13 on this machine) that has
# `mcp` (>=1.19,<2 — eplan-mcp v1.3.0 tool annotations need it) and `pythonnet`
# (`clr`) for the EPLAN automation server. The EPLAN_Skills environment is
# preferred; a venv with `pip install -r vendor\eplan-mcp\...\requirements.txt`
# works too. The documentation server itself only needs the standard library.

[CmdletBinding()]
param(
    [string]$Python,
    [string]$PlatformRoot,
    [switch]$SkipIndex,
    [switch]$RebuildIndex
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $Root 'runtime'
$PythonFile = Join-Path $RuntimeDir 'python-path.txt'
$PatchFile = Join-Path $Root 'cordis.patch.yml'
$VendorServer = Join-Path $Root 'vendor\eplan-mcp\eplan-p8-mcp-server\mcp_server\server.py'
$IndexScript = Join-Path $Root 'scripts\build-eplan2025-index.py'
$DbFile = Join-Path $Root 'data\eplan2025.sqlite'
$PlatformRootFile = Join-Path $RuntimeDir 'eplan-platform-root.txt'

Write-Host "DSH_Eplan root: $Root"

# --- 1. Normalize the launchers to CRLF (cmd.exe requirement) ---------------
Get-ChildItem (Join-Path $Root 'scripts') -Filter '*.cmd' -ErrorAction SilentlyContinue | ForEach-Object {
    $text = [System.IO.File]::ReadAllText($_.FullName)
    $text = $text -replace "`r?`n", "`r`n"
    [System.IO.File]::WriteAllText($_.FullName, $text, [System.Text.Encoding]::ASCII)
}

# --- 2. Vendor check --------------------------------------------------------
# The vendored server is pinned to eplan-mcp v1.3.0 (see
# vendor\eplan-mcp\PROVENANCE.md). A Bochica self-update can change its own
# runtime, so never silently copy an unpinned version over a missing one: if the
# bundled server is gone, fail loudly with the exact restore command instead.
if (-not (Test-Path $VendorServer)) {
    $fallback = Join-Path $env:LOCALAPPDATA 'Programs\bochica\resources\runtime\eplan-mcp'
    if (Test-Path (Join-Path $fallback 'eplan-p8-mcp-server\mcp_server\server.py')) {
        Write-Warning "Bundled eplan-mcp v1.3.0 is missing. A legacy Bochica runtime exists at $fallback, but it is NOT pinned and may be a different version — refusing to copy it automatically."
        Write-Warning "Restore the pinned snapshot: re-install the plugin package (vendor/eplan-mcp is shipped with it), or re-sync from upstream tag v1.3.0 / commit 77a78f63 per PROVENANCE.md."
    }
    throw "Bundled eplan-mcp v1.3.0 server not found at $VendorServer. Re-install the plugin package or restore vendor\eplan-mcp from the pinned upstream commit; do not substitute an unpinned Bochica runtime."
}

# --- 3. Resolve Python ------------------------------------------------------
function Test-EplanPython([string]$Exe) {
    if ([string]::IsNullOrWhiteSpace($Exe) -or -not (Test-Path $Exe)) { return $false }
    & $Exe -c "import sys, mcp, clr; sys.exit(0)" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

$candidates = [System.Collections.Generic.List[string]]::new()
if ($Python) { $candidates.Add($Python) }
if ($env:EPLAN_DSH_PYTHON) { $candidates.Add($env:EPLAN_DSH_PYTHON) }
# Prefer the EPLAN_Skills runtime (the interpreter this bundle was set up with).
Get-ChildItem (Join-Path $env:LOCALAPPDATA 'EPLAN_Skills\environments') -Directory -ErrorAction SilentlyContinue |
    ForEach-Object {
        $candidates.Add((Join-Path $_.FullName 'Scripts\python.exe'))
        $candidates.Add((Join-Path $_.FullName 'python.exe'))
    }
# Legacy Bochica bundled interpreter, kept only as a last-resort fallback.
$candidates.Add((Join-Path $env:LOCALAPPDATA 'Programs\bochica\resources\runtime\python\python.exe'))
try {
    $pyLauncher = & py -3 -c "import sys;print(sys.executable)" 2>$null
    if ($pyLauncher) { $candidates.Add($pyLauncher.Trim()) }
} catch { }
$pathPython = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if ($pathPython) { $candidates.Add($pathPython) }

$resolved = $null
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (Test-EplanPython $candidate) { $resolved = $candidate; break }
}

$pythonOk = $true
if (-not $resolved) {
    # The documentation index only needs a plain Python; keep the bundle usable.
    $pythonOk = $false
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ($candidate -and (Test-Path $candidate)) {
            & $candidate -c "import sys; sys.exit(0)" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { $resolved = $candidate; break }
        }
    }
}
if (-not $resolved) {
    throw "No Python interpreter found. Install Python 3.12+, or set EPLAN_DSH_PYTHON to a Python that has 'mcp' (>=1.19,<2) and 'pythonnet' installed."
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
Set-Content -Path $PythonFile -Value $resolved -Encoding ascii -NoNewline
Write-Host "Python: $resolved"
if (-not $pythonOk) {
    Write-Warning "This Python lacks 'mcp'/'pythonnet': the EPLAN automation server will not start. The 2025 documentation server still works."
}

# --- 4. Bundle patch self-check --------------------------------------------
# cordis.patch.yml contains no absolute path: every row launches
# scripts\launch-*.cmd by a cwd-relative name, and the `cwd:` values are
# evaluated at load time from the installed package location. Nothing has to be
# rewritten after a move or a fresh clone, so this stage only verifies that the
# bundle still holds together and points the user at the plugin settings page
# when it does not.
if (Test-Path $PatchFile) {
    $patch = [System.IO.File]::ReadAllText($PatchFile)
    $absolute = [regex]::Matches($patch, "[A-Za-z]:[\\/][^'\r\n]*")
    if ($absolute.Count -gt 0) {
        Write-Warning "cordis.patch.yml contains $($absolute.Count) absolute path(s); the bundle is meant to stay portable. Check the file against the packaged version."
    }
    foreach ($launcher in @('launch-eplan-mcp.cmd', 'launch-docs2025.cmd', 'launch-docs2025guide.cmd', 'launch-docs2026.cmd', 'launch-docs2027.cmd', 'launch-docseecpro.cmd')) {
        $path = Join-Path $Root "scripts\$launcher"
        if (-not (Test-Path $path)) { Write-Warning "Bundle launcher missing: $path" }
    }
}

# --- 5. EPLAN install path --------------------------------------------------
# The bundled MCP server scans one Platform root for installed versions and
# reads EPLAN_PLATFORM_ROOT only once, at start-up. Remember the root we find
# here so scripts\launch-eplan-mcp.cmd can export it, and never overwrite a root
# the user already picked in the plugin settings page.
function Test-EplanPlatformRoot([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return $false }
    foreach ($child in (Get-ChildItem -LiteralPath $Path -Directory -ErrorAction SilentlyContinue)) {
        if (Test-Path -LiteralPath (Join-Path $child.FullName 'Bin\Eplan.EplApi.RemoteClientu.dll')) { return $true }
    }
    return $false
}

$rootCandidates = [System.Collections.Generic.List[string]]::new()
if ($PlatformRoot) { $rootCandidates.Add($PlatformRoot) }
if ($env:EPLAN_PLATFORM_ROOT) { $rootCandidates.Add($env:EPLAN_PLATFORM_ROOT) }
foreach ($base in @($env:ProgramFiles, 'C:\Program Files', ${env:ProgramFiles(x86)})) {
    if ($base) { $rootCandidates.Add((Join-Path $base 'EPLAN\Platform')) }
}
# EPLAN sometimes installs a platform folder beside the usual one.
foreach ($base in @($env:ProgramFiles, 'C:\Program Files', ${env:ProgramFiles(x86)})) {
    if (-not $base) { continue }
    Get-ChildItem -LiteralPath (Join-Path $base 'EPLAN') -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'Platform*' } |
        ForEach-Object { $rootCandidates.Add($_.FullName) }
}

$detectedRoot = $null
foreach ($candidate in ($rootCandidates | Select-Object -Unique)) {
    if (Test-EplanPlatformRoot $candidate) { $detectedRoot = $candidate.TrimEnd('\'); break }
}

$chosenRoot = $null
if (Test-Path -LiteralPath $PlatformRootFile) {
    $existing = (Get-Content -LiteralPath $PlatformRootFile -TotalCount 1 -ErrorAction SilentlyContinue)
    if ($existing) { $existing = ($existing -replace '^\uFEFF', '').Trim() }
    if ($existing) { $chosenRoot = $existing }
}

if ($chosenRoot -and (Test-EplanPlatformRoot $chosenRoot)) {
    Write-Host "EPLAN install path: $chosenRoot (kept from settings)"
} elseif ($detectedRoot) {
    # No BOM: cmd.exe's for /f would carry it into the environment variable.
    [System.IO.File]::WriteAllText($PlatformRootFile, $detectedRoot + "`n", (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "EPLAN install path: $detectedRoot (detected)"
} else {
    Write-Warning "No EPLAN Platform installation found. Install EPLAN, or set the folder in the plugin settings page (设置 → 插件 → dsh-eplan)."
}

# --- 6. Build the offline EPLAN 2025 documentation index --------------------
if (-not $SkipIndex) {
    if ((-not (Test-Path $DbFile)) -or $RebuildIndex) {
        Write-Host "Building EPLAN 2025 API index (this can take a minute)..."
        & $resolved $IndexScript
        if ($LASTEXITCODE -ne 0) { throw "Index build failed (exit $LASTEXITCODE)." }
    } else {
        Write-Host "EPLAN 2025 index already present: $DbFile (use -RebuildIndex to refresh)"
    }
}

# --- 7. Summary -------------------------------------------------------------
Write-Host ''
Write-Host 'Setup complete.'
Write-Host "  bundle     : $Root"
Write-Host "  python     : $resolved"
if ($chosenRoot -and (Test-EplanPlatformRoot $chosenRoot)) { Write-Host "  eplan      : $chosenRoot" }
elseif ($detectedRoot) { Write-Host "  eplan      : $detectedRoot" }
else { Write-Host "  eplan      : NOT FOUND (set it in the plugin settings)" }
if (Test-Path $DbFile) {
    $size = [math]::Round((Get-Item $DbFile).Length / 1MB, 2)
    $count = & $resolved -c "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);print(c.execute('select count(*) from member').fetchone()[0])" $DbFile 2>$null
    Write-Host "  2025 API   : $DbFile ($size MB, $count members)"
}
# The crawled help indexes need network access to build, so setup only reports them.
foreach ($pair in @(
        @('2025 guide', 'eplan2025-guide.sqlite'),
        @('2026 help ', 'eplan2026-help.sqlite'),
        @('2027 help ', 'eplan2027-help.sqlite'),
        @('EEC Pro   ', 'eecpro-help.sqlite'))) {
    $f = Join-Path $Root ('data\' + $pair[1])
    if (Test-Path $f) {
        $sz = [math]::Round((Get-Item $f).Length / 1MB, 2)
        $pg = & $resolved -c "import sqlite3,sys;c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True);print(c.execute('select count(*) from page where status=200').fetchone()[0])" $f 2>$null
        Write-Host ("  {0}: {1} ({2} MB, {3} pages)" -f $pair[0], $f, $sz, $pg)
    } else {
        Write-Host ("  {0}: MISSING — build it with scripts\build-help-index.py (needs www.eplan.help)" -f $pair[0])
    }
}
Write-Host ''
Write-Host 'Next: install the bundle in DeepSeek Harness (plugin manager -> install from folder), then restart or reload.'
