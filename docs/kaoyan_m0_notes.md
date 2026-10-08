# M0 准备：工程骨架和评测集入口

- **日期：** 2026-10-08
- **分支：** `m0/skeleton`（从 `main` `98a809c` 拉出）。骨架在 `4e39661`，候选题核对未提交
- **计划：** `docs/kaoyan_improvement_plan.md` 的第一周清单。这份说明只记已经核对过的结果。
- **花钱：** 没有调用 DeepSeek。旧 18 题基线留到你明确要跑的时候。

## 本阶段做完的

| 项 | 结果 |
|---|---|
| 合并 `feat/kaoyan` | 已在 `main`。`98a809c` 的说明是 `Merge branch 'feat/kaoyan': K6 crawler, K7 OCR and frontend`，包含计划评审时的 `5a71c22`。不是 fast-forward，是一次 merge commit |
| `pyproject.toml` | 依赖与 `requirements.txt` 相同。extras：`embedding`、`ocr`、`frontend`、`dev`（pytest + ruff）。`pytest` 的 `pythonpath` 改到这里，`pytest.ini` 已删 |
| 代码许可 | **MIT**（`LICENSE`）。这是本阶段的默认，要改成 Apache-2.0 就换文件。数据版权不在这份许可里，见 README「数据来源与版权」 |
| CI | `.github/workflows/ci.yml`：Python 3.12，`pip install -e ".[dev]"`，然后 `ruff check` 和 `pytest -q`。还没有 L0–L2 |
| 评测集入口 | `data/gold/README.md`。18 题迁入 `data/gold/kaoyan_eval_v2.jsonl`，`split=dev`，`expected_facts` 为空，`reviewed_by` 为空 |
| 模板候选 | `scripts/build_gold_candidates.py` 写出 `data/gold/candidates_m0.jsonl`：60 道，35 道复试线 + 25 道计划 |
| 候选题核对 | `data/gold/review_m0.json`：经 agent 核对和两轮交互审查，20 道直接收，29 道改后收，11 道丢，另手写补 1 道。50 道以 `rv-*` 并入评测集（`split=unsplit`），评测集共 68 道。见下文「候选题核对」 |
| token 统计 | `run_agent` 返回 `usage`（把图里 `AIMessage.usage_metadata` 加总）。`scripts/smoke_kaoyan.py` 把每题 token、耗时和汇总写进 `--json` |

## 验证

在本机 `.venv`（Python 3.12.13）执行：

```text
ruff check
pytest -q
```

`ruff check` 通过。`pytest -q`：**253 passed**，1 条 Starlette deprecation warning，约 68 秒。K7 记录是 250 passed；新增 3 条在 `tests/test_m0_gold.py`（token 加总、18 题都在 dev、候选题结构）。

ruff 只开了 `E9` 和 `F`，避免把这次变成全库格式化。修掉的是 4 处原有问题：`errors.py` 未使用的 `Field`、`pipeline.py` 未使用的 `DocumentStore`、`store.py` 未使用的 `Path`、`download_demo_data.py` 里写了但没有读的 `extras` 列表。

## 故意没做

- **`docs/baseline_2026-10.json` 没有生成。** 命令是 `python scripts/smoke_kaoyan.py --json docs/baseline_2026-10.json`，需要 `LLM_API_KEY` 和 `data/kaoyan.db`。18 道端到端题会花钱，所以这次不跑。脚本已经会记 `seconds`、`prompt_tokens`、`completion_tokens`、`total_tokens`。
- **没有去官网盘点 2024、2025 复试线。** 下面只是本机库里已经有的，不能当成「官方公开情况」的分母。

## 本机库里的 2024–2025（只读 `data/kaoyan.db`）

复试线事实：2026 年 160 条；2025 年 1 条（中大 `sysu-765-085400` 学院线 370，来源 `sysu-088`，标题写明「往年参考」）；**2024 年 0 条**。

计划事实：2027 年 56 条，2026 年 236 条，2025 年 3 条（都在 `sysu-088`：rules_total 95、tm 24、public_exam 71），**2024 年 0 条**。

`documents.intake_year`：2024 年 3 篇（华师 2024 拟录取名单公示、华师 2024 推免章程、华工 2024 招生简章及专业目录），2025 年 18 篇。其中多数是名单、通知、港澳台目录，不是四校计算机复试线。P4 回填前还要按学校栏目核对官方是否公开了 2024、2025 的复试线。

37 个专业里，复试线模板跳过了 2 个：`sysu-757-083900`（仅招推免，本来没有统考复试线）、`scnu-019-085410`（库里没有学院线或学校基本线）。计划模板跳过 `pool_scope` 非空的行，所以暨大 0812 的一级学科合计不会被写成某一个二级学科自己的计划。

## 写死的年份和事实（复核，本阶段不改）

业务默认年份仍是 2026：

| 位置 | 内容 |
|---|---|
| `src/doc_agent/tools/kaoyan.py:86` | `year: int = 2026` |
| `src/doc_agent/agent/kaoyan_flow.py:108` | `year or 2026` |
| `src/doc_agent/api/routes_kaoyan.py:89` | `Query(2026, …)` |
| `src/doc_agent/kaoyan/seed.py:45` | `SCORE_LINE_YEAR = 2026`，同文件 88、485、587、593 使用它 |
| `src/doc_agent/kaoyan/query.py:543` | `year: int \| None = 2026`。计划正文没列这一处，P2 时一起改 |

