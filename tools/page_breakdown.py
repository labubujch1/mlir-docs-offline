"""Per-section printed page estimates (same model as the groff cross-check)."""

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fence = re.compile(r"^```.*?^```", re.S | re.M)

PROSE_CHARS_PER_PAGE = 3300
CODE_LINES_PER_PAGE = 55

groups = defaultdict(lambda: [0, 0, 0])     # name -> [chars, code lines, files]
per_file = []

for path in sorted((ROOT / "markdown").rglob("*.md")):
    rel = path.relative_to(ROOT / "markdown").as_posix()
    text = path.read_text(encoding="utf-8")
    code = "\n".join(fence.findall(text))
    prose_chars = len(fence.sub("", text))
    code_lines = code.count("\n")
    pages = prose_chars / PROSE_CHARS_PER_PAGE + code_lines / CODE_LINES_PER_PAGE
    per_file.append((pages, rel))

    top = rel.split("/")[0]
    if top.startswith("Dialects") :
        group = "Dialects 操作符参考 (/docs/Dialects/**)"
    elif top.startswith("Tutorials"):
        group = "Tutorials 教程"
    elif top.startswith("Rationale"):
        group = "Rationale 设计原理"
    else:
        group = "核心概念文档 (LangRef/Passes/Bufferization/...)"
    entry = groups[group]
    entry[0] += prose_chars
    entry[1] += code_lines
    entry[2] += 1

print(f"{'section':46s} {'files':>5s} {'pages':>7s}")
total = 0
for group, (chars, code_lines, count) in sorted(groups.items(),
                                                key=lambda kv: -(kv[1][0] / PROSE_CHARS_PER_PAGE
                                                                 + kv[1][1] / CODE_LINES_PER_PAGE)):
    pages = chars / PROSE_CHARS_PER_PAGE + code_lines / CODE_LINES_PER_PAGE
    total += pages
    print(f"{group:46s} {count:5d} {pages:7.0f}")
print(f"{'TOTAL':46s} {sum(v[2] for v in groups.values()):5d} {total:7.0f}")
print()
print("heaviest single pages:")
for pages, rel in sorted(per_file, reverse=True)[:8]:
    print(f"  {pages:6.0f} pages  {rel}")
print()
sheets = total / 2
print(f"double-sided sheets : {sheets:,.0f}")
print(f"paper weight (~80gsm, 5 g/sheet) : {sheets * 5 / 1000:.1f} kg")
print(f"2-up duplex (2 pages per side)   : {total / 4:,.0f} sheets")
