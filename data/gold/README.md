# 考研评测集

## `kaoyan_qa.json`

K1 的 18 道验收题。已经被调过参，只作旧集合。`scripts/smoke_kaoyan.py` 仍读这个文件。

## `kaoyan_eval_v2.jsonl`

一行一题，现在 68 道：

- 18 道 `v1-*`：从上面迁过来，`split=dev`。`expected_facts` 还没回填，`reviewed_by` 为空。
- 50 道 `rv-*`：49 道从模板候选题核对后收进来，1 道是审查时手写补的（`origin=handwritten`），都是 `split=unsplit`，有核对人和依据。P1 按“学校 × 类别”抽 test 时再分成 dev / test。

字段：

| 字段 | 含义 |
|---|---|
| `id` | 稳定题号。迁移题是 `v1-01`，核对过的模板题是 `rv-…` |
| `split` | `dev` / `test` / `adversarial`；`unsplit` 表示已核对、还没分 |
| `category` | `score_line` `plan` `subjects` `tm` `compare` `filter` `narrative` `export` `multi_turn` `out_of_scope` `privacy` `unknown_data` `year_mismatch` `cross_attribution` |
| `turns` | 多轮时只评最后一轮 |
| `school` / `program_ids` / `year` | 题目范围 |
| `expected_intent` | 学校、代码、年份、操作。M0 迁移题的 `metrics` 留空 |
| `expected_facts` | 库里的键：`table`、`program_id`、`kind`、`year`、`value`、`source_doc_id` |
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
python scripts/build_gold_candidates.py --migrate-v1     # 只替换 v1-* 行
```

不要在 `candidates_m0.jsonl` 上手改；`--candidates` 会按库重新生成它。重新生成后 id 若有变化，`--apply-review` 会报出缺决定的题。

M0 的核对口径：

- 数字要能在原文里对上这个专业、这一年。图片来源（华工基本线表、中大软件学院分数线图）没有重新 OCR，依据是已核对的人工种子；中大软件学院另有 OCR 读数一致。
- 一级学科统筹的线（暨大 010 学院 0812）留两道：一道问 0812，一道问 081201，后者答案要说明是一级学科线。2027 目录 0812 统筹 24 人另有一道手写题，答案要说明一级学科统筹。
- 华工只有学校基本线的，答案必须写“学校基本线”。华工计划要写“统考”；两种计划都有的两个数都要写；附表备注里的联培人数也要写。
- `must_not_include` 只放不会误伤正确答案的串。“学院复试线”这类词正确答案也可能出现（“学院没有另发学院复试线”），所以写进 `judge_rubric`。
- 目录人数（含推免）的题，答案必须出现“目录”。
- 和 `v1-*` 同专业同数字的题丢掉，避免一题算两次。
