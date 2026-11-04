---
name: eplan
description: Drive the installed EPLAN Electric P8 2025 through the local `eplan` MCP tools (mcp__eplan__*) — connect, find the hidden typed tools, run any of the ~1150 actions, map a ribbon button back to its action, and work safely on projects, pages and parts. Use for anything aimed at the running program, including a project (.elk/.elp/.elx/…), an action, an export or a renumbering, and as the router to the scripting, documentation, EEC Pro and setup skills.
---

# EPLAN live operation

One machine, one install: **EPLAN Electric P8 2025.0.3** at `C:\Program Files\EPLAN\Platform\2025.0.3`.
Everything here reaches it through the `eplan` MCP server, exposed as `mcp__eplan__<tool>`.

## Route first

| The request is about | Load |
| --- | --- |
| the running program: connect, project, pages, parts, exports, an action | this skill |
| C# code: scripts, add-ins, Remote Client apps | `eplan-scripting` |
| a documented name or a dialog: an API member, a menu path, "what does this option do" | `eplan-docs` |
| EEC Pro: typicals, formulas, EOX, Job Server | `eec-pro-development` |
| the plugin itself: missing tools, empty index, rebuild, reinstall | `eplan-setup` |

Two traps this table exists to prevent: a 2026/2027 documentation hit is **not** evidence about this
2025 install, and an absent `mcp__eplan2026__*` / `mcp__eplan2027__*` tool means that row is switched
off in 设置 → 插件 — not that the topic is undocumented.

## Discovery mode

The server publishes **13 meta-tools**, not ~200 schemas. The workflow is always the same three steps:
find, read the signature, call.

- Connection: `eplan_versions` → `eplan_servers` → `eplan_connect` → `eplan_status` / `eplan_ping`
- Typed wrappers (~180, hidden): `eplan_tools_search({query})` → `eplan_tools_describe({names})` →
  `eplan_tools_call({name, arguments})`; argument names are validated before anything runs
- Raw actions (~1150): `eplan_action_catalog` → `eplan_action_describe` → `eplan_action_run`
- GUI mapping: `eplan_ribbon_catalog({tab?|search?})`

Wrappers worth reaching for by name — project: `eplan_get_current_project`, `eplan_open_project`,
`eplan_backup_project`, `eplan_restore_project`, `eplan_check_project`, `eplan_search_project_data`;
pages: `eplan_get_selected_pages`, `eplan_preview_page`, `eplan_export_pdf_pages`,
`eplan_export_dxf_pages`, `eplan_renumber_pages`, `eplan_get_page_property`; parts:
`eplan_check_parts`, `eplan_export_parts_list`, `eplan_backup_masterdata`; scripts:
`eplan_execute_script`, `eplan_register_script`.

## Connection

1. `eplan_versions` — free, loads no DLLs. Here: 2025 → `2025.0.3`, runtime `netfx`.
2. `eplan_servers` — loads the DLLs, lists running instances. An empty list is **not** proof EPLAN is
   closed: auto-detection is unreliable, especially right after EPLAN started.
3. `eplan_connect` — on localhost it auto-detects the port. On gRPC "failed to connect to all
   addresses", ask the user for EPLAN.exe's real listening port (`netstat -ano | findstr LISTENING`,
   cross-referenced with the PID); 49152 is only a guess. Never sweep ports silently.
4. `eplan_status` / `eplan_ping` — `connected: true`, `api_loaded: true`.

One major version per server process: after the DLLs are loaded, another version needs a DSH restart,
and `eplan_connect({version})` only works before that first load.

## Typed tool vs raw action

Prefer the typed wrapper — it documents its parameters. `eplan_action_catalog({wrapped: true})` lists
which actions already have one. Raw actions cover everything else, with parameters sent verbatim as
`/KEY:value`; EPLAN's casing is **not** uniform (`PROJECTNAME` but `OpenMode`, `PartNr`) and a wrong
case is silently dropped, so validation here is case-sensitive — `dry_run: true` first shows the exact
command line. To find the action behind a GUI feature, `eplan_action_catalog({search: "Page macro"})`
matches action names, descriptions, parameter names, ribbon text and "tab > group" paths; built-in
ribbon buttons usually report an empty `action_command_line`, so match on their display text.
`documented_only` narrows to the ~100 actions in the official API docs; `available_only` is advisory
(the probe was recorded on a reference install, not this machine).

Results look like `{"success": bool, "parameters": {...}}`. Report `success` and the parameters — a
silent result is normal (`QuietModes.ShowNoDialogs`), and `{"success": false}` is a return value, not
an exception. Verify the effect with a read-only query afterwards.

## Safety

- **Read-only first**: `eplan_status`, `eplan_get_current_project`, `eplan_tools_search`,
  catalog/describe, exports into a temp path. The user's project is theirs — do not open, close or
  switch it "to have a look".
- **Back up before the first modification**: `eplan_backup_project`, or confirm the user already has a
  backup. Same for `eplan_compress_project`, restores and upgrades.
- **Destructive means asking**: delete, remove, purge, reorganize, discard, erase, destroy, wipe need
  approval naming the project, in this conversation. DSH's approval policy can be "never"; that
  silences prompts, it does not transfer ownership of the user's data.

## Pitfalls

- EPLAN action names are not API members: `InsertSymbol` is an action and has no .NET member — a 2025
  API search miss there is correct behaviour.
- Project extensions: `.elk .elp .els .elx .ell .elr .elt .ema .elm`.
- A dialog-driven action needs its parameters. If `eplan_action_describe` shows none declared, read the
  registry entry, then the docs — never invent parameter names.
