"""Generate the list of h3 headings that still have no Chinese translation.

The output is a ready-to-fill TSV for another agent (e.g. Copilot) to complete:
    english heading <TAB> (empty) <TAB> occurrences <TAB> one example file
"""

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "markdown"
I18N = ROOT / "i18n" / "headings_zh.tsv"
OUT = ROOT / "i18n" / "todo_h3.tsv"

QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
          "\u00a0": " ", "\u2013": "-", "\u2014": "-"}
HEAD = re.compile(r"^(#{3})\s+(.*)\s*$", re.M)
FENCE = re.compile(r"^```.*?^```", re.S | re.M)


def norm(text: str) -> str:
    for bad, good in QUOTES.items():
        text = text.replace(bad, good)
    return re.sub(r"\s+", " ", text).strip()


known = set()
for line in I18N.read_text(encoding="utf-8").splitlines():
    if line.strip() and not line.lstrip().startswith("#"):
        known.add(norm(line.split("\t")[0]))

counter: Counter = Counter()
example: dict[str, str] = {}
for path in sorted(MD.rglob("*.md")):
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    for _, raw in HEAD.findall(text):
        title = norm(re.sub(r"`[^`]*`", "", raw))       # identifiers dropped
        if not title or "`" in raw:                      # op names: never translate
            continue
        if title in known:
            continue
        counter[title] += 1
        example.setdefault(title, path.relative_to(ROOT).as_posix())

lines = ["# 待补译的三级标题（h3）：english <TAB> 中文 <TAB> 出现次数 <TAB> 示例文件",
         "# 填好第二列后，把本文件相关行并入 i18n/headings_zh.tsv，再跑 make_printable.py",
         ""]
for title, count in counter.most_common():
    lines.append(f"{title}\t\t{count}\t{example[title]}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"untranslated h3 headings: {len(counter)}  ->  {OUT}")
print("top 10:")
for title, count in counter.most_common(10):
    print(f"  {count:3d}x  {title}")
