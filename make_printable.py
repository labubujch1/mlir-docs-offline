#!/usr/bin/env python3
"""Build a bilingual (Chinese/English) print-ready HTML version of the docs.

Why HTML: everything here is offline, and every browser can turn it into a PDF
with correct page numbers (File -> Print -> Save as PDF). No LaTeX/pandoc needed.

What you get, in  print/ :
    vol1-core.html        核心概念
    vol2-tutorials.html   教程
    vol3-rationale.html   设计理由
    vol4-dialects.html    方言操作符参考
    all-in-one.html       全部合成一本

Headings are rendered as "中文标题" with the English original right after it, and
the table of contents is bilingual too. Translations come from
i18n/headings_zh.tsv; anything missing there simply stays English.

Usage:
    python3 make_printable.py                 # all volumes + combined
    python3 make_printable.py --only vol3     # just one volume
"""

from __future__ import annotations

import argparse
import html as html_mod
import posixpath
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
OUT = ROOT / "print"
I18N = ROOT / "i18n" / "headings_zh.tsv"

VOLUMES = [
    ("vol1", "vol1-core.html", "核心概念", "Core Concepts"),
    ("vol2", "vol2-tutorials.html", "教程", "Tutorials"),
    ("vol3", "vol3-rationale.html", "设计理由", "Rationale"),
    ("vol4", "vol4-dialects.html", "方言操作符参考", "Dialect Reference"),
]

# 单卷页数过大时再拆：vol4 拆成 3 份（每份约 500 页，浏览器打 PDF 才稳）
SPLIT = {"vol4": 3}
CN_NUM = ["一", "二", "三", "四", "五", "六"]
PART_LETTERS = "abcdef"

QUOTE_MAP = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u00a0": " ", "\u2013": "-", "\u2014": "-", "\u2026": "...",
}

HEADING_RE = re.compile(r"<h([1-6])\b([^>]*)>(.*?)</h\1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")


def norm_key(text: str) -> str:
    for bad, good in QUOTE_MAP.items():
        text = text.replace(bad, good)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def plain(fragment: str) -> str:
    """Strip tags/entities from an HTML fragment."""
    text = TAG_RE.sub("", fragment)
    text = html_mod.unescape(text)
    return norm_key(text.replace("¶", ""))


def load_translations() -> tuple[dict[str, str], dict[str, str]]:
    """Return (level-1 titles, all headings).

    Level-1 and level-2 entries can share an English key (e.g. "Rationale"),
    so chapter titles are looked up in their own table first.
    """
    level1: dict[str, str] = {}
    everything: dict[str, str] = {}
    if not I18N.is_file():
        return level1, everything
    in_level2 = False
    for line in I18N.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            if "level 2" in line:
                in_level2 = True
            continue
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        en, zh = norm_key(parts[0]), parts[1].strip()
        if not en or not zh:
            continue
        everything[en] = zh
        if not in_level2:
            level1[en] = zh
    return level1, everything


AUTO_RULES = [
    (re.compile(r"^['\"]?(.+?)['\"]?\s+Dialect Passes$"), "{0} 方言 Pass"),
    (re.compile(r"^(.+?)\s+Transform Operations$"), "{0} 变换操作"),
    (re.compile(r"^(.+?)\s+Match Operations$"), "{0} 匹配操作"),
    (re.compile(r"^(.+?)\s+Interface\s*\(`[^`]+`\)$"), "{0} 接口"),
]


def translate(text: str, table: dict[str, str], level1: dict[str, str] | None = None,
              level: int = 2) -> str:
    key = norm_key(text)
    if level == 1 and level1 is not None and key in level1:
        return level1[key]
    if key in table:
        return table[key]
    for pattern, template in AUTO_RULES:
        match = pattern.match(key)
        if match:
            return template.format(match.group(1).strip())
    return ""


