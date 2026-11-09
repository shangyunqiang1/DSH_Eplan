# Vendored eplan-mcp — provenance

This directory contains a **read-only, byte-for-byte copy of the runtime subset**
of [Canary-ECAD/eplan-mcp](https://github.com/Canary-ECAD/eplan-mcp), pinned to a
single upstream release. It is shipped inside the `dsh-eplan` bundle so the EPLAN
MCP server needs no network access and no Bochica installation at run time.

Do **not** hand-edit files under `vendor/eplan-mcp/`. To change them, re-sync from
the pinned upstream commit using the procedure at the bottom of this file.

## Pinned release

| Field | Value |
| --- | --- |
| Upstream repository | https://github.com/Canary-ECAD/eplan-mcp |
| Tag | `v1.3.0` |
| Commit | `77a78f6315992d8e50745de87f221c7e53a08a53` |
| Tree | `77a78f6315992d8e50745de87f221c7e53a08a53` (recursive tree, 201 entries; 144 blobs under `eplan-p8-mcp-server/`) |
| Commit date | 2026-11-06 ("Merge pull request #82 from Canary-ECAD/feat/engapplic-live-ops") |
| License | MIT, Copyright (c) 2025 Christian D. Lopez (see `LICENSE`) |
| Bochica pin | `components.lock.json` on Bochica `main` (`fcbfaaf8`, 2026-11-06) points at the same commit with tag `v1.3.0` |
| Previous pin (for history) | `d207fc72908b763cf38eab6dd504e0b6886d98be` (2026-10-28, pre-`v1.0.0`; 3 commits behind the first tag `v1.0.0`) |

> The version string `1.30.0` that appeared in some older DSH_Eplan docs was the
> installed **MCP SDK** version (`mcp==1.30.0`), not the eplan-mcp version. The
> vendored server had no upstream version tag until this sync; it is now `v1.3.0`.

## Verification method

Every vendored file is checked as a Git blob, not by diffing text:

```powershell
# local blob SHA (must equal the upstream tree blob SHA)
git hash-object -- vendor/eplan-mcp/<relpath>

# upstream blob SHA, from the recursive tree of the pinned commit
$hdr = @{ 'User-Agent'='dsh-eplan-audit'; 'Accept'='application/vnd.github+json' }
$tree = Invoke-RestMethod -Headers $hdr `
  -Uri 'https://api.github.com/repos/Canary-ECAD/eplan-mcp/git/trees/77a78f6315992d8e50745de87f221c7e53a08a53?recursive=1'
$tree.tree | Where-Object { $_.type -eq 'blob' -and $_.path -eq 'eplan-p8-mcp-server/<relpath>' } |
  Select-Object -ExpandProperty sha
```

`git hash-object` is authoritative: it hashes the file content the way Git does,
independent of CRLF/LF working-tree conversion, and catches silent truncation of
large files (e.g. `schematic.py` is 150,629 bytes). **Always** fetch files larger
than ~100 KB through the GitHub blob API with base64 decode into bytes, never
through a plain raw `web_fetch`, which quietly truncates at 100,000 bytes.

Result at sync time (2026-11-09): **86 / 86 vendored files byte-identical to the
pinned tree; 0 differing; 0 extra; 0 modified locally.**

The only file in this directory that is **not** from upstream is this
`PROVENANCE.md` itself (bundle-authored metadata). Exclude it from the
byte-identity check; everything else under `vendor/eplan-mcp/` must match the
pinned tree exactly.

## What is vendored (86 files)

- `eplan-p8-mcp-server/mcp_server/` — all 72 runtime files: `server.py`,
  `tool_registry.py`, `tool_annotations.py`, `ui_windows.py`,
  `eplan_connection.py`, `requirements.txt`, and the full `api/` action package.
- `eplan-p8-mcp-server/tools/` — the offline registry builders and their
  `data/*.json` inputs (`build_action_registry.py`, `validate_actions.py`,
  `capture_ribbon_labels.py`, `probe_live_actions.py`, `generate_wiki_pages.py`,
  `action_validation_report.md`, 4 JSON data files).
- `eplan-p8-mcp-server/extensions/symbol_search.py` — the optional extension
  (loaded only when `EPLAN_MCP_EXTENSIONS` is set; off by default).
- `eplan-p8-mcp-server/ACTION_COVERAGE.md`, `TOKEN_COST.md`, `LICENSE`.

## Deliberately NOT vendored (59 upstream files)

Development/release artifacts that the running server never imports:

- `eplan-p8-mcp-server/tests/**` — upstream pytest suite (~50 files, including
  `test_tool_annotations_offline.py`, `test_ui_windows_offline.py`, `test_v2027_offline.py`).
- `eplan-p8-mcp-server/tools.json` — the generated full-mode tool manifest
  (release attachment only; discovery mode builds its registry by introspection).
- `eplan-p8-mcp-server/tools/dump_tools.py`, `tools/release_notes.py` — release tooling.
- `.github/workflows/**`, top-level `README.md`, `llm.md`, `.gitignore`, `CLAUDE.md`.
- `mcp_server/scripts/generated/.gitkeep` and `mcp_server/scripts/results/.gitkeep`
  — empty upstream placeholders for runtime scratch directories. The bundle
  creates those directories on demand and excludes them via `.gitignore`:

```
vendor/eplan-mcp/eplan-p8-mcp-server/mcp_server/scripts/generated/
vendor/eplan-mcp/eplan-p8-mcp-server/mcp_server/scripts/results/
```

Excluding the test suite is intentional: it would add ~50 files with no runtime
use, and the pinned tree comparison above remains exhaustive over what is kept.

## Changelog of this sync (old `d207fc7` → `v1.3.0`)

9 files modified, 13 added, 0 deleted; the other 64 vendored files were already
byte-identical to `v1.3.0`.

**Modified** (blob SHA at `v1.3.0`, 8-char prefix):

| File | Blob |
| --- | --- |
| `mcp_server/api/actions/__init__.py` | `874e727c` |
| `mcp_server/api/actions/_base.py` | `a310c7fc` |
| `mcp_server/api/actions/catalog.py` | `0a28cadc` |
| `mcp_server/api/actions/live.py` | `c695eadc` |
| `mcp_server/api/actions/schematic.py` | `1666b716` |
| `mcp_server/api/actions/scripted.py` | `d0d36c08` |
| `mcp_server/eplan_connection.py` | `a3a21d8a` |
| `mcp_server/requirements.txt` | `8e4afc26` |
| `mcp_server/server.py` | `037a3be9` |

**Added:**

| File | Blob |
| --- | --- |
| `mcp_server/api/actions/cables_live.py` | `0dc93657` |
| `mcp_server/api/actions/dataportal.py` | `c1771d88` |
| `mcp_server/api/actions/dialogs.py` | `cbd92099` |
| `mcp_server/api/actions/ops.py` | `c8193d2b` |
| `mcp_server/api/actions/panel_live.py` | `4b08b027` |
| `mcp_server/api/actions/project_live.py` | `9a9c86a3` |
| `mcp_server/api/actions/reports_live.py` | `83a59004` |
| `mcp_server/api/actions/structure_live.py` | `4e401d11` |
| `mcp_server/api/actions/target.py` | `f3b7d707` |
| `mcp_server/api/actions/terminals_live.py` | `b775c594` |
| `mcp_server/api/actions/v2027.py` | `2099b086` |
| `mcp_server/tool_annotations.py` | `49007e02` |
| `mcp_server/ui_windows.py` | `5de983fa` |

**Runtime-relevant changes in `v1.3.0`:**

- `mcp_server/requirements.txt`: `mcp>=1.8.0,<2` → `mcp>=1.19.0,<2`. Reason:
  tool annotations with `_meta`. The bundled runtime already has `mcp==1.30.0`,
  so no environment change is needed. `pythonnet>=3.0.0` and
  `basyx-python-sdk>=2.0.1` are unchanged.
- `tool_annotations.py`: `META_KEY = "canary-ecad/eplan"`; every tool gets
  `ToolAnnotations(readOnlyHint, destructiveHint, idempotentHint, openWorldHint)`
  plus EPLAN facts `{changesProject, runsCode, changesEplan[, projectArgument]}`.
  DSH's safety rules live in `index.js` system-prompt guidance and do **not**
  consume these annotations — they are informational here.
- `server.py`: full mode now registers 248 tools; discovery publishes 15
  (12 core + `eplan_tools_search` / `_describe` / `_call`). Two new core tools,
  `eplan_list_dialogs` and `eplan_click_dialog_button`, unlock EPLAN when a modal
  prompt blocks the Remote Client. Unknown `EPLAN_MCP_MODE` values fall back to
  `full`.
- New `*_live` modules add parts/database, Data Portal, dialog, panel, project,
  report, structure, terminal-strip and 2027-only actions. They are reachable in
  discovery mode through `eplan_tools_search` automatically.

## Upgrade procedure

1. Pick the new upstream commit/tag; read its `components.lock.json` value from
   the Bochica `main` branch if the bundle is meant to track Bochica.
2. Fetch the recursive tree:
   `https://api.github.com/repos/Canary-ECAD/eplan-mcp/git/trees/<sha>?recursive=1`.
3. Compute the sync set against the current vendor: for every path under
   `eplan-p8-mcp-server/` that the runtime imports (see "What is vendored"),
   compare the local `git hash-object` with the upstream blob SHA. Files whose
   SHA changed or that are new are the update set; never delete a still-imported
   file just because it is absent from a newer tree without checking imports.
4. Download each changed/new file through the blob API (base64 → bytes →
   `[System.IO.File]::WriteAllBytes`), then re-run `git hash-object` and assert
   it equals the upstream SHA. Do not use raw text fetch for files >100 KB.
5. Verify: `python -m py_compile` over `mcp_server/**/*.py`; import every new
   module; boot with `EPLAN_MCP_MODE=discovery` and confirm the published tool
   set; compare `ToolRegistry` names/published/hidden counts.
6. Check `requirements.txt` for a raised `mcp` floor and confirm the runtime
   satisfies it.
7. Update this file (pin fields, sync table, counts), `THIRD_PARTY_NOTICES.md`,
   and the tool-count strings in `index.js`, `README.md`,
   `cordis.patch.yml`, `skills/eplan-setup/SKILL.md`.
8. `git add` the new files and commit. Keep the byte-identity invariant: at the
   end, **every** vendored file must still match the new pinned tree exactly.

## Bochica is no longer a runtime source

Older versions of `scripts/setup.ps1` silently `robocopy`d a missing vendor
directory from `%LOCALAPPDATA%\Programs\bochica\resources\runtime\eplan-mcp`.
Bochica 0.3.x self-updates that runtime to an **unpinned** commit, so copying it
would silently break the byte-identity guarantee above. `setup.ps1` now refuses
to do so and throws with restore instructions instead. Reinstall the plugin
package (which ships `vendor/eplan-mcp`) or re-sync from the pinned commit above.
