#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline EPLAN Electric P8 2025 .NET API documentation MCP server.

Serves the version-exact EPLAN 2025 API reference that ships as .NET XML
documentation files with the installed platform.  Content is read from the
SQLite index built by ``scripts/build-eplan2025-index.py``.

Tools
-----
eplan2025_search  full-text search over 36k+ types, methods, properties, ...
eplan2025_get     full documentation of one member (all overloads)
eplan2025_type    all documented members of one type
eplan2025_stats   index statistics and version information

Transport: newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio).
Standard library only.  Set ``EPLAN2025_DB`` to override the database path.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from urllib.parse import quote

SERVER_NAME = "eplan2025-docs"
SERVER_VERSION = "1.0.0"
PROTOCOL_DEFAULT = "2024-11-05"
MAX_TEXT = 24000

_KINDS = ("namespace", "type", "method", "property", "field", "event", "other")
_KIND_LABEL = {
    "namespace": "Namespace",
    "type": "Type",
    "method": "Method",
    "property": "Property",
    "field": "Field",
    "event": "Event",
    "other": "Member",
}

_DB_PATH = None


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
def _data_dir() -> str:
    """Where the local documentation indexes live.

    Resolution order: ``EPLAN_DATA_DIR`` (one override for every docset), then
    the bundle's own ``data`` directory (``<bundle>/data``, two levels above
    this file).
    """
    override = os.environ.get("EPLAN_DATA_DIR")
    if override:
        return override
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "data"))


def _default_db() -> str:
    env = os.environ.get("EPLAN2025_DB")
    if env:
        return env
    return os.path.join(_data_dir(), "eplan2025.sqlite")


