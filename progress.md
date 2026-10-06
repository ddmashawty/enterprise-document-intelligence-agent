# 进度日志

## 会话：2026-09-29（考研改造 K5：Agent 工具、提示词、API）

### K5
- **状态：** complete（待提交到 `feat/kaoyan`）
- 新增 `kaoyan/query.py`（查询服务：筛选、统招取值、复试线口径、科目、对比表行、文档元数据）、`tools/kaoyan.py`（6 个结构化工具 + citation / 导出行 / LLM 视图）、`agent/kaoyan_flow.py`（按意图确定性调工具、reflect、finalize 数字校验）、`api/routes_kaoyan.py` + `schemas_kaoyan.py`（`/v1/programs`、`/v1/programs/{id}`、`/v1/score-lines`、`/v1/documents`、`/v1/documents/{id}`）、`scripts/smoke_kaoyan.py`
- 修改 `guardrails.py`（考研意图识别、数字校验）、`prompts.py`（考研 15 条规则）、`nodes.py`（按意图分流，企业路径不变）、`state.py` / `graph.py`（`intent`、`facts`）、`registry.py`（注册工具，`rag_search` 加 `profile`）、`/health` 加可选字段、`__version__` 0.4.0 并用于 `create_app()`
- `PYTHONPATH=src pytest -q`：196 passed（139 + 57）；`test_api_errors.py` 未改
- 真实 DeepSeek 冒烟 `smoke_kaoyan.py`：18/18（数值 14/14、未知 2/2、隐私 1/1、导出 1/1、引用 18/18）；企业 `smoke_chat.py` 3/3
- 文档：`docs/kaoyan_phase5_notes.md`

## 五问重启检查（K5）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K5 完成，等用户看 diff 摘要后提交 |
| 我要去哪里？ | K6：采集层（`collect/`、按 host 限速 ≥3s、robots、`POST /v1/crawl` 默认 dry-run），全部用 MockTransport 测试 |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 工具调用交给规则后，模型失误集中在措辞：会主动讲没问的缺口、用有歧义的“考 408”；数字校验要豁免学科代码这类“看起来像数字”的标识 |
| 我做了什么？ | 查询服务、6 个工具、意图识别、数字校验、考研提示词、Agent 分流、5 个接口、57 条新测试、真实冒烟 18/18 |

## 会话：2026-09-28（考研改造 K4：结构化抽取）

### K4
- **状态：** complete（已提交 `d933603`）
- 新增 `kaoyan/extract/`：10 个规则抽取器（中大细则 / 校线 / 目录 PDF、暨南目录 / 复试方案 xlsx / 推免 PDF、华师目录 / 推免 xls / 复试方案、华工计划）、`apply.py`（专业解析 + 与种子逐键比对 + 幂等写库）、`run.py`、`llm_fallback.py`（证据片段必须在原文中）、`evaluate.py`
- 脚本 `scripts/extract_kaoyan.py`、`scripts/eval_extraction.py` → `docs/kaoyan_extraction_report.md`
- 四类验收逐值一致、冲突 0；450 条种子复现 363 条，其余为名单统计 / 图片 / 种子判断；504 条规则事实全部带来源和证据；本机 `data/kaoyan.db` 已抽取
- `PYTHONPATH=src pytest -q`：139 passed（113 + 26）
- 文档：`docs/kaoyan_phase4_notes.md`

## 五问重启检查（K4）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K4 完成并已提交（`d933603`） |
| 我要去哪里？ | K5：考研结构化工具（search_programs / get_score_lines / …）、考研提示词与数字校验、`/v1/programs` 等接口 |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 真实表格的特殊行靠备注 / 括号说明区分，且备注常在双层表头的另一行；跳过考生表要看表头，不能看数据行 |
| 我做了什么？ | 抽取协议、10 个规则抽取器、比对写库、LLM 证据校验、评估报告、26 条新测试 |

## 会话：2026-09-28（考研改造 K3：检索元数据 + 考研索引）

### K3
- **状态：** complete（已提交 `0aa958f`）
- chunk 带 doc_id / school / college / year / doc_type / title / url / redacted；表格按行切块，重复标题 + 表头 + 学院 / 专业行
- 独立考研索引 `data/chroma_kaoyan/`（`scripts/ingest_kaoyan.py`）：90 文档、1926 chunk、hybrid；检索可按学校 / 年份 / 类型过滤，问题里只有一所学校时自动过滤
- 考研排序先验（名单降权、文档类型 / 学院匹配）；golden hit@5：BM25 16/18、hybrid 15/18
- 企业语料：chunks 逐字节相同、检索结果与工具输出一致、`smoke_chat.py` 3/3
- `PYTHONPATH=src pytest -q`：113 passed（100 + 13）
- 文档：`docs/kaoyan_phase3_notes.md`

