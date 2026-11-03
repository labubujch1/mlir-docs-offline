#!/usr/bin/env python3
"""Validate the offline mirror.

检查范围（明确写出来，避免"0 broken"被过度解读）：

* `href` / `src` / `poster` / `srcset` 里指向本地文件的链接，目标文件是否存在；
* 带 `#fragment` 的本地链接，目标 HTML 里是否真有对应的 `id=` / `name=`；
* Markdown 导出里的相对链接（跳过代码块）。

不检查：CSS 里 `url()` 的目标、外部站点的可达性。

    python3 check_mirror.py            # 只报数量
    python3 check_mirror.py --verbose  # 列出每条问题
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
MD = ROOT / "markdown"

ATTR_RE = re.compile(r'\b(href|src|poster|srcset)="([^"]*)"', re.I)
# Hugo 有时输出无引号的属性（id=foo），三种写法都要认
ID_RE = re.compile(r"""\b(?:id|name)\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>"']+))""")
MD_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
FENCE_RE = re.compile(r"^\s*```.*?^\s*```", re.S | re.M)
SKIP = ("#", "mailto:", "javascript:", "data:", "tel:")

ID_CACHE: dict[Path, set[str]] = {}


def ids_of(path: Path) -> set[str]:
    if path not in ID_CACHE:
        found: set[str] = set()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        for match in ID_RE.finditer(text):
            value = match.group(1) or match.group(2) or match.group(3)
            if value:
                found.add(value)
        ID_CACHE[path] = found
    return ID_CACHE[path]


def urls_in(value: str) -> list[str]:
    """`srcset` 里是 "a.png 1x, b.png 2x"，拆成单个 URL。"""
    if "," in value or " " in value:
        out = []
        for item in value.split(","):
            item = item.strip().split(" ")[0]
            if item:
                out.append(item)
        return out
    return [value.strip()]


def check_html() -> tuple[int, int, Counter, Counter]:
    local_links = online_links = 0
    missing_file: Counter = Counter()
    missing_anchor: Counter = Counter()

    for page in sorted(SITE.rglob("*.html")):
        html = page.read_text(encoding="utf-8", errors="ignore")
        for attr, value in ATTR_RE.findall(html):
            for url in urls_in(value):
                if not url or url.lower().startswith(SKIP):
                    continue
                parts = urlsplit(url)
                if parts.scheme in ("http", "https", "//"):
                    online_links += 1
                    continue
                local_links += 1
                target = (page.parent / unquote(parts.path)).resolve() if parts.path \
                    else page.resolve()
                if not target.exists():
                    missing_file[f"{page.relative_to(ROOT)}\t-> {url}"] += 1
                    continue
                if parts.fragment and target.suffix.lower() in (".html", ".htm"):
                    if parts.fragment not in ids_of(target):
                        missing_anchor[f"{page.relative_to(ROOT)}\t-> {url}"] += 1
    return local_links, online_links, missing_file, missing_anchor


def check_markdown() -> tuple[int, Counter]:
    local_links = 0
    missing: Counter = Counter()
    for doc in sorted(MD.rglob("*.md")):
        text = FENCE_RE.sub("", doc.read_text(encoding="utf-8", errors="ignore"))
        for raw in MD_LINK_RE.findall(text):
            if raw.startswith(SKIP) or raw.startswith("http://") or raw.startswith("https://"):
                continue
            path = unquote(urlsplit(raw).path)
            if not path:
                continue
            local_links += 1
            if not (doc.parent / path).exists():
                missing[f"{doc.relative_to(ROOT)}\t-> {raw}"] += 1
    return local_links, missing


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    if not SITE.is_dir():
        print(f"! {SITE} not found - run crawl_mlir_docs.py first")
        return 2

    html_local, html_online, missing_file, missing_anchor = check_html()
    md_local, md_missing = check_markdown()

    pages = len(list(SITE.rglob("*.html")))
    files = sum(1 for f in SITE.rglob("*") if f.is_file())
    print(f"HTML pages      : {pages}")
    print(f"files in site/  : {files}")
    print(f"local links     : {html_local} (html), {md_local} (markdown)")
    print(f"online links    : {html_online} (kept as absolute URLs)")
    print(f"broken files    : {len(missing_file)} (html), {len(md_missing)} (markdown)")
    print(f"broken anchors  : {len(missing_anchor)} (#fragment 没有对应 id)")

    for label, counter in (("html file", missing_file), ("markdown", md_missing),
                           ("anchor", missing_anchor)):
        if counter and verbose:
            print(f"\n-- broken {label} links --")
            for line in sorted(counter)[:100]:
                print(f"  {line}")
    # 片段锚点缺失多为上游文档自身问题，只作提示，不影响退出码
    return 0 if not (missing_file or md_missing) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

