# 考研改造 K2：多格式解析层说明

- **日期：** 2026-09-28
- **分支：** `feat/kaoyan`
- **范围：** 不联网、不调 LLM；把 `data/kaoyan/raw` 里的 html / pdf / xlsx / xls / 图片都解析成“文本 + 表格 + 图片”，个人信息在进入下游之前脱敏

## 交付项

| 能力 | 实现 |
|------|------|
| 表格模型 | `ingest/tables.py`：`Table(cells, source, page, index, title, bbox, origins)`；合并单元格展开到每个位置，`origins` 记录来源格；`row_values` 去掉横向合并的重复值；`find_rows` / `column_index`（忽略空格）/ `ffill` / `drop_columns`；`split_blocks` 按空行切块，单值行当标题 |
| 解析结果 | `ingest/loaders.py`：`ParsedDocument(LoadedDocument)` 多了 `tables / images / meta`；`meta["prose"]` 保存带 `[[TABLE:n]]` 占位的页文本，脱敏后可重新渲染；`needs_ocr` / `ocr_pages` |
| HTML | `parse_html`：`<meta charset>` → utf-8 → gb18030 解码；去掉导航 / 页脚类元素（内部没有表格的才删）；只取叶子表格（华师目录的外层布局表跳过）；data URI 图片解码并算 sha256 |
| PDF | 默认仍用 pypdf 文本（企业索引不变）；`tables=True`（`data/kaoyan/` 下的文件）用 pdfplumber `find_tables`，纵向合并的空格按覆盖它的格子补值，表外文字 + 渲染后的表格组成页文本；无字符层但有图片的页进 `ocr_pages`，不再抛错 |
| 表格文件 | `load_xlsx`（openpyxl `data_only`，合并区域展开）、`load_xls`（xlrd `formatting_info=True`）；每个 sheet 一页，页首 `[sheet 名]` |
| 图片 | `load_image`：`.jpg/.jpeg/.png` 只记 `ImageRef`（sha256、mime），`needs_ocr=True` |
| OCR 接口 | `ingest/ocr.py`：`OCRBackend` 协议 + `NoOCR`；`get_ocr_backend("none")`；`rapidocr` / `paddleocr` / `vision` 留到 K7，现在报 “not implemented yet” |
| 脱敏 | `ingest/redact.py`：表头识别（`姓名` / `考生姓名`；`考生编号` / `准考证号` / `身份证号` 等，括号说明忽略），姓名列 → 姓+某（含复姓），编号列整列删除；续页无表头的表沿用同列数的上一张表头；文本兜底：已见姓名全部替换，15 位 / 18 位编号删除，“拟录取X等N人”首名打码 |
| 脱敏触发 | `kaoyan/privacy.py` 读 `sources.json` 的 `contains_personal_data`（按 mtime 缓存）；或任意文件里出现“姓名列 + 编号列”的表（自动识别，企业目录下同样生效） |
| 统一入口 | `ingest/pipeline.load_document(path, settings)`：ingest 和 `parse_document` 工具都走它，策略只写一处 |
| 附件发现 | `collect/attachments.py`：`discover_attachments(html, base_url)` → `Attachment(url, name, kind, ext, mime, sha256, data)`；支持 `<base>`、`div[pdfsrc]` + `sudyfile-attr` 标题、`<a href>`（URL / 锚文本 / sudy 标题任一带扩展名）、`<img>`、data URI（按 sha256 去重） |
| 配置 / 接口 | `OCR_BACKEND=none`；`IngestResponse` 加 `docs_needs_ocr: list[str]`、`docs_redacted: int`（旧字段不变） |
| 依赖 | `pdfplumber`、`beautifulsoup4`、`lxml`、`xlrd`（`requirements.txt` 与 `requirements-embedding.txt` 同步） |

## 设计要点

- **不改旧接口：** `load_file(path)` 仍然可用，返回的 `ParsedDocument` 是 `LoadedDocument` 子类；`.doc` 仍抛错；`tests/test_docx_loader.py` 未改。
- **企业语料不受影响：** `data/raw` 只有 pdf / txt；PDF 默认不抽表，文本与改动前一致。新后缀只有 html / xlsx / xls / 图片，`.csv` 仍跳过（`majors.csv` 是种子，不是文档）。
- **表格渲染：** 一行一行 `" | "` 连接，横向合并只出现一次，空格略去。例：`085404 | 计算机技术（全日制） | 69 | 不分方向 | 379 | 50 | 50 | 60 | 60`。
- **needs_ocr 与失败分开：** 能解析出文字的进索引；只有图片的记到 `docs_needs_ocr`；既没字又没图的才进 `docs_failed`（带原因 “No extractable text”）。
- **脱敏先于切片：** 名单类文件在 `load_document` 里就完成脱敏，切片 / 索引 / 工具输出看到的都是“李某”版本；统计抽取（K4）读原文件，只存人数和分数区间。

