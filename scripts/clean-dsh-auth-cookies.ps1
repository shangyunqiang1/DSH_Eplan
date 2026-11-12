<#
  clean-dsh-auth-cookies.ps1

  Removes accumulated "dsh-auth-*" browser session cookies from the Chromium
  cookie store used by the DeepSeek Harness desktop app.

  Background
  ----------
  The desktop host starts its web server on a random port (--port 0, hard-coded
  in dsh-desktop-host). The session cookie name is
  "dsh-auth-" + base64url(sha256(authority)), where authority is host:port, so
  every launch mints a NEW cookie name and the old ones are never replaced
  (Max-Age = client-connection cookieMaxAgeDays, default 30 days).
  The Cookie request header therefore grows with every launch until it passes
  Node's default 16 KB header limit; the welcome handshake comes back 431 and
  the app dies with: "desktop welcome: Web authentication failed".

  Usage (DeepSeek Harness must be closed; the store is locked while it runs)
  -----
      powershell -NoProfile -ExecutionPolicy Bypass -File clean-dsh-auth-cookies.ps1
      ... -DryRun      report only, delete nothing
      ... -Force       skip the "is DSH running" check (unsafe while running)
      ... -DbPath X    clean a specific cookie store (testing / other profiles)

  Exit codes: 0 ok (or nothing to do), 2 DSH still running (skipped),
              4 a store could not be opened or cleaned, 1 unexpected failure.
#>
[CmdletBinding()]
param(
  [switch]$DryRun,
  [switch]$Force,
  [string]$DbPath
)

$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot 'clean-dsh-auth-cookies.log'

function Write-Log([string]$msg) {
  $line = '[{0}] {1}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $msg
  Write-Host $line
  Add-Content -LiteralPath $log -Value $line -Encoding utf8 -ErrorAction SilentlyContinue
}

# --- is the desktop app running? -------------------------------------------
if (-not $Force -and -not $DbPath) {
  $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -and ($_.Path -like 'D:\Programs\DeepSeek Harness\*') } catch { $false }
  })
  if ($running.Count -gt 0) {
    $pids = ($running | Select-Object -First 6 | ForEach-Object { $_.Id }) -join ','
    Write-Log ('DeepSeek Harness is running ({0} processes, pid {1}); cookie store is locked, nothing done.' -f $running.Count, $pids)
    Write-Log 'Quit DeepSeek Harness completely (including the tray icon) and run this again.'
    exit 2
  }
}

# --- which stores to clean --------------------------------------------------
$stores = @()
if ($DbPath) {
  $stores = @($DbPath)
} else {
  $base = Join-Path $env:APPDATA '@deepseek-ai\dsh-desktop'
  $main = Join-Path $base 'Network\Cookies'
  if (Test-Path -LiteralPath $main) { $stores += $main }
  $parts = Join-Path $base 'Partitions'
  if (Test-Path -LiteralPath $parts) {
    $stores += @(Get-ChildItem -LiteralPath $parts -Directory -ErrorAction SilentlyContinue |
      ForEach-Object { Join-Path $_.FullName 'Network\Cookies' } |
      Where-Object { Test-Path -LiteralPath $_ })
  }
}
if ($stores.Count -eq 0) {
  Write-Log 'No Chromium cookie store found; nothing to do.'
  exit 0
}

# --- node ------------------------------------------------------------------
$node = Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe'
if (-not (Test-Path -LiteralPath $node)) {
  $node = (Get-Command node -ErrorAction SilentlyContinue).Source
}

$js = @'
const { DatabaseSync } = require('node:sqlite');
const db = process.argv[2];
const dry = process.argv[3] === 'dry';
const out = {};
try {
  const c = new DatabaseSync(db);
  const total = c.prepare("select count(*) n from cookies").get().n;
  const mine = c.prepare(
    "select count(*) n, coalesce(sum(length(name)+length(encrypted_value)+48),0) b " +
    "from cookies where name like 'dsh-auth-%'"
  ).get();
  out.total = total;
  out.dshAuth = mine.n;
  out.approxHeaderBytes = mine.b;
  if (!dry && mine.n > 0) {
    c.prepare("delete from cookies where name like 'dsh-auth-%'").run();
    c.exec("vacuum");
    out.removed = mine.n;
  }
  c.close();
  console.log(JSON.stringify(out));
} catch (e) {
  console.log(JSON.stringify({ error: String(e && e.message || e) }));
  process.exit(3);
}
'@

# --- clean -----------------------------------------------------------------
$failed = 0
foreach ($db in $stores) {
  if (-not (Test-Path -LiteralPath $db)) { continue }
  $before = (Get-Item -LiteralPath $db).Length

  if (-not $node) {
    if ($DryRun) {
      Write-Log ('{0}: node not found, DryRun, nothing deleted (store is {1} B).' -f $db, $before)
    } else {
      Remove-Item -LiteralPath $db -Force
      Remove-Item -LiteralPath ($db + '-journal') -Force -ErrorAction SilentlyContinue
      Write-Log ('{0}: node not found, deleted the whole store ({1} B); one fresh cookie will be issued.' -f $db, $before)
    }
    continue
  }

  $tmp = Join-Path $env:TEMP ('dsh-cookie-clean-' + [guid]::NewGuid().ToString('N') + '.cjs')
  Set-Content -LiteralPath $tmp -Value $js -Encoding utf8
  $mode = if ($DryRun) { 'dry' } else { 'live' }
  $code = 0
  try {
    $out = & $node $tmp $db $mode 2>&1
    $code = $LASTEXITCODE
  } finally {
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
  }

  if ($code -ne 0) {
    Write-Log ('{0}: could not open the store (still locked?): {1}' -f $db, ($out -join ' '))
    $failed = 1
    continue
  }

  $after = (Get-Item -LiteralPath $db).Length
  Write-Log ('{0}: {1} (store {2} B -> {3} B)' -f $db, ($out -join ' '), $before, $after)
}

if ($failed -ne 0) { exit 4 }
Write-Log 'Done.'
exit 0