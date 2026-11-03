#!/usr/bin/env python3
"""Mirror https://mlir.llvm.org/docs/ (and every sub-page) for offline use.

What it does
------------
1. Seeds the crawl from https://mlir.llvm.org/sitemap.xml (every /docs/ page)
   plus the documentation index, then follows every in-scope link
   (/docs/...) breadth-first, so no sub-page is missed.
2. Saves every page as  site/<url-path>/index.html  and downloads the page
   requisites (theme CSS, JS, images, CDN libraries) into  site/css ,
   site/js , site/_external/<host>/... .
3. Rewrites absolute links to relative local paths, so the mirror can be
   browsed straight from disk (file://) without a web server.
4. Also writes a clean Markdown copy of every page ( markdown/  plus
   ALL_DOCS.md ) which is handy for feeding an LLM or building a RAG index.

Usage
-----
    python3 crawl_mlir_docs.py                 # full crawl, HTML + Markdown
    python3 crawl_mlir_docs.py --max-pages 5   # small smoke test
    python3 crawl_mlir_docs.py --no-markdown   # HTML mirror only
"""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import requests

SITE = "https://mlir.llvm.org"
HOST = urlsplit(SITE).netloc
SCOPE = "/docs/"          # only this URL prefix is mirrored as "documentation"
UA = "Mozilla/5.0 (compatible; mlir-docs-offline-mirror/1.0)"

ASSET_EXT = {
    ".css", ".js", ".mjs", ".json", ".xml", ".txt", ".map", ".webmanifest",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".mp4", ".webm", ".wasm", ".zip",
}

# <script>/<style> bodies hold JS templates, not links: never look inside them.
RAW_BODY_RE = re.compile(r"(<(script|style)\b[^>]*>)(.*?)(</\2\s*>)", re.S | re.I)
# only attributes that really sit inside a tag may be rewritten; body text
# (code samples, prose that happens to contain `src="..."`) must stay untouched
TAG_RE = re.compile(r"<[a-zA-Z][^>]*>", re.S)

# attributes that can point somewhere; values may be unquoted (Hugo emits that)
ATTR_RE = re.compile(
    r'(?P<pre>\b(?:href|src|poster|data-src)\s*=\s*)(?P<q>["\']?)(?P<val>[^"\'\s>]*)(?P=q)',
    re.I,
)
CSS_URL_RE = re.compile(r'url\(\s*(["\']?)([^)"\']+)\1\s*\)', re.I)
SKIP_PREFIXES = ("#", "mailto:", "javascript:", "data:", "tel:", "irc:", "ftp:")


# --------------------------------------------------------------------------- #
# small URL / path helpers
# --------------------------------------------------------------------------- #
def clean_path(path: str) -> str:
    """Normalise a URL path: unquote, collapse duplicate slashes."""
    path = unquote(path or "/")
    path = re.sub(r"/{2,}", "/", path)
    return path or "/"


def has_asset_ext(path: str) -> bool:
    return posixpath.splitext(path)[1].lower() in ASSET_EXT


def norm_url(url: str) -> str:
    """Canonical form used as dictionary key (no fragment)."""
    parts = urlsplit(url)
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), clean_path(parts.path), parts.query, "")
    )


def split_fragment(url: str) -> tuple[str, str]:
    if "#" in url:
        base, frag = url.split("#", 1)
        return base, "#" + frag
    return url, ""


def site_rel_path(url: str) -> str:
    """Map an absolute URL to its file path, relative to the site/ directory.

    Path segments are normalised (no `.`/`..`), sanitised for Windows, and the
    result is always relative -- so a hostile link cannot escape the mirror.
    """
    parts = urlsplit(url)
    path = clean_path(parts.path)
    if path.endswith("/") or not posixpath.splitext(path)[1]:
        path = path.rstrip("/") + "/index.html"
    safe = safe_path(path)
    if not safe:
        raise ValueError(f"无法映射为安全路径：{url}")
    if parts.netloc and parts.netloc.lower() != HOST:
        return posixpath.join("_external", safe_host(parts.netloc), safe)
    return safe


WINDOWS_ILLEGAL = re.compile(r'[:*?"<>|\x00-\x1f]')
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL",
                  *(f"COM{i}" for i in range(1, 10)),
                  *(f"LPT{i}" for i in range(1, 10))}


