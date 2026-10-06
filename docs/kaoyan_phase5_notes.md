# 考研改造 K5：Agent 工具、提示词、API 说明

- **日期：** 2026-09-29
- **分支：** `feat/kaoyan`
- **版本：** `0.4.0`
- **范围：** 在 K1 种子库 + K4 抽取结果上提供结构化查询（服务层 → LangChain 工具 → Agent / HTTP 接口）；Agent 识别考研意图后先查结构化库，答案里的数字逐个对照工具证据校验。测试不联网、不调真实 LLM；真实模型只在 `scripts/smoke_kaoyan.py` 里跑

## 交付项

| 能力 | 实现 |
|------|------|
| 查询服务 | `kaoyan/query.py` `KaoyanQuery`：专业筛选（学校别名、学院名 / 代码 / slug、6 位代码或 4 位前缀、方向关键词、学位类型、学习方式、初试科目 / 408、统招阈值、年份）、计划 / 复试线 / 初试科目 / 方向 / 名单统计、统招估算、对比表行、文档元数据。工具和 API 共用 |
| 6 个工具 | `tools/kaoyan.py`：`search_programs`、`get_score_lines`、`get_exam_subjects`、`compare_programs`、`get_document`、`list_sources`，都返回 JSON，每条事实带 `definition`（口径）和 `source`（doc_id / 标题 / URL / 页 / 年份 / 发布日期）；已注册到 `registry.get_tool_list()` |
| 引用 | `citations_from_output()` 把工具输出转成 citation：`doc_id`、`doc_name`（标题）、`url`、`page`、`year`、一句证据（如“中山大学 670计算机学院 085404 …：2026 学院复试线 总分 379（单科 50/50/60/60）；口径：…”），`source_type="kaoyan_db"` |
| 导出 | 考研导出走原 `export_excel / export_markdown`；行来自 `KaoyanQuery.table_row()`：学校、学院、专业代码、专业名称、学习方式、年份、复试线、线的口径、专项线、计划、计划口径、统招、初试科目、来源URL、doc_id、备注；空格子写“未取得”，原因写进备注 |
| 意图识别 | `guardrails.detect_kaoyan_intent()`：学校别名、专业代码 `(0[1-9]\|1[0-4])\d{2}[0-9A-Z]{2}`、4 位一级学科前缀（排除年份）、学院名（先去掉学校别名）、年份、问题类型（复试线 / 计划 / 科目 / 对比 / 筛选 / 方向 / 名单隐私 / 导出 / 叙述）、筛选条件（408、全日制、学硕 / 专硕、“统招 > 20” → `min_public_plan=21`）、“有没有 X” 关键词。企业问题（年报、制度）不会被识别为考研 |
| 数字校验 | `guardrails.find_unsupported_numbers()` / `strip_unsupported_numbers()`：答案里的数字必须出现在证据（全部结构化工具原始输出 + 检索片段 + 提示 + 用户问题）中；豁免年份（1990–2035）、专业代码、0 开头的 4 位学科代码、URL / 文件名、行首序号、“第 N”；比较时 `03`=`3`、`2.00`=`2` |
| Agent 流程 | `agent/kaoyan_flow.py` + `nodes.py` 分流：见下节 |
| 提示词 | `prompts.KAOYAN_FINAL_SYSTEM`（15 条）+ `KAOYAN_RETRY_PROMPT`；企业版提示词原样保留 |
| 状态 | `AgentState` 加 `intent`、`facts`（`notes` 缺口提示 + `validation` 校验结果）；`run_agent` 给默认值并在返回值里带出（`ChatResponse` 忽略多余字段，接口契约不变） |
| API | `api/routes_kaoyan.py` + `api/schemas_kaoyan.py`（见“接口”）；`/health` 在 `data/kaoyan.db` 存在时加 `kaoyan_db / programs / documents`（不会创建库文件）；`create_app()` 标题 / 描述换成考研，`version=__version__`（0.4.0） |
| `rag_search` | 加可选 `profile` 参数（`enterprise` / `kaoyan`），考研叙述题不带学校时也能查考研索引；旧调用不变 |
| 冒烟 | `scripts/smoke_kaoyan.py [--ids] [--json]`：跑 `data/gold/kaoyan_qa.json` 18 题，按 must_include / must_not_include / 有引用 / 导出 xlsx 判定，并汇总验收 |

