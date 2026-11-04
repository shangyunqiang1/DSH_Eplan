#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline EPLAN help MCP server (pure local, no network at query time).

Serves documentation databases crawled from the official EPLAN help site
(www.eplan.help) by ``scripts/build-help-index.py``.  One process serves one
docset, selected with ``--docset``:

    2025guide  EPLAN Electric P8 2025 platform help (user guide, dialogs)
    2026       EPLAN Electric P8 2026 API reference + platform help
    2027       EPLAN Electric P8 2027 API reference + platform help
    eecpro     EPLAN EEC Pro 2026 help chapters

Tools, one triple per docset:

    2025guide  eplan2025_guide_search, eplan2025_guide_get, eplan2025_guide_stats
    2026       eplan_search, eplan2026_get, eplan_stats
    2027       eplan2027_search, eplan2027_get, eplan2027_stats
    eecpro     eecpro_search, eecpro_get, eecpro_stats

Transport: newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio).
Standard library only.  Database path: ``--db``, else the env var named in
DOCSETS, else ``../../data/<file>`` relative to this file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.parse

PROTOCOL_DEFAULT = "2024-11-05"
MAX_TEXT = 24000
GET_PAGE_CHARS = 12000

DOCSETS = {
    "2025guide": {
        "server": "eplan2025-guide",
        "version": "2025",
        "title": "EPLAN Electric P8 2025 platform help (user guide and dialogs, local crawl of www.eplan.help)",
        "db_file": "eplan2025-guide.sqlite",
        "db_env": "EPLAN2025_GUIDE_DB",
        "tools": ("search", "get", "stats"),
        "tool_names": {
            "search": "eplan2025_guide_search",
            "get": "eplan2025_guide_get",
            "stats": "eplan2025_guide_stats",
        },
    },
    "2026": {
        "server": "eplan2026-docs",
        "version": "2026",
        "title": "EPLAN Electric P8 2026 documentation (local crawl of www.eplan.help)",
        "db_file": "eplan2026-help.sqlite",
        "db_env": "EPLAN2026_DB",
        "tools": ("search", "get", "stats"),
        "tool_names": {
            "search": "eplan_search",
            "get": "eplan2026_get",
            "stats": "eplan_stats",
        },
    },
    "2027": {
        "server": "eplan2027-docs",
        "version": "2027",
        "title": "EPLAN Electric P8 2027 documentation (local crawl of www.eplan.help)",
        "db_file": "eplan2027-help.sqlite",
        "db_env": "EPLAN2027_DB",
        "tools": ("search", "get", "stats"),
        "tool_names": {
            "search": "eplan2027_search",
            "get": "eplan2027_get",
            "stats": "eplan2027_stats",
        },
    },
    "eecpro": {
        "server": "eecpro-docs",
        "version": "2026",
        "title": "EPLAN EEC Pro 2026 help (local crawl of www.eplan.help)",
        "db_file": "eecpro-help.sqlite",
        "db_env": "EECPRO_DB",
        "tools": ("search", "get", "stats"),
        "tool_names": {
            "search": "eecpro_search",
            "get": "eecpro_get",
            "stats": "eecpro_stats",
        },
    },
}

DOCSET = "2026"
CONFIG = DOCSETS[DOCSET]
_DB_PATH = None

_TOKENS_RE = re.compile(r"[A-Za-z0-9_]+")


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
def _data_dir() -> str:
    """Where the local documentation indexes live.

    Resolution order: ``EPLAN_DATA_DIR`` (one override for every docset), then
    the bundle's own ``data`` directory (``<bundle>/data``, two levels above
    this file).  Keeping the default inside the bundle means a checkout, a
    directory link and a copied install all keep their indexes next to the
    code they belong to.
    """
    override = os.environ.get("EPLAN_DATA_DIR")
    if override:
        return override
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "data"))


def _default_db(docset: str) -> str:
    conf = DOCSETS[docset]
    env = os.environ.get(conf["db_env"])
    if env:
        return env
    return os.path.join(_data_dir(), conf["db_file"])


