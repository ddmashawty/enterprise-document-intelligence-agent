# 广东四校计算机考研信息 Agent（Document Intelligence Agent）

查询中山大学、华南理工大学、暨南大学、华南师范大学泛计算机类 37 个硕士专业的招生计划、复试线、初试科目和推免数。每个数字都带**年份、口径和官方来源**；官方没给的写“未知 / 未取得”，不猜、不拿第三方聚合站的数字补。名单类文件只给统计，不输出姓名、考生编号或个人成绩。

原来的企业文档问答保留为**通用文档模式**：PDF、Word、txt、Markdown 导入后检索、对比、抽取，并导出 Markdown / Excel。

作者：的懒

## 能做什么

- **结构化库**：`data/kaoyan.db`（SQLite），由人工核对的 `data/kaoyan/majors.csv` 种子和官方文档的规则抽取生成。同一事实的多个口径（目录总数、学院细则公开招考、学校统考可用计划……）并列保存，冲突只记录不覆盖。
- **多格式解析**：PDF（含表格）、`.docx`、txt、Markdown、HTML、xlsx / xls、图片。图片和扫描页可选 OCR（`rapidocr` 本地识别或 OpenAI 兼容的多模态模型），表格按线框还原，合并单元格展开。
- **检索**：Ollama `qwen3-embedding:0.6b`（Chroma）与 BM25 混合检索，按学校 / 年份 / 文档类型过滤；未配置向量服务时退回 BM25。
- **Agent**：LangGraph 图 `plan → act → reflect`，最多 5 轮工具调用。考研问题优先查结构化库，答案里的数字要和工具结果对得上（数字校验），并给出来源。
- **采集**：礼貌抓取四校研招网（遵守 robots.txt，同一主机串行、间隔 ≥3 秒，单次有页数上限，不绕过登录或验证码），新文档登记进库，按 304 / sha256 / 正文指纹识别是否更新。
- **界面**：FastAPI 服务，外加 Streamlit 演示页（对话、专业筛选、知识库、任务中心、演示剧本）。

## 环境

- Python 3.12
- DeepSeek API Key（`deepseek-chat`）
- 可选：本机 Ollama，并已拉取 `qwen3-embedding:0.6b`

## 启动

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -r requirements-embedding.txt

cp .env.example .env
# 填写 LLM_API_KEY
# ollama pull qwen3-embedding:0.6b

# 考研数据：校验种子包 → 建结构化库 → 规则抽取 → 建考研索引（都可重复执行）
PYTHONPATH=src python scripts/verify_kaoyan_bundle.py
PYTHONPATH=src python scripts/seed_kaoyan.py
PYTHONPATH=src python scripts/extract_kaoyan.py
PYTHONPATH=src python scripts/ingest_kaoyan.py

# 通用文档模式的企业演示语料
bash scripts/demo_repro.sh

PYTHONPATH=src python -m uvicorn doc_agent.api:app --host 127.0.0.1 --port 8000
```

### 可选：OCR（图片表格、扫描 PDF）

```bash
pip install -r requirements-ocr.txt          # rapidocr_onnxruntime，模型随包，不需联网下载
PYTHONPATH=src python scripts/extract_kaoyan.py --ocr rapidocr
```

- `.env` 里设 `OCR_BACKEND=rapidocr` 后，导入和抽取都会识别图片 / 扫描页；结果按图片 sha256 缓存在 `data/kaoyan/ocr_cache/`（不入库）。
- `OCR_BACKEND=vision` 走 OpenAI 兼容的多模态接口，需要填 `VISION_BASE_URL`、`VISION_MODEL`、`VISION_API_KEY`（`deepseek-chat` 不能看图）。
- OCR 抽出的事实标 `extraction_method=ocr`，只有和人工种子同键同值时才算已核对（`verified=1`），其余保持 `verified=0`。
- 名单类文件（`sources.json` 里 `contains_personal_data=true`）不做 OCR 入库；只能用 `scripts/roster_stats.py --doc <doc_id>` 统计每个专业代码的行数，输出里没有任何个人信息。

### 可选：采集官方网站

```bash
PYTHONPATH=src python scripts/crawl_kaoyan.py --school jnu --mode probe              # 默认 dry run，只列出要抓什么
PYTHONPATH=src python scripts/crawl_kaoyan.py --school jnu --mode probe --no-dry-run
```

华工 `yanzhao.scut.edu.cn` 需要统一认证，会被标为 `blocked`，不会重试；这类文件手动下载后用 `--import` 登记。

另开一个终端启动界面：

```bash
bash scripts/run_frontend.sh
```

- 接口文档：http://127.0.0.1:8000/docs
- 演示界面：http://127.0.0.1:8501（“专业筛选”页调 `/v1/programs`，表格列出口径和来源链接；“演示剧本”是 18 条考研验收问句，企业演示问句放在“通用文档模式”里）

界面标题下会显示当前 API 地址，默认是 `http://127.0.0.1:8000`。若 8000 上不是本服务，而 8001 上是，界面会改连 8001 并提示。请求体里的 `message` 只写一层字符串。