# --------------------------------------------------------------------------- #
# read the mirrored pages
# --------------------------------------------------------------------------- #
SIDEBAR_RE = re.compile(r"<nav class=slide-menu>(.*?)</nav>", re.S | re.I)
ANCHOR_RE = re.compile(r'<a\b([^>]*)>(.*?)</a>', re.S | re.I)
IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=)"([^"]*)"', re.I)


def doc_order() -> list[str]:
    """Reading order taken from the site's own sidebar."""
    index = SITE / "docs" / "index.html"
    text = index.read_text(encoding="utf-8", errors="ignore")
    match = SIDEBAR_RE.search(text)
    block = match.group(1) if match else text
    order: list[str] = []
    for attrs, _ in ANCHOR_RE.findall(block):
        href = re.search(r'href="([^"]*)"', attrs)
        if not href:
            continue
        value = href.group(1).split("#")[0]
        if not value.endswith("index.html") or value.startswith(("http", "../")):
            continue
        local = posixpath.normpath(posixpath.join("docs", value))
        if local not in order:
            order.append(local)
    if len(order) < 50:                      # fallback: alphabetical
        order = sorted(p.relative_to(SITE).as_posix()
                       for p in (SITE / "docs").rglob("index.html"))
    return order


def load_body(local: str) -> str:
    raw = (SITE / local).read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"<main[^>]*>(.*?)</main>", raw, re.S | re.I)
    body = match.group(1) if match else raw
    body = re.sub(r"<nav[^>]*>.*?</nav>", "", body, flags=re.S | re.I)
    body = re.sub(r"<footer[^>]*>.*?</footer>", "", body, flags=re.S | re.I)
    body = re.sub(r"<div class=edit-meta>.*?</div>", "", body, flags=re.S | re.I)
    body = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.S | re.I)
    body = re.sub(r'<a[^>]*class=headline-hash[^>]*>.*?</a>', "", body, flags=re.S | re.I)
    return body


def slug_of(local: str) -> str:
    rel = local[len("docs/"):] if local.startswith("docs/") else local
    rel = rel[: -len("/index.html")] if rel.endswith("/index.html") else rel
    return re.sub(r"[^a-z0-9]+", "-", rel.lower()).strip("-") or "docs"


def fix_assets(body: str, doc_local: str) -> str:
    """Point images at ../site/... so they resolve from print/."""
    doc_dir = posixpath.dirname(doc_local)

    def img(match: re.Match) -> str:
        value = match.group(2)
        if value.lower().startswith(("http://", "https://", "data:")):
            return match.group(0)
        target = posixpath.normpath(posixpath.join(doc_dir, value))
        rel = posixpath.relpath(posixpath.join("site", target), "print")
        return f'{match.group(1)}"{rel}"'

    return IMG_SRC_RE.sub(img, body)


def strip_internal_links(body: str) -> str:
    """Cross-document links cannot work on paper: keep the text only."""

    def anchor(match: re.Match) -> str:
        attrs, inner = match.group(1), match.group(2)
        href = re.search(r'href="([^"]*)"', attrs)
        if not href:
            return inner
        value = href.group(1)
        if value.lower().startswith(("http://", "https://", "mailto:")):
            return match.group(0)          # external link: keep it clickable
        return inner                       # internal / anchor link: text only

    return ANCHOR_RE.sub(anchor, body)


def tidy_title(zh: str, en: str) -> str:
    """Drop the "(English)" tail when the English title is shown separately anyway."""
    if not zh:
        return zh
    for opening, closing in (("（", "）"), ("(", ")")):
        tail = f"{opening}{en}{closing}"
        if zh.endswith(tail):
            return zh[: -len(tail)].strip()
    return zh