def _connect() -> sqlite3.Connection:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = _default_db(DOCSET)
    if not os.path.isfile(_DB_PATH):
        raise RuntimeError(
            "local documentation index for %s not found at %s.\n"
            "Build it with `python scripts\\build-help-index.py ... --out \"%s\"` "
            "(see skills/eplan-setup), or point %s / EPLAN_DATA_DIR at an existing database."
            % (DOCSET, _DB_PATH, _DB_PATH, DOCSETS[DOCSET]["db_env"])
        )
    conn = sqlite3.connect("file:%s?mode=ro" % _DB_PATH.replace("?", "%3F"), uri=True)
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


def _tokens(query: str) -> list[str]:
    return [tok for tok in _TOKENS_RE.findall(query or "") if len(tok) >= 2]


def _snippet(row: sqlite3.Row, tokens: list[str], limit: int = 320) -> str:
    body = " ".join((row["body"] or "").split())
    if not body:
        return ""
    lowered = body.lower()
    pos = -1
    for tok in tokens:
        pos = lowered.find(tok.lower())
        if pos >= 0:
            break
    if pos < 0:
        return _clip(body, limit)
    start = max(0, pos - limit // 3)
    end = min(len(body), start + limit)
    text = body[start:end]
    if start > 0:
        text = "… " + text
    if end < len(body):
        text = text + " …"
    return text


def _kind_group(kind: str) -> str:
    if kind in ("type", "members", "namespace", "member"):
        return "Api"
    return "User Guide"


def _format_hit(row: sqlite3.Row, tokens: list[str], index: int) -> str:
    title = row["title"] or row["path"]
    lines = ["### %d. %s" % (index, title)]
    meta = []
    if row["breadcrumb"]:
        meta.append(row["breadcrumb"])
    meta.append("category `%s`" % _kind_group(row["kind"] or ""))
    lines.append("- " + " · ".join(meta))
    snippet = _snippet(row, tokens)
    if snippet:
        lines.append("")
        lines.append(snippet)
    lines.append("")
    lines.append("- Source: %s" % row["url"])
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #
def _fts_query(query: str) -> str | None:
    tokens = _tokens(query)
    if not tokens:
        return None
    return " AND ".join('"%s"*' % tok.replace('"', "") for tok in tokens)


def _search(conn: sqlite3.Connection, args: dict) -> str:
    query = str(args.get("query") or "").strip()
    if not query:
        return "query is required"
    top_k = args.get("topK", args.get("top_k", 5))
    try:
        top_k = max(1, min(20, int(top_k)))
    except (TypeError, ValueError):
        top_k = 5
    kind = str(args.get("kind") or "").strip()
    category = str(args.get("category") or "").strip()
    assembly = str(args.get("assembly") or "").strip()

    where = []
    params: list = []
    if category:
        low = category.lower()
        if low in ("api", "api reference"):
            where.append("kind != 'topic'")
        elif low == "user guide":
            where.append("kind = 'topic'")
        elif DOCSET == "eecpro":
            where.append("path LIKE ?")
            params.append("%" + category + "%")
    if kind and kind not in ("any", "all"):
        # 2027 hosted service accepts bundle|standalone; local DB uses page kinds.
        if kind in ("bundle", "standalone"):
            pass
        elif kind == "api" or kind == "api reference":
            where.append("kind != 'topic'")
        else:
            where.append("kind = ?")
            params.append(kind)
    if assembly:
        where.append("path LIKE ?")
        params.append("%" + assembly + "%")
    where_sql = (" AND " + " AND ".join(where)) if where else ""

    tokens = _tokens(query)
    results = []
    fts = _fts_query(query)
    if fts:
        try:
            sql = (
                "SELECT p.*, bm25(fts, 4.0, 1.0) AS rank FROM fts "
                "JOIN page p ON p.id = fts.rowid WHERE fts MATCH ?" + where_sql.replace("kind", "p.kind").replace("path", "p.path") +
                " ORDER BY rank LIMIT ?"
            )
            results = conn.execute(sql, [fts] + params + [top_k]).fetchall()
        except sqlite3.Error:
            results = []
    if not results:
        # LIKE fallback: the whole query first, then every token separately (so
        # "ProjectManager OpenProject" still finds pages carrying both words when
        # the FTS index is still being built or the tokens are too short for it).
        attempts = [[query]] + ([tokens] if len(tokens) > 1 else [])
        for needle_set in attempts:
            where2 = []
            params2: list = []
            for needle in needle_set:
                like = "%" + needle + "%"
                where2.append("(title LIKE ? OR body LIKE ? OR path LIKE ?)")
                params2.extend([like, like, like])
            if where:
                where2.extend(where)
                params2.extend(params)
            sql = "SELECT * FROM page WHERE status = 200 AND " + " AND ".join(where2) + " LIMIT ?"
            results = conn.execute(sql, params2 + [top_k]).fetchall()
            if results:
                break

    if not results:
        return 'No documentation pages matched "%s".\n\nTip: this index holds the official EPLAN %s help. For an exact API identifier try its member name (e.g. "ProjectManager OpenProject"); for concepts use plain words.' % (query, CONFIG["version"])

    blocks = [_format_hit(row, tokens, i + 1) for i, row in enumerate(results)]
    count = conn.execute("SELECT COUNT(*) FROM page WHERE status = 200").fetchone()[0]
    header = "Found %d page(s) in the local EPLAN %s index (%d pages total)." % (
        len(results), CONFIG["version"], count,
    )
    return header + "\n\n" + "\n\n".join(blocks)


def _get(conn: sqlite3.Connection, args: dict) -> str:
    raw = str(args.get("path") or args.get("url") or "").strip()
    if not raw:
        return "path is required"
    try:
        offset = max(0, int(args.get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0

    candidates = [raw]
    if raw.startswith("http://") or raw.startswith("https://"):
        candidates.append(urllib.parse.unquote(urllib.parse.urlparse(raw).path))
    path = candidates[-1]
    row = conn.execute(
        "SELECT * FROM page WHERE status = 200 AND (path = ? OR url = ?)", (path, raw)
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM page WHERE status = 200 AND (path LIKE ? OR url LIKE ?) LIMIT 1",
            ("%" + path, "%" + raw),
        ).fetchone()
    if row is None:
        return 'No local page matches path "%s". Use the search tool first.' % raw

    body = row["body"] or ""
    chunk = body[offset:offset + GET_PAGE_CHARS]
    header = [
        "# %s" % (row["title"] or row["path"]),
        "- breadcrumb: %s" % row["breadcrumb"] if row["breadcrumb"] else "",
        "- source: %s" % row["url"],
        "- chars: %d-%d of %d" % (offset, offset + len(chunk), len(body)),
        "",
    ]
    out = "\n".join(line for line in header if line != "") + "\n\n" + chunk
    if offset + len(chunk) < len(body):
        out += "\n\n[truncated: call the get tool again with offset=%d]" % (offset + len(chunk))
    return out


def _stats(conn: sqlite3.Connection) -> str:
    meta = _meta(conn)
    row = conn.execute(
        "SELECT COUNT(*) AS pages, SUM(LENGTH(body)) AS chars FROM page WHERE status = 200"
    ).fetchone()
    kinds = dict(conn.execute(
        "SELECT kind, COUNT(*) FROM page WHERE status = 200 GROUP BY kind ORDER BY 2 DESC"
    ).fetchall())
    size_mb = os.path.getsize(_DB_PATH) / (1024 * 1024)
    lines = [
        "Local documentation index: %s" % CONFIG["title"],
        "- docset: %s" % DOCSET,
        "- pages: %d (body chars: %s)" % (row["pages"] or 0, "{:,}".format(row["chars"] or 0)),
        "- kinds: %s" % ", ".join("%s=%d" % kv for kv in kinds.items()),
    ]
    if meta.get("source"):
        lines.append("- crawled from: %s" % meta["source"])
    if meta.get("built_at"):
        lines.append("- built at: %s" % meta["built_at"])
    if meta.get("version"):
        lines.append("- help version: %s" % meta["version"])
    lines.append("- database: %s (%.1f MB)" % (_DB_PATH, size_mb))
    lines.append("- network: none — every query is answered from this file")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Tool definitions
# --------------------------------------------------------------------------- #
def _search_schema() -> dict:
    extra = {}
    if DOCSET in ("2026", "2027", "2025guide"):
        extra = {
            "category": {"type": "string", "enum": ["API Reference", "User Guide", "Api"],
                         "description": "Optional category filter."},
        }
    else:
        extra = {
            "category": {"type": "string",
                         "description": "Optional path filter, e.g. eecscripting, eecplc, refformulas."},
        }
    props = {
        "query": {"type": "string", "description": "Search words or an exact identifier."},
        "topK": {"type": "number", "minimum": 1, "maximum": 20, "default": 5,
                 "description": "Number of results to return"},
    }
    props.update(extra)
    return {"type": "object", "properties": props, "required": ["query"]}


def _get_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string",
                     "description": "Page path (or full URL) from a search result, e.g. "
                                    "/en-us/Infoportal/Content/Plattform/2025/Content/htm/wirenumberinggui_k_start.htm"},
            "offset": {"type": "number", "minimum": 0, "default": 0,
                       "description": "Character offset to continue from"},
        },
        "required": ["path"],
    }


