---
name: eplan-scripting
description: Write C# for EPLAN Electric P8 — in-EPLAN scripts (actions, ribbon, event handlers), add-ins and API extensions, and external apps driving EPLAN over Remote Client. Use when writing or debugging EPLAN code, reaching Eplan.EplApi types, reading or writing parts, projects, pages and properties, executing actions from code, or resolving the blocking/threading/dispose failures automation hits. Covers 2022–2027, measured on the installed 2025.0.3.
---

# EPLAN Electric P8 development

Distilled from working production code: scripting (C#), the EPLAN API, and remote automation.

## Three development models

| Model | Runs | Licence | For |
| --- | --- | --- | --- |
| **Scripting** | inside EPLAN (compiled on load, C# subset) | none extra | actions, ribbon additions, event hooks, exports |
| **API extension** | inside EPLAN as a DLL, or offline | API licence | deep data access: parts DB, project object model, pages, properties |
| **Remote Client** | external process driving a running EPLAN | RemoteClient DLLs | orchestration apps, headless pipelines, Cogineer generation |

**A script reaches the ENTIRE `Eplan.EplApi.*` surface — no API licence, no add-in.** The limit is
compile-time only: `using` works for a fixed set (`Base`, `ApplicationFramework`, `Gui`, `MasterData`,
`Scripting`), anything else is CS0234 — but every namespace is reachable at runtime through reflection.
Measured on 2025.0.3: 26 namespaces, 606 public types, and all six non-preloaded `Eplan.EplApi.*.dll`
load on demand with zero refusals. A failed `using` never means the namespace is unavailable — see
`references/api-data-access.md`.

## Reference files — read the one that matches the task

- **`references/script-basics.md`** — script structure, entry-point attributes (`[Start]`,
  `[DeclareAction]`, `[DeclareEventHandler]`, `[DeclareRegister]`), deployment, scripting limits.
- **`references/actions-reference.md`** — running actions via `CommandLineInterpreter` +
  `ActionCallingContext`; catalogue of common actions (backup, export PDF, reports, labels, edit,
  selectionset…) with their parameters.
- **`references/core-classes.md`** — `Progress`, `Decider`, `PathMap` variables, `Settings`,
  `MultiLangString`, ribbon and context menus, `QuietModeStep`, system messages (`BaseException`,
  `SysMessagesCollection`).
- **`references/api-data-access.md`** — parts database (`MDPartsManagement`), reading *and writing*
  part properties (`AddPart`/`RemovePart`, the `MDPropertyValue` constructor that does not exist, the
  `AmbiguousMatchException` every name-based lookup hits), user-defined properties, multilanguage
  parsing, `$(MD_DOCUMENTS)`-style paths, and why `using Eplan.EplApi.DataModel;` / `…HEServices;` fail
  in scripts (CS0234) yet still work via reflection. Also `SymbolLibrary`/`Symbol` enumeration: walking
  `Symbol(lib, int)` by index must `continue`, never `break`, on a construction miss (SymbolIds are
  sparse), and a symbol's identity comes from `Symbol.Properties.SYMB_DESC`/`FUNC_CATEGORY`, never its
  short name or IEC-letter prefix.
- **`references/eec-typicals.md`** — building a project from an EEC One "typical" workbook without EEC:
  reading the sheet (already condition-filtered), inserting page/window macros through `Insert`,
  renaming pages to the sheet's structure with `PagePropertyList`, and the page-index collision on the
  second cabinet. (EEC Pro's own model, conditions and formulas live in `eec-pro-development`.)
- **`references/e3d-installation-spaces.md`** — the version-proof reflection recipe for reaching
  `Eplan.EplApi.DataModel`/`HEServices` from a script (`LockingStep`, `FindType()` scanning, 2027's
  `…Netu` assemblies), applied to creating 3D installation spaces and inserting window macros headlessly.
- **`references/remoting.md`** — `EplanRemoteClient`: discovery, dynamic ports, headless launch,
  version gotchas (2023 vs 2025), running actions and scripts remotely, Cogineer from Excel.
- **`references/pitfalls.md`** — the command-blocking issue (message loop / monitor thread),
  `using`/`Dispose` discipline, the sequential execution model, error handling, and the compile errors
  that masquerade as timeouts, including which C# each version's engine actually accepts.
- **`references/integration-patterns.md`** — EPLAN to the outside: HTTP servers, SignalR, forwarding
  EPLAN system errors to external services.

## Resolve identifiers, never guess

Action names, their parameters and API signatures are exact, case-sensitive identifiers, many of them
undocumented in the manual. Resolve each against a source before writing it:

1. **Ask EPLAN itself** — through the `eplan` MCP server (`mcp__eplan__*`: `eplan_tools_search` /
   `eplan_tools_describe` / `eplan_tools_call`, `eplan_action_catalog` / `eplan_action_describe` /
   `eplan_action_run`), a Remote Client, or a script you execute. Introspection beats any document:
   enumerate the registered actions and their parameters, reflect over `Eplan.EplApi.*` to confirm a
   member before calling it. See `references/actions-reference.md` and `references/api-data-access.md`.
2. **Search the local documentation** — `mcp__eplan2025__*` for this install's exact API,
   `mcp__eplan2025guide__*` for the program and its dialogs, `mcp__eecpro__*` for EEC Pro; the full
   routing is in `eplan-docs`. Every index is local SQLite, so queries stay on the machine. For
   anything with a real or guessable exact name (action name, class/method/property, error code) a
   keyword/FTS5 index beats a semantic one — it never fragments a page into disconnected chunks.
3. **The official help** at `https://www.eplan.help/` for prose rather than identifiers.

Query in English, and prefer several narrow queries over one broad one ("action to renumber devices",
"PagePropertyList page type values").

## Golden rules

1. **EPLAN actions are pseudo-asynchronous.** After `oCLI.Execute(...)` in an external or long-running
   context, code can hang forever without an active message loop. Read `references/pitfalls.md` before
   any multi-step automation.
2. **Dispose everything** — `ActionCallingContext`, `EplanRemoteClient`, temp clients: `using`, or
   `finally`.
3. **Operations are sequential.** Each action finishes before the next; never fire actions at one
   instance in parallel.
4. **No empty `catch {}`.** Log with `BaseException(msg, MessageLevel.X).FixMessage()` inside EPLAN, a
   logger outside.
5. **EPLAN 2025 remoting needs "Remote Client Access"** enabled in EPLAN options; transport is gRPC
   (default 49152, dynamic). 2023 had it on by default.
6. **Target .NET Framework 4.8.1** for EPLAN 2025 API and RemoteClient work; reference the DLLs from
   `C:\Program Files\EPLAN\Platform\<version>\Bin\`.
7. **Verify action names and parameters before use** — most are undocumented and all are
   case-sensitive: ask a live EPLAN, or search the docs.
8. **Never `using Eplan.EplApi.DataModel;` / `…HEServices;` in a script** (CS0234 — fixed assembly set).
   Reach that object model through runtime reflection, and never hardcode the assembly name: on 2027
   the managed assemblies are `…DataModelNetu`/`HEServicesNetu` and the un-suffixed names are the
   mixed-mode *native* twins, so an old hardcoded name throws `BadImageFormatException` there. That is
   not a clean version cutoff either — measured on 2025.0.3 the loaded managed assembly *is*
   `Eplan.EplApi.DataModelu` and nothing refuses to load. Scan
   `AppDomain.CurrentDomain.GetAssemblies()` for the type, then try candidate names. See
   `references/e3d-installation-spaces.md`.
9. **Never `RegisterScript` a one-shot `[Start]` script.** That installs persistent hooks
   (`[DeclareAction]`/`[DeclareEventHandler]`/`[DeclareRegister]`); a `[Start]`-only script has none, so
   registering first earns a spurious EPLAN warning and wastes two round-trips. Call `ExecuteScript`
   alone. See `references/pitfalls.md` #10.
10. **Write generated scripts to the oldest C# the fleet needs — on 2026 that is C# 5**: no `?.`, no
    `$"…"`, no `{ ["k"] = v }`, no `nameof`. A compile error is *silent*: `ExecuteScript` reports
    success, the script never runs, and a caller waiting on its output sees a timeout — which reads as
    a hung EPLAN. **On any script timeout, read EPLAN's system-message tree for the `CS####` line first.**
    (2027 accepts more than 2026, so probe rather than assume.) See `references/pitfalls.md` #9.

## Deployment notes for this plugin

- Installed platform: EPLAN Electric P8 **2025.0.3**, Remote Client access must be enabled.
- Live automation: MCP server `eplan` → `mcp__eplan__*`, in discovery mode (typed tools are found with
  `eplan_tools_search`, read with `eplan_tools_describe`, called with `eplan_tools_call`; raw actions via
  `eplan_action_*`). Details in the `eplan` skill.
- Documentation is entirely local: `mcp__eplan2025__*` is this install's exact API reference (12
  assemblies, 36,493 members), `mcp__eplan2025guide__*` the 2025 platform help (2,691 pages), and
  `mcp__eecpro__*` the EEC Pro 2026 help (1,971 pages). Where older material in this skill mentions
  `eplan-rag`, `eplan-wiki-2027` or `eecpro-rag`, use these tools instead. The 2026 and 2027 indexes
  exist locally but ship disabled; see `eplan-docs`.
- Upstream: https://github.com/Canary-ECAD/eplan-scripting-skill (MIT, © 2025 Christian D. Lopez); see
  `licenses/` in the plugin root.
