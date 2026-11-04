---
name: eec-pro-development
description: Develop with EPLAN EEC Pro 2026 — the mechatronic model and typicals (variants, conditions), the formula language, configuration interfaces (Form-UI, Excel/CSV/XML/IMX), commands, Groovy actions and C# post-generation scripts, the EOX model file, and generation into P8, Pro Panel, PLC, Graph2D and Office targets, locally or through the Job Server. Use when building or debugging EEC Pro libraries, typical workbooks, configurations, EOX files, recipes or generation pipelines.
---

# EPLAN EEC Pro development

EEC Pro generates deliverables — P8 schematics, Pro Panel layouts, PLC programs, Graph2D documents,
Word files — from a **mechatronic model plus a configuration**, instead of drawing them by hand. This
skill carries the mental model and the workflow; the details (every formula function, command and
parameter) live in the local documentation index — see *Resolve identifiers*.

## The pipeline

```
mechatronic model  +  configuration values  ──►  generation  ──►  target output
(typicals, params,     (GUI, Form-UI,          (resolve           (P8 project, Pro
 conditions, formulas)  Excel/CSV/XML/IMX)      conditions,        Panel, PLC, text)
                                                insert macros)
```

1. **Mechatronic model** — the product, independent of any target system: functions, parameters, and
   the rules connecting them.
2. **Typicals** — reusable blocks. A typical wraps target artifacts (macro files, templates) behind
   **variants** and **conditions**: "include this macro only when `VOLTAGE=400` and `EARTHING` is `TT`
   or `TNS`". Conditions are written in the formula language; filenames encode them as `_VOLTAGE=400`,
   `Y(...)` for AND, `O(...)` for OR.
3. **Configuration** — concrete parameter values, through the GUI, a custom **Form-UI**
   (`refformui`), bulk import (`refexcel`, `refcsv`, `refxml`, `refimx`) or SAP (`eecsap`).
4. **Generation** — conditions are evaluated against the configuration and the target artifacts are
   produced, in-process or queued on a **Job Server** (`eecjobserver`, `refjobserver`, `tutjobs`).

For the ECAD module the output is a "typical workbook": one sheet per mounting location listing the
page/window macros to insert, already filtered to the resolved configuration. The field-proven decode
of that workbook (column layout, `####` group markers, why you must *not* re-evaluate the conditions)
is the reference `eec-typicals.md` inside the `eplan-scripting` skill.

## Where the work is

- **Formula language** (`refformulas` — the biggest doc category): parameter values, conditions,
  string building. Functions and operators are exact identifiers.
- **Commands** (`refcommands`): the automation verbs used during generation and scripting — open,
  import, assign, generate, export.
- **Scripting** (`refscripting`, `eecscripting`): custom logic inside EEC Pro.
- **Form-UI** (`refformui`): the configuration dialogs users fill in.
- **Administration** (`admin`): installation, system configuration, VMArgs (EEC Pro runs on a JVM).
- **Per-target modules**: `eececad` (P8), `eecpropanel`, `eecplc` (incl. Step7), `eecgraph2d`,
  `eectext`/`reftextgen` (Word), `eecoffice`, `eecsap`.

## Field references — read before building pipelines

The index explains *what* exists. These record *what actually happens* when you automate EEC Pro:

| Page | Read it when you… |
| --- | --- |
| [`references/job-server.md`](references/job-server.md) | write `.jmx` recipes, use file or web-service triggers, chain jobs, run several workers, call the REST API, or measure generation time |
| [`references/eox-format.md`](references/eox-format.md) | patch an `.eox` by script, share a library across many models, recompute checksums, check integrity, version resource folders |
| [`references/groovy-actions.md`](references/groovy-actions.md) | write Groovy recipe actions, call commands from them, feed JSON into the model, run the ECAD generation sequence, or pass arguments to the P8 post-generation script |
| [`references/doc-categories.md`](references/doc-categories.md) | choose a `category` for a documentation search |

## Resolve identifiers

EEC Pro identifiers — formula functions, commands, parameters, VMArgs — are exact, and many are
documented only in the official help, which this plugin indexes locally.

1. **`mcp__eecpro__eecpro_search`** (`{query, topK, category?}`) over the EEC Pro 2026 help, 1,971
   pages. `category` matches the page path (`refformulas`, `eecjobserver`, `eecplc`, `eecscripting`,
   `admin`, … — map in `references/doc-categories.md`); `eecpro_get` reads a page, `eecpro_stats`
   reports index health. Queries stay on this machine: the upstream hosted `eecpro-rag` service and its
   REST endpoint are not used.
2. **Wrong target warning** — `mcp__eplan2025__*` / `mcp__eplan2026__*` / `mcp__eplan2027__*` index
   EPLAN Electric P8, which contains no EEC Pro material.
3. Query in **English**, prefer several narrow queries, and filter by `category` whenever you know
   which subsystem owns the answer — the index is small enough that an unfiltered query can pull a
   same-named concept from the wrong module.

## Crossing to the P8 side

EEC Pro's main output *is* an EPLAN Electric P8 project. The moment the task crosses over — inserting
generated macros, renaming pages to the workbook's structure, scripting the EPLAN API, driving EPLAN
remotely — load `eplan-scripting` (and `eplan` for the running program). Typical boundary:

- configurator / model / conditions / formulas → this skill
- `.elk` project, `.ema`/`.emp` macros, `Eplan.EplApi.*`, Remote Client → `eplan-scripting`

## Golden rules

1. **A generated workbook is already condition-filtered.** Never re-evaluate `_VOLTAGE=400`, `Y()` or
   `O()` against the parameters — EEC resolved them when it wrote the sheet.
2. **Never guess a formula function, command or parameter name.** Search the index; identifiers are
   exact and the docs are the authority.
3. **Conditions, parameters and variants are model data, not decoration.** Changing them changes what
   generation produces — understand the mechatronic model before editing it.
4. **Generation is a batch, not a preview.** Run against scratch/test targets until the output is
   verified; a Job Server run is not a dry run.
5. **EEC Pro ≠ EEC One ≠ EPLAN P8 scripting.** Same vendor, different products and extensibility
   surfaces. A docs hit about `Eplan.EplApi.*` describes the *target* system's API — switch skills.
6. **"Successful" in a job log is not proof.** Some commands report success and change nothing. Verify
   the effect: the parameter value, the exported EOX, the file on the share.
7. **Every EOX edit ends with a checksum recompute and an integrity check.** Write to a new file; never
   overwrite the deployed model in place.
8. **A job's project reaches the output share only after the job ends.** Anything another job needs is
   published explicitly, from the post-generation script.
9. **Design for more than one worker from the start.** Exact paths, atomic `createNewFile`, and never
   "the newest file" or a directory count.
10. **Reload a changed recipe in the Job Server before testing.** Keep test batches small — a handful
    of entities, not hundreds; a large batch ties up the workers for hours.
11. **Measure before optimizing.** Per-action durations come from `/api/logs`; generation time is
    usually P8 macro insertion and worker hardware, not EEC formulas.

Upstream: https://github.com/Canary-ECAD/eec-pro-skill (MIT, © 2025 Christian D. Lopez); see
`licenses/` in the plugin root.