def process_headings(body: str, level1: dict[str, str], table: dict[str, str],
                     slug: str, chapter_no: int):
    """Renumber ids, add bilingual titles, collect the section list."""
    sections: list[tuple[int, str, str, str]] = []
    counter = [0]

    def render(match: re.Match) -> str:
        level = int(match.group(1))
        inner = match.group(3)
        english = plain(inner)
        chinese = translate(english, table, level1, level)
        counter[0] += 1
        if level == 1:
            heading_id = f"ch-{slug}"
        else:
            heading_id = f"{slug}-s{counter[0]}"
        if level <= 2:
            sections.append((level, english, chinese, heading_id))
        en_html = re.sub(r"(&nbsp;|\s)+$", "", inner.strip())
        en_html = re.sub(r"^(&nbsp;|\s)+", "", en_html)
        same = chinese and norm_key(chinese) == norm_key(english)
        if chinese and not same and level <= 3:
            label = tidy_title(chinese, english) if level == 1 else chinese
            return (f'<h{level} id="{heading_id}">{html_mod.escape(label)}'
                    f'<span class="en">{en_html}</span></h{level}>')
        return f'<h{level} id="{heading_id}">{en_html}</h{level}>'

    return HEADING_RE.sub(render, body), sections


def code_lines(body: str) -> int:
    return sum(block.count("\n") for block in re.findall(r"<pre\b.*?</pre>", body, re.S | re.I))


# --------------------------------------------------------------------------- #
# page layout
# --------------------------------------------------------------------------- #
CSS = """
@page { size: A4; margin: 17mm 15mm 16mm 15mm; }
:root { --mono: "JetBrains Mono","Cascadia Mono",Consolas,"DejaVu Sans Mono",monospace;
        --sans: "Noto Sans CJK SC","Source Han Sans SC","Microsoft YaHei",sans-serif; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; color: #111; background: #fff;
       font-family: "Noto Serif CJK SC","Source Han Serif SC","Songti SC",SimSun,serif;
       font-size: 10.5pt; line-height: 1.62; }
.cover { page-break-after: always; padding-top: 55mm; text-align: center; }
.cover .kicker { font-family: var(--sans); font-size: 10pt; letter-spacing: .2em; color: #888; }
.cover .cover-title { font-family: var(--sans); font-size: 30pt; font-weight: 700; margin: 12mm 0 3mm; }
.cover .cover-sub { font-family: var(--sans); font-size: 14pt; color: #555; }
.cover .cover-meta { margin-top: 20mm; font-size: 10pt; color: #444; line-height: 2.1; }
.cover .cover-note { margin: 12mm auto 0; max-width: 118mm; text-align: left; font-size: 8.8pt;
                     color: #555; border-top: .6pt solid #ccc; padding-top: 4mm; line-height: 1.7; }
h1,h2,h3,h4,h5,h6 { font-family: var(--sans); line-height: 1.36; }
h1 { font-size: 19pt; margin: 0 0 10pt; padding-bottom: 6pt; border-bottom: 1.6pt solid #333;
     page-break-before: always; page-break-after: avoid; }
h1 .en { display: block; margin-top: 4pt; font-size: 10pt; font-weight: 400; color: #666; }
h2 { font-size: 13pt; margin: 16pt 0 6pt; padding-bottom: 2pt; border-bottom: .6pt solid #bbb;
     page-break-after: avoid; }
h2 .en { margin-left: 6pt; font-size: 8.8pt; font-weight: 400; color: #777; }
h3 { font-size: 11.4pt; margin: 12pt 0 4pt; page-break-after: avoid; }
h3 .en { margin-left: 5pt; font-size: 8.6pt; font-weight: 400; color: #777; }
h4 { font-size: 10.4pt; margin: 10pt 0 3pt; page-break-after: avoid; }
h5,h6 { font-size: 10pt; margin: 8pt 0 3pt; }
p { margin: 0 0 6pt; text-align: justify; }
ul,ol { margin: 0 0 6pt; padding-left: 18pt; }
li { margin-bottom: 2.5pt; }
pre { font-family: var(--mono); font-size: 8.2pt; line-height: 1.34; margin: 6pt 0 8pt;
      padding: 5pt 7pt; background: #f7f7f9; border-left: 2.4pt solid #c9d1d9;
      white-space: pre-wrap; word-break: break-word; page-break-inside: avoid; }
code { font-family: var(--mono); font-size: 9pt; background: #f2f3f5; padding: 0 1.5pt; }
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 8pt; font-size: 8.8pt;
        page-break-inside: avoid; }
th,td { border: .6pt solid #aaa; padding: 2.5pt 4pt; vertical-align: top; text-align: left; }
th { background: #f0f0f3; }
img { max-width: 100%; }
blockquote { margin: 6pt 0 6pt 10pt; padding-left: 8pt; border-left: 2pt solid #ccc; color: #444; }
hr { border: 0; border-top: .6pt solid #ccc; margin: 10pt 0; }
.toc { page-break-after: always; }
.toc .toc-title { font-family: var(--sans); font-size: 20pt; font-weight: 700; margin: 0 0 4pt;
                  border-bottom: 1.6pt solid #333; padding-bottom: 6pt; }
.toc .toc-sub { font-size: 9.5pt; color: #666; margin-bottom: 12pt; }
.toc ul { list-style: none; margin: 0; padding: 0; }
.toc li.ch { margin-top: 5.5pt; font-weight: 600; font-size: 10.2pt; }
.toc li.sec { margin-left: 18pt; font-size: 9pt; color: #333; font-weight: 400; }
.toc a { color: inherit; text-decoration: none; }
.toc .num { display: inline-block; min-width: 26pt; color: #777; font-weight: 400; }
.toc .en { color: #888; font-weight: 400; font-size: 8.6pt; }
.colophon { page-break-before: always; font-size: 9.2pt; color: #444; line-height: 1.8; }
.colophon h2 { border: 0; font-size: 13pt; }
"""

