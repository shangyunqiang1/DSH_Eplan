#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the offline, version-exact EPLAN Electric P8 2025 .NET API reference index.

Reads the .NET XML documentation files shipped with the installed EPLAN platform
(``Eplan.EplApi.*u.xml``) and writes a single SQLite database that the local MCP
server (server/docs2025/server.py) serves to the agent.

Standard library only.  Examples
-------------------------------
    python build-eplan2025-index.py
    python build-eplan2025-index.py --xml-dir "D:\\EPLAN\\Bin" --out .\\eplan.sqlite

The database is rebuilt from scratch on every run (an existing file is deleted).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import os
import re
import sqlite3
import sys
import urllib.parse
import xml.etree.ElementTree as ET

SCHEMA_VERSION = "1"
URL_BASE = "https://www.eplan.help/en-us/Infoportal/Content/api/2025/"

KINDS = ("namespace", "type", "method", "property", "field", "event", "other")
PREFIX_KIND = {
    "N": "namespace",
    "T": "type",
    "M": "method",
    "P": "property",
    "F": "field",
    "E": "event",
}

# Characters kept verbatim in the online URL; everything else is percent encoded.
_URL_SAFE = "()~.{}`-_@[],*!$&+=:;'"

_WS_RE = re.compile(r"[ \t\r\f\v\u00a0]+")
_NL_RE = re.compile(r"\n{2,}")


