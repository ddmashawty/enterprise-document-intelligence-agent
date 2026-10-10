# 考研评测集

## `kaoyan_qa.json`

K1 的 18 道验收题。已经被调过参，只作旧集合。`scripts/smoke_kaoyan.py` 仍读这个文件。

## `kaoyan_eval_v2.jsonl`

一行一题，现在 148 道：

- 18 道 `v1-*`：从上面迁过来，`split=dev`。`expected_facts` 和核对人来自 `v1_review.json`；v1-11（筛选，答案是派生差值）和 v1-14（范围内没有该专业）没有事实。
- 50 道 `rv-*`：49 道从模板候选题核对后收进来，1 道是审查时手写补的（`origin=handwritten`），都是 `split=unsplit`，有核对人和依据。P1 按“学校 × 类别”抽 test 时再分成 dev / test。
- 80 道 `adv-*`：手写对抗题，`split=adversarial`，8 类陷阱各 10 道，来自 `adversarial_m1.json`。

字段：

| 字段 | 含义 |
|---|---|
| `id` | 稳定题号。迁移题是 `v1-01`，核对过的模板题是 `rv-…` |
| `split` | `dev` / `test` / `adversarial`；`unsplit` 表示已核对、还没分 |
| `category` | `score_line` `plan` `subjects` `tm` `compare` `filter` `narrative` `export` `multi_turn` `out_of_scope` `privacy` `unknown_data` `year_mismatch` `cross_attribution` |
| `trap` | 只有对抗题有：`out_of_scope` `privacy` `year` `cross_school` `upper_bound` `pool` `boundary` `no_exam` |
| `turns` | 多轮时只评最后一轮 |
| `school` / `program_ids` / `year` | 题目范围 |
| `expected_intent` | 学校、代码、年份、操作。M0 迁移题的 `metrics` 留空 |
| `expected_facts` | 库里的键：`table`、`program_id`、`kind`、`year`、`value`、`source_doc_id`。`table` 是 `score_lines`（kind 为线的口径）、`plans`、`admission_stats` 或 `exam_subjects`（kind 为 `slot1`–`slot4`，value 为科目代码） |
| `expected_refusal` | `out_of_scope` / `privacy` / `unknown_data` / `null` |
| `expected_sources` | 事实应引用的 URL |
| `must_include` / `must_not_include` | 粗的字符串检查。`must_include` 里必须有每条 `expected_facts` 的数值 |
| `judge_rubric` | 字符串查不准的口径要求（专项线、学校基本线、计划口径），留给 P1 的 L2 裁判。空串表示没有 |
| `origin` | `db_template` / `handwritten` / `paraphrase` / `user_log` |
| `reviewed_by` / `reviewed_at` | 核对人。空着表示还没核对 |
| `notes` | 来源候选题、核对依据、改了什么 |

## 候选题和核对

`candidates_m0.jsonl`：从本机 `data/kaoyan.db` 生成的模板题，60 道，只含复试线和计划。没有核对过，本身不进评测集。

`review_m0.json`：60 道题每道一条决定（`accept` / `edit` / `drop`），写明对照的原文文件和理由；`additions` 放模板生成不出来、审查时手写补的题。`rv-*` 行完全由它生成，要改题就改这个文件，再重放：

```bash
python scripts/build_gold_candidates.py --apply-review   # 只替换 rv-* 行
python scripts/build_gold_candidates.py --migrate-v1     # 只替换 v1-* 行（kaoyan_qa.json + v1_review.json）
```

不要在 `candidates_m0.jsonl` 上手改；`--candidates` 会按库重新生成它。重新生成后 id 若有变化，`--apply-review` 会报出缺决定的题。

M0 的核对口径：

- 数字要能在原文里对上这个专业、这一年。图片来源（华工基本线表、中大软件学院分数线图）没有重新 OCR，依据是已核对的人工种子；中大软件学院另有 OCR 读数一致。
- 一级学科统筹的线（暨大 010 学院 0812）留两道：一道问 0812，一道问 081201，后者答案要说明是一级学科线。2027 目录 0812 统筹 24 人另有一道手写题，答案要说明一级学科统筹。
- 华工只有学校基本线的，答案必须写“学校基本线”。华工计划要写“统考”；两种计划都有的两个数都要写；附表备注里的联培人数也要写。
- `must_not_include` 只放不会误伤正确答案的串。“学院复试线”这类词正确答案也可能出现（“学院没有另发学院复试线”），所以写进 `judge_rubric`。
- 目录人数（含推免）的题，答案必须出现“目录”。
- 和 `v1-*` 同专业同数字的题丢掉，避免一题算两次。

## 对抗集

`adversarial_m1.json` 每题写问句、意图、拒答类型、`judge_rubric`，事实只写键 `program_id|table|kind|year[|source_doc_id][|checked]`。生成时脚本到库里取值和来源：只认 `verified=1` 的行，取到 0 条或两个不同的值就报错。`checked` 表示库里没有人工种子可比、已人工对照原文（`checked_notes` 写了对照的文件和原文）。

```bash
python scripts/build_gold_candidates.py --adversarial   # 只替换 adv-* 行；--db 可换库
```

对抗题的 `expected_facts` 是工具必须查到的事实，不一定原样出现在回答里（统招 0 回答成“只招推免”，问句自带的人数不用复述），所以不要求事实数值都在 `must_include` 里。纯拒答题没有事实。

| 陷阱 | 考什么 |
|---|---|
| `out_of_scope` | 四校以外的学校、非计算机类专业；混合题只答范围内的部分 |
| `privacy` | 按姓名、考生编号、准考证号、本科学校查个人；可以给统计数 |
| `year` | 未发布年份、库里没有的年份；不能拿别的年份顶替 |
| `cross_school` | 多轮追问时把数字、学院归到错的学校 |
| `upper_bound` | 暨大推免“≤N”只是上限，统考只能给下限 |
| `pool` | 暨大 0812 一级学科统筹，二级学科不单列 |
| `boundary` | 中大 085400 考 884 不考 408，线和计划口径 |
| `no_exam` | 中大 083900 只招推免 |

和用户确认的规则（也写在 `adversarial_m1.json` 的 `review_rules`）：

- 不带姓名、编号的逐人分数不算隐私，只有能对应到具体个人的才拒绝。库里只有统计数，这类题（priv-07、priv-09）答案要如实说只有统计，不能编逐人分数。
- 问未发布年份答 `unknown_data`，可以补最近一年的数，但要标年份。
- 一边超范围的比较题，`operation` 记 `lookup`。
- 问句有两个年份时 `year` 记问的那一年，两年都要比时记 `null`。
- `expected_intent` 记解析后的意图：追问继承上一轮的学校和代码；专业名能唯一对应代码时记代码（“中大网安学硕”记 083900，“中大电子信息专硕”对应多个代码，不记）。
