# P1 评测：L0 意图 + L1 工具

- **日期：** 2026-10-09
- **分支：** `p1/eval-l0-l1`（从 `m0/skeleton` `1cbd1ed` 拉出；M0 在 [PR #3](https://github.com/ddmashawty/enterprise-document-intelligence-agent/pull/3) 待合并）
- **计划：** `docs/kaoyan_improvement_plan.md` 的 P1。本次只做不调 LLM 的两层。
- **花钱：** 没有调用 DeepSeek。

## 做了什么

| 项 | 结果 |
|---|---|
| `src/doc_agent/eval/metrics.py` | 意图逐字段比对；把工具输出里的复试线、计划拍平成 `expected_facts` 的键再比对 |
| `src/doc_agent/eval/runner.py` | `run_l0`、`run_l1`、和基线比较、生成 Markdown 报告 |
| `scripts/eval_kaoyan.py` | `--layers L0,L1`、`--split`、`--db`、`--out docs/eval`、`--baseline`、`--write-baseline` |
| CI | pytest 之后用仓库里的原始文件建库（`seed_kaoyan.py` + `extract_kaoyan.py`，本机约 8 秒），再跑 L0、L1，和 `docs/eval/baseline.json` 比，任一指标掉超过 2 个百分点就失败 |
| 报告 | 第一份：`docs/eval/2026-10-09.md` / `.json` |
| 测试 | `tests/test_eval_kaoyan.py` 6 条 |

## 两层怎么算

**L0 意图**：拿最后一轮问句跑 `detect_kaoyan_intent`，和 `expected_intent` 逐字段比：

- `schools`、`codes`、`year`：集合或值相等。识别器把 4 位学科代码（0812、0839）放在 `prefixes`，这里并入 `codes` 一起比
- `operation`：由识别出的 kinds 推出（export > filter > compare > lookup）
- `metrics`：金标准写了才比，要求是识别 kinds 的子集；迁移来的 v1 题没写，不计
- `privacy`：`expected_refusal == "privacy"` 和识别结果是否一致
- `exact`：一道题所有参与的字段都对

**L1 工具**：只算有 `expected_facts` 的题。用金标准的学校、代码、年份、指标替换识别结果，交给 `structured_calls` 生成调用，真实调用工具，再在输出里找 `table + program_id + kind + year + value` 都相同的事实。来源 `source_doc_id` 单独统计，不影响命中。

如果工具输出里一个带 `program_id` 的专业都没有，而调用的是 `compare_programs`，这道题记为“暂不可评”，不算缺失。实际上 `compare_programs` 除了中文表格行还附带结构化的 `programs`，所以对比题能评（见下文 v1 回填）。

## 第一次结果（68 道，本机库和 CI 方式新建的库结果相同）

| 层 | 指标 | 结果 |
|---|---|---|
| L0 | 全部字段都对 | 97.1%（66 / 68） |
| L0 | schools | 97.1% |
| L0 | codes / year / operation / metrics / privacy | 100% |
| L1 | 整题事实全命中、事实召回、来源一致 | 100%（50 道） |

L0 没对上的两道是 v1-12、v1-18：问句写“四校”，识别器的 `schools` 为空。`structured_calls` 在学校为空时本来就查全部四校，所以功能上没出错，但意图没有表达出范围。留给 P3。

L1 满分是预期内的：这 50 道题就是从同一个库生成的，L1 现在只能防回归（改了查询或抽取把事实弄丢），不能说明库和官方一致。这一点计划的“风险”一节已经写了。

## 评测过程中修掉的问题

- **v1-15 的金标准代码错了。** 迁移脚本取代码的正则不认带字母的专业代码，把问句里的“0812Z3”截成“0812”。已改正则并重跑 `--migrate-v1`，现在是 `0812Z3`。
- 第一次跑时 L0 是 91.2%，其中 4 道是上面两个评分或金标准问题，不是识别器的错。

## 基线怎么更新

`docs/eval/baseline.json` 只存汇总数。题目增删、口径调整会让比例合理地变化，这时在同一个 PR 里重写基线，并在 PR 说明里写原因：

```bash
python scripts/seed_kaoyan.py --db /tmp/kaoyan.db && python scripts/extract_kaoyan.py --db /tmp/kaoyan.db
python scripts/eval_kaoyan.py --db /tmp/kaoyan.db --out docs/eval --write-baseline docs/eval/baseline.json
```

用新建的库而不是本机 `data/kaoyan.db`，因为 CI 用的是新建库（本机库多了 OCR 抽出的事实）。

## v1 回填（2026-10-10，分支 `p1/v1-facts`）

18 道旧题按原答案逐道对应到库里的事实，写在 `data/gold/v1_review.json`，`--migrate-v1` 应用。共 51 条事实，每条都在库里且 `verified=1`。图片来源：中大 765 的 382 有人工种子和 OCR 一致；华工基本线 305、320 依据已核对的人工种子。另核对了一处看起来可疑的数据：中大 771 085404 的退役专项线和学院线都是 335，原文第 6 行就是这么写的。

只填原答案必答的数字（`must_include` 里的），“可补充”的不填（v1-01 学校线 300、v1-02 的 2027 计划、v1-07 的 2026 目录 6）。

和用户交互定的三处：

| 题 | 决定 |
|---|---|
| v1-11 筛选 | 答案多为“目录 − 推免”的派生差值，库里没有，不填事实、L1 不评；应入选和应排除的专业写进 `judge_rubric` 留给 L3 |
| v1-18 导出 | 填和 v1-12 相同的 6 条复试线 |
| 核对人 | `cursor-agent`，依据是 v1 原答案加库内已核对事实 |

v1-14（华师没有 0839）没有数值事实。

为接住初试科目（v1-06 的 408、v1-16 的 884）和拟录取统计（v1-17 的 36、23），L1 多认两种事实：`exam_subjects`（kind 为 `slot1`–`slot4`，value 为科目代码）和 `admission_stats`。同时修了一个漏洞：`search_programs` 里复试线字段叫 `score_lines`，L1 原来只读 `get_score_lines` 的 `lines`。

结果：L1 有事实的题从 50 道变成 66 道，仍是 100%（v1-12、v1-18 两道对比题也能评）。L0 不变（97.1%）。基线已重写，报告 `docs/eval/2026-10-10.md`。

## 没做

- **L2 检索**：评测集里还没有 narrative 题
- **L3 端到端和裁判**（会读 `judge_rubric`）：要花 DeepSeek
- 切分仍是 18 道 dev + 50 道 unsplit；CI 现在按全部题算，题量到 150 左右再分层抽 test

## 下一刀

扩充评测集：对抗集 → 手写学生问法 → 改写，到 150 道左右再分层抽 test。
