---
name: eplan-docs
description: Answer EPLAN questions from five local documentation indexes, naming the version that answered. Covers the version-exact P8 2025 .NET API reference (mcp__eplan2025__*), the P8 2025 platform help with its dialogs, settings, commands and procedures (mcp__eplan2025guide__*), the P8 2026 and 2027 help crawls, and the EEC Pro 2026 help (mcp__eecpro__*). Use for any API member, signature, exception, dialog location, menu path, setting, workflow, action name or EEC Pro formula. No query leaves the machine.
---

# EPLAN documentation

Five services, and they are not interchangeable: each has its own version, coverage and retrieval.
Pick deliberately, and say which one answered.

| Index | Tools | Version | Holds | Network |
| --- | --- | --- | --- | --- |
| 2025 API | `eplan2025_search` / `_get` / `_type` / `_stats` | **2025.0.3**, this install's own XML | .NET API reference: 12 `Eplan.EplApi.*` assemblies, 36,493 members (namespaces, types, methods, properties, fields, events) | none |
| 2025 guide | `eplan2025_guide_search` / `_get` / `_stats` | **2025** platform help | the user manual: dialogs, settings, commands, concepts, messages — 2,691 pages from `Plattform/2025` | none |
| 2026 | `eplan_search` / `eplan2026_get` / `eplan_stats` | P8 2026 | API pages **and** the platform guide in one index, 25,024 pages | none |
| 2027 | `eplan2027_search` / `_get` / `_stats` | P8 2027 | API pages **and** the platform guide, 26,360 pages | none |
| EEC Pro | `eecpro_search` / `eecpro_get` / `eecpro_stats` | EEC Pro 2026 | reference, formulas, CAD, PLC, scripting, administration — 1,971 pages | none |

`mcp__eplan2025__*`, `mcp__eplan2025guide__*` and `mcp__eecpro__*` are mounted. **2026 and 2027 ship
disabled** (`disabled: true` in `cordis.patch.yml`, because the installed platform is P8 2025), so
`mcp__eplan2026__*` / `mcp__eplan2027__*` answer *unknown tool* until the row is switched on in
设置 → 插件. Say that, and offer to enable it — an unloaded index is not an undocumented topic.

## API question or program question

The split that decides the answer, because both 2025 indexes are version-exact and cover different material:

- **API** (`mcp__eplan2025__*`) — .NET types and members: class names, overloads, parameters,
  return values, exceptions, remarks. Written for code.
