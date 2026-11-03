"""Measure the MLIR docs text volume to estimate printed page counts."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
files = sorted((ROOT / "markdown").rglob("*.md"))

fence = re.compile(r"^```.*?^```", re.S | re.M)
rows = []
total_chars = prose_chars_total = code_lines_total = prose_words_total = 0
code_blocks = 0

for path in files:
    text = path.read_text(encoding="utf-8")
    blocks = fence.findall(text)
    code = "\n".join(blocks)
    prose = fence.sub("", text)
    code_lines = code.count("\n")
    prose_words = len(prose.split())
    rows.append((path.relative_to(ROOT / "markdown").as_posix(),
                 len(text), prose_words, code_lines))
    total_chars += len(text)
    prose_chars_total += len(prose)
    code_lines_total += code_lines
    prose_words_total += prose_words
    code_blocks += len(blocks)

print(f"files            : {len(files)}")
print(f"total chars      : {total_chars:,}")
print(f"prose chars      : {prose_chars_total:,}  ({prose_words_total:,} words)")
print(f"code blocks      : {code_blocks:,}  ({code_lines_total:,} lines)")
print()
print("top 10 pages by size:")
for name, chars, words, code_lines in sorted(rows, key=lambda r: -r[1])[:10]:
    print(f"  {chars:7,} chars {words:7,} words {code_lines:6,} code lines  {name}")
print()

# A4 portrait, 2 cm margins, single column, single-sided:
PROSE_CHARS_PER_PAGE = 3300     # 11 pt body text
CODE_LINES_PER_PAGE = 55        # 9 pt monospace, no wrapping
pages_prose = prose_chars_total / PROSE_CHARS_PER_PAGE
pages_code = code_lines_total / CODE_LINES_PER_PAGE
pages = pages_prose + pages_code
print(f"prose pages (3300 chars/page) : {pages_prose:,.0f}")
print(f"code  pages (55 lines/page)   : {pages_code:,.0f}")
print(f"total single-sided            : {pages:,.0f} pages")
print(f"double-sided sheets (duplex)  : {pages / 2:,.0f} sheets")
print(f"cross-check words/550         : {prose_words_total / 550:,.0f} prose pages")
