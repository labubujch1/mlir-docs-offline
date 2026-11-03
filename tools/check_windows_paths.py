"""Scan the mirror for path names that Windows cannot create."""

import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
ILLEGAL = re.compile(r'[<>:"\\|?*\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}

bad = []
for path in sorted(SRC.rglob("*")):
    rel = path.relative_to(SRC)
    for part in rel.parts:
        if ILLEGAL.search(part):
            bad.append((str(rel), part))
            break
        if part.rstrip(". ") != part:
            bad.append((str(rel), f"trailing dot/space: {part!r}"))
            break
        if part.split(".")[0].upper() in RESERVED:
            bad.append((str(rel), f"reserved name: {part!r}"))
            break

print(f"problem paths: {len(bad)}")
for rel, why in bad[:40]:
    print(f"  {rel}\n      <- {why}")
sys.exit(1 if bad else 0)
