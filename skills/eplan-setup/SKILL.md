---
name: eplan-setup
description: Install, verify, repair and rebuild the DSH_Eplan bundle — its six MCP servers, the `dsh-eplan` host plugin, the Python runtime, and the five local documentation indexes (2025 API, 2025 guide, 2026, 2027, EEC Pro). Use when EPLAN tools are missing from a session, a server will not start, Python/mcp/pythonnet is missing, a documentation search is empty or stale, an index must be built or refreshed, or the bundle must be reinstalled on this or another machine.
---

# DSH_Eplan setup, verification, repair

Bundle: `$bundle` (the plugin root — set it once with `$bundle = (Get-Location).Path` after entering the checkout), installed into the DSH profile as a bundle. It mounts six MCP
servers plus the `dsh-eplan` host plugin, ships five skills and one system-prompt section.

## Layout

| Path | What it is |
| --- | --- |
| `cordis.patch.yml` | The seven rows. No absolute paths: each row runs `cmd.exe` with a launcher name relative to a `cwd:` that a `!!js` expression resolves to the installed package at load time |
| `mcp/<row>/index.js` + `locale/{en,zh}.json` | Per-row row packages: `index.js` re-exports `@deepseek-ai/dsh-mcp-client`, the locale files give the row its title in 设置 → 插件 (`eplan`, `eplan2025`, `eplan2025guide`, `eplan2026`, `eplan2027`, `eecpro`) |
| `index.js` | Host plugin: the `eplan:integration` system-prompt section |
| `scripts/launch-*.cmd` | One launcher per server: `launch-eplan-mcp`, `launch-docs2025`, `launch-docs2025guide`, `launch-docs2026`, `launch-docs2027`, `launch-docseecpro` |
| `scripts/setup.ps1` | Resolves Python, writes `runtime\python-path.txt`, repairs `vendor\`, checks the six launchers and warns if the patch ever grows an absolute path, builds the 2025 API index |
| `scripts/build-eplan2025-index.py` | `data\eplan2025.sqlite` from the installed 2025 API XML |
| `scripts/build-help-index.py` | The four crawled indexes (`api` / `guide` / `sitemap` / `reindex` modes, resumable) |
| `server/docs2025/server.py` | 2025 API docs MCP server (stdlib only) |
| `server/docs/server.py` | 2025 guide / 2026 / 2027 / EEC Pro docs server (stdlib, `--docset`) |
| `vendor/eplan-mcp/` | eplan-mcp v1.3.0 @ `77a78f63` (MIT, © 2025 Christian D. Lopez) — pinned upstream tag, see `PROVENANCE.md`; re-sync, never hand-edit |
| `runtime/python-path.txt` | Absolute interpreter chosen by setup, read by every launcher |
| `data/*.sqlite` | `eplan2025` (36,493 members, ~35 MB), `eplan2025-guide` (2,691 pages), `eplan2026-help` (25,024), `eplan2027-help` (26,360), `eecpro-help` (1,971) |
| `licenses/` | MIT licences for the vendored skills |

## Prerequisites

- Windows 10/11 x64, EPLAN Electric P8 2025.0.3 at `C:\Program Files\EPLAN\Platform\2025.0.3`.
- EPLAN remote access: **File → Settings → Workstation → Interfaces → Remote access → "Allow remote
  access via Remote Client"**. Without it `eplan_connect` fails while EPLAN is open and healthy.
- Python 3.12+ (3.13 on this machine) with `mcp` (>=1.19,<2, required by the v1.3.0 tool annotations)
  and `pythonnet`. The interpreter actually in use is written to `runtime\python-path.txt`
  (EPLAN_Skills environment); `setup.ps1` also falls back to the `py` launcher, PATH and a legacy
  Bochica bundled interpreter. vendor is shipped with the plugin — no Bochica install is needed.
- Network to `www.eplan.help` only while building the 2026 / 2027 / EEC Pro crawls (and the 2025 guide).

## Install and repair

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $bundle\scripts\setup.ps1
```

Options `-Python <path>`, `-RebuildIndex`, `-SkipIndex`. The script normalises the `.cmd` launchers to
CRLF, verifies the pinned `vendor/eplan-mcp` is present (fails loudly instead of copying an
unpinned Bochica runtime), validates the interpreter (`import sys, mcp, clr`), writes
`runtime\python-path.txt`, checks that the six launchers are present (and that `cordis.patch.yml` still has no
absolute path), then builds the 2025 index (~4 s) unless told to skip.

Then (re)install through DSH's plugin manager with the absolute package directory
`$bundle`. A fresh install **links** the checkout, so later file edits are visible
without reinstalling; changed MCP rows need a DSH restart, a changed host plugin is HMR-reloaded.

## Building the indexes

2025 API — rebuild after an EPLAN update:

```powershell
python $bundle\scripts\build-eplan2025-index.py `
  --xml-dir "C:\Program Files\EPLAN\Platform\2025.0.3\Bin" `
  --out $bundle\data\eplan2025.sqlite
```

2025 platform help. Its published sitemap lists page *names* from another release, so it is fetched
once into `_recon\sitemaps\` and the `guide` mode re-points the names at the version's own directory:

```powershell
Invoke-WebRequest -UseBasicParsing -OutFile $bundle\_recon\sitemaps\plattform2025.xml `
  https://www.eplan.help/en-us/Infoportal/Content/Plattform/2025/sitemap.xml
& $py $bundle\scripts\build-help-index.py guide --version 2025 `
  --sitemap $bundle\_recon\sitemaps\plattform2025.xml `
  --out $bundle\data\eplan2025-guide.sqlite --workers 10
```

2026 / 2027 / EEC Pro — one-time crawls of the official help site, resumable:

```powershell
$py = Get-Content $bundle\runtime\python-path.txt
# 2026: API reference (seeds from webindex.html, follows each type's "_members" page) …
& $py $bundle\scripts\build-help-index.py api --version 2026 `
  --out $bundle\data\eplan2026-help.sqlite --workers 12
# … then the platform guide merged into the same DB
& $py $bundle\scripts\build-help-index.py guide --version 2026 `
  --sitemap $bundle\_recon\sitemaps\plattform2026.xml `
  --out $bundle\data\eplan2026-help.sqlite --workers 10
# 2027 the same way
& $py $bundle\scripts\build-help-index.py api --version 2027 `
  --out $bundle\data\eplan2027-help.sqlite --workers 12
& $py $bundle\scripts\build-help-index.py guide --version 2027 `
  --sitemap $bundle\_recon\sitemaps\plattform2027.xml `
  --out $bundle\data\eplan2027-help.sqlite --workers 10
# EEC Pro 2026: every HTML page in the project sitemap
& $py $bundle\scripts\build-help-index.py sitemap `
  --sitemap https://www.eplan.help/en-us/infoportal/content/eecpro/2026/sitemap.xml `
  --prefix  https://eplan.help/en-US/infoportal/Content/EECPro/2026/Content/htm/ `
  --out $bundle\data\eecpro-help.sqlite --workers 8
```

The crawl honours `robots.txt` (HTML allowed), writes `page(path, url, title, breadcrumb, kind,
assembly, type_name, member_name, body, status, fetched_at)` plus an FTS5 index, skips stored 200s and
remembers 404s, and ends with a full index rebuild plus a WAL checkpoint — the servers open the DB
read-only, so an uncheckpointed WAL would hide the newest pages.

Sitemaps are copied between releases, so their internal paths do not always match their own version
directory (2025's still lists `Plattform/2023/...`). `load_sitemap(..., flatten_prefix=…)` keeps only
the page file names and re-points them at `Plattform/<version>/Content/htm/` — which is why the guide
command takes that version's own sitemap instead of matching a URL prefix.

Pages counted but search finds nothing? Rebuild the index only, no network:

```powershell
& $py $bundle\scripts\build-help-index.py reindex `
  --out $bundle\data\eplan2026-help.sqlite
```

## Verification

1. `mcp__eplan__eplan_versions` → `2025` / `2025.0.3`; `eplan_status` shows the connection state
   (`api_loaded: true` only after `eplan_connect`).
2. `mcp__eplan__eplan_tools_search({query: "pdf"})` returns wrappers; `eplan_action_catalog` answers
   offline, with no EPLAN running.
3. `mcp__eplan2025__eplan2025_stats` → 36,493 members; then
   `eplan2025_get({name: "Eplan.EplApi.DataModel.ProjectManager.OpenProject"})` → 3 overloads.
4. `mcp__eplan2025guide__eplan2025_guide_stats` → 2,691 pages; then
   `eplan2025_guide_search({query: "connection numbering"})` → real dialog pages.
5. `mcp__eecpro__eecpro_stats` → 1,971 pages. **2026 and 2027 are off by default** (`disabled: true`,
   installed platform is 2025), so their tools are normally *unknown tool* errors until enabled in
   设置 → 插件; `eplan2026__eplan_stats` and `eplan2027__eplan2027_stats` work once they are.
6. Skills surface at **session start**: installing or changing the bundle needs a new session (or a DSH
   restart) before `eplan`, `eplan-docs`, `eplan-scripting`, `eec-pro-development` and this skill exist.
   MCP tools, by contrast, hot-mount into the running session.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| EPLAN tools absent | Server failed to start. Run `scripts\launch-eplan-mcp.cmd` in a console, read stderr, check `runtime\python-path.txt` names a real interpreter. |
| `ModuleNotFoundError: mcp` / `clr` | Wrong interpreter. Re-run setup with `-Python <python that has mcp and pythonnet>`. |
| `eplan_connect` fails, gRPC "failed to connect to all addresses" | Remote access off, EPLAN closed, or a non-default port. Ask the user for EPLAN.exe's listening port (`netstat -ano | findstr LISTENING`) and pass it; 49152 is only a guess. |
| Connected to the wrong EPLAN version | One major version per server process. Restart DSH, then `eplan_connect({version})` before the first DLL load. |
| `eplan2025_search` empty, or stats show no DB | Rebuild the 2025 index; confirm `--xml-dir` points at the installed platform's `Bin`. |
| A docs server's tools are missing | DB missing or launcher failed. Run the matching `scripts\launch-docs*.cmd`, read stderr, rebuild. |
| Guide search empty though the API index works | The platform-help crawl never ran for that version, or `--sitemap` named another version's file. Re-run `guide` with that version's cached sitemap. |
| A crawl stopped early / few pages | Re-run the same command: it resumes past stored 200s and 404s. Check `_recon\crawl*.log` for throttling or TLS errors; lower `--workers`. |
| Thousands of pages, no hits | FTS index out of sync. `build-help-index.py reindex --out <db>` — rebuilds and checkpoints, no network. |
| Empty at 2025 *and* 2026 for one name | Correct for names that are EPLAN actions or GUI options rather than .NET members — use `eplan_action_catalog` or 2027 keyword search. |
| Bundle loads, guidance missing | The `dsh-eplan` row is absent or the host plugin failed to apply; `index.js` changes HMR-reload, apply failures log in DSH. |
| Copied to another machine, servers will not start | The patch is portable by design (relative launcher names, `cwd` resolved by a `!!js` expression), so check the machine-local pieces first: `runtime\python-path.txt` must name a working interpreter and the five `.sqlite` files must sit in `data\` (unpack them from the `offline-indexes` release asset). Then re-run `scripts\setup.ps1`, which redoes both. |
| Indexes should live outside the bundle | Set `EPLAN_DATA_DIR` to a writable directory holding the five `.sqlite` files. Order: per-docset `EPLAN2025_DB` / `EPLAN2025_GUIDE_DB` / `EPLAN2026_DB` / `EPLAN2027_DB` / `EECPRO_DB` → `EPLAN_DATA_DIR` → `<bundle>\data`. |
| All MCP rows read "@deepseek-ai/dsh-mcp-client" again | The `mcp/<row>/` packages are missing, or `package.json` lost its exports. Row titles come from `readPluginMeta(specifier)`; a subpath specifier reads only `<specifier>/locale/en.json`, so each row needs `mcp/<row>/locale/{en,zh}.json` **and** the three literal exports `./mcp/*`, `./mcp/*/locale/en.json`, `./mcp/*/locale/zh.json` (a `./mcp/*/locale/*.json` pattern will not resolve — Node substitutes one `*`). |
| A row switched in 设置 → 插件 reverts | The UI writes `disabled` into the PROFILE patch (`…\profiles\desktop\cordis.patch.yml`), which overrides the bundle's default. Delete the stale entry there. |

`vendor/eplan-mcp/` is never patched by hand: replace the whole directory from a fresh eplan-mcp
release, then re-run setup.