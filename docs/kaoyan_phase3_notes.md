# 考研改造 K3：检索元数据 + 考研索引说明

- **日期：** 2026-09-28
- **分支：** `feat/kaoyan`
- **范围：** 不联网、不调 LLM；考研文档单独建索引（`data/chroma_kaoyan/`、collection `kaoyan_docs`），每个 chunk 带来源元数据，检索可按学校 / 年份 / 文档类型过滤；企业语料的行为不变

## 交付项

| 能力 | 实现 |
|------|------|
| chunk 元数据 | `ingest/chunking.py`：`TextChunk` 加可选 `doc_id / school / college / year / doc_type / title / url / redacted`；`metadata()` 只返回非空字段（企业 chunk 为空） |
| 按行切表 | `chunk_document(..., meta=, table_rows=True)`：表外文字照旧切，表格按行装块；每块重复“文档标题 + 表名（表前像标题的一行，如“…如下：”）+ 表头”；暨南目录这类三级表，块开头再带上当前学院行、专业行 |
| 表头识别 | `table_header_rows`：前 8 行里第一段“全是标签、没有纯数字 / 代码开头”的行，最多连续 3 行（中大细则的双层表头）；表内重复出现的表头行跳过 |
| chunk_id | 考研 chunk 用 `doc_id` 前缀：`jnu-016::p1::c174`；企业仍是文件名前缀 |
| 存储 | `rag/store.py`：元数据写进 `chunks.jsonl` 和 Chroma metadata；`search(..., school=, year=, doc_type=)` 在 BM25 和 Chroma（`where` + 结果再过滤）两路都生效；`Hit.metadata`（为空时 `to_dict()` 不输出） |
| profile | `get_store(settings, profile="enterprise"|"kaoyan")`，按 (profile, 目录, collection) 缓存；`Settings.for_profile()`；`reset_store(profile)` |
| 查询扩展 | `rag/query_expand.py`：企业规则原样；考研 profile 把学校全称（中大 → 中山大学）和意图词（复试线 / 招生人数 / 推免 / 初试科目 / 方向导师 / 学费）拼在原问题后面；问题里只出现一所学校时自动按该校过滤 |
| 排序先验 | 仅考研 profile：名单类 chunk（`redacted`）× 0.5；文档类型与意图匹配（问复试线 → 复试细则 / 分数线文件）× 1.2；chunk 所属学院名出现在问题里 × 1.2；候选池放大到 `max(8k, 60)` |
| 导入 | `kaoyan/index.py` `ingest_kaoyan()` + `scripts/ingest_kaoyan.py [--reindex] [--no-embed] [paths…]`：按 `sources.json` 给每个文件带元数据，经 `load_document`（抽表 + 脱敏）后按行切表入库；报告 `docs_missing`（清单里有但本机缺）和 `docs_unlisted` |
| 工具 | `rag_search` 加可选 `school / year / doc_type`：给了任一过滤条件就查考研索引，否则用 `RAG_PROFILE`（默认 enterprise）；`list_documents` 同样按 `RAG_PROFILE` |
| 配置 | `KAOYAN_CHROMA_DIR=data/chroma_kaoyan`、`KAOYAN_COLLECTION=kaoyan_docs`、`RAG_PROFILE=enterprise`；根 `.gitignore` 早已包含 `data/chroma_kaoyan/` |
| 脱敏补强 | 按单元格切块会绕过页面级兜底，所以 `redact_document` 把兜底（已知姓名、15 / 18 位号码、“拟录取X等N人”）落到每个单元格；姓名编译成一个正则，一次替换 |

## 设计要点

