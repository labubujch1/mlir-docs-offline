"""检查 sitemap 里的每个 /docs/ URL 是否都在本地镜像里（防漏页）。

    python3 tools/check_sitemap_coverage.py                 # 现抓 sitemap
    python3 tools/check_sitemap_coverage.py sitemap.xml     # 用本地文件
"""

import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "site"
SITEMAP_URL = "https://mlir.llvm.org/sitemap.xml"


def load_sitemap(path: str) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    print(f"下载 {SITEMAP_URL} …")
    with urllib.request.urlopen(SITEMAP_URL, timeout=30) as response:
        return response.read().decode("utf-8")


def main(argv: list[str]) -> int:
    xml = load_sitemap(argv[0] if argv else "")
    locs = sorted({u for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
                   if urlsplit(u).path.startswith("/docs/")})

    missing = []
    for url in locs:
        path = urlsplit(url).path
        if not path.endswith("/"):
            path += "/"
        if not (SITE_DIR / (path.lstrip("/") + "index.html")).is_file():
            missing.append(url)

    print(f"sitemap /docs/ urls : {len(locs)}")
    print(f"missing from mirror : {len(missing)}")
    for url in missing:
        print("  MISSING", url)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

