"""Inventory all headings in the Markdown export."""

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEAD = re.compile(r"^(#{1,6})\s+(.*)\s*$", re.M)

by_level = Counter()
per_file = []
lines = []
for path in sorted((ROOT / "markdown").rglob("*.md")):
    rel = path.relative_to(ROOT / "markdown").as_posix()
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)     # ignore code blocks
    heads = [(len(m.group(1)), m.group(2).strip()) for m in HEAD.finditer(text)]
    for level, title in heads:
        by_level[level] += 1
        lines.append(f"{rel}\t{level}\t{title}")
    per_file.append((len(heads), rel))

print(f"total headings: {sum(by_level.values()):,}")
for level in sorted(by_level):
    print(f"  h{level}: {by_level[level]:,}")
print()
print("files with most headings:")
for count, rel in sorted(per_file, reverse=True)[:8]:
    print(f"  {count:5,}  {rel}")

Path("/tmp/headings.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\nwrote /tmp/headings.tsv")

# how many h1/h2/h3 are plain prose (no backticks / identifiers) ?
plain = [line for line in lines
         if int(line.split("\t")[1]) <= 3 and "`" not in line.split("\t")[2]]
print(f"h1-h3 without code identifiers: {len(plain):,}")