def _tool_names() -> dict:
    return CONFIG["tool_names"]


def _tool_defs() -> list[dict]:
    names = _tool_names()
    tools = [{
        "name": names["search"],
        "description": "Full-text search over the local offline copy of the EPLAN %s help "
                       "(crawled once from www.eplan.help; no network needed). Returns ranked pages "
                       "with a snippet and the original source URL." % CONFIG["version"],
        "inputSchema": _search_schema(),
    }]
    if "get" in CONFIG["tools"]:
        tools.append({
            "name": names["get"],
            "description": "Read one page of the local EPLAN %s help by its path from a search "
                           "result. Paginated with offset for long pages." % CONFIG["version"],
            "inputSchema": _get_schema(),
        })
    tools.append({
        "name": names["stats"],
        "description": "Show what this local EPLAN %s documentation index contains." % CONFIG["version"],
        "inputSchema": {"type": "object", "properties": {}},
    })
    return tools


def _call_tool(name: str, args: dict) -> str:
    names = _tool_names()
    conn = _connect()
    try:
        if name == names["search"]:
            return _search(conn, args)
        if "get" in CONFIG["tools"] and name == names["get"]:
            return _get(conn, args)
        if name == names["stats"]:
            return _stats(conn)
        raise ValueError("unknown tool: %s" % name)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# MCP stdio (newline-delimited JSON-RPC 2.0)
