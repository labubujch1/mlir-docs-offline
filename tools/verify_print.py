"""Verify the generated print HTML: images, anchors, translation coverage."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRINT = ROOT / "print"

for name in ("vol1-core.html", "vol2-tutorials.html", "vol3-rationale.html",
             "vol4-dialects.html", "all-in-one.html"):
    path = PRINT / name
    text = path.read_text(encoding="utf-8")

    # 1) images resolve
    missing_img = [src for src in re.findall(r'<img[^>]*src="([^"]+)"', text)
                   if not src.startswith(("http", "data:")) and not (PRINT / src).resolve().exists()]

    # 2) every in-document anchor target exists
    ids = set(re.findall(r'id="([^"]+)"', text))
    broken_anchors = sorted({href[1:] for href in re.findall(r'href="#([^"]+)"', text)
                             if href.lstrip("#") not in ids})

    h1 = len(re.findall(r"<h1 ", text))
    h2 = len(re.findall(r"<h2 ", text))
    translated = len(re.findall(r'class="en"', text))

    print(f"{name}")
    print(f"   h1={h1:4d} h2={h2:4d} translated={translated:4d} "
          f"coverage={translated / max(1, h1 + h2) * 100:.0f}%")
    print(f"   missing images={len(missing_img)}  broken anchors={len(broken_anchors)}")
    for item in missing_img[:3]:
        print(f"      img {item}")
    for item in broken_anchors[:5]:
        print(f"      anchor #{item}")