- **Guide** (`mcp__eplan2025guide__*`) — the program: where a dialog lives ("Dialog call: File >
  Extras > …"), what a setting does, how a workflow runs, what a message means. Nothing has a signature.

"Which method returns the connection numbering?" is API. "How do I change the connection numbering
scheme?" is guide. An empty result on one is usually the wrong index, not a gap — try the other
before concluding anything.

## 2025 API reference

The authority for this machine: built from the installed
`C:\Program Files\EPLAN\Platform\2025.0.3\Bin\Eplan.EplApi.*u.xml`, so it cannot drift from the binaries.

- `eplan2025_search({query, topK=8, kind?, assembly?})` — best with dotted full names; falls back to
  substring matching for CJK and partial words. `kind`: `any|namespace|type|method|property|field|event`;
  `assembly` filters to one index id (`eplan2025_stats` lists them, e.g. `Baseu`, `DataModelu`, `Systemu`).
- `eplan2025_get({name})` — one member or type: accepts a full name
  (`Eplan.EplApi.Base.PathMap.ReSubstitutePath`), a signature head (`…OpenProject(`), a short member
  name, or a bare type name (returns the type listing). Every overload comes back with Parameters,
  Returns, Exceptions, Remarks and the Source URL.
- `eplan2025_type({type})` — a type's summary plus Methods / Properties / Fields / Events, one line
  each. Reach the surface before guessing member names.
- `eplan2025_stats()` — version, build time, source directory, counts per kind and assembly, DB size.

Queries that work: `ProjectManager OpenProject`, `Eplan.EplApi.DataModel.Project`, `PathMap
ReSubstitutePath`, `Gui` + `kind: "namespace"`. `InsertSymbol` correctly returns nothing — it is an
action name, not an API member.

## 2025 platform help

`eplan2025_guide_search({query, topK=5})` — plain words, the way the manual is written ("connection
numbering", "generate functions", "wire numbering scheme"). The 2025 index is all topic pages, so its
`category` filter is normally left out. `eplan2025_guide_get({path, offset})` reads one page in
12,000-character chunks; call it again with a higher `offset` for the rest. `eplan2025_guide_stats()`
for counts.

Pages keep their original `Source` URL under
`https://www.eplan.help/en-us/Infoportal/Content/Plattform/2025/Content/htm/<page>.htm`, so a procedure
can be cited exactly. The HTML is stripped to text: images, screenshots, video and the Flare
table-of-contents pane are not stored. "The button in the picture" is therefore unanswerable; the
surrounding text and the "Dialog call:" line usually are.

## 2026 and 2027

`eplan_search({query, topK=5, category?})` / `eplan2027_search({query, topK=8, category?})`, with
`category` in `API Reference` | `User Guide` | `Api` selecting the two halves of the same index. Best
with **exact** names for 2027 (action names, option ids, full type names). `eplan2026_get` /
`eplan2027_get` read a hit's page by the path or `Source` URL from the result, paginated by `offset`;
`eplan_stats` / `eplan2027_stats` report per-kind counts. Member pages are individually searchable —
one method name returns that method's page, not just its class.

Use them for a later release's behaviour, or to see whether a name absent from 2025 appeared later.
The version is 2026 or 2027 — say so; never present it as this install's behaviour. The 2027 build
additionally ships the `*Netu` assembly variants (`Eplan.EplApi.BaseNetu`, `…AFNetu`).

## EEC Pro

`eecpro_search({query, topK=5, category?})`; `category` matches the page path (`refformulas`,
`eecplc`, `refscripting`, `admin`, …). `eecpro_get` reads a page, `eecpro_stats` reports coverage.
Neither 2025 index holds EEC Pro content — pair this with the `eec-pro-development` skill.

## Lookup order

1. **Classify** — .NET API on this installation, how the program behaves, a later release, or EEC Pro.
2. **API**: type first (`eplan2025_type`), then the member (`eplan2025_get`). Cheaper than search and
   overloads arrive together.
3. **Guide**: search with the manual's own words, then read the best hit with `eplan2025_guide_get`.
   Pages are short — one or two, not ten.
4. **English technical terms**. For a Chinese request, translate the identifier and keep the original
   symbol names in the answer.
5. **Nothing at 2025**? Try alternate casing, overload or spelling, then the other 2025 index. Only
   then check 2026/2027 for later appearance — and say that is what you did.
6. **Cite the Source URL** the tool returned, with the version in the same sentence. 2025 API pages:
   `/en-us/Infoportal/Content/api/2025/<Assembly>u~<Type>[~<Member>(<Args>)].html`; 2025 guide:
   `/en-us/Infoportal/Content/Plattform/2025/Content/htm/<page>.htm`; 2026/2027: `/api/2026|2027/` or
   `/Plattform/2026|2027/Content/htm/`; EEC Pro: `/en-us/infoportal/content/eecpro/2026/Content/htm/`.
   Never synthesise a URL no tool returned — inherited or undocumented members legitimately have none.
7. **Runtime beats docs** when they disagree: inspect the real assembly or type through
   `eplan_execute_script` (see `eplan-scripting`) and report both.

## Local by construction

Every index is a SQLite file on this machine, built once from public EPLAN help pages — customer
names, project paths, part numbers and internal identifiers are fine in a query. The only network use
is that deliberate build (`scripts/build-help-index.py`, see `eplan-setup`); a query never uploads
anything. If a service's tools are absent, its server did not start: rebuild per `eplan-setup` and
name the unavailable services instead of treating the gap as empty documentation.