def safe_segment(segment: str) -> str:
    """Strip characters Windows cannot store in a file name."""
    segment = WINDOWS_ILLEGAL.sub("_", segment).rstrip(". ")
    if segment.upper().split(".")[0] in RESERVED_NAMES:
        segment = "_" + segment
    return segment or "_"


def safe_path(path: str) -> str:
    """``clean_path`` + drop `.`/`..` + Windows-safe segments ('' if it escapes)."""
    parts: list[str] = []
    for part in clean_path(path).split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return ""            # 试图跳出根目录
            parts.pop()
            continue
        parts.append(safe_segment(part))
    return "/".join(parts)


def safe_host(netloc: str) -> str:
    """``host:port`` -> ``host_port``; Windows cannot store ':' in a file name."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", netloc.lower())


def write_bytes(root: Path, rel: str, data: bytes) -> None:
    """Write atomically, and refuse to escape the output directory."""
    if not rel:
        raise ValueError("空的输出路径")
    base = root.resolve()
    target = (root / rel).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"拒绝写到输出目录之外：{rel}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".part")
    temp.write_bytes(data)
    temp.replace(target)          # 原子替换：中断时不会留下半截文件


def write_text(root: Path, rel: str, text: str) -> None:
    write_bytes(root, rel, text.encode("utf-8"))


def fetch(session: requests.Session, url: str, retries: int = 3, timeout: int = 30):
    """GET with retries. Returns a Response or None."""
    for attempt in range(retries):
        try:
            return session.get(url, timeout=timeout, allow_redirects=True)
        except requests.RequestException as exc:  # noqa: PERF203
            if attempt == retries - 1:
                print(f"  ! request failed {url}: {exc}", file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def iter_attr_values(html: str):
    """Yield attribute values that sit inside a real HTML tag.

    Text nodes are ignored on purpose: documentation code samples such as
    ``<code>src="{}"</code>`` must never be mistaken for links.
    """
    for tag_match in TAG_RE.finditer(html):
        for attr_match in ATTR_RE.finditer(tag_match.group(0)):
            value = attr_match.group("val")
            if value:
                yield value


def blank_inline_bodies(html: str) -> str:
    """Drop <script>/<style> bodies (keeping the opening tags) so JS templates
    are not mistaken for links."""
    return RAW_BODY_RE.sub(lambda m: m.group(1) + m.group(4), html)


# URL -> local path (relative to site/); filled in while crawling
URL_MAP: dict[str, str] = {}


def register_url(url: str, local: str) -> None:
    """Remember that `url` lives at `local`, with and without trailing slash/query."""
    key = norm_url(url)
    local = posixpath.normpath(local)
    URL_MAP[key] = local
    URL_MAP[key.rstrip("/")] = local
    URL_MAP[key.split("?")[0]] = local
    URL_MAP[key.split("?")[0].rstrip("/")] = local


def resolve_local(url: str) -> str | None:
    """Local path for an absolute URL, or None when it was not mirrored."""
    key = norm_url(split_fragment(url)[0])
    if key in URL_MAP:
        return URL_MAP[key]
    key = key.rstrip("/")
    if key in URL_MAP:
        return URL_MAP[key]
    return None


def rel_link(target_local: str, from_local: str) -> str:
    """Relative link from the file `from_local` to the file `target_local`."""
    start = posixpath.dirname(from_local) or "."
    return posixpath.relpath(target_local, start)


# --------------------------------------------------------------------------- #
# 1) crawl the documentation pages
# --------------------------------------------------------------------------- #
def seed_urls(session: requests.Session) -> list[str]:
    """All /docs/ URLs known up-front: the index + everything in sitemap.xml."""
    seeds = [SITE + SCOPE]
    resp = fetch(session, SITE + "/sitemap.xml")
    if resp is not None and resp.ok:
        for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", resp.text):
            if urlsplit(loc).path.startswith(SCOPE):
                seeds.append(loc)
        print(f"[crawl] sitemap lists {len(seeds) - 1} /docs/ pages")
    else:
        print("[crawl] sitemap unavailable - discovering pages through links only")
    return list(dict.fromkeys(seeds))


def crawl_pages(session: requests.Session, args):
    """Breadth-first crawl of SCOPE. Returns (pages, assets, report)."""
    queue: deque[str] = deque(seed_urls(session))
    queued: set[str] = set(queue)
    pages: list[dict] = []
    assets: dict[str, str] = {}
    report: list[tuple[str, str, str]] = []
    done: set[str] = set()

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        while queue:
            batch = [queue.popleft() for _ in range(min(args.batch, len(queue)))]
            results = list(pool.map(lambda u: (u, fetch(session, u)), batch))
            for url, resp in results:
                if resp is None:
                    report.append(("NETWORK-ERROR", url, ""))
                    continue
                if not resp.ok:
                    report.append((f"HTTP {resp.status_code}", url, ""))
                    continue
                final = resp.url
                ctype = resp.headers.get("content-type", "")
                local = site_rel_path(final)
                if "html" not in ctype.lower():
                    # e.g. an index.xml picked up inside the docs tree
                    if local not in done:
                        done.add(local)
                        write_bytes(args.out, local, resp.content)
                        register_url(final, local)
                    assets.setdefault(norm_url(final), local)
                    report.append((f"OK ({ctype.split(';')[0]})", final, local))
                    continue
                if local in done:
                    register_url(final, local)
                    continue
                if args.max_pages and len(pages) >= args.max_pages:
                    continue            # 本批次多抓到的页面直接丢弃，严格守住上限
                done.add(local)
                register_url(final, local)
                html = resp.text
                pages.append({"url": final, "local": local, "html": html,
                              "title": page_title(html)})
                report.append(("OK", final, local))
                print(f"  [{len(pages):3d}] {final}")
                # ---- discover links on this page ----
                for value in iter_attr_values(blank_inline_bodies(html)):
                    if value.lower().startswith(SKIP_PREFIXES):
                        continue
                    absolute = urljoin(final, value)
                    parts = urlsplit(absolute)
                    if parts.scheme not in ("http", "https"):
                        continue
                    target = absolute.split("#")[0]
                    if not target:
                        continue
                    path = clean_path(parts.path)
                    same_host = parts.netloc.lower() == HOST
                    if same_host and path.startswith(SCOPE) and not has_asset_ext(path):
                        key = norm_url(target)
                        if key in queued:
                            continue
                        if args.max_pages and len(pages) >= args.max_pages:
                            continue
                        queued.add(key)
                        queue.append(target)
                    elif has_asset_ext(path):
                        assets.setdefault(norm_url(target), site_rel_path(target))
                    # else: other parts of the site (/getting_started/, /doxygen/)
                    # stay as absolute online URLs
    return pages, assets, report


def page_title(html: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


# --------------------------------------------------------------------------- #
# 2) download assets (css / js / images / fonts, incl. CDN copies)
# --------------------------------------------------------------------------- #
def download_assets(session: requests.Session, args, assets: dict[str, str]):
    """Fetch every asset; CSS files may reference more assets (fonts / images)."""
    report: list[tuple[str, str, str]] = []
    pending: deque[str] = deque(sorted(assets))
    seen: set[str] = set(pending)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        while pending:
            batch = [pending.popleft() for _ in range(min(args.batch, len(pending)))]
            to_fetch: list[str] = []
            for url in batch:
                local = assets.get(url) or site_rel_path(url)
                existing = args.out / local
                if existing.is_file() and existing.stat().st_size > 0:
                    # already mirrored by an earlier run - keep it (fast refresh)
                    register_url(url, local)
                    report.append(("OK-asset(cached)", url, local))
                    continue
                to_fetch.append(url)
            if not to_fetch:
                continue
            for url, resp in pool.map(lambda u: (u, fetch(session, u)), to_fetch):
                local = assets.get(url) or site_rel_path(url)
                if resp is None or not resp.ok:
                    status = "NETWORK-ERROR" if resp is None else f"HTTP {resp.status_code}"
                    report.append((status, url, local))
                    continue
                register_url(resp.url or url, local)
                ctype = resp.headers.get("content-type", "").lower()
                is_css = url.split("?")[0].lower().endswith(".css") or "text/css" in ctype
                if is_css:
                    data = rewrite_css(resp.text, resp.url or url, local,
                                       assets, pending, seen)
                    write_bytes(args.out, local, data.encode("utf-8"))
                else:
                    write_bytes(args.out, local, resp.content)
                report.append(("OK-asset", url, local))
    return report


def rewrite_css(css: str, css_url: str, css_local: str, assets: dict[str, str],
                pending: deque[str], seen: set[str]) -> str:
    """Point url(...) references inside a stylesheet at local copies."""

    def replace(match: re.Match) -> str:
        ref = match.group(2).strip()
        if ref.lower().startswith(("data:", "about:")):
            return match.group(0)
        absolute = urljoin(css_url, ref)
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            return match.group(0)
        target = norm_url(absolute)
        ext = posixpath.splitext(parts.path)[1].lower()
        if ext not in ASSET_EXT and ext not in (".woff", ".woff2", ".ttf", ".svg"):
            return match.group(0)
        local = assets.setdefault(target, site_rel_path(absolute))
        register_url(absolute, local)
        if target not in seen:
            seen.add(target)
            pending.append(target)
        return f'url("{rel_link(local, css_local)}")'

    return CSS_URL_RE.sub(replace, css)


# --------------------------------------------------------------------------- #
# 3) rewrite the mirrored HTML so everything works from file://
# --------------------------------------------------------------------------- #
def rewrite_html(html: str, page_url: str, page_local: str) -> str:
    """Turn absolute / site-rooted links into relative links to local files."""

    def replace(match: re.Match) -> str:
        value = match.group("val")
        if not value or value.lower().startswith(SKIP_PREFIXES):
            return match.group(0)
        absolute = urljoin(page_url, value)
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            return match.group(0)
        target, fragment = split_fragment(absolute)
        local = resolve_local(target)
        if local is not None:
            new_value = rel_link(local, page_local) + fragment
        elif parts.netloc.lower() == HOST:
            # not mirrored -> keep a working absolute link to the live site
            query = f"?{parts.query}" if parts.query else ""
            new_value = f"{SITE}{clean_path(parts.path)}{query}{fragment}"
        else:
            new_value = absolute
        return f'{match.group("pre")}"{new_value}"'

    def fix_tag(match: re.Match) -> str:
        return ATTR_RE.sub(replace, match.group(0))

    def fix_chunk(chunk: str) -> str:
        return TAG_RE.sub(fix_tag, chunk)

    # leave <script>/<style> bodies untouched, rewrite only real tag attributes
    out: list[str] = []
    pos = 0
    for match in RAW_BODY_RE.finditer(html):
        out.append(fix_chunk(html[pos:match.start()]))
        out.append(match.group(0))
        pos = match.end()
    out.append(fix_chunk(html[pos:]))
    return "".join(out)


# --------------------------------------------------------------------------- #
# 4) HTML -> Markdown (no third-party dependencies)
# --------------------------------------------------------------------------- #
SKIP_TAGS = {"script", "style", "nav", "footer", "svg", "button", "form", "noscript"}
BLOCK_TAGS = {"p", "div", "section", "article", "main", "header", "details", "summary",
              "figure", "figcaption", "dl", "dt", "dd", "center"}
PERMALINK_LABELS = {"¶", "#", "§", "🔗", "permalink"}


class MarkdownConverter(HTMLParser):
    """Very small HTML -> Markdown converter tuned for the Hugo/MLIR docs."""

    def __init__(self, link_mapper=None):
        super().__init__(convert_charrefs=True)
        self.buf: list[str] = []
        self.cur: list[str] = []
        self.stack: list[tuple[str, str, str, list[str]]] = []
        self.skip = 0
        self.pre = 0
        self.pre_buf: list[str] = []
        self.pre_lang = ""
        self.lists: list[list] = []      # ['ul'|'ol', counter]
        self.table: list[list[str]] | None = None
        self.map_link = link_mapper or (lambda href: href)

    # ---------- helpers ----------
    def flush(self, sep: str = "\n\n") -> None:
        if sep == "\n\n" and self.lists:
            sep = "\n"          # no blank lines inside a list item
        text = "".join(self.cur)
        self.cur = []
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        if text.strip():
            self.buf.append(text.strip("\n"))
            self.buf.append(sep)

    def emit(self, text: str) -> None:
        self.cur.append(text)

    def block_break(self) -> None:
        """Guarantee a blank line before a fenced code block / table."""
        tail = "".join(self.buf[-2:])
        if self.buf and not tail.endswith("\n\n"):
            self.buf.append("\n")

    # ---------- parser callbacks ----------
    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag in SKIP_TAGS:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "pre":
            self.flush()
            self.pre = 1
            self.pre_buf = []
            self.pre_lang = ""
            self._detect_lang(attr.get("class") or "")
            return
        if self.pre:
            if tag == "code":
                self._detect_lang(attr.get("class") or "")
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.flush()
            self.emit("#" * int(tag[1]) + " ")
            return
        if tag in ("ul", "ol"):
            self.flush("\n")
            self.lists.append([tag, 0])
            return
        if tag == "li":
            self.flush("\n")
            indent = "  " * max(0, len(self.lists) - 1)
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                self.emit(f"{indent}{self.lists[-1][1]}. ")
            else:
                self.emit(f"{indent}- ")
            return
        if tag == "br":
            self.emit("\n")
            return
        if tag == "hr":
            self.flush()
            self.buf.append("---\n\n")
            return
        if tag == "table":
            self.flush()
            self.table = []
            return
        if tag == "tr" and self.table is not None:
            self.table.append([])
            return
        if tag in ("td", "th") and self.table is not None:
            self.stack.append(("cell", tag, "", self.cur))
            self.cur = []
            return
        if tag == "blockquote":
            self.flush()
            self.emit("> ")
            return
        if tag in BLOCK_TAGS:
            if not self.lists:      # keep "- item" on one line
                self.flush()
            return
        if tag in ("strong", "b"):
            self.stack.append(("bold", tag, "", self.cur))
            self.cur = []
            return
        if tag in ("em", "i"):
            self.stack.append(("italic", tag, "", self.cur))
            self.cur = []
            return
        if tag == "code":
            self.stack.append(("code", tag, "", self.cur))
            self.cur = []
            return
        if tag == "a":
            self.stack.append(("link", tag, attr.get("href") or "", self.cur))
            self.cur = []
            return
        if tag == "img":
            src = attr.get("src") or ""
            alt = attr.get("alt") or ""
            if src:
                self.emit(f"![{alt}]({self.map_link(src)})")
            return

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            if self.skip:
                self.skip -= 1
            return
        if self.skip:
            return
        if tag == "pre":
            self.pre = 0
            code = "".join(self.pre_buf).strip("\n")
            self.flush()
            self.block_break()
            self.buf.append(f"```{self.pre_lang}\n{code}\n```\n\n")
            return
        if self.pre:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.flush()
            return
        if tag in ("ul", "ol"):
            self.flush("\n")
            if self.lists:
                self.lists.pop()
            return
        if tag == "li":
            self.flush("\n")
            return
        if tag in ("td", "th") and self.table is not None:
            if self.stack and self.stack[-1][0] == "cell":
                _, _, _, saved = self.stack.pop()
                cell = re.sub(r"\s+", " ", "".join(self.cur)).strip()
                self.cur = saved
                self.table[-1].append(cell)
            return
        if tag == "table":
            self._emit_table()
            self.flush()
            self.table = None
            return
        if tag == "blockquote":
            self.flush()
            return
        if tag in BLOCK_TAGS:
            if not self.lists:      # keep "- item" on one line
                self.flush()
            return
        if self.stack and self.stack[-1][1] == tag:
            kind, _, data, saved = self.stack.pop()
            text = "".join(self.cur).strip()
            self.cur = saved
            if kind == "link":
                href = self.map_link(data) if data else ""
                label = re.sub(r"\s+", " ", text) or href
                if href.startswith("#") and label in PERMALINK_LABELS:
                    return          # drop heading permalinks such as "[¶](#usage)"
                self.emit(f"[{label}]({href})" if href else label)
            elif kind == "code":
                self.emit(f"`{text}`" if text else "")
            elif kind == "bold":
                self.emit(f"**{text}**" if text else "")
            elif kind == "italic":
                self.emit(f"*{text}*" if text else "")

    def handle_data(self, data):
        if self.skip:
            return
        if self.pre:
            self.pre_buf.append(data)
            return
        self.cur.append(re.sub(r"[ \t\r\n]+", " ", data))

    # ---------- bits ----------
    def _detect_lang(self, css_class: str) -> None:
        if self.pre_lang:
            return
        match = re.search(r"language-([\w+#.-]+)", css_class or "")
        if match:
            self.pre_lang = match.group(1)

    def _emit_table(self) -> None:
        rows = [row for row in (self.table or []) if any(c.strip() for c in row)]
        if not rows:
            return
        ncols = max(len(row) for row in rows)

        def line(row: list[str]) -> str:
            cells = [c.replace("|", "\\|") for c in row]
            cells += [""] * (ncols - len(cells))
            return "| " + " | ".join(cells) + " |"

        out = [line(rows[0]), "|" + "|".join([" --- "] * ncols) + "|"]
        out += [line(row) for row in rows[1:]]
        self.buf.append("\n".join(out) + "\n\n")


def extract_main(html: str) -> str:
    match = re.search(r"<main[^>]*>(.*?)</main>", html, re.S | re.I)
    body = match.group(1) if match else html
    body = re.sub(r"<nav[^>]*>.*?</nav>", "", body, flags=re.S | re.I)
    body = re.sub(r"<footer[^>]*>.*?</footer>", "", body, flags=re.S | re.I)
    body = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.S | re.I)
    return body


def html_to_markdown(html: str, link_mapper=None) -> str:
    converter = MarkdownConverter(link_mapper)
    converter.feed(extract_main(html))
    converter.close()
    converter.flush()
    text = "".join(converter.buf)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


# --------------------------------------------------------------------------- #
# 5) Markdown export (one file per page + everything concatenated)
# --------------------------------------------------------------------------- #
MD_BY_LOCAL: dict[str, str] = {}


def md_rel_path(url: str) -> str:
    """/docs/Bindings/Python/ -> 'Bindings/Python.md', /docs/ -> 'index.md'."""
    path = clean_path(urlsplit(url).path)
    rel = path[len(SCOPE):] if path.startswith(SCOPE) else path.lstrip("/")
    rel = rel.strip("/")
    if rel.endswith(".html"):
        rel = rel[:-5]
    return (rel or "index") + ".md"


def make_link_mapper(page: dict):
    """Map hrefs found in `page` to paths that work inside markdown/."""
    page_url = page["url"]
    page_md = page["md"]

    def mapper(href: str) -> str:
        href = (href or "").strip()
        if not href or href.lower().startswith(SKIP_PREFIXES):
            return href
        absolute = urljoin(page_url, href)
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            return href
        target, fragment = split_fragment(absolute)
        local = resolve_local(target)
        if local is None:
            return absolute          # not mirrored: keep the online URL
        md_target = MD_BY_LOCAL.get(local)
        if md_target:
            start = posixpath.dirname(page_md) or "."
            return posixpath.relpath(md_target, start) + fragment
        start = posixpath.dirname(posixpath.join("markdown", page_md)) or "."
        return posixpath.relpath(posixpath.join("site", local), start) + fragment

    return mapper


def write_markdown(project: Path, pages: list[dict], site_root: str) -> None:
    for page in pages:
        page["md"] = md_rel_path(page["url"])
        MD_BY_LOCAL[page["local"]] = page["md"]

    for page in pages:
        md = html_to_markdown(page["html"], make_link_mapper(page))
        header = f"<!-- source: {page['url']} -->\n"
        write_text(project / "markdown", page["md"], header + "\n" + md)

    # ---- single concatenated file, handy for an LLM / full-text search ----
    ordered = sorted(pages, key=lambda p: (p["md"] != "index.md", p["md"].lower()))
    toc = [
        "# MLIR documentation - offline copy\n",
        f"Source: <{SITE}{SCOPE}>  ",
        f"Pages: {len(pages)}  ",
        f"Mirror: `{site_root}/` (open `{site_root}/docs/index.html`)\n",
        "## Contents\n",
    ]
    for page in ordered:
        title = page["title"].replace(" - MLIR", "") or page["md"]
        toc.append(f"- [{title}](markdown/{page['md']})")
    body = ["\n".join(toc)]
    for page in ordered:
        md = html_to_markdown(page["html"], make_link_mapper(page))
        body.append(f"\n\n<!-- ===== {page['url']} ===== -->\n\n{md}")
    write_text(project, "ALL_DOCS.md", "".join(body))


# --------------------------------------------------------------------------- #
# 6) main
# --------------------------------------------------------------------------- #
def write_report(project: Path, rows: list[tuple[str, str, str]], pages: list[dict]) -> None:
    lines = ["# crawl report", f"# generated {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"# pages mirrored: {len(pages)}", "", "STATUS\tURL\tLOCAL FILE"]
    for status, url, local in rows:
        lines.append(f"{status}\t{url}\t{local}")
    write_text(project, "crawl_report.txt", "\n".join(lines) + "\n")


def write_readme(project: Path, pages: list[dict]) -> None:
    site_size = sum(f.stat().st_size for f in (project / "site").rglob("*") if f.is_file())
    md_size = sum(f.stat().st_size for f in (project / "markdown").rglob("*") if f.is_file())
    write_text(project, "README.md", f"""# MLIR docs - offline copy

