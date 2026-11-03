# MLIR docs - offline copy

Static mirror of <https://mlir.llvm.org/docs/> (the whole documentation tree), generated on
2026-11-03 with `crawl_mlir_docs.py`.

| what | where | notes |
| --- | --- | --- |
| browsable HTML mirror | `site/docs/index.html` | 124 pages, 40.8 MB |
| Markdown, one file per page | `markdown/` | 6.2 MB |
| everything in one file | `ALL_DOCS.md` | good for LLM input / grep |
| per-URL status log | `crawl_report.txt` | |
| bilingual print edition (中英对照) | `print/` | 6 册（vol4 拆三卷）+ 合集，见 `print/README-print.md` |
| 校验与打包脚本 | `tools/` | 11 个脚本，见 `tools/README.md` |

## How to read it

* **Browser**: open `site/docs/index.html` (or `site/index.html`) straight from
  disk - links, sidebar navigation, CSS and code highlighting all work offline
  over `file://`, no web server needed.

  ```bash
  xdg-open site/docs/index.html      # or: firefox site/docs/index.html
  # optional, if you prefer http:
  python3 -m http.server 8000 -d site
  ```

* **Editor / grep / LLM**: use `markdown/` or `ALL_DOCS.md`.

  ```bash
  grep -rn "Bufferization" markdown/ | head
  ```

## Regenerating / updating

```bash
python3 crawl_mlir_docs.py                # full refresh (HTML + Markdown)
python3 crawl_mlir_docs.py --no-markdown  # HTML mirror only
python3 crawl_mlir_docs.py --max-pages 5  # quick smoke test
python3 make_printable.py                 # rebuild print/ (bilingual edition)
```

Only `/docs/**` is mirrored. Links to other parts of the site
(`/getting_started/`, `/doxygen/`, `/python-bindings/`, GitHub, ...) are kept as
absolute URLs pointing at <https://mlir.llvm.org> so they still work while you are online.
To mirror more of the site, widen the scope test in `crawl_pages()`.
