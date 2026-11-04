# Offline documentation indexes

These SQLite files are what every documentation server reads. Nothing here is
redistributed with the plugin: each index is built on the machine that runs it,
by crawling `www.eplan.help` or by reading the locally installed EPLAN XML docs.

| File | Built by | Contents |
| --- | --- | --- |
| `eplan2025.sqlite` | `scripts/build-eplan2025-index.py` | P8 2025 .NET API reference from the installed XML docs (~35 MB, 36,493 members) |
| `eplan2025-guide.sqlite` | `scripts/build-help-index.py guide --version 2025` | P8 2025 platform help (user guide, dialogs), 2,691 pages |
| `eplan2026-help.sqlite` | `scripts/build-help-index.py api` then `… guide --version 2026` | P8 2026 API reference **and** platform help |
| `eplan2027-help.sqlite` | same, `--version 2027` | P8 2027 API reference **and** platform help |
| `eecpro-help.sqlite` | `scripts/build-help-index.py sitemap …` | EEC Pro 2026 help |

## Where the servers look

1. `EPLAN2025_DB` / `EPLAN2025_GUIDE_DB` / `EPLAN2026_DB` / `EPLAN2027_DB` / `EECPRO_DB` — one file each.
2. `EPLAN_DATA_DIR` — this directory, wherever it points.
3. `<bundle>\data` — the default, i.e. where this README sits.

So a copied or moved bundle keeps working, and `EPLAN_DATA_DIR` lets the ~199 MB
of indexes live outside a read-only or shared plugin folder.

Rebuild instructions and the exact commands are in `../README.md`
("离线文档") and in the `eplan-setup` skill.