Static mirror of <{SITE}{SCOPE}> (the whole documentation tree), generated on
{time.strftime('%Y-%m-%d')} with `crawl_mlir_docs.py`.

| what | where | notes |
| --- | --- | --- |
| browsable HTML mirror | `site/docs/index.html` | {len(pages)} pages, {site_size / 1e6:.1f} MB |
| Markdown, one file per page | `markdown/` | {md_size / 1e6:.1f} MB |
| everything in one file | `ALL_DOCS.md` | good for LLM input / grep |
| per-URL status log | `crawl_report.txt` | |
| bilingual print edition (中英对照) | `print/` | 6 册（vol4 拆三卷）+ 合集，见 `print/README-print.md` |
| 校验与打包脚本 | `tools/` | 11 个脚本，见 `tools/README.md` |

## How to read it

* **Browser**: open `site/docs/index.html` (or `site/index.html`) straight from
  disk - links, sidebar navigation, CSS and code highlighting all work offline
  over `file://`, no web server needed.

  ```bash
  xdg-open site/docs/index.html      # or: firefox site/docs/index.html
  # optional, if you prefer http:
  python3 -m http.server 8000 -d site
  ```

* **Editor / grep / LLM**: use `markdown/` or `ALL_DOCS.md`.

  ```bash
  grep -rn "Bufferization" markdown/ | head
  ```

