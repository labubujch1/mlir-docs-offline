import re
import sys

path = sys.argv[1]
needle = sys.argv[2]
html = open(path, encoding="utf-8", errors="ignore").read()
for match in re.finditer(re.escape(needle), html):
    start = max(0, match.start() - 120)
    print(repr(html[start:match.end() + 60]))
    print("-" * 70)