- **企业语料零变化：** 企业路径不传 `meta`、不开 `table_rows`，切块、chunk_id、`chunks.jsonl` 字段、查询扩展、候选池、排序都走原逻辑。
- **考研扩展拼接而不单独成查询：** 企业扩展是独立查询（“主营业务分行业”），考研如果单独查“复试分数线”会把四校的分数线都拉进来，所以拼在原问题后面，保留专业代码等具体信息。
- **名单降权不过滤：** 名单只用于统计，很少能回答问题，但每行都重复专业代码，BM25 分数很高。降权后仍可检索到（比如问“拟录取多少人”时）。
- **自动推断学校：** 与企业的 `infer_doc_name` 对应；问题里出现两所及以上学校（“对比四校”）时不过滤。

## 验收结果

**正式索引**（`python scripts/ingest_kaoyan.py --reindex`，本机 Ollama `qwen3-embedding:0.6b`）：

```
90 indexed · 0 failed · 7 needs_ocr · 26 redacted · missing scut-044（29MB 扫描件，本机没有）
1926 chunks · hybrid(qwen3-embedding:0.6b+bm25) · 2 分 39 秒
```

**企业语料不变：** 改动前后各把 `data/raw` 导入临时 BM25 库（8 个文档、14705 个 chunk）：`chunks.jsonl` 逐字节相同；`sample_qa` 3 题 + 5 个补充问题的 top-8 结果与分数完全一致，`rag_search` 工具输出逐字节相同。

**golden 18 题检索（来源文档是否进前 5）：**

| 索引 | hit@5 | 未命中 |
|------|-------|--------|
| 纯 BM25 | 16 / 18 | #6 华工 140500（来源是图片，K7 OCR 后才有文字）；#17 名单查人（名单本身被降权，排第一的是该名单的公示通知，属设计如此） |
| hybrid | 15 / 18 | #6；#13 中大 2027 年 085404（2027 目录未发布，向量召回偏向免试生目录）；#14 华师 0839（排前面的是全校推免目录，同样能看出没有 0839） |

调参过程：最初 BM25 下名单 chunk 占满前几名（中大计算机学院 379 的细则排第 5）；加名单降权 + 文档类型先验后排第 1；#9 华师人工智能学院 085410 靠学院先验 + 放大候选池解决。

**泄漏扫描：** 从 26 个名单原表收集 4187 个姓名，扫描正式索引全部 1926 个 chunk：801 个名单 chunk 里名单自身姓名 0 泄漏，全库 0 个 15 位编号。另有 10 处跨文件撞名：某位中大考生的姓名等于一个省份名，而华工推免名单的“本科院校”列里有该省份开头的大学名（同一行考生已是“某”字打码），不是泄漏。

## 测试

```bash
PYTHONPATH=src pytest -q          # 113 passed（原 100 + 新 13）
```

- `tests/test_kaoyan_retrieval.py`（13）：用 7 个已入库夹具建临时索引（纯 BM25，约 2 s）——元数据与 doc_id 前缀；`school='jnu'` 只回暨南、别名“暨大”结果相同；问题里的学校自动过滤；`year=2027 + doc_type='catalog'` 命中 2027 目录且块里带学院行；表格块保留表头（暨南目录、中大细则双层表头、华师推免 xls）；`rag_search` 带过滤走考研索引、不带过滤仍走企业索引；合成名单：`redacted` 标记、脱敏、降权；表头识别 / 上下文行单测；企业 chunk / 行字段 / `Hit.to_dict` / `list_documents` 不变；两个 profile 的查询扩展；先验系数；profile 与缓存。
- `tests/test_redact.py` 本地泄漏测试同时检查表格单元格（K3 直接用单元格切块）。

## 说明

- `POST /v1/ingest` 仍写企业索引（K2 行为不变）；考研索引只由 `scripts/ingest_kaoyan.py` / `ingest_kaoyan()` 构建。
- 带向量的全量导入受 Ollama 速度限制（约 2.5 分钟 / 1926 chunk）；`--no-embed` 纯 BM25 约 30 s。
- 表格上下文行的判定依赖“3 位学院代码 / 6 位专业代码开头 + 值少于列数一半”，对很窄的表（≤3 列）不生效，这类表本来就很短。
