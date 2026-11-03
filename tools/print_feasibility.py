#!/usr/bin/env python3
"""打印可行性自检：单卷体量、超长代码行、宽表格、图片。

为什么需要：`print/` 是给浏览器"打印成 PDF"用的，单个 HTML 太大或代码行太长，
Chrome 容易卡死或把行裁掉。这里只做静态测量，不需联网。

    python3 tools/print_feasibility.py
    python3 tools/print_feasibility.py --limit 800   # 自定义"单卷页数"阈值
"""

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRINT = ROOT / "print"

PRE_RE = re.compile(r"<pre\b.*?</pre>", re.S | re.I)
TABLE_RE = re.compile(r"<table\b.*?</table>", re.S | re.I)
ROW_RE = re.compile(r"<tr\b.*?</tr>", re.S | re.I)
CELL_RE = re.compile(r"<t[dh]\b", re.I)
TAG_RE = re.compile(r"<[^>]+>")
ENTITIES = {"&lt;": "<", "&gt;": ">", "&amp;": "&", "&quot;": '"', "&#39;": "'",
            "&nbsp;": " "}
PAGES_PER_CHAR = 1 / 3300
PAGES_PER_CODE_LINE = 1 / 55


def text_of(fragment: str) -> str:
    for entity, char in ENTITIES.items():
        fragment = fragment.replace(entity, char)
    return TAG_RE.sub("", fragment)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="打印稿可行性检查")
    parser.add_argument("--limit", type=int, default=800, help="单卷页数告警阈值")
    parser.add_argument("--long-line", type=int, default=120, help="代码行长度阈值")
    args = parser.parse_args(argv)

    if not PRINT.is_dir():
        print("没有 print/ 目录，先跑 make_printable.py")
        return 2

    problems = 0
    print(f"{'file':22s} {'MB':>5s} {'页':>6s} {'代码块':>6s} "
          f"{'>%d字符' % args.long_line:>9s} {'宽表':>4s} {'图':>3s}")
    print("-" * 66)
    for path in sorted(PRINT.glob("*.html")):
        html = path.read_text(encoding="utf-8", errors="ignore")
        pres = PRE_RE.findall(html)
        code_lines = sum(block.count("\n") for block in pres)

        longest = 0
        too_long = 0
        for block in pres:
            for line in text_of(block).splitlines():
                length = len(line)
                longest = max(longest, length)
                if length > args.long_line:
                    too_long += 1

        wide_tables = 0
        for table in TABLE_RE.findall(html):
            for row in ROW_RE.findall(table)[:1]:
                if len(CELL_RE.findall(row)) > 6:
                    wide_tables += 1

        images = len(re.findall(r"<img\b", html, re.I))
        prose_chars = len(text_of(html))
        pages = prose_chars * PAGES_PER_CHAR + code_lines * PAGES_PER_CODE_LINE

        flag = ""
        if pages > args.limit:
            flag = " ← 单卷过大，建议再拆"
            problems += 1
        print(f"{path.name:22s} {path.stat().st_size / 1e6:5.1f} {pages:6.0f} "
              f"{len(pres):6d} {too_long:9d} {wide_tables:4d} {images:3d}{flag}")
        print(f"{'  └ 最长代码行':22s} {longest} 字符")

    print()
    print(f"阈值：单卷 {args.limit} 页、代码行 {args.long_line} 字符")
    print("代码块已用 pre-wrap + break-word，超长行会折行显示（不会被裁掉），"
          "但折行会拉长篇幅，必要时可考虑把长行按 100 字符硬折。")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