# --------------------------------------------------------------------------- #
# XML flattening helpers
# --------------------------------------------------------------------------- #
def _norm(text: str) -> str:
    """Collapse whitespace runs, drop empty lines and trailing spaces."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = _WS_RE.sub(" ", line).strip()
        if line:
            lines.append(line)
    return _NL_RE.sub("\n", "\n".join(lines)).strip()


def _ref_name(cref: str) -> str:
    """Turn a doc cref ("T:Eplan.X.Y", "!:Some.html") into a readable label."""
    if not cref:
        return ""
    cref = cref.strip()
    if len(cref) > 2 and cref[1] == ":":
        cref = cref[2:]
    return cref


def _inline(node: ET.Element) -> str:
    """Flatten an element to plain text, keeping block separation as newlines."""
    out = []

    def walk(el: ET.Element) -> None:
        if el.text:
            out.append(el.text)
        for child in el:
            tag = child.tag
            if tag in ("see", "seealso"):
                label = child.get("text") or _ref_name(child.get("cref"))
                if label:
                    out.append(" " + label + " ")
            elif tag == "exref":
                label = child.get("text") or child.get("target") or ""
                if label:
                    out.append(" " + label + " ")
            elif tag == "code":
                src = child.get("source")
                if src:
                    out.append(" [code sample: %s] " % src)
                elif child.text:
                    out.append(child.text)
            elif tag == "list":
                out.append("\n")
                _dump_list(child, out, walk)
                out.append("\n")
            elif tag == "br":
                out.append("\n")
            elif tag in ("para", "p", "item"):
                out.append("\n")
                walk(child)
                out.append("\n")
            elif tag == "term":
                walk(child)
                out.append(": ")
            elif tag == "description":
                walk(child)
                out.append("\n")
            elif tag in ("exclude", "deprecated"):
                # structural markers without useful prose
                pass
            else:
                walk(child)
            if child.tail:
                out.append(child.tail)

    walk(node)
    return _norm("".join(out))


def _dump_list(lst: ET.Element, out: list, walk) -> None:
    """Render a <list> as "term: description" rows (tables) or bullets."""
    is_table = (lst.get("type") or "").lower() == "table"
    for entry in lst:
        if entry.tag not in ("item", "listheader"):
            continue
        term = ""
        desc = ""
        for sub in entry:
            if sub.tag == "term":
                term = _inline(sub)
            elif sub.tag == "description":
                desc = _inline(sub)
        if term and desc:
            out.append("%s: %s" % (term, desc))
        elif term or desc:
            out.append(term or desc)
        if is_table is False and entry.tag == "item" and (term or desc):
            # bullet lists read better as one item per line
            pass
        out.append("\n")


def _flatten_params(sig_args: list, param_elems: list) -> str:
    """Render <param> entries; add the argument type when the arity matches."""
    rows = []
    typed = len(sig_args) == len(param_elems) and len(sig_args) > 0
    for index, (pname, ptext) in enumerate(param_elems):
        if typed:
            rows.append("%s (%s): %s" % (pname, sig_args[index], ptext))
        else:
            rows.append("%s: %s" % (pname, ptext))
    return "\n".join(rows)


def _split_signature(sig: str) -> list:
    """Split "(A,B{C,D},E)" into ["A", "B{C,D}", "E"] respecting nesting."""
    if not sig:
        return []
    body = sig[1:] if sig.startswith("(") else sig
    if body.endswith(")"):
        body = body[:-1]
    if not body.strip():
        return []
    parts, depth, cur = [], 0, []
    for ch in body:
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


def _short_name(token: str) -> str:
    """Drop the namespace and generic-arity marker from one type name."""
    token = token.strip().replace("`", "")
    if not token:
        return token
    return token.rsplit(".", 1)[-1]


def _short_type(text: str) -> str:
    """Turn "System.Collections.Generic.IEnumerable{Eplan.X.Foo}" into
    "IEnumerable<Foo>" and "System.String[]" into "String[]" (EPLAN help style)."""
    text = (text or "").strip()
    suffix = ""
    while text.endswith("[]"):
        text = text[:-2]
        suffix += "[]"
    out = []
    token = ""
    for ch in text.replace("{", "<").replace("}", ">"):
        if ch in ",<>":
            out.append(_short_name(token))
            out.append(ch)
            token = ""
        else:
            token += ch
    out.append(_short_name(token))
    return "".join(out) + suffix


def build_url(assembly: str, kind: str, name: str) -> str:
    """Online doc URL for a member.

    EPLAN help uses MadCap page names of the form
    ``<assembly stem>~<type full name>~<member signature>.html`` where method
    parameter types are shortened (``String`` rather than ``System.String``).
    """
    asm = urllib.parse.quote(assembly, safe=_URL_SAFE)

    def page(path: str) -> str:
        return URL_BASE + asm + "~" + urllib.parse.quote(path, safe=_URL_SAFE) + ".html"

    if kind in ("namespace", "type", "other"):
        return page(name)
    if kind == "method":
        head = name.split("(", 1)[0]
        type_name, _, method = head.rpartition(".")
        if not type_name:
            return URL_BASE + asm + ".html"
        signature = ""
        if "(" in name:
            args = name[name.index("(") + 1:]
            if args.endswith(")"):
                args = args[:-1]
            params = [_short_type(p) for p in _split_signature("(" + args + ")")]
            signature = "(" + ",".join(params) + ")"
        return page(type_name + "~" + method + signature)
    type_name, _, member = name.rpartition(".")
    if not type_name:
        # no containing type (e.g. "F:MODULE_NAME"): point at the assembly page
        return URL_BASE + asm + ".html"
    return page(type_name + "~" + member)


# --------------------------------------------------------------------------- #
# Member record extraction
# --------------------------------------------------------------------------- #
def _split_member_name(kind: str, body: str):
    """Return (namespace, type_name, member_name, signature)."""
    signature = ""
    if kind == "namespace":
        return body, body, "", ""
    if kind in ("type", "other"):
        type_name = body
        ns = body.rpartition(".")[0]
        return ns, type_name, "", ""
    # methods / properties / fields / events
    if "(" in body:
        head = body.split("(", 1)[0]
        signature = body[len(head):]
        if "." in head:
            type_name, _, member = head.rpartition(".")
            member_name = member + signature
        else:
            type_name, member_name = "", body
    else:
        type_name, _, member_name = body.rpartition(".")
        if not type_name:
            member_name = body
    ns = type_name.rpartition(".")[0] if type_name else ""
    return ns, type_name, member_name, signature


def extract_record(assembly: str, member_el: ET.Element) -> dict:
    raw = member_el.get("name") or ""
    prefix, sep, body = raw.partition(":")
    if not sep:
        prefix, body = "", raw
    kind = PREFIX_KIND.get(prefix, "other")

    summary = ""
    remarks_parts = []
    returns_parts = []
    example_parts = []
    params_list = []
    exceptions_list = []
    seealso_list = []
    stray = []

    if (member_el.text or "").strip():
        stray.append(_norm(member_el.text))

    for child in member_el:
        tag = child.tag
        if tag == "summary":
            chunk = _inline(child)
            summary = (summary + "\n" + chunk).strip() if summary else chunk
        elif tag == "remarks":
            chunk = _inline(child)
            if chunk:
                remarks_parts.append(chunk)
        elif tag in ("returns", "return"):
            chunk = _inline(child)
            if chunk:
                returns_parts.append(chunk)
        elif tag == "value":
            chunk = _inline(child)
            if chunk:
                returns_parts.append(chunk)
        elif tag == "example":
            chunk = _inline(child)
            if chunk:
                example_parts.append(chunk)
        elif tag == "param":
            pname = (child.get("name") or "").strip() or "param"
            params_list.append((pname, _inline(child)))
        elif tag == "typeparam":
            pname = "<%s>" % ((child.get("name") or "").strip() or "T")
            params_list.append((pname, _inline(child)))
        elif tag == "exception":
            etype = _ref_name(child.get("cref") or "")
            etext = _inline(child)
            if etype and etext:
                exceptions_list.append("%s: %s" % (etype, etext))
            elif etype or etext:
                exceptions_list.append(etype or etext)
        elif tag == "seealso":
            label = child.get("text") or _ref_name(child.get("cref"))
            if label:
                seealso_list.append(label)
        elif tag == "code":
            src = child.get("source")
            if src:
                example_parts.append("[code sample: %s]" % src)
            elif child.text:
                example_parts.append(_norm(child.text))
        else:
            chunk = _inline(child)
            if chunk:
                stray.append(chunk)

    if not summary and stray:
        summary = "\n".join(x for x in stray if x)
    elif stray:
        remarks_parts.extend(x for x in stray if x)

    ns, type_name, member_name, signature = _split_member_name(kind, body)

    remarks = "\n".join(remarks_parts)
    if example_parts:
        remarks = (remarks + "\n\nExample: " + " ".join(example_parts)).strip()
    if seealso_list:
        remarks = (remarks + "\n\nSee also: " + "; ".join(seealso_list)).strip()

    params_text = ""
    if params_list:
        params_text = _flatten_params(
            _split_signature(signature), params_list
        )

    returns = "\n".join(returns_parts)
    exceptions = "\n".join(exceptions_list)
    has_doc = 1 if (summary or remarks or params_text or returns or exceptions) else 0

    return {
        "assembly": assembly,
        "kind": kind,
        "name": body,
        "ns": ns,
        "type_name": type_name,
        "member_name": member_name,
        "signature": signature,
        "summary": summary,
        "remarks": remarks,
        "params": params_text,
        "returns": returns,
        "exceptions": exceptions,
        "url": build_url(assembly, kind, body),
        "has_doc": has_doc,
    }


def iter_members(path: str):
    """Stream <member> records out of one XML doc file, without holding it all."""
    handle = open(path, "rb")
    try:
        for event, elem in ET.iterparse(handle, events=("end",)):
            if elem.tag == "member":
                yield elem
                elem.clear()
    finally:
        handle.close()


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
DDL = """
CREATE TABLE member(
    id          INTEGER PRIMARY KEY,
    assembly    TEXT NOT NULL,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    ns          TEXT,
    type_name   TEXT,
    member_name TEXT,
    signature   TEXT,
    summary     TEXT,
    remarks     TEXT,
    params      TEXT,
    returns     TEXT,
    exceptions  TEXT,
    url         TEXT,
    has_doc     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE meta(
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX idx_member_name     ON member(name COLLATE NOCASE);
CREATE INDEX idx_member_kind     ON member(kind);
CREATE INDEX idx_member_assembly ON member(assembly);
"""

FTS_DDL = """
CREATE VIRTUAL TABLE fts USING fts5(
    name,
    member_name,
    summary,
    params,
    content='member',
    content_rowid='id',
    tokenize='unicode61'
);
"""

INSERT_SQL = """
INSERT INTO member(assembly, kind, name, ns, type_name, member_name, signature,
                   summary, remarks, params, returns, exceptions, url, has_doc)
VALUES (:assembly, :kind, :name, :ns, :type_name, :member_name, :signature,
        :summary, :remarks, :params, :returns, :exceptions, :url, :has_doc)
"""


def build(xml_dir: str, out_path: str, version: str) -> dict:
    pattern = os.path.join(xml_dir, "Eplan.EplApi.*u.xml")
    files = sorted(glob.glob(pattern))
    if not files:
        raise SystemExit("No Eplan.EplApi.*u.xml files found under %s" % xml_dir)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    tmp_path = out_path + ".tmp"
    for stale in (out_path, out_path + "-wal", out_path + "-shm", tmp_path):
        try:
            if os.path.exists(stale):
                os.remove(stale)
        except OSError as exc:
            raise SystemExit("Cannot replace %s: %s" % (stale, exc))

    conn = sqlite3.connect(tmp_path)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.executescript(DDL)

    counts = {}
    total = 0
    started = _dt.datetime.now(_dt.timezone.utc).astimezone()
    batch = []
    try:
        for path in files:
            assembly = os.path.splitext(os.path.basename(path))[0]
            count = 0
            for member_el in iter_members(path):
                batch.append(extract_record(assembly, member_el))
                count += 1
                if len(batch) >= 2000:
                    conn.executemany(INSERT_SQL, batch)
                    batch.clear()
            if batch:
                conn.executemany(INSERT_SQL, batch)
                batch.clear()
            counts[assembly] = count
            total += count

        # FTS5 index over the canonical table (columns mirror member.*)
        conn.executescript(FTS_DDL)
        conn.execute("INSERT INTO fts(fts) VALUES('rebuild')")
        conn.execute("INSERT INTO fts(fts) VALUES('optimize')")

        known_kinds = {}
        for kind, cnt in conn.execute(
            "SELECT kind, count(*) FROM member GROUP BY kind"
        ):
            known_kinds[kind] = cnt

        meta = {
            "schema_version": SCHEMA_VERSION,
            "eplan_version": version,
            "built_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "source_dir": os.path.abspath(xml_dir),
            "member_count": str(total),
            "kind_counts": ",".join(
                "%s=%s" % (k, known_kinds.get(k, 0)) for k in KINDS
            ),
        }
        for asm, cnt in sorted(counts.items()):
            meta["assembly_count:" + asm] = str(cnt)
        conn.executemany(
            "INSERT INTO meta(key, value) VALUES(?, ?)", sorted(meta.items())
        )
        conn.commit()
    finally:
        conn.close()

    os.replace(tmp_path, out_path)
    return {
        "counts": counts,
        "total": total,
        "kind_counts": known_kinds,
        "built_at": meta["built_at"],
        "elapsed": (_dt.datetime.now(_dt.timezone.utc).astimezone() - started),
        "out": out_path,
    }


def main(argv=None) -> int:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_out = os.path.normpath(os.path.join(script_dir, "..", "data", "eplan2025.sqlite"))
    parser = argparse.ArgumentParser(
        description="Build the offline EPLAN P8 2025 .NET API index (SQLite)."
    )
    parser.add_argument(
        "--xml-dir",
        default=r"C:\Program Files\EPLAN\Platform\2025.0.3\Bin",
        help="Directory holding Eplan.EplApi.*u.xml (default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        default=default_out,
        help="Output SQLite database (default: %(default)s)",
    )
    parser.add_argument("--version", default="2025.0.3", help="EPLAN version label")
    args = parser.parse_args(argv)

    result = build(args.xml_dir, args.out, args.version)
    for assembly, count in sorted(result["counts"].items()):
        print("%-40s %7d" % (assembly, count))
    print("%-40s %7d" % ("TOTAL", result["total"]))
    if not os.path.isfile(args.out):
        print("ERROR: database was not written: %s" % args.out, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