## Agent 流程（考研路径）

1. **plan：** 识别到考研意图且 `data/kaoyan.db` 有专业时，按意图确定性地生成计划，不调 LLM；否则走原企业规划（不访问考研库）。
2. **act 第 0 轮（确定性调用，不让模型选工具）：**
   - 名单 / 个人信息类 → 只调 `search_programs` 取统计，不做 RAG；
   - 筛选 → `search_programs(条件…)`；
   - 对比 / 导出 → `compare_programs`（多个代码或多所学校时先解析成 `program_ids`；导出时取全部字段）→ 导出时再 `export_excel`；
   - 单个专业：复试线 → `get_score_lines(year 默认 2026)`，科目 → `get_exam_subjects`，再补一次 `search_programs` 取计划 / 备注 / 来源；“有没有 X” 再按关键词查一次；
   - 叙述类或没有可用条件 → `rag_search(goal, profile="kaoyan", school=…)`；
   - 学院名在该校匹配不到专业时去掉学院条件。
3. **reflect（不调 LLM）：** 要导出未导出 → 重试导出；已有结构化证据（含 `unknown` 说明）→ 结束，不因 unknown 反复重试；没有结构化证据且没做过 RAG → 重试一次 `rag_search`，数字题在提示里写明该用哪个工具；同时生成缺口提示（问的年份库里没有 → “应写官方资料中未取得”；名单问题 → 隐私提示）。
4. **finalize：** 证据按工具分块给模型（`llm_view` 去掉证据原文 / 方法 / 附件 URL 等冗余字段，`compare_programs` 只给表格行，总预算约 2.8 万字）；答完做数字校验 → 有找不到的数字就把这些数字告诉模型重写一次 → 还有就替换成“（依据不足）”并加注；名单问题答案里没有“个人信息”字样时在开头补隐私说明；有导出文件时在末尾列路径。

## “统招”取值规则

