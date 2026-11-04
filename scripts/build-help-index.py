#!/usr/bin/env python3
"""Build a local, searchable index of EPLAN documentation help pages.

Two crawl modes:

  api   -- crawl the official EPLAN API reference for one version
           (seeds: <base>/<version>/webindex.html, then follows namespace,
           type and "_members" pages to discover every member page).
  guide -- crawl the EPLAN platform user guide (dialogs, commands, message
           texts, concepts) from Plattform/<version>/sitemap.xml.
  bfs   -- crawl an arbitrary help set by breadth-first following links
           that stay inside one URL prefix.
  sitemap -- crawl every HTML page of a sitemap.xml inside one URL prefix
           (used for EEC Pro, whose Flare pages link nothing).

The result is a SQLite database with a ``page`` table and an FTS5 index that
``server/docs/server.py`` serves over MCP. The crawl is resumable: pages that
were already fetched (status 200) are not requested again, and 404s are
remembered so a rerun does not hammer the server.

Usage:
    python scripts/build-help-index.py api --version 2026 \
        --out data/eplan2026-help.sqlite --workers 12
    python scripts/build-help-index.py bfs --seed URL --prefix URL \
        --out data/eecpro-help.sqlite --workers 8
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser

USER_AGENT = "DSH_Eplan-docs-builder/1.0 (personal offline documentation index)"
DEFAULT_BASE = "https://www.eplan.help/en-us/Infoportal/Content/api"
# The platform (user guide / dialog reference) help set, not the API reference.
GUIDE_BASE = "https://www.eplan.help/en-us/Infoportal/Content/Plattform"

SCHEMA = """
CREATE TABLE IF NOT EXISTS page (
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,
    url         TEXT NOT NULL,
    title       TEXT,
    breadcrumb  TEXT,
    kind        TEXT,
    assembly    TEXT,
    type_name   TEXT,
    member_name TEXT,
    body        TEXT,
    status      INTEGER,
    fetched_at  TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
    title, body,
    content='page', content_rowid='id'
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TRIGGER IF NOT EXISTS page_ai AFTER INSERT ON page BEGIN
    INSERT INTO fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
CREATE TRIGGER IF NOT EXISTS page_ad AFTER DELETE ON page BEGIN
    INSERT INTO fts(fts, rowid, title, body) VALUES ('delete', old.id, old.title, old.body);
END;
CREATE TRIGGER IF NOT EXISTS page_au AFTER UPDATE ON page BEGIN
    INSERT INTO fts(fts, rowid, title, body) VALUES ('delete', old.id, old.title, old.body);
    INSERT INTO fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
"""


# --------------------------------------------------------------------------- #
# HTML -> text
# --------------------------------------------------------------------------- #
BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "h1", "h2", "h3", "h4",
    "h5", "h6", "section", "pre", "dt", "dd", "dl", "thead", "tbody", "thead",
}
SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "svg"}


class _PageParser(HTMLParser):
    """Extract <title>, the i-body-content div (or <body>), and page links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.main_parts: list[str] = []
        self.fallback_parts: list[str] = []
        self.body_depth = 0
        self.in_body = False
        self.skip_depth = 0
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "body":
            self.in_body = True
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if tag == "div":
            if self.body_depth:
                self.body_depth += 1
            elif attrs.get("id") in ("i-body-content", "mainbody"):
                self.body_depth = 1
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in BLOCK_TAGS and not self.skip_depth:
            if self.body_depth:
                self.main_parts.append("\n")
            if self.in_body:
                self.fallback_parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag == "body":
            self.in_body = False
        if tag == "div" and self.body_depth:
            self.body_depth -= 1
            if self.body_depth == 0:
                self.main_parts.append("\n")
        if tag in BLOCK_TAGS and not self.skip_depth:
            if self.body_depth:
                self.main_parts.append("\n")
            if self.in_body:
                self.fallback_parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        elif not self.skip_depth:
            if self.body_depth:
                self.main_parts.append(data)
            if self.in_body:
                self.fallback_parts.append(data)


def clean_text(parts: list[str]) -> str:
    text = html.unescape("".join(parts))
    text = text.replace("\xa0", " ")
    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def parse_page(raw: str) -> tuple[str, str, list[str]]:
    parser = _PageParser()
    parser.feed(raw)
    parser.close()
    title = re.sub(r"\s+", " ", "".join(parser.title_parts)).strip()
    body = clean_text(parser.main_parts) or clean_text(parser.fallback_parts)
    return title, body, parser.links


# --------------------------------------------------------------------------- #
# URL classification
# --------------------------------------------------------------------------- #
def classify(path: str) -> dict[str, str]:
    path = path.rsplit("/", 1)[-1]
    stem, _ext = os.path.splitext(path)
    parts = stem.split("~")
    if len(parts) == 1:
        return {"kind": "topic"}
    assembly = parts[0]
    if len(parts) == 2:
        name = parts[1]
        if name.endswith("_namespace"):
            return {"kind": "namespace", "assembly": assembly, "type_name": name[:-10]}
        if name.endswith("_members"):
            return {"kind": "members", "assembly": assembly, "type_name": name[:-8]}
        return {"kind": "type", "assembly": assembly, "type_name": name}
    if len(parts) >= 3:
        return {
            "kind": "member",
            "assembly": assembly,
            "type_name": parts[1],
            "member_name": "~".join(parts[2:]),
        }
    return {"kind": "topic"}


def breadcrumb_of(meta: dict[str, str]) -> str:
    parts = [meta.get("assembly", ""), meta.get("type_name", "")]
    if meta.get("member_name"):
        parts.append(meta["member_name"])
    return " / ".join(p for p in parts if p)


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
def fetch(url: str, timeout: float = 30.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.status, resp.read().decode(charset, "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception:  # timeouts, TLS, DNS
        return 0, ""


def fetch_with_retry(url: str, attempts: int = 3) -> tuple[int, str]:
    status, raw = 0, ""
    for attempt in range(attempts):
        status, raw = fetch(url)
        if status == 200 or status == 404:
            return status, raw
        time.sleep(0.8 * (attempt + 1))
    return status, raw


# --------------------------------------------------------------------------- #
# Crawl driver
# --------------------------------------------------------------------------- #
def load_seeds(webindex_url: str) -> list[str]:
    """webindex.html lists every indexed help page for this version."""
    status, raw = fetch_with_retry(webindex_url)
    if status != 200:
        raise SystemExit(f"cannot fetch {webindex_url}: status {status}")
    _, _, links = parse_page(raw)
    seeds = sorted({abs_url(webindex_url, h) for h in links if is_help_html(h)})
    print(f"webindex: {len(seeds)} seed pages from {webindex_url}")
    return seeds


def load_sitemap(sitemap_source: str, include_prefix: str, flatten_prefix: str = "") -> list[str]:
    """sitemap.xml lists every published asset; keep the HTML pages we want.

    ``sitemap_source`` is a URL or a local file. When ``flatten_prefix`` is
    given, every HTML entry is re-pointed at that directory by file name
    instead of keeping its own path — the published sitemaps are copied
    between help versions (the 2025 sitemap still lists Plattform/2023
    paths, the 2027 one uses different casing), so the version directory
    cannot be trusted to match the sitemap that lists it.
    """
    if os.path.exists(sitemap_source):
        with open(sitemap_source, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        status = 200
    else:
        status, raw = fetch_with_retry(sitemap_source)
    if status != 200:
        raise SystemExit(f"cannot read {sitemap_source}: status {status}")
    locs = re.findall(r"(?is)<loc>\s*([^<\s]+)\s*</loc>", raw)
    locs = [loc.strip() for loc in locs
            if loc.lower().split("?")[0].endswith((".html", ".htm"))]
    if flatten_prefix:
        seeds = sorted({flatten_prefix + loc.rsplit("/", 1)[-1] for loc in locs})
    else:
        seeds = sorted({loc for loc in locs if loc.startswith(include_prefix)})
    print(f"sitemap {sitemap_source}: {len(locs)} HTML entries, {len(seeds)} seeds for {include_prefix}")
    return seeds


def is_help_html(href: str) -> bool:
    if href.startswith(("http://", "https://", "mailto:", "javascript:", "#")):
        return False
    return href.lower().split("?")[0].endswith((".html", ".htm"))


def abs_url(base_url: str, href: str) -> str:
    url = urllib.parse.urljoin(base_url, href)
    return url.split("#")[0]


def url_path(url: str) -> str:
    return urllib.parse.unquote(urllib.parse.urlparse(url).path)


def record_page(db: sqlite3.Connection, url: str, status: int, raw: str) -> list[str]:
    path = url_path(url)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if status != 200:
        db.execute(
            """INSERT INTO page (path,url,status,fetched_at) VALUES (?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET status=excluded.status, fetched_at=excluded.fetched_at""",
            (path, url, status, stamp),
        )
        return []
    title, body, links = parse_page(raw)
    if not title:
        title = path.rsplit("/", 1)[-1][:-5]
    meta = classify(path)
    db.execute(
        """INSERT INTO page (path,url,title,breadcrumb,kind,assembly,type_name,member_name,body,status,fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(path) DO UPDATE SET title=excluded.title, body=excluded.body,
             status=excluded.status, fetched_at=excluded.fetched_at""",
        (path, url, title, breadcrumb_of(meta), meta["kind"],
         meta.get("assembly"), meta.get("type_name"), meta.get("member_name"),
         body[:80000], status, stamp),
    )
    return links


def crawl(
    db: sqlite3.Connection,
    start_url: str,
    seeds: list[str],
    workers: int,
    include_prefix: str,
    limit: int,
    follow_depth: int,
    follow_kinds: set[str] | None,
) -> None:
    existing = {row[0] for row in db.execute("SELECT path FROM page WHERE status=200")}
    queue: list[str] = []
    queued: set[str] = set()
    depth: dict[str, int] = {}
    for seed in seeds:
        if url_path(seed) in existing:
            continue
        queue.append(seed)
        queued.add(url_path(seed))
        depth[url_path(seed)] = 0
    done = 0
    started = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while queue and (limit <= 0 or done < limit):
            batch = queue[: workers * 4]
            queue = queue[workers * 4:]
            futures = {pool.submit(fetch_with_retry, href): href for href in batch}
            for fut in as_completed(futures):
                url = futures[fut]
                status, raw = fut.result()
                links = record_page(db, url, status, raw)
                done += 1
                for link in links:
                    if not is_help_html(link):
                        continue
                    target = abs_url(url, link)
                    path = url_path(target)
                    if path in queued or path in existing:
                        continue
                    if not target.startswith(include_prefix):
                        continue
                    kind = classify(path)["kind"]
                    if follow_kinds is not None and kind not in follow_kinds:
                        continue
                    d = depth.get(url_path(url), 0) + 1
                    if follow_depth >= 0 and d > follow_depth:
                        continue
                    queue.append(target)
                    queued.add(path)
                    depth[path] = d
                if done % 200 == 0:
                    db.commit()
                    rate = done / max(time.time() - started, 0.01)
                    print(f"  {done} pages, {rate:.1f}/s, queue {len(queue)}", flush=True)
            db.commit()
    rate = done / max(time.time() - started, 0.01)
    print(f"fetched {done} pages in {time.time() - started:.0f}s ({rate:.1f}/s)")


def build_fts(db: sqlite3.Connection) -> None:
    """Rebuild FTS from the page table, then fold the WAL back into the main file.

    The documentation servers open the database read-only; a read-only connection
    cannot create the -shm file a WAL needs, so anything still sitting in the WAL
    would be invisible to them (page rows visible, search results missing).
    """
    db.execute("INSERT INTO fts(fts) VALUES('rebuild')")
    db.commit()
    try:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        pass
    db.commit()


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)

    api = sub.add_parser("api", help="crawl an EPLAN API reference version")
    api.add_argument("--version", required=True, choices=["2025", "2026", "2027"])
    api.add_argument("--base", default=DEFAULT_BASE)
    api.add_argument("--out", required=True)

    bfs = sub.add_parser("bfs", help="crawl a help set by breadth-first link following")
    bfs.add_argument("--seed", required=True, help="absolute URL of the first page")
    bfs.add_argument("--prefix", required=True, help="only follow links under this URL prefix")
    bfs.add_argument("--out", required=True)

    sm = sub.add_parser("sitemap", help="crawl every HTML page listed in a sitemap.xml")
    sm.add_argument("--sitemap", required=True, help="absolute URL of sitemap.xml, or a local file")
    sm.add_argument("--prefix", required=True, help="only fetch sitemap URLs under this prefix")
    sm.add_argument("--out", required=True)

    gd = sub.add_parser("guide", help="crawl the EPLAN platform user guide (Plattform/<year>)")
    gd.add_argument("--version", required=True, choices=["2025", "2026", "2027"])
    gd.add_argument("--sitemap", default="",
                    help="sitemap.xml URL or local file (default: the version's own sitemap)")
    gd.add_argument("--out", required=True)

    rx = sub.add_parser("reindex", help="rebuild the FTS index of an existing database (no network)")
    rx.add_argument("--out", required=True, help="existing database file")

    for p in (api, bfs, sm, gd):
        p.add_argument("--workers", type=int, default=12)
        p.add_argument("--limit", type=int, default=0, help="stop after N pages (0 = all)")
        p.add_argument("--follow-depth", type=int, default=3, help="-1 = unlimited")

    args = ap.parse_args()

    # The output usually lives in <bundle>/data, which a fresh checkout may lack.
    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    if args.mode == "reindex":
        db = sqlite3.connect(args.out)
        db.executescript(SCHEMA)  # adds the FTS sync triggers to older databases
        build_fts(db)
        pages = db.execute("SELECT COUNT(*) FROM page WHERE status=200").fetchone()[0]
        hits = db.execute("SELECT COUNT(*) FROM fts WHERE fts MATCH '\"eplan\"'").fetchone()[0]
        print(f"reindexed {args.out}: {pages} pages, {hits} pages match 'eplan'")
        return 0

    db = sqlite3.connect(args.out)
    db.executescript(SCHEMA)
    db.execute("PRAGMA journal_mode=WAL")

    if args.mode == "api":
        base_url = f"{args.base}/{args.version}/"
        db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('version',?)", (args.version,))
        db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('source',?)", (base_url,))
        seeds = load_seeds(f"{base_url}webindex.html")
        crawl(db, base_url, seeds, args.workers, base_url, args.limit, -1,
              {"namespace", "type", "members", "member"})
    elif args.mode == "bfs":
        base_url = args.seed
        db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('source',?)", (args.seed,))
        crawl(db, base_url, [args.seed], args.workers, args.prefix, args.limit,
              args.follow_depth, None)
    elif args.mode == "guide":
        base_url = f"{GUIDE_BASE}/{args.version}/"
        prefix = f"{base_url}Content/htm/"
        db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('version',?)", (args.version,))
        # The 2026/2027 databases already hold the API crawl; keep both sources visible.
        prev = db.execute("SELECT value FROM meta WHERE key='source'").fetchone()
        sources = [prefix]
        if prev and prev[0] and prefix not in prev[0]:
            sources.insert(0, prev[0])
        db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('source',?)", (" | ".join(sources),))
        sitemap = args.sitemap or f"{base_url}sitemap.xml"
        seeds = load_sitemap(sitemap, prefix, flatten_prefix=prefix)
        crawl(db, prefix, seeds, args.workers, prefix, args.limit, 0, set())
    else:
        db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('source',?)", (args.sitemap,))
        seeds = load_sitemap(args.sitemap, args.prefix)
        crawl(db, args.sitemap, seeds, args.workers, args.prefix, args.limit, 0, set())

    db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('built_at',?)",
               (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
    counts = dict(db.execute("SELECT kind, COUNT(*) FROM page WHERE status=200 GROUP BY kind").fetchall())
    db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('counts',?)",
               (", ".join(f"{k}={v}" for k, v in sorted(counts.items())),))
    print("pages by kind:", counts)
    build_fts(db)
    db.commit()
    print(f"index ready: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