def _connect() -> sqlite3.Connection:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = _default_db()
    path = _DB_PATH
    if not os.path.isfile(path):
        raise RuntimeError(
            "EPLAN 2025 documentation index not found at %s. "
            "Run scripts/build-eplan2025-index.py first." % path
        )
    conn = sqlite3.connect("file:%s?mode=ro" % path.replace("?", "%3F"), uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _meta(conn: sqlite3.Connection) -> dict:
    try:
        return dict(conn.execute("SELECT key, value FROM meta").fetchall())
    except sqlite3.Error:
        return {}


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def _clip(text: str | None, limit: int) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " …"


def _first_line(text: str | None, limit: int = 400) -> str:
    if not text:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return _clip(line, limit)
    return ""


def _search_tokens(query: str) -> list[str]:
    return [tok for tok in re.findall(r"[A-Za-z0-9_]+", query or "") if len(tok) >= 2]


def _format_member(row, include_body: bool = False, max_body: int = 1500) -> str:
    kind = row["kind"]
    label = _KIND_LABEL.get(kind, kind)
    name = row["name"] or ""
    lines = ["### %s `%s`" % (label, name)]
    meta = []
    if row["assembly"]:
        meta.append("assembly `%s`" % row["assembly"])
    if row["ns"]:
        meta.append("namespace `%s`" % row["ns"])
    if meta:
        lines.append("- " + " · ".join(meta))
    summary = _clip(row["summary"], max_body)
    if summary:
        lines.append("")
        lines.append(summary)
    if include_body:
        for field, title in (
            ("params", "Parameters"),
            ("returns", "Returns"),
            ("exceptions", "Exceptions"),
            ("remarks", "Remarks"),
        ):
            value = _clip(row[field], max_body)
            if value:
                lines.append("")
                lines.append("**%s**" % title)
                lines.append(value)
    if row["url"]:
        lines.append("")
        lines.append("Source: %s" % row["url"])
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
def _tool_search(args: dict) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return "Error: 'query' is required."
    top_k = args.get("topK") or 8
    try:
        top_k = max(1, min(20, int(top_k)))
    except (TypeError, ValueError):
        top_k = 8
    kind = (args.get("kind") or "any").strip().lower()
    assembly = (args.get("assembly") or "").strip()

    conn = _connect()
    where = []
    params: list = []
    if kind in _KINDS:
        where.append("m.kind = ?")
        params.append(kind)
    if assembly:
        where.append("m.assembly LIKE ?")
        params.append("%" + assembly + "%")

    rows = []
    tokens = _search_tokens(query)
    if tokens:
        match = " ".join('"%s"*' % t.replace('"', "") for t in tokens[:10])
        sql = (
            "SELECT m.* FROM fts JOIN member m ON m.id = fts.rowid "
            "WHERE fts MATCH ?" + (" AND " + " AND ".join(where) if where else "") +
            " ORDER BY bm25(fts, 8.0, 6.0, 1.0, 0.5) LIMIT ?"
        )
        try:
            rows = conn.execute(sql, [match] + params + [top_k]).fetchall()
        except sqlite3.OperationalError:
            rows = []

    # Fallback for dotted names, CJK text or exotic syntax: plain substring match.
    if not rows:
        like = "%" + query + "%"
        clauses = ["m.name LIKE ? OR m.summary LIKE ?"]
        like_params: list = [like, like]
        if where:
            clauses.extend(where)
            like_params.extend(params)
        sql = (
            "SELECT m.* FROM member m WHERE " + " AND ".join(clauses) +
            " ORDER BY (m.kind='type') DESC, length(m.name) LIMIT ?"
        )
        rows = conn.execute(sql, like_params + [top_k]).fetchall()

    conn.close()
    if not rows:
        return (
            "No EPLAN 2025 API member matched %r.\n"
            "Tips: search for exact identifiers (e.g. 'ProjectManager', 'OpenProject', "
            "'InsertSymbol', 'Function'), drop namespaces, or try a shorter term." % query
        )

    header = "EPLAN P8 2025 API — %d of at most %d results for %r" % (len(rows), top_k, query)
    blocks = [header, ""]
    for row in rows:
        blocks.append(_format_member(row, include_body=False, max_body=320))
        blocks.append("")
    return _cap("\n".join(blocks))


def _lookup_members(conn: sqlite3.Connection, name: str) -> list:
    """Resolve a full name, a dotted name without signature, or a short name."""
    q = name.strip()
    short = q.rsplit(".", 1)[-1]
    queries = [
        ("SELECT * FROM member WHERE name = ? COLLATE NOCASE ORDER BY length(name) LIMIT 8", (q,)),
        # method / indexer head without signature: '...ProjectManager.OpenProject(%'
        ("SELECT * FROM member WHERE name = ? COLLATE NOCASE OR name LIKE ? COLLATE NOCASE "
         "ORDER BY length(name) LIMIT 8", (q, q + "(%")),
        # short member name: 'OpenProject' or 'OpenProject(%'
        ("SELECT * FROM member WHERE member_name = ? COLLATE NOCASE OR member_name LIKE ? COLLATE NOCASE "
         "ORDER BY length(name) LIMIT 8", (short, short + "(%")),
        # fuzzy: dotted suffix anywhere in the full name
        ("SELECT * FROM member WHERE name LIKE ? COLLATE NOCASE ORDER BY length(name) LIMIT 8",
         ("%." + q + "(%" if not q.endswith(")") else "%" + q,)),
        ("SELECT * FROM member WHERE name LIKE ? COLLATE NOCASE ORDER BY length(name) LIMIT 8",
         ("%" + q + "%",)),
    ]
    for sql, args in queries:
        rows = conn.execute(sql, args).fetchall()
        if rows:
            return rows
    return []


def _tool_get(args: dict) -> str:
    name = (args.get("name") or args.get("member") or "").strip()
    if not name:
        return "Error: 'name' is required (full or short member name, e.g. 'Eplan.EplApi.DataModel.ProjectManager.OpenProject' or 'OpenProject')."
    conn = _connect()
    rows = _lookup_members(conn, name)
    type_rows = [row for row in rows if row["kind"] == "type"]
    conn.close()
    if not rows:
        short = name.rsplit(".", 1)[-1]
        hint = ""
        try:
            hint = "\n\nClosest matches:\n" + _tool_search({"query": short, "topK": 3})
        except Exception:
            pass
        return "No EPLAN 2025 API member found for %r. Use eplan2025_search.%s" % (name, hint)

    blocks = []
    if len(rows) > 1:
        blocks.append("Found %d matching member(s), showing %d:" % (len(rows), min(len(rows), 8)))
    for row in rows[:8]:
        if row["kind"] == "type":
            type_members = _tool_type({"type": row["name"]})
            blocks.append(type_members)
        else:
            blocks.append(_format_member(row, include_body=True, max_body=2400))
        blocks.append("")
    if type_rows and len(rows) == 1:
        blocks.append("Tip: use `eplan2025_type` to list every member of this type.")
    return _cap("\n".join(blocks))


def _tool_type(args: dict) -> str:
    name = (args.get("type") or args.get("name") or "").strip()
    if not name:
        return "Error: 'type' is required (e.g. 'ProjectManager' or 'Eplan.EplApi.DataModel.ProjectManager')."
    conn = _connect()
    types = conn.execute(
        "SELECT * FROM member WHERE kind = 'type' AND (name = ? COLLATE NOCASE OR name LIKE ? COLLATE NOCASE) "
        "ORDER BY length(name) LIMIT 3",
        (name, "%." + name),
    ).fetchall()
    if not types:
        conn.close()
        return "No EPLAN 2025 API type found for %r. Use eplan2025_search." % name

    full = types[0]["name"]
    members = conn.execute(
        "SELECT * FROM member WHERE type_name = ? COLLATE NOCASE AND kind != 'type' "
        "ORDER BY kind, member_name LIMIT 400",
        (full,),
    ).fetchall()
    conn.close()

    lines = ["# %s" % full]
    summary = _clip(types[0]["summary"], 1200)
    if summary:
        lines += ["", summary]
    if types[0]["url"]:
        lines += ["", "Source: %s" % types[0]["url"]]
    if len(types) > 1:
        lines += ["", "Related types: " + ", ".join("`%s`" % t["name"] for t in types[1:])]

    groups: dict[str, list] = {}
    for m in members:
        groups.setdefault(m["kind"], []).append(m)
    plural = {
        "method": "Methods",
        "property": "Properties",
        "field": "Fields",
        "event": "Events",
        "other": "Members",
    }
    for kind in ("method", "property", "field", "event", "other"):
        items = groups.get(kind)
        if not items:
            continue
        lines += ["", "## %s (%d)" % (plural.get(kind, kind), len(items))]
        for m in items:
            sig = m["member_name"] or m["name"]
            desc = _first_line(m["summary"], 220)
            lines.append("- `%s`%s" % (sig, (" — " + desc) if desc else ""))
    return _cap("\n".join(lines))


def _tool_stats(args: dict) -> str:
    conn = _connect()
    meta = _meta(conn)
    total = conn.execute("SELECT count(*) FROM member").fetchone()[0]
    kinds = conn.execute(
        "SELECT kind, count(*) FROM member GROUP BY kind ORDER BY count(*) DESC"
    ).fetchall()
    assemblies = conn.execute(
        "SELECT assembly, count(*) FROM member GROUP BY assembly ORDER BY assembly"
    ).fetchall()
    documented = conn.execute("SELECT count(*) FROM member WHERE has_doc = 1").fetchone()[0]
    conn.close()
    size_mb = round(os.path.getsize(_default_db()) / (1024 * 1024), 1)

    lines = [
        "# EPLAN P8 2025 API index",
        "",
        "- EPLAN version: **%s**" % meta.get("eplan_version", "unknown"),
        "- Built: %s" % meta.get("built_at", "unknown"),
        "- Source: %s" % meta.get("source_dir", "unknown"),
        "- Members: **%d** (%d with documentation)" % (total, documented),
        "- Database: %s (%s MB)" % (_default_db(), size_mb),
        "",
        "## Kinds",
    ]
    for kind, count in kinds:
        lines.append("- %s: %d" % (_KIND_LABEL.get(kind, kind), count))
    lines += ["", "## Assemblies"]
    for assembly, count in assemblies:
        lines.append("- `%s`: %d" % (assembly, count))
    lines += [
        "",
        "## Usage",
        "- `eplan2025_search(query, topK=8, kind=any, assembly=\"\")` — ranked search.",
        "- `eplan2025_get(name)` — full page for one member (all overloads).",
        "- `eplan2025_type(type)` — all documented members of a type.",
        "- Documentation is version-exact for the locally installed 2025 platform;",
        "  for 2026/2027 user guides use the eplan2026 / eplan2027 servers.",
    ]
    return _cap("\n".join(lines))


TOOLS = [
    {
        "name": "eplan2025_search",
        "description": (
            "Search the version-exact EPLAN Electric P8 2025 .NET API reference that is installed "
            "locally (36k+ namespaces, types, methods, properties, fields). Returns ranked members "
            "with short summaries and source links. Use exact identifiers for best results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Identifier or keywords, e.g. 'ProjectManager OpenProject', 'InsertSymbol', 'Function.GetProperty'."},
                "topK": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8, "description": "Maximum results (default 8)."},
                "kind": {
                    "type": "string",
                    "enum": ["any", "namespace", "type", "method", "property", "field", "event"],
                    "default": "any",
                    "description": "Restrict result kind.",
                },
                "assembly": {"type": "string", "description": "Optional assembly fragment, e.g. 'DataModel', 'Base', 'HEServices'."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "eplan2025_get",
        "description": (
            "Get the full EPLAN 2025 API documentation page for one member: summary, parameters, "
            "return value, exceptions, remarks and source URL. Accepts the full member name "
            "(with optional signature) or a short member name; all overloads are returned."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Full or short member name, e.g. 'Eplan.EplApi.DataModel.ProjectManager.OpenProject' or 'OpenProject'."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "eplan2025_type",
        "description": (
            "List every documented member (methods, properties, events, fields) of one EPLAN 2025 "
            "API type, with one-line descriptions. Faster than repeated searches when you explore a class."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "Type name, e.g. 'ProjectManager', 'Project', 'Eplan.EplApi.DataModel.Function'."},
            },
            "required": ["type"],
        },
    },
    {
        "name": "eplan2025_stats",
        "description": "Show what the local EPLAN 2025 API index contains: version, build time, member counts per kind and assembly.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _cap(text: str) -> str:
    if len(text) <= MAX_TEXT:
        return text
    return text[:MAX_TEXT] + "\n\n… output truncated at %d characters." % MAX_TEXT


# --------------------------------------------------------------------------- #
# JSON-RPC plumbing
# --------------------------------------------------------------------------- #
def _send(message: dict) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _text_result(text: str, is_error: bool = False) -> dict:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def _handle_call(msg_id, name: str, args: dict) -> dict:
    handler = {
        "eplan2025_search": _tool_search,
        "eplan2025_get": _tool_get,
        "eplan2025_type": _tool_type,
        "eplan2025_stats": _tool_stats,
    }.get(name)
    if handler is None:
        return _error(msg_id, -32602, "Unknown tool: %s" % name)
    try:
        text = handler(args or {})
    except Exception as exc:  # keep the session alive, report the failure
        return {"jsonrpc": "2.0", "id": msg_id, "result": _text_result("Tool failed: %s" % exc, True)}
    return {"jsonrpc": "2.0", "id": msg_id, "result": _text_result(text)}


def _handle(message: dict) -> dict | None:
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        client_version = params.get("protocolVersion") or PROTOCOL_DEFAULT
        version = client_version if client_version in ("2024-11-05", "2025-03-26", "2025-06-18") else PROTOCOL_DEFAULT
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Version-exact EPLAN Electric P8 2025 .NET API documentation (offline, from the "
                    "installed platform). Prefer this server for EPLAN 2025 API questions; use the "
                    "eplan2027 / eplan2026 servers for user-guide and 2027-only content."
                ),
            },
        }
    if method == "notifications/initialized" or method == "initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        return _handle_call(msg_id, params.get("name", ""), params.get("arguments") or {})
    if method in ("resources/list",):
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"resources": []}}
    if method in ("prompts/list",):
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"prompts": []}}
    if msg_id is not None:
        return _error(msg_id, -32601, "Method not found: %s" % method)
    return None


def _setup_stdio() -> None:
    """MCP stdio is UTF-8; Windows consoles may default to a legacy code page."""
    for stream, kwargs in (
        (sys.stdin, {"encoding": "utf-8", "errors": "replace"}),
        (sys.stdout, {"encoding": "utf-8", "errors": "strict", "newline": "\n"}),
        (sys.stderr, {"encoding": "utf-8", "errors": "replace"}),
    ):
        try:
            stream.reconfigure(**kwargs)
        except (AttributeError, ValueError):
            pass


def _serve() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        try:
            response = _handle(message)
        except Exception as exc:  # never die mid-session
            response = _error(message.get("id"), -32603, "Internal error: %s" % exc)
        if response is not None:
            _send(response)
    return 0


if __name__ == "__main__":
    _setup_stdio()
    try:
        sys.exit(_serve())
    except KeyboardInterrupt:
        sys.exit(0)
