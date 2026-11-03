"""Flatten the Markdown export to plain text for a groff page-count check."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path("/tmp/all_docs_plain.txt")

parts = []
for path in sorted((ROOT / "markdown").rglob("*.md")):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)          # source comment
    text = re.sub(r"^```.*$", "", text, flags=re.M)             # fence markers
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)       # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)        # links
    text = re.sub(r"[*_`]{1,3}", "", text)                      # emphasis / code ticks
    text = re.sub(r"^#+\s*", "", text, flags=re.M)              # heading marks
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    parts.append(text)

body = "\n\n.ps 11\n.sp 2\n" + "\n\n.sp 2\n".join(parts) + "\n"
OUT.write_text(body, encoding="utf-8")
print(f"plain text: {OUT} ({OUT.stat().st_size:,} bytes, {body.count(chr(10)):,} lines)")