写死的事实仍在 `src/doc_agent/agent/prompts.py` 的 `KAOYAN_FINAL_SYSTEM`：第 6 条（华工目录被统一认证拦截、暨南 0812 统筹、推免上限）、第 7 条（中大 765 的 085400 边界项）。P2 再外置到 `data_gaps`。

## 候选题核对

核对人是 Cursor agent，不是人。60 道题逐道对照本机官方原文：暨大复试方案 xlsx 汇总行、华师和中大的 HTML 表、华工学院通知和统考可用计划 PDF、中大目录 PDF、华师目录页的 `lblNzsrs`。没有调用 LLM，名单数据也没有外发，所以没用 Grok Bot。

数字全部对上，没有发现错值。改动都是问法和口径：

| 结论 | 题数 | 原因 |
|---|---|---|
| 丢：和 `v1-*` 重复 | 9 | 同专业同数字已经在旧 18 题里（v1-01/02/03/05/06/09/15/16） |
| 丢：并入 0812 | 3 | 暨大 010 学院原文只有一条 0812 一级学科线 264，不拆成二级学科各一条 |
| 改：合并成 0812 题 | 1 | 081201 那道改问 0812，带 4 条 `expected_facts`（四个二级学科都是 264） |
| 改：目录人数 | 18 | 数字是目录人数（含推免），问法改成学生口吻，答案必须出现“目录”。其中暨大珠海 085410 那道同时补“非全日制” |
| 改：华工学校基本线 | 3 | 华工这几个专业只有学校基本线 305，答案必须写“学校基本线”，不能说成学院线 |
| 改：华工计划口径 | 4 | 写明统考招生计划还是学校统考可用计划；未来技术学院 140500 两个都有（28 / 22），两个都要写 |
| 改：非全日制复试线 | 2 | 暨大珠海 085410、中大 085411，问法补“非全日制”，免得和全日制混 |
| 收：带 `must_not_include` | 5 | 原文同表有退役大学生、少数民族骨干线，答案不能把特殊线当普通线 |
| 收：原样 | 15 | — |

图片来源没有重新 OCR：华工基本线图依据已核对的人工种子；中大软件学院分数线图人工种子和 OCR 读数一致。

重放命令：`python scripts/build_gold_candidates.py --apply-review`。脚本只替换 `origin=db_template` 的行；`--migrate-v1` 也改成只替换 `v1-*` 行，两个顺序随便，结果一致。

`tests/test_m0_gold.py` 加了 2 条：每道候选题恰好一条决定且写了依据；收进来的题数和决定一致，每条 `expected_facts` 的数值都在 `must_include` 里。`ruff check` 通过，`pytest -q` 255 passed。

### 和用户交互审查（第一轮）

agent 挑出 6 处有争议的判断，由用户拍板：

| 争议 | 用户决定 | 落地 |
|---|---|---|
| 和旧题重复的 9 道是否收回（旧题被调过参） | 维持丢弃 | 不变 |
| 暨大 0812 一级学科线合并后测不到“二级学科怎么套线” | 0812 题保留，另加 081201 题 | 0812 题改由 081202 候选题生成；081201 题要求答案含“一级学科”。丢弃从 12 道变 11 道 |
| 华工 081200 计划另有联培 5 | 必须同时答 18 和 5 | `must_include` 加 “5”“联培” |
| 目录人数题必须出现“目录” | 维持 | 不变 |
| 华工软件学院逐字要求“统考可用计划” | 放宽成“统考” | 不能说成目录人数这条写进 `judge_rubric` |
| `must_not_include` 太窄，形同虚设 | 字符串只留粗的，细的交给 L2 | 新增字段 `judge_rubric`。5 道专项线题、3 道华工基本线题的 `must_not_include` 清空，要求写进 `judge_rubric` |

华工基本线题没有改成禁止“学院复试线”：正确答案也可能写“学院没有另发学院复试线”，会误判，所以也放进 `judge_rubric`。

核对原文时发现，华工 081200 附表写的是“统考招生计划数 18，备注 5 中法南特联培项目”，没说 5 是含在内还是另计；库里证据写的“另有 5”是录入时的理解。

### 第二轮

| 争议 | 用户决定 | 落地 |
|---|---|---|
| 华工 081200 联培 5 是含在 18 里还是另计 | 保持中立 | `judge_rubric`：答案写 18 和联培 5，不断言含还是另计 |
| 华工基本线不用字符串禁止“学院复试线” | 同意 | 维持 `judge_rubric` |
| 暨大 2027 目录 0812 一级学科统筹 24 人没有题（生成器跳过 `pool_scope` 行） | 补一道 | `review_m0.json` 新增 `additions`，手写 `rv-jnu-010-0812-plan-2027`，`origin=handwritten`。原文：2027 目录 010 学院标题行“计算机科学与技术指标为24个，以上均按一级学科统筹” |

`--apply-review` 现在按 `rv-` 前缀替换，模板题和手写补充题一起重放。

两轮之后：60 道候选题收 20 / 改 29 / 丢 11，加 1 道手写题；评测集 68 道（18 道 `v1-*` + 50 道 `rv-*`）。`ruff check` 通过，`pytest -q` 255 passed。

## 下一刀

P1：评测脚本和 L0–L2，按“学校 × 类别”从 68 道里分 dev / test，再回填 `v1-*` 的 `expected_facts`。L2 裁判要读 `judge_rubric`。