EXTRA_CSS = """
.ch-label { display: block; font-size: 8.6pt; font-weight: 400; letter-spacing: .14em;
            color: #888; margin-bottom: 3pt; }
h2 .no { color: #888; font-weight: 400; font-size: 9pt; margin-right: 3pt; }
.toc li.ch a { display: block; }
"""


def volume_of(local: str) -> str:
    rel = local[len("docs/"):] if local.startswith("docs/") else local
    if rel.startswith("Dialects"):
        return "vol4"
    if rel.startswith("Tutorials"):
        return "vol2"
    if rel.startswith("Rationale"):
        return "vol3"
    return "vol1"


def page_title(local: str) -> str:
    raw = (SITE / local).read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"<title>(.*?)</title>", raw, re.S | re.I)
    return re.sub(r"\s*-\s*MLIR\s*$", "", html_mod.unescape(match.group(1)).strip()) if match else ""


def number_sections(body: str, chapter_no: int) -> str:
    counter = [0]

    def repl(match: re.Match) -> str:
        counter[0] += 1
        return (f'<h2 id="{match.group(1)}">'
                f'<span class="no">{chapter_no}.{counter[0]}</span> ')

    return re.sub(r'<h2 id="([^"]+)">', repl, body)


def label_chapter(body: str, chapter_no: int) -> str:
    def repl(match: re.Match) -> str:
        return (f'<h1 id="{match.group(1)}">'
                f'<span class="ch-label">第 {chapter_no} 篇 · CHAPTER {chapter_no}</span>')

    return re.sub(r'<h1 id="([^"]*)">', repl, body, count=1)


