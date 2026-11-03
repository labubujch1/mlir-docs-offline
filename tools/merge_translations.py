#!/usr/bin/env python3
"""校验并合并外部交付的译名表（默认先把 h3 待补表并入主表）。

校验项：
  1. 数据行数与原始待补表一致；
  2. 第 1/3/4 列与原始文件逐行一致（防止改了英文原文）；
  3. 第 2 列非空；
  4. 主表不重复插入同一英文键。

    python3 tools/merge_translations.py --dry-run     # 只校验不落盘
    python3 tools/merge_translations.py               # 校验 + 合并
"""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "i18n"
TODO = I18N / "todo_h3.tsv"
FILLED = I18N / "todo_h3.filled.tsv"
MAIN = I18N / "headings_zh.tsv"
LEVEL3_MARKER = "# ---- level 3: h3 headings contributed by agents ----"


def rows(path: Path) -> list[list[str]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        out.append(line.split("\t"))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="校验并合并译名表")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    for path in (TODO, FILLED, MAIN):
        if not path.is_file():
            print(f"缺少文件：{path}")
            return 2

    src, filled = rows(TODO), rows(FILLED)
    problems = []

    if len(src) != len(filled):
        problems.append(f"行数不一致：原始 {len(src)} / 交付 {len(filled)}")

    for index, (a, b) in enumerate(zip(src, filled), 1):
        if len(b) != 4:
            problems.append(f"第 {index} 行列数={len(b)}（应为 4）")
            continue
        if [a[0], a[2], a[3]] != [b[0], b[2], b[3]]:
            problems.append(f"第 {index} 行 1/3/4 列被改动：{a[0]!r} -> {b[0]!r}")
        if not b[1].strip():
            problems.append(f"第 {index} 行中文为空：{b[0]!r}")

    known = set()
    for line in MAIN.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            known.add(line.split("\t")[0].strip())

    added, skipped, identical = [], 0, 0
    for row in filled:
        english, chinese = row[0].strip(), row[1].strip()
        if not english or not chinese:
            continue
        if english == chinese:
            # 交付方对纯标识符原样回填；主表里存这种"译名"会让双语标题重复显示
            identical += 1
            continue
        if english in known:
            skipped += 1
            continue
        known.add(english)
        added.append((english, chinese))

    print(f"交付行数      : {len(filled)}")
    print(f"校验问题      : {len(problems)}")
    for problem in problems[:10]:
        print(f"  - {problem}")
    print(f"可新增译名    : {len(added)}")
    print(f"中英相同跳过  : {identical}")
    print(f"已存在跳过    : {skipped}")
    print("\n示例（前 5 条）：")
    for english, chinese in added[:5]:
        print(f"  {english}  →  {chinese}")

    if problems:
        print("\n存在校验问题，未写入。")
        return 1
    if args.dry_run:
        print("\n--dry-run：未写入。")
        return 0

    backup = MAIN.with_suffix(".tsv.bak")
    shutil.copy2(MAIN, backup)
    with MAIN.open("a", encoding="utf-8") as handle:
        handle.write(f"\n{LEVEL3_MARKER}\n")
        for english, chinese in added:
            handle.write(f"{english}\t{chinese}\n")
    print(f"\n已合并 {len(added)} 条到 {MAIN.name}（备份 {backup.name}）")
    print("下一步：python3 make_printable.py && python3 tools/verify_print.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