- 明确口径优先：`public_exam`（公开招考 / 统招计划）、`college_exam_plan`（学院通知统考计划）、`available_exam`（学校统考可用计划），逐条标口径，全部并列。
- 否则派生：同年 `catalog_total − tm`，优先同一文档的推免数，否则同年其他文档（如中大 670：目录 210 − 细则已招推免 165 = 45）；输出 `formula`（“210 − 165 = 45”）和两份来源，数字校验能在证据里找到。
- 推免是“≤N”上限时只得下限（暨南 010 085404：54 − ≤41 = ≥13），下限低于阈值不算满足，进 `unknown` 并写原因；下限 ≥ 阈值则满足。
- 一级学科统筹的数（暨南 0812 目录合计 24、2026 统招 10）不当作本专业人数，写进原因。
- **判断阈值只看该专业能算出统招的最新一年，且明确口径优先于派生值**（不混用 2026 / 2027）：暨南 052 085412 用 2027 的 62 − 25 = 37，不用 2026 的 51；华师 2027 只有推免没有目录，用 2026；中大 725 085405 用细则公开招考 23，派生值 7 只作并列展示。
- 初试科目未知（华工目录被统一认证拦截）时，“是否考 408”判断不了，列进 `unknown`；仅招推免（`no_exam`）的专业直接排除。

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/programs` | 参数同 `search_programs`（`school, college, code, name_kw, degree_type, study_mode, exam_subject, is_408, min_public_plan, year`）；返回 `programs`（完整事实）、`unknown`（带原因）、`excluded`、`public_plan_rule` |
| GET | `/v1/programs/{program_id}` | 单个专业全部事实；不存在 → 404 `program_not_found` |
| GET | `/v1/score-lines?school=&code=&college=&year=2026&include_special=true` | `school` 必填（缺 → 422 `validation_error`）；未知学校 → 404 `school_not_found` |
| GET | `/v1/documents?school=&doc_type=&year=` | 只有元数据；`content_available` 恒为 false，不返回本地路径 |
| GET | `/v1/documents/{doc_id}` | 元数据 + 各表事实条数；名单类文档（`contains_personal_data=true`）同样不提供内容；不存在 → 404 `document_not_found` |

库文件不存在时以上接口返回 503 `kaoyan_db_missing`。全部走统一错误信封 `{error:{code,message,details}}`。`/v1/crawl` 属于 K6。

## 验收结果

### 单元测试

```bash
PYTHONPATH=src pytest -q          # 196 passed（原 139 + 新 57）
```

- `tests/conftest.py`：会话级夹具，用已提交的 `data/kaoyan` 种子包建临时 `kaoyan.db`（约 0.2 秒，缺包时 skip），不依赖本机抽取结果。
- `tests/test_kaoyan_tools.py`（23）：统招规则纯函数（明确优先、上限 → 下限、一级学科 / 缺失进原因、只看最新年份）；筛选“408 + 全日制 + 统招 > 20”的命中集和 unknown（华工科目未知、暨南 ≥13，全文不出现“统招13”）；no_exam 被 408 条件排除；学院别名 / 前缀 / 方向关键词；复试线口径（中大学院线 379 + 学校基本线 300 + 专项线、华工只有学校基本线 305、仅招推免无线、2027 无线进 unknown）；科目 unknown / known / 边界项 884；种子与规则同值去重；085404 对比六行；文档元数据不含本地路径；工具注册、citation、导出行、LLM 视图；名单统计输出不含个人信息。
- `tests/test_kaoyan_guardrails.py`（19）：6 道 golden 意图、学院 / 年份、筛选条件、“有没有 X”、隐私、企业问题不误判、年份不当学科前缀；数字校验通过 / 豁免 / 删除 / 规范化 / 学科代码豁免但普通数字仍查。
- `tests/test_kaoyan_api.py`（7）：版本 0.4.0 与 `/health` 新字段；筛选、详情、复试线、文档接口；404 / 422 / 503 错误信封；503 时不创建库文件。
- `tests/test_kaoyan_agent.py`（8，假模型）：复试线题只调结构化工具且只调 1 次模型；编造数字 → 重写一次；仍编造 → 替换为“依据不足”；名单题不做 RAG 且有隐私说明；2027 缺口提示进入提示词；导出题生成 6 行 xlsx；企业寒暄不访问考研库；冒烟脚本判定逻辑。
- `tests/test_api_errors.py` 未改动，通过。

### 真实 LLM 冒烟（DeepSeek）

`PYTHONPATH=src python scripts/smoke_kaoyan.py`（本机 `data/kaoyan.db` = 种子 + K4 规则抽取）：

| 组 | 结果 | 验收线 |
|------|------|------|
| 数值类（14 题） | 14/14 | ≥ 90% |
| 必须回答未知（#5 华工科目、#13 中大 2027） | 2/2 | 100% |
| 名单隐私（#17） | 1/1（拒绝，只给 36 / 23 人与分数区间） | 100% |
| 导出（#18） | 1/1（6 行 xlsx） | — |
| 有引用 | 18/18 | 100% |

- 18 题总耗时约 44 秒；最终一轮没有触发数字重写。
- 调试过程（共 5 轮）：第 1 轮 16/18，失败原因都在措辞：主动写了用户没问的“2027 年复试线未取得”、写“考 408 / 不考 408”这种有歧义的说法、边界项没补复试线 382。为此加了提示词规则 4（只对问到的年份说缺口）、14（写“初试科目含 / 不含 408”，科目未知写“官方资料中未取得初试科目，是否含 408 无法确认”，没问 408 不提）、15（单专业题补最新复试线和计划），规则 5 要求原样写“官方资料中未取得”；数字校验豁免 0 开头的 4 位学科代码（“0812”曾被误判）。
- 企业 `scripts/smoke_chat.py` 仍 3/3。

## 说明

- 考研路径的 plan / act / reflect 都是确定性的，每题只在 finalize 调 1–2 次模型；模型只负责组织语言，数字由工具给出、由校验把关。
- 学院名匹配用“去掉‘学院’后互相包含”，同校内“计算机学院”能对上华工“计算机科学与工程学院”；匹配不到时不带学院条件，避免漏答。
- 名单统计（复试人数、拟录取人数、分数区间）来自种子人工计数；答案、日志、导出、测试快照都不含姓名 / 编号 / 个人分数。冒烟 #17 的回答只复述了问题里的占位词“某某某”。
- 冒烟输出（`data/exports/smoke_kaoyan_*.json`）在被忽略目录，不提交。