def collect_docs(level1: dict[str, str], table: dict[str, str]) -> list[dict]:
    docs = []
    for local in doc_order():
        body = load_body(local)
        slug = slug_of(local)
        body, sections = process_headings(body, level1, table, slug, 0)
        body = fix_assets(body, local)
        body = strip_internal_links(body)
        body = re.sub(r"<p>\s*(?=<h[1-6])", "", body)     # stray <p> before a heading
        body = re.sub(r"<p>\s*</p>", "", body)

        first = sections[0] if sections and sections[0][0] == 1 else None
        en_title = first[1] if first else ""
        zh_title = tidy_title(first[2], first[1]) if first else ""
        if not en_title or en_title.lower().startswith("[source"):
            en_title = page_title(local)
            if en_title.strip().lower() in ("", "mlir", "docs"):
                # generated page without a real title: use the URL segment
                en_title = local.rsplit("/", 2)[-2] if local.endswith("/index.html") else slug
            zh_title = tidy_title(translate(en_title, table, level1, 1), en_title)

        pages = len(plain(body)) / 3300 + code_lines(body) / 55

        # a couple of generated pages ship an empty <h1>; put the real title in
        def fix_empty_h1(match: re.Match) -> str:
            if plain(match.group(2)):
                return match.group(0)
            label = html_mod.escape(zh_title) if zh_title else ""
            return (f'<h1 id="{match.group(1)}">{label}'
                    f'<span class="en">{html_mod.escape(en_title)}</span></h1>')

        body = re.sub(r'<h1 id="([^"]*)">(.*?)</h1>', fix_empty_h1, body,
                      count=1, flags=re.S)

        docs.append({"local": local, "slug": slug, "body": body,
                     "en": en_title, "zh": zh_title, "sections": sections,
                     "pages": pages, "volume": volume_of(local)})
    return docs


def split_evenly(docs: list[dict], parts: int) -> list[list[dict]]:
    """按估算页数把 docs 顺序切成 parts 份（保持原顺序，尽量等分）。"""
    if parts <= 1 or len(docs) <= parts:
        return [docs]
    total = sum(doc["pages"] for doc in docs) or 1.0
    groups: list[list[dict]] = []
    current: list[dict] = []
    running = 0.0
    for doc in docs:
        current.append(doc)
        running += doc["pages"]
        threshold = total * (len(groups) + 1) / parts
        if len(groups) < parts - 1 and running >= threshold:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def number_for_output(docs: list[dict]) -> list[dict]:
    """Assign 1..N chapter numbers for one output file (each volume restarts at 1)."""
    numbered = []
    for index, doc in enumerate(docs, 1):
        body = number_sections(doc["body"], index)
        body = label_chapter(body, index)
        numbered.append({**doc, "num": index, "body": body})
    return numbered


def build_toc(docs: list[dict], title_zh: str, title_en: str) -> str:
    rows = ['<div class="toc">',
            '  <div class="toc-title">目 录 / Contents</div>',
            f'  <div class="toc-sub">{html_mod.escape(title_zh)} · '
            f'{html_mod.escape(title_en)} — 共 {len(docs)} 篇</div>',
            '  <ul>']
    for doc in docs:
        zh = doc["zh"] or doc["en"]
        rows.append(
            f'    <li class="ch"><a href="#ch-{doc["slug"]}">'
            f'<span class="num">{doc["num"]}.</span>{html_mod.escape(zh)}'
            f'<span class="en"> &nbsp;{html_mod.escape(doc["en"])}</span></a></li>')
        subsections = [s for s in doc["sections"] if s[0] == 2]
        for index, (_, en_s, zh_s, hid) in enumerate(subsections, 1):
            label = zh_s or en_s
            rows.append(
                f'    <li class="sec"><a href="#{hid}">'
                f'<span class="num">{doc["num"]}.{index}</span>'
                f'{html_mod.escape(label)}</a></li>')
    rows += ['  </ul>', '</div>']
    return "\n".join(rows)


def build_chapters(docs: list[dict]) -> str:
    return "\n".join(f'<section class="chapter">\n{doc["body"]}\n</section>' for doc in docs)


