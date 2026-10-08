# M0 准备：工程骨架和评测集入口

- **日期：** 2026-10-08
- **分支：** `m0/skeleton`（从 `main` `98a809c` 拉出，未提交）
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
| 模板候选 | `scripts/build_gold_candidates.py` 写出 `data/gold/candidates_m0.jsonl`：60 道，35 道复试线 + 25 道计划。未人工核对，没有并进评测集 |
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

## 下一刀

P1：评测脚本和 L0–L2。动手前先人工看 `candidates_m0.jsonl`，核对过的才能进 `kaoyan_eval_v2.jsonl`。