## Regenerating / updating

```bash
python3 crawl_mlir_docs.py                # full refresh (HTML + Markdown)
python3 crawl_mlir_docs.py --no-markdown  # HTML mirror only
python3 crawl_mlir_docs.py --max-pages 5  # quick smoke test
python3 make_printable.py                 # rebuild print/ (bilingual edition)
```

Only `/docs/**` is mirrored. Links to other parts of the site
(`/getting_started/`, `/doxygen/`, `/python-bindings/`, GitHub, ...) are kept as
absolute URLs pointing at <{SITE}> so they still work while you are online.
To mirror more of the site, widen the scope test in `crawl_pages()`.
""")


def positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return value


def non_negative_int(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("不能是负数")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Mirror https://mlir.llvm.org/docs/")
    parser.add_argument("--jobs", type=positive_int, default=8, help="parallel downloads")
    parser.add_argument("--batch", type=positive_int, default=16,
                        help="URLs fetched per round")
    parser.add_argument("--max-pages", type=non_negative_int, default=0,
                        help="stop after N pages (0 = no limit)")
    parser.add_argument("--no-markdown", action="store_true", help="skip Markdown export")
    args = parser.parse_args(argv)

    project = Path(__file__).resolve().parent
    args.out = project / "site"
    args.out.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = UA

    print(f"[1/4] crawling {SITE}{SCOPE}")
    pages, assets, report = crawl_pages(session, args)
    print(f"[1/4] done: {len(pages)} pages, {len(assets)} assets referenced")

    print("[2/4] downloading assets")
    report += download_assets(session, args, assets)

    print("[3/4] rewriting and saving HTML")
    for page in pages:
        html = rewrite_html(page["html"], page["url"], page["local"])
        write_text(args.out, page["local"], html)

    # a plain site/index.html that lands on the documentation home page
    if not (args.out / "index.html").exists():
        write_text(args.out, "index.html",
                   '<!doctype html><meta charset="utf-8">'
                   '<meta http-equiv="refresh" content="0; url=docs/index.html">'
                   '<title>MLIR docs</title><a href="docs/index.html">MLIR docs</a>\n')

    if args.no_markdown:
        print("[4/4] Markdown export skipped")
    else:
        print("[4/4] writing Markdown")
        write_markdown(project, pages, "site")

    write_report(project, report, pages)
    write_readme(project, pages)

    failed = [row for row in report if not row[0].startswith("OK")]
    print(f"\nfinished: {len(pages)} pages -> {args.out}")
    print(f"          {len(failed)} failures (see crawl_report.txt)")
    for status, url, _ in failed[:10]:
        print(f"          {status} {url}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