def build_colophon(docs: list[dict], total_pages: float) -> str:
    missing = [d for d in docs if not d["zh"]]
    lines = [
        '<div class="colophon">',
        '  <h2>关于本打印稿 / About this print copy</h2>',
        f'  <p>内容取自 <code>https://mlir.llvm.org/docs/</code> 的离线镜像，'
        f'共 {len(docs)} 篇、约 {total_pages:,.0f} 页（A4，双面约 {total_pages / 2:,.0f} 张）。'
        f'生成时间：{time.strftime("%Y-%m-%d %H:%M")}。</p>',
        '  <p>原文版权归 LLVM/MLIR 项目所有（Apache-2.0 with LLVM Exceptions）。'
        '本打印稿仅为个人离线阅读之用。</p>',
        '  <p>中文标题为人工对照翻译，术语沿用社区习惯：Pass、Dialect（方言）、'
        'Trait、Operation（操作）、Bufferization（缓冲化）等；'
        '代码标识符保持英文，便于与源码对照。</p>',
    ]
    if missing:
        names = "、".join(html_mod.escape(d["en"]) for d in missing[:12])
        lines.append(f'  <p>尚未提供中文译名的篇目：{names}'
                     f'{"等" if len(missing) > 12 else ""}。</p>')
    lines.append('</div>')
    return "\n".join(lines)