本机演示没有登录。不要把 API 或 Streamlit 暴露到公网。

## 调用示例

```bash
curl -s localhost:8000/health | python3 -m json.tool

curl -s localhost:8000/v1/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","message":"中大计算机学院 085404 的 2026 复试线是多少？"}'

curl -s 'localhost:8000/v1/programs?is_408=true&study_mode=全日制&min_public_plan=20' | python3 -m json.tool
curl -s 'localhost:8000/v1/score-lines?school=华师&code=085404' | python3 -m json.tool

curl -s localhost:8000/v1/chat/async -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","message":"把四校 085404 的复试线和计划导出 Excel"}'
# 用返回的 task_id 轮询 GET /v1/tasks/<task_id>

# 通用文档模式
curl -s localhost:8000/v1/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-2","message":"演示产品手册里 TopK 是多少？"}'
```

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 状态、模型是否配置、检索后端、切片数；考研库存在时加 `kaoyan_db`、`programs`、`documents` |
| POST | `/v1/ingest` | 按路径导入文档（含 `data/kaoyan/raw`），`reindex` 可清空后重建 |
| POST | `/v1/chat` | 同步问答 |
| POST | `/v1/chat/async` | 异步排队，返回 `task_id` |
| GET | `/v1/tasks` | 任务列表，可用 `session_id` 过滤 |
| GET | `/v1/tasks/{task_id}` | 回答、plan、trace、引用、导出 |
| GET | `/v1/sessions/{session_id}` | 会话轮次与近期任务 |
| GET | `/v1/programs` | 专业筛选：`school`、`college`、`code`、`name_kw`、`degree_type`、`study_mode`、`exam_subject`、`is_408`、`min_public_plan`、`year`；每条事实带口径和来源，判不了的放进 `unknown` 并说明原因 |
| GET | `/v1/programs/{program_id}` | 一个专业的全部事实（计划、复试线、科目、方向、统计） |
| GET | `/v1/score-lines` | 复试线：`school` 必填，可选 `code`、`college`、`year`（默认 2026） |
| GET | `/v1/documents` | 来源文档元数据，可按 `school`、`doc_type`、`year` 过滤；不提供名单类文件内容 |
| GET | `/v1/documents/{doc_id}` | 单个文档元数据和事实数 |
| POST | `/v1/crawl` | 启动采集任务 `{schools, mode: probe/list/full, dry_run: true, max_pages}`，返回 `run_id` |
| GET | `/v1/crawl/{run_id}` | 采集任务状态与统计 |

错误格式：`{"error":{"code":"...","message":"...","details":...}}`。

## 目录

```
src/doc_agent/
  agent/     LangGraph 规划、执行、反思；考研意图识别与数字校验
  tools/     检索、解析、对比、导出；考研结构化查询
  ingest/    多格式加载（PDF / DOCX / HTML / xlsx / 图片）、表格还原、OCR、切片、脱敏
  kaoyan/    结构化库、种子导入、规则抽取、名单统计
  collect/   礼貌爬虫、站点适配、变更检测
  rag/       混合检索
  memory/    会话记忆与 SQLite 轨迹
  api/       FastAPI
frontend/    Streamlit 演示界面
data/kaoyan/ 考研种子包（来源清单、人工核对数据、原始文件）
data/raw/    通用文档模式的演示文档
```

旧版 `.doc` 不支持，请另存为 `.docx`。

## 测试

```bash
PYTHONPATH=src pytest -q                                   # 不联网、不调真实 LLM；缺本地专用文件的用例自动 skip
PYTHONPATH=src python scripts/eval_extraction.py --ocr rapidocr   # 抽取 vs 种子 → docs/kaoyan_extraction_report.md
PYTHONPATH=src python scripts/smoke_kaoyan.py              # 18 条考研验收问答（需要 LLM_API_KEY）
PYTHONPATH=src python scripts/smoke_chat.py                # 通用文档模式
```

人工验收清单：`docs/frontend_verification_checklist.md`、`docs/backend_verification_checklist.md`；考研各阶段说明见 `docs/kaoyan_phase*_notes.md`。

## 配置

密钥只放 `.env`，不要提交。常用项见 `.env.example`：`LLM_API_KEY`、`EMBEDDING_BASE_URL`、`KAOYAN_DB`、`RAG_PROFILE`、`OCR_BACKEND`、`VISION_*`、`CRAWL_*`、`CHUNK_SIZE`、`TOP_K`、`MAX_TOOL_CALLS`。

`data/chroma*`、`data/kaoyan.db`、`data/memory.db`、`data/exports`、`data/uploads`、`data/kaoyan/cache`、`data/kaoyan/ocr_cache`、名单类文件和大于 3MB 的文件不入库。
