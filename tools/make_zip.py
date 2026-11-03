"""Zip the whole project folder for transfer to Windows.

    python3 tools/make_zip.py                       # 自动选目标（Windows 桌面 → 项目根）
    python3 tools/make_zip.py --dest-dir /tmp/out   # 指定目录
    python3 tools/make_zip.py --name my.zip
"""

import argparse
import sys
import time
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
CANDIDATE_DIRS = [
    Path("/mnt/c/Users/jinch/OneDrive/Desktop"),
    Path("/mnt/c/Users/jinch/Desktop"),
]


def pick_dest_dir(explicit: str) -> Path:
    if explicit:
        return Path(explicit)
    for candidate in CANDIDATE_DIRS:
        if candidate.is_dir():
            return candidate
    return SRC.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 mlir-docs-offline 目录")
    parser.add_argument("--dest-dir", default="", help="输出目录")
    parser.add_argument("--name", default=f"mlir-docs-offline-{time.strftime('%Y%m%d')}.zip")
    args = parser.parse_args()

    dest_dir = pick_dest_dir(args.dest_dir)
    if not dest_dir.is_dir():
        sys.exit(f"! 目标目录不存在: {dest_dir}")
    dest = dest_dir / args.name

    files = [p for p in sorted(SRC.rglob("*"))
             if p.is_file() and "__pycache__" not in p.parts]
    total = sum(p.stat().st_size for p in files)
    print(f"packing {len(files)} files ({total / 1e6:.1f} MB) -> {dest}")

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6,
                         allowZip64=True) as archive:
        for index, path in enumerate(files, 1):
            # 顶层目录名固定为 mlir-docs-offline/，解压后结构干净
            archive.write(path, (Path("mlir-docs-offline") /
                                 path.relative_to(SRC)).as_posix())
            if index % 50 == 0:
                print(f"  ... {index}/{len(files)}")

    with zipfile.ZipFile(dest) as archive:
        bad = archive.testzip()
        entries = len(archive.namelist())

    print(f"\nzip entries : {entries}")
    print(f"zip size    : {dest.stat().st_size / 1e6:.1f} MB "
          f"({dest.stat().st_size / total * 100:.0f}% of original)")
    print(f"integrity   : {'OK' if bad is None else 'CORRUPT at ' + bad}")
    return 0 if bad is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