## 五问重启检查（K3）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K3 完成，等用户看 diff 摘要后提交 |
| 我要去哪里？ | K4：规则抽取器（暨南目录、华师目录 / 推免 xls、中大细则 / 校线）+ LLM 兜底，与种子逐条比对 |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 名单类文档在词频检索里天然占优，必须用元数据先验压下去；先验只在候选池里生效，池子要够大 |
| 我做了什么？ | chunk 元数据、按行切表、考研索引与过滤、查询扩展与先验、单元格级脱敏、13 条新测试 |

## 会话：2026-09-28（考研改造 K2：多格式解析层）

### K2
- **状态：** complete（已提交 `f6ea30f`）
- 新增 `ingest/{tables,ocr,redact}.py`、`kaoyan/privacy.py`、`collect/attachments.py`；`loaders.py` 支持 html / xlsx / xls / 图片与 PDF 抽表，`ParsedDocument` 带表格 / 图片 / `needs_ocr`
- 个人信息：名单文件在 `load_document` 里脱敏（姓+某、删编号列）；泄漏扫描发现并修复公示正文“拟录取X等N人”首名
- 临时库 ingest `data/kaoyan/raw`：96 文件，90 indexed / 0 failed / 7 needs_ocr / 26 redacted；4187 个姓名 0 泄漏
- `PYTHONPATH=src pytest -q`：100 passed（70 + 30）
- 文档：`docs/kaoyan_phase2_notes.md`

## 五问重启检查（K2）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K2 完成，等用户看 diff 摘要后提交 |
| 我要去哪里？ | K3：chunk 元数据（school / year / doc_type）、独立考研索引、表格按行切块 |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 名单以外的公示正文也会带姓名；泄漏扫描要扫全库而不是只扫名单文件 |
| 我做了什么？ | 多格式解析 + 表格模型、附件发现、OCR 接口、脱敏与统一入口、30 条新测试 |

## 会话：2026-09-27（考研改造 K1：种子库 + golden）

### K1
- **状态：** complete（已提交 `125b5a0`）
- 新增 `src/doc_agent/kaoyan/`（schema / db / models / normalize / seed）、`scripts/seed_kaoyan.py`、`scripts/verify_kaoyan_bundle.py`、`data/gold/kaoyan_qa.json`（18 条）、两组测试
- 联网下载中大 2026 目录 PDF（5.2MB，sha256 与 manifest 一致，本地专用不入库）；verify：96 ok / 1 missing(warn) / 0 bad
- 种子：37 专业、97 文档、`seed_only` 0；K1 七组断言全部通过；幂等
- `PYTHONPATH=src pytest -q`：70 passed（21 + 49）
- 文档：`docs/kaoyan_phase1_notes.md`

## 五问重启检查（K1）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K1 完成，等用户看 diff 摘要后提交 |
| 我要去哪里？ | K2：多格式解析层（html / xlsx / xls / 图片 / 扫描 PDF 识别、附件发现） |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 页面级 URL 对应多个文档，来源要按事实类型打分；一级学科统筹值要带 `pool_scope`，统计表也一样 |
| 我做了什么？ | 建结构化库与种子、备注窄正则（含真实字符串单测）、golden 18 条、包校验脚本 |

## 会话：2026-09-27（考研改造 K0：阅读 + 基线 + 计划）

### K0
- **状态：** in_progress（计划已写，等待用户确认）
- 种子包 `kaoyan_bundle_lite.zip` 解压到 `data/kaoyan/`；`git status` 80 个未跟踪文件，28 条忽略规则生效
- 基线 `PYTHONPATH=src pytest -q`：21 passed
- manifest：95/97 sha256 一致，缺 2 个 >3MB 本地专用文件（lite 包不含）
- 阶段 6 前端按代码核对：F1–F3 已完成，F4 未做；已更正 task_plan
- 计划：`task_plan.md` 阶段 K0–K7

## 五问重启检查（K0）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K0 完成计划，等用户确认 |
| 我要去哪里？ | 确认后执行 K1（种子库 + golden） |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 备注写法比需求里列的多（暨南 2026 统招计划、拟录取人数等），K1 正则要覆盖 |
| 我做了什么？ | 通读仓库与种子包、跑基线、写 K0–K7 计划 |

## 会话：2026-09-06（终测 + 前端计划）

### 后端终测
- **状态：** complete / 可发布
- pytest 13；phase4 smoke OK；async done；人工 P0–P4 通过
- 修复 smoke_chat 空格判分；结论见 `docs/final_backend_test.md`

### 阶段 6：前端
- **状态：** pending（计划已写）
- 文档：`docs/frontend_implementation_plan.md`

### 阶段 5
- **状态：** complete

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | 后端已终测可推送；前端计划已就绪 |
| 我要去哪里？ | 推送 GitHub 后实施 F1 |
| 目标是什么？ | Streamlit 可视化全流程 |
| 我学到了什么？ | 冒烟判分需归一化中文空格 |
| 我做了什么？ | 终测 + 前端计划 |

---
*每个阶段完成后或遇到错误时更新此文件*
