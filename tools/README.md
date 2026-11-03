# tools/ —— 校验与运维小工具

从项目根目录运行，全部只用 Python 标准库，路径都按脚本位置自动定位。

| 脚本 | 干什么 | 典型用法 |
| --- | --- | --- |
| `verify_print.py` | 检查 `print/` 5 个 HTML：图片是否存在、目录锚点是否都有对应 id、标题数与译名覆盖率 | `python3 tools/verify_print.py` |
| `check_windows_paths.py` | 扫全项目，找 Windows 建不出来的路径（`: * ? " < > |`、结尾点/空格、`CON/PRN/...` 保留名） | `python3 tools/check_windows_paths.py` |
| `check_sitemap_coverage.py` | 拿线上 sitemap 比对本地镜像，确认没有漏页 | `python3 tools/check_sitemap_coverage.py` |
| `gen_todo_h3.py` | 导出还没中文译名的三级标题 → `i18n/todo_h3.tsv`（派活给别的 agent 用） | `python3 tools/gen_todo_h3.py` |
| `heading_inventory.py` | 统计各级标题数量、写 `headings.tsv`（翻译工作量评估） | `python3 tools/heading_inventory.py` |
| `page_estimate.py` | 按字数/代码行估算打印页数（A4 单面/双面） | `python3 tools/page_estimate.py` |
| `page_breakdown.py` | 按 Dialects / Tutorials / Rationale / 核心 分组估算页数 | `python3 tools/page_breakdown.py` |
| `md_to_plain.py` | 把 Markdown 拍平成纯文本（`/tmp/all_docs_plain.txt`），供 groff 实际排版数页数 | `python3 tools/md_to_plain.py` |
| `merge_translations.py` | 校验外部交付的译名表并合并（跳过"中英相同"的标识符条目） | `python3 tools/merge_translations.py --dry-run` |
| `make_zip.py` | 打包整项目到 Windows 桌面（自动跳过 `__pycache__`） | `python3 tools/make_zip.py` |
| `find_context.py` | 在某个文件里定位字符串并打印上下文（排查镜像内容用） | `python3 tools/find_context.py site/docs/X.html 'src="{}"'` |
| `test_helpers.py` | `crawl_mlir_docs.py` 的单元测试：属性重写、代码块保护、Markdown 转换 | `python3 tools/test_helpers.py` |

## 建议的自检顺序

```bash
python3 tools/test_helpers.py            # 1. 抓取器核心逻辑
python3 check_mirror.py                  # 2. 镜像链接完整性
python3 tools/check_sitemap_coverage.py  # 3. 有没有漏页
python3 tools/verify_print.py            # 4. 打印稿图片/锚点
python3 tools/check_windows_paths.py     # 5. 打包前的 Windows 兼容性
python3 tools/make_zip.py                # 6. 出包
```

> 约定：**一次性中间产物**（日志、下载样例、临时正文）走 `/tmp`；
> **可重复使用的脚本**一律放这里，不要在 `/tmp` 里留着。
