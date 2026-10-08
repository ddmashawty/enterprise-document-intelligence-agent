# 考研评测集

## `kaoyan_qa.json`

K1 的 18 道验收题。已经被调过参，只作旧集合。`scripts/smoke_kaoyan.py` 仍读这个文件。

## `kaoyan_eval_v2.jsonl`

一行一题。M0 只迁入了上面的 18 题，`split` 全部是 `dev`。`expected_facts` 还没回填，`reviewed_by` 为空。test 切分还没抽，不要拿这 18 题当新指标基线。

字段：

| 字段 | 含义 |
|---|---|
| `id` | 稳定题号。迁移题是 `v1-01` 这种 |
| `split` | `dev` / `test` / `adversarial`。候选题不进这个文件 |
| `category` | `score_line` `plan` `subjects` `tm` `compare` `filter` `narrative` `export` `multi_turn` `out_of_scope` `privacy` `unknown_data` `year_mismatch` `cross_attribution` |
| `turns` | 多轮时只评最后一轮 |
| `school` / `program_ids` / `year` | 题目范围 |
| `expected_intent` | 学校、代码、年份、操作。M0 迁移题的 `metrics` 留空 |
| `expected_facts` | 库里的键：`table`、`program_id`、`kind`、`year`、`value`、`source_doc_id` |
| `expected_refusal` | `out_of_scope` / `privacy` / `unknown_data` / `null` |
| `expected_sources` | 事实应引用的 URL |
| `must_include` / `must_not_include` | 沿用旧集合的字符串检查 |
| `origin` | `db_template` / `handwritten` / `paraphrase` / `user_log` |
| `reviewed_by` / `reviewed_at` | 人工核对。空着表示还没核对 |
| `notes` | 迁移或出题说明 |

重新生成迁移文件：

```bash
python scripts/build_gold_candidates.py --migrate-v1
```

## `candidates_m0.jsonl`

从本机 `data/kaoyan.db` 生成的模板题，最多 60 道，只含复试线和计划。每个专业每类至多一道。优先学院复试线，没有则用学校基本线；计划优先目录人数。这些题**没有人工核对**，不能并进 `kaoyan_eval_v2.jsonl`。

```bash
python scripts/build_gold_candidates.py --candidates
```