# --------------------------------------------------------------------------- #
def _respond(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _error(msg_id, code: int, message: str) -> None:
    _respond({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


def _handle(msg: dict) -> None:
    method = msg.get("method") or ""
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        _respond({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL_DEFAULT,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": CONFIG["server"], "version": "1.0.0"},
                "instructions": (
                    "Offline copy of the official EPLAN %s help, crawled locally from "
                    "www.eplan.help. All queries are answered from a local SQLite file; "
                    "nothing is sent over the network." % CONFIG["version"]
                ),
            },
        })
    elif method == "notifications/initialized":
        return
    elif method == "ping":
        _respond({"jsonrpc": "2.0", "id": msg_id, "result": {}})
    elif method == "tools/list":
        _respond({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": _tool_defs()}})
    elif method == "tools/call":
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}
        try:
            text = _call_tool(name, args)
            _respond({"jsonrpc": "2.0", "id": msg_id,
                      "result": {"content": [{"type": "text", "text": text}], "isError": False}})
        except Exception as exc:  # keep the session alive on tool errors
            _respond({"jsonrpc": "2.0", "id": msg_id,
                      "result": {"content": [{"type": "text", "text": "Error: %s" % exc}], "isError": True}})
    elif method in ("shutdown", "exit"):
        sys.exit(0)
    else:
        _error(msg_id, -32601, "Method not found: %s" % method)


def _setup_stdio() -> None:
    # Windows defaults to cp936 for pipes; MCP is UTF-8.
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def main() -> int:
    global DOCSET, CONFIG, _DB_PATH
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docset", required=True, choices=sorted(DOCSETS))
    ap.add_argument("--db", default="")
    args = ap.parse_args()
    DOCSET = args.docset
    CONFIG = DOCSETS[DOCSET]
    if args.db:
        _DB_PATH = os.path.abspath(args.db)
    _setup_stdio()
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _error(None, -32700, "Parse error")
            continue
        try:
            _handle(msg)
        except SystemExit:
            raise
        except Exception as exc:  # never die on one bad message
            _error(msg.get("id"), -32603, "Internal error: %s" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