def write_print_readme(volumes: list[tuple[str, int, float]]) -> None:
    rows = "\n".join(f"| `{name}` | {count} 篇 | ~{pages:,.0f} 页 | ~{pages / 2:,.0f} 张 |"
                     for name, count, pages in volumes)
    (OUT / "README-print.md").write_text(f"""# MLIR 文档 · 中英对照打印稿

由 `make_printable.py` 从 `site/` 的离线镜像生成，**不联网即可打印**。

| 文件 | 规模 | 单面 | 双面 |
| --- | --- | --- | --- |
{rows}

> `all-in-one.html`（124 篇，约 2,152 页）只适合屏幕检索和整本搜索，**不建议一次打印**——
> 单文件太大，浏览器生成 PDF 容易卡死或爆内存。要整本请按上面的分卷打印。

## 怎么打印成 PDF

1. 用 Chrome / Edge 打开其中一个 html（例如 `vol1-core.html`）。
2. `Ctrl+P` → 目标打印机选 **“另存为 PDF”**。
3. 纸张 A4、边距“默认”、缩放 **100%**、勾选 **“背景图形”**（否则代码块底色和表格表头会丢）。
4. 勾选 **“页眉和页脚”** → 页脚会带页码（这是本文件里唯一拿不到的东西，交给浏览器）。
5. 双面打印时选“长边翻转 / Long edge”。

## 版式说明

* 每篇文档从新页开始（h1 强制分页），标题上方有 `第 N 篇 · CHAPTER N`。
* 标题为**中英对照**：中文在前，英文原标题紧随其后（灰色小字）。
* `vol4` 按页数**均衡拆成三卷**（512 / 527 / 474 页），每卷独立编号、独立目录，
  这样单个 HTML 体积控制在 3 MB 左右，浏览器打 PDF 不会卡死。
* 目录两级：篇 + 二级小节，带 `1.`、`1.2` 编号，点击可跳转；导出的 PDF 里
  Chrome 还会自动用标题生成书签。
* 操作/属性/类型名（`arith.addf` 等）不翻译，保证可检索。
* 译名来自 `i18n/headings_zh.tsv`，未收录的标题只显示英文——想补译直接编辑该文件再重跑。

## 重新生成

```bash
python3 make_printable.py            # 全部
python3 make_printable.py --only vol3
```
""", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build bilingual printable HTML")
    parser.add_argument("--only", default="", help="vol1 / vol2 / vol3 / vol4")
    args = parser.parse_args(argv)

    table = load_translations()
    level1, table_all = table
    print(f"translations : {len(table_all)} entries ({len(level1)} chapter titles)")
    docs = collect_docs(level1, table_all)
    print(f"documents    : {len(docs)}")
    OUT.mkdir(exist_ok=True)

    by_volume: dict[str, list[dict]] = {}
    for doc in docs:
        by_volume.setdefault(doc["volume"], []).append(doc)

    summary = []
    for position, (key, filename, zh, en) in enumerate(VOLUMES, 1):
        subset = by_volume.get(key, [])
        if not subset:
            continue
        parts = split_evenly(subset, SPLIT.get(key, 1))
        for index, group in enumerate(parts):
            split = len(parts) > 1
            letter = PART_LETTERS[index] if split else ""
            name = filename.replace(f"{key}-", f"{key}{letter}-") if split else filename
            part_zh = f"{zh}（{CN_NUM[index]}）" if split else zh
            part_en = f"{en} ({index + 1}/{len(parts)})" if split else en
            pages = sum(doc["pages"] for doc in group)
            summary.append((name, len(group), pages))
            if args.only and args.only != key:
                continue

            which = f"第 {position} 卷之{CN_NUM[index]}" if split else f"第 {position} 卷"
            meta = (f"{which} / 共 {len(VOLUMES)} 卷<br>"
                    f"{len(group)} 篇 · 约 {pages:,.0f} 页 A4 · "
                    f"双面约 {pages / 2:,.0f} 张<br>"
                    f"生成日期 {time.strftime('%Y-%m-%d')}")
            numbered = number_for_output(group)
            html_text = build_document(
                part_zh, f"MLIR {part_en}", meta,
                build_toc(numbered, part_zh, part_en),
                build_chapters(numbered),
                build_colophon(numbered, pages))
            (OUT / name).write_text(html_text, encoding="utf-8")
            print(f"  {name:24s} {len(group):3d} 篇  ~{pages:,.0f} 页  "
                  f"{(OUT / name).stat().st_size / 1e6:.1f} MB")

    if not args.only:
        pages = sum(d["pages"] for d in docs)
        meta = (f"全 {len(docs)} 篇 · 约 {pages:,.0f} 页 A4 · "
                f"双面约 {pages / 2:,.0f} 张<br>生成日期 {time.strftime('%Y-%m-%d')}")
        numbered = number_for_output(docs)
        html_text = build_document(
            "MLIR 文档全集", "MLIR Documentation (complete)",
            meta,
            build_toc(numbered, "全集", "Complete"),
            build_chapters(numbered),
            build_colophon(numbered, pages))
        (OUT / "all-in-one.html").write_text(html_text, encoding="utf-8")
        print(f"  {'all-in-one.html':24s} {len(docs):3d} 篇  ~{pages:,.0f} 页  "
              f"{(OUT / 'all-in-one.html').stat().st_size / 1e6:.1f} MB")
        write_print_readme(summary)

    return 0


def build_document(title_zh: str, title_en: str, meta: str, toc: str, chapters: str,
                   colophon: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html_mod.escape(title_zh)} / {html_mod.escape(title_en)}</title>
<style>{CSS}
{EXTRA_CSS}</style>
</head>
<body>
<div class="cover">
  <div class="kicker">MLIR 文档 · 离线打印版 &nbsp;/&nbsp; OFFLINE PRINT EDITION</div>
  <div class="cover-title">{html_mod.escape(title_zh)}</div>
  <div class="cover-sub">{html_mod.escape(title_en)}</div>
  <div class="cover-meta">{meta}</div>
  <div class="cover-note">
    标题为<strong>中英对照</strong>：先中文，紧随其后的是英文原标题。<br>
    操作名、属性名、类型名（如 <code>arith.addf</code>、<code>memref.load</code>）保持英文原样，便于检索。<br>
    打印：A4、双面（长边翻转）、缩放 100%；在打印对话框里勾选“页眉和页脚”即可得到页码。
  </div>
</div>
{toc}
{chapters}
{colophon}
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