## 验收结果

`POST /v1/ingest {"paths":["data/kaoyan/raw"],"reindex":true}`，`CHROMA_DIR` 指到临时目录、不开 Embedding（纯 BM25），企业索引未动：

```
status 200 · 28.6s
files 96（html 55 / pdf 28 / xlsx 6 / png 4 / jpg 2 / xls 1）
docs_indexed 90 · docs_failed 0 · docs_needs_ocr 7 · docs_redacted 26
chunks 1344 · 脱敏姓名 5822 处 · 15 位编号 0
```

- `docs_needs_ocr`：6 张图片（华工 2 张表格图 + ft 招生专业图、中大 sse 2 张、sece 内嵌 PNG 另存件）+ `sysu_sece_2026_复试录取实施细则.html`（正文可索引，另带 1 张 data URI 图）。
- `docs_redacted` 26 = manifest 里 27 个 `contains_personal_data` 文件减去本机缺失的华工拟录取扫描件（29MB，lite 包不含）。
- **泄漏扫描：** 从 26 个名单原表收集 4187 个姓名，扫描全部 chunk：名单文件自身 0 泄漏、0 个 15 位编号。全库有 97 个字符串撞上，逐一看过都是公开内容：暨南目录的导师名单（530 处）、华工推免名单里的本科院校名（同一行的考生已是“某”字打码）、中大目录里的科目名。首次扫描发现华工公示正文“拟录取曹某等2582人”的首名（该页未标个人信息），已加“拟录取X等N人”规则并对所有考研文档生效。

## CURSOR_PROMPT K2 断言

| 断言 | 结果 |
|------|------|
| 中大 cse 细则表：085404 计算机技术（全日制）379 / 50 / 50 / 60 / 60 | ✅ |
| 暨南 2027 目录：085412 招生人数 62；052 学院行 116；010 备注“计算机科学与技术指标为24个” | ✅（一张 1082×9 的表，三级行都在） |
| 华师 019 目录：081200 `48(17)`、085404 `50(4)` | ✅（外层布局表跳过，rowspan 科目格铺到 4 个方向行） |
| 华师 2027 推免 xls：前 3 列 ffill 后 085410 → 019 计算机学院 3、041 人工智能学院 8 | ✅ |
| 中大校线 PDF：`学术学位 | 工学[08] | 280 | 45 | 60` | ✅（竖排“学/术/学/位”合并格补齐） |
| sece data URI PNG sha256 `19cedf27…6209`，与另存图片一致 | ✅ |
| 华工 cs 页 2 个 `pdfsrc`：`2026学硕.pdf` / `2026专硕.pdf`，URL 与 sources.json scut-053/054 一致 | ✅ |
| `iter_source_files` 覆盖新后缀，仍跳过 `.csv` | ✅ |

## 测试

```bash
PYTHONPATH=src pytest -q          # 100 passed（原 70 + 新 30）
```

- `tests/test_kaoyan_tables.py`（17）：上面 8 条断言中的解析部分 + 表格工具函数、格内换行拼接、GBK 解码、导航去除、合成的纯图片 PDF → `needs_ocr`、空白 PDF 仍抛错、OCR 后端注册。
- `tests/test_kaoyan_attachments.py`（4）：华工 pdfsrc 命名、sece 相对路径 + data URI、暨南 47 个 UUID 文件名 xlsx 按锚文本命名、手写页面覆盖 `<base>` / javascript / 锚点 / 去重。
- `tests/test_redact.py`（9）：只用“测试甲”这类假名；复姓、表头变体、续页表、文本兜底、公示首名、`load_document` 自动识别；外加一条**本地专用**泄漏测试（名单文件缺失时 skip，失败信息只含计数，不含姓名）。

## 说明

- 性能：暨南 2.4MB 目录 HTML 0.3 s；华工推免名单 PDF（48 张表）抽表约 18 s；全量 96 个文件 ingest 约 29 s。
- 本机 sandbox 下往 `.venv` 装包会报 “Read-only file system”，需要在沙箱外执行 `pip install`。
- 图片内容（华工 / 中大 sse 的分数线、计划表）要到 K7 接入 OCR 才有文字；在那之前这些事实只来自种子（`verified=1`）。
