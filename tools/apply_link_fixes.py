#!/usr/bin/env python3
"""按 i18n/link_fixes.tsv 修掉上游死链（可重复执行，抓取后必须再跑一次）。

    python3 tools/apply_link_fixes.py --dry-run   # 只看会改什么
    python3 tools/apply_link_fixes.py             # 真的改

规则来自 T5 报告：
* `replace`：把旧 URL 换成新 URL（`site/` 的 HTML、`markdown/`、`ALL_DOCS.md`）；
* `note`：图片已 404，删掉 `<img>` 标签，在原位留一行说明文字。
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXES = ROOT / "i18n" / "link_fixes.tsv"
SITE = ROOT / "site"
MD = ROOT / "markdown"
ALL_DOCS = ROOT / "ALL_DOCS.md"


def load_fixes() -> list[tuple[str, str, str]]:
    rows = []
    for line in FIXES.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    return rows


def note_for(old: str, text: str) -> str:
    return f'<span class="deadlink">〔图片不可用：{text}（{old}）〕</span>'


def fix_html(path: Path, fixes) -> int:
    original = path.read_text(encoding="utf-8", errors="ignore")
    text = original
    for old, action, target in fixes:
        if old not in text:
            continue
        if action == "replace":
            text = text.replace(old, target)
        elif action == "note":
            pattern = re.compile(r'<img\b[^>]*?\bsrc="' + re.escape(old) + r'"[^>]*>', re.I)
            text = pattern.sub(lambda _m: note_for(old, target), text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return 1
    return 0


def fix_markdown(path: Path, fixes) -> int:
    original = path.read_text(encoding="utf-8", errors="ignore")
    text = original
    for old, action, target in fixes:
        if old not in text:
            continue
        if action == "replace":
            text = text.replace(old, target)
        elif action == "note":
            pattern = re.compile(r"!\[[^\]]*\]\(" + re.escape(old) + r"\)")
            text = pattern.sub(f"〔图片不可用：{target}〕", text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="修上游死链")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not FIXES.is_file():
        print(f"缺少规则文件：{FIXES}")
        return 2
    fixes = load_fixes()
    print(f"规则 {len(fixes)} 条：")
    for old, action, target in fixes:
        print(f"  [{action}] {old}")
        print(f"        → {target}")

    targets = [p for p in SITE.rglob("*.html")]
    html_hits = sum(1 for p in targets
                    if any(old in p.read_text(encoding="utf-8", errors="ignore")
                           for old, _, _ in fixes))
    md_files = list(MD.rglob("*.md")) + ([ALL_DOCS] if ALL_DOCS.is_file() else [])
    md_hits = sum(1 for p in md_files
                  if any(old in p.read_text(encoding="utf-8", errors="ignore")
                         for old, _, _ in fixes))

    print(f"\n命中的 HTML 文件：{len(targets)} 个里 {html_hits} 个")
    print(f"命中的 Markdown  ：{len(md_files)} 个里 {md_hits} 个")

    if args.dry_run:
        print("\n--dry-run：未写入")
        return 0

    changed = sum(fix_html(p, fixes) for p in targets)
    changed += sum(fix_markdown(p, fixes) for p in md_files)
    print(f"\n已修改 {changed} 个文件（规则 {len(fixes)} 条）")
    print("下一步：python3 make_printable.py && python3 check_mirror.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
