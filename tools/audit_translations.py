#!/usr/bin/env python3
"""译名质量抽检：找出口径不一致、标点混用、疑似没译的条目。

    python3 tools/audit_translations.py           # 汇总
    python3 tools/audit_translations.py --samples # 附带随机样本
"""

import argparse
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "i18n" / "headings_zh.tsv"

CJK = re.compile(r"[\u4e00-\u9fff]")
# 中文后面紧跟半角标点，印刷上不好看，也说明翻译时没统一风格
HALF_PUNCT = re.compile(r"[\u4e00-\u9fff][,:;?!]")
# 译文里还留着成串英文（可能是没翻完）
LATIN_WORD = re.compile(r"[A-Za-z]{4,}")
TERMS = ["Pass", "Dialect", "Trait", "Operation", "Lowering",
         "Bufferization", "Canonicalization", "Attribute", "Type"]


def load() -> list[tuple[str, str]]:
    rows = []
    for line in MAIN.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].strip():
            rows.append((parts[0].strip(), parts[1].strip()))
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="译名质量抽检")
    parser.add_argument("--samples", action="store_true")
    args = parser.parse_args(argv)

    rows = load()
    print(f"译名总数        : {len(rows)}")
    print(f"含中文          : {sum(1 for _, zh in rows if CJK.search(zh))}")
    print(f"纯英文（标识符）: {sum(1 for _, zh in rows if not CJK.search(zh))}")

    half = [(en, zh) for en, zh in rows if HALF_PUNCT.search(zh)]
    latin = [(en, zh) for en, zh in rows
             if CJK.search(zh) and LATIN_WORD.search(zh)]
    print(f"\n中文后接半角标点: {len(half)}")
    for en, zh in half[:8]:
        print(f"  {en}  →  {zh}")
    print(f"\n译文里夹着英文单词: {len(latin)}")
    for en, zh in latin[:8]:
        print(f"  {en}  →  {zh}")

    print("\n术语译法分布（同一英文词是否被译乱）：")
    for term in TERMS:
        variants: Counter = Counter()
        for en, zh in rows:
            if re.search(rf"\b{term}s?\b", en) and CJK.search(zh):
                variants[zh] += 1
        if not variants:
            continue
        top = variants.most_common(4)
        print(f"  {term:16s} 共 {sum(variants.values()):3d} 条，"
              f"不同译法 {len(variants):2d} 种："
              + "；".join(f"{zh}({n})" for zh, n in top))

    if args.samples:
        print("\n随机样本 12 条：")
        for en, zh in random.sample(rows, min(12, len(rows))):
            print(f"  {en}  →  {zh}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
