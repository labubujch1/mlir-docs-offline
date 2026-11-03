"""crawl_mlir_docs 的辅助函数单元测试（属性重写 + Markdown 转换）。

    python3 tools/test_helpers.py        # 全部 PASS 时退出码为 0
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import crawl_mlir_docs as m

m.register_url("https://mlir.llvm.org/docs/Bindings/", "docs/Bindings/index.html")
m.register_url("https://mlir.llvm.org//mlir-logo.png", "mlir-logo.png")
m.register_url("https://mlir.llvm.org/css/theme.css", "css/theme.css")

sample = (
    '<link rel=stylesheet href=https://mlir.llvm.org/css/theme.css>'
    '<img src=https://mlir.llvm.org//mlir-logo.png width=40px>'
    '<a href=/docs/Bindings/>Bindings</a>'
    '<a href=https://mlir.llvm.org/getting_started/Faq/>FAQ</a>'
    '<code>emitc.verbatim "#pragma my src="{}" dst={}" %src</code>'
    '<pre class=chroma><code>x = src="a"\ny = "</code></pre>'
    '<script>var t = `<a href="/docs/Bindings/">`;</script>'
)
out = m.rewrite_html(sample, "https://mlir.llvm.org/docs/Tools/", "docs/Tools/index.html")
print(out)
checks = {
    "css relative": '../css/theme.css' in out,
    "logo relative": '../mlir-logo.png' in out,
    "docs link relative": 'href="../Bindings/index.html"' in out,
    "out-of-scope goes online": 'https://mlir.llvm.org/getting_started/Faq/' in out,
    "inline code untouched": 'src="{}" dst={}' in out,
    "pre untouched": 'x = src="a"' in out,
    "script untouched": '<a href="/docs/Bindings/">' in out,
}
for name, ok in checks.items():
    print(("PASS  " if ok else "FAIL  ") + name)

# markdown conversion sanity
md = m.html_to_markdown(
    "<main><h1>Title</h1><p>Some <strong>bold</strong> text with "
    '<a href="#x">anchor</a>.</p><ul><li><p>one</p></li><li>two</li></ul>'
    '<pre class="chroma"><code class="language-cpp">int x = 1 &amp;&amp; 2;\n</code></pre>'
    '<h2>Usage <a href="#usage">¶</a></h2><table><tr><th>a</th><th>b</th></tr>'
    "<tr><td>1</td><td>2</td></tr></table></main>"
)
print("---- markdown ----")
print(md)
md_checks = {
    "heading": md.startswith("# Title"),
    "bold": "**bold**" in md,
    "bullets": "- one" in md and "- two" in md,
    "no blank line in li": "- one\n" in md,
    "code fence": "```cpp\nint x = 1 && 2;" in md,
    "permalinks dropped": "¶" not in md,
    "table": "| a | b |" in md and "| 1 | 2 |" in md,
}
for name, ok in md_checks.items():
    print(("PASS  " if ok else "FAIL  ") + name)

# ---- path safety: review findings from copilot (Major 1 / Minor 6) ----
path_checks = {
    "docs url": m.site_rel_path("https://mlir.llvm.org/docs/Bindings/")
                == "docs/Bindings/index.html",
    "external host": m.site_rel_path("https://cdn.example.com/lib.min.js")
                     == "_external/cdn.example.com/lib.min.js",
    "colon in path": m.site_rel_path("https://cdn.example.com/a:b/c.js")
                     == "_external/cdn.example.com/a_b/c.js",
    "dot segments": m.safe_path("/docs/./Foo/../Bar/index.html") == "docs/Bar/index.html",
    "escape rejected": m.safe_path("/../etc/passwd") == "",
    "reserved name": m.safe_segment("CON") == "_CON",
    "trailing dot": m.safe_segment("name.") == "name",
}

import tempfile
from pathlib import Path as _Path

with tempfile.TemporaryDirectory() as tmp:
    root = _Path(tmp)
    m.write_bytes(root, "a/b.txt", b"hi")
    path_checks["atomic write"] = (root / "a/b.txt").read_bytes() == b"hi"
    path_checks["no .part left"] = not list(root.rglob("*.part"))
    try:
        m.write_bytes(root, "../escape.txt", b"x")
        path_checks["traversal blocked"] = False
    except ValueError:
        path_checks["traversal blocked"] = True

for name, ok in path_checks.items():
    print(("PASS  " if ok else "FAIL  ") + name)

# ---- CLI validation: review finding Major 2 ----
cli_checks = {}
for bad in (["--jobs", "0"], ["--batch", "0"], ["--max-pages", "-1"]):
    try:
        m.main(bad + ["--no-markdown"])
        cli_checks[f"reject {' '.join(bad)}"] = False
    except SystemExit:
        cli_checks[f"reject {' '.join(bad)}"] = True

for name, ok in cli_checks.items():
    print(("PASS  " if ok else "FAIL  ") + name)

# ---- check_mirror 解析器的回归测试（copilot 复查指出的两处）----
import check_mirror as c

with tempfile.TemporaryDirectory() as tmp:
    page = _Path(tmp) / "p.html"
    page.write_text(
        '<div data-id="ghost"></div>'
        '<code>id=id</code>'
        '<h2 id=real>t</h2>'
        '<!-- id = "note" -->'
        '<pre>id=fake</pre>',
        encoding="utf-8")
    found = c.ids_of(page)
    parser_checks = {
        "real id 保留": "real" in found,
        "data-id 不算": "ghost" not in found,
        "code 里的 id= 不算": "id" not in found,
        "注释里的 id 不算": "note" not in found,
        "pre 里的 id= 不算": "fake" not in found,
        "data URL 跳过": c.urls_in("data:image/png;base64,AAAA") == [],
        "srcset 正常拆分": c.urls_in("a.png 1x, b.png 2x", True) == ["a.png", "b.png"],
        "srcset 里的 data URL 整体跳过":
            c.urls_in("a.png 1x, data:image/png;base64,X 2x", True) == [],
        "普通 URL 不被逗号拆开": c.urls_in("https://x/y.png") == ["https://x/y.png"],
    }

for name, ok in parser_checks.items():
    print(("PASS  " if ok else "FAIL  ") + name)

all_ok = all(list(checks.values()) + list(md_checks.values())
             + list(path_checks.values()) + list(cli_checks.values())
             + list(parser_checks.values()))
sys.exit(0 if all_ok else 1)
