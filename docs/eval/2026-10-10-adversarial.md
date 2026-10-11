# 考研评测报告 2026-10-10

- commit：`b935897-dirty`
- 评测集：`data/gold/kaoyan_eval_v2.jsonl`，切分 全部，148 道
- 层：L0, L1（不调用 LLM）

## L0 意图

| 指标 | 结果 |
|---|---|
| 全部字段都对 | 78.4% |
| schools | 96.0% |
| codes | 91.2% |
| year | 97.3% |
| operation | 98.0% |
| metrics | 88.9% |
| privacy | 97.3% |

| 分组 | 题数 | exact | schools | codes | year | operation | metrics | privacy |
|---|---|---|---|---|---|---|---|---|
| 切分 adversarial | 80 | 62.5% | 95.0% | 83.8% | 95.0% | 96.2% | 79.3% | 95.0% |
| 切分 dev | 18 | 88.9% | 88.9% | 100.0% | 100.0% | 100.0% | — | 100.0% |
| 切分 unsplit | 50 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 陷阱 boundary | 10 | 70.0% | 100.0% | 100.0% | 90.0% | 100.0% | 80.0% | 100.0% |
| 陷阱 cross_school | 10 | 0.0% | 70.0% | 0.0% | 80.0% | 100.0% | 42.9% | 100.0% |
| 陷阱 no_exam | 10 | 60.0% | 90.0% | 80.0% | 100.0% | 90.0% | 100.0% | 100.0% |
| 陷阱 out_of_scope | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 陷阱 pool | 10 | 60.0% | 100.0% | 90.0% | 90.0% | 80.0% | 85.7% | 100.0% |
| 陷阱 privacy | 10 | 60.0% | 100.0% | 100.0% | 100.0% | 100.0% | — | 60.0% |
| 陷阱 upper_bound | 10 | 60.0% | 100.0% | 100.0% | 100.0% | 100.0% | 60.0% | 100.0% |
| 陷阱 year | 10 | 90.0% | 100.0% | 100.0% | 100.0% | 100.0% | 90.0% | 100.0% |

### L0 没对上的题

| 题号 | 错的字段 | 识别结果 |
|---|---|---|
| v1-12 | schools | `{"schools": [], "codes": ["085404"], "prefixes": [], "year": 2026, "kinds": ["score_line", "compare"], "privacy": false}` |
| v1-18 | schools | `{"schools": [], "codes": ["085404"], "prefixes": [], "year": null, "kinds": ["score_line", "plan", "compare", "export"], "privacy": false}` |
| adv-priv-01 | privacy | `{"schools": ["scnu"], "codes": ["085404"], "prefixes": [], "year": null, "kinds": ["narrative"], "privacy": false}` |
| adv-priv-03 | privacy | `{"schools": ["scut"], "codes": ["085404"], "prefixes": [], "year": null, "kinds": ["score_line"], "privacy": false}` |
| adv-priv-04 | privacy | `{"schools": ["scut"], "codes": ["085404"], "prefixes": [], "year": null, "kinds": ["narrative"], "privacy": false}` |
| adv-priv-10 | privacy | `{"schools": ["sysu"], "codes": [], "prefixes": [], "year": null, "kinds": ["score_line"], "privacy": false}` |
| adv-year-03 | metrics | `{"schools": ["scut"], "codes": ["085405"], "prefixes": [], "year": 2028, "kinds": ["narrative"], "privacy": false}` |
| adv-cross-01 | codes, year, metrics | `{"schools": ["scnu"], "codes": [], "prefixes": [], "year": null, "kinds": ["narrative"], "privacy": false}` |
| adv-cross-02 | codes | `{"schools": ["jnu"], "codes": [], "prefixes": [], "year": null, "kinds": ["narrative"], "privacy": false}` |
| adv-cross-03 | codes | `{"schools": ["scut"], "codes": [], "prefixes": [], "year": null, "kinds": ["plan"], "privacy": false}` |
| adv-cross-04 | schools, codes, metrics | `{"schools": [], "codes": [], "prefixes": [], "year": null, "kinds": ["narrative"], "privacy": false}` |
| adv-cross-05 | codes, year, metrics | `{"schools": ["sysu"], "codes": [], "prefixes": [], "year": null, "kinds": ["narrative"], "privacy": false}` |
| adv-cross-06 | schools, codes | `{"schools": [], "codes": [], "prefixes": [], "year": null, "kinds": ["plan"], "privacy": false}` |
| adv-cross-07 | codes, metrics | `{"schools": ["scut"], "codes": [], "prefixes": [], "year": null, "kinds": ["narrative"], "privacy": false}` |
| adv-cross-08 | schools, codes | `{"schools": [], "codes": [], "prefixes": [], "year": null, "kinds": ["narrative"], "privacy": false}` |
| adv-cross-09 | codes | `{"schools": ["sysu"], "codes": [], "prefixes": [], "year": null, "kinds": ["score_line"], "privacy": false}` |
| adv-cross-10 | codes | `{"schools": ["scnu"], "codes": [], "prefixes": [], "year": null, "kinds": ["narrative"], "privacy": false}` |
| adv-ub-03 | metrics | `{"schools": ["jnu"], "codes": ["085410"], "prefixes": [], "year": 2027, "kinds": ["narrative"], "privacy": false}` |
| adv-ub-08 | metrics | `{"schools": ["jnu"], "codes": ["085404"], "prefixes": [], "year": 2027, "kinds": ["narrative"], "privacy": false}` |
| adv-ub-09 | metrics | `{"schools": ["jnu"], "codes": ["085410"], "prefixes": [], "year": 2027, "kinds": ["narrative"], "privacy": false}` |
| adv-ub-10 | metrics | `{"schools": ["jnu"], "codes": ["0812Z3"], "prefixes": [], "year": 2027, "kinds": ["narrative"], "privacy": false}` |
| adv-pool-06 | codes | `{"schools": ["jnu"], "codes": [], "prefixes": [], "year": 2027, "kinds": ["plan"], "privacy": false}` |
| adv-pool-07 | operation, metrics | `{"schools": ["jnu"], "codes": ["081201", "081203"], "prefixes": [], "year": 2027, "kinds": ["narrative"], "privacy": false}` |
| adv-pool-08 | year | `{"schools": ["jnu"], "codes": ["081201"], "prefixes": [], "year": 2026, "kinds": ["narrative"], "privacy": false}` |
| adv-pool-09 | operation | `{"schools": ["jnu"], "codes": ["081202", "0812Z3"], "prefixes": [], "year": null, "kinds": ["score_line"], "privacy": false}` |
| adv-bd-06 | year | `{"schools": ["sysu"], "codes": ["085400"], "prefixes": [], "year": 2025, "kinds": ["score_line"], "privacy": false}` |
| adv-bd-07 | metrics | `{"schools": ["sysu"], "codes": ["085400"], "prefixes": [], "year": null, "kinds": ["directions"], "privacy": false}` |
| adv-bd-10 | metrics | `{"schools": ["sysu"], "codes": ["085400"], "prefixes": [], "year": null, "kinds": ["plan"], "privacy": false}` |
| adv-noexam-02 | codes | `{"schools": ["sysu"], "codes": [], "prefixes": [], "year": null, "kinds": ["plan"], "privacy": false}` |
| adv-noexam-05 | operation | `{"schools": ["sysu"], "codes": ["083900", "085412"], "prefixes": [], "year": null, "kinds": ["narrative"], "privacy": false}` |
| adv-noexam-06 | codes | `{"schools": ["sysu"], "codes": [], "prefixes": [], "year": 2026, "kinds": ["plan"], "privacy": false}` |
| adv-noexam-07 | schools | `{"schools": [], "codes": ["083900"], "prefixes": [], "year": null, "kinds": ["filter"], "privacy": false}` |

## L1 工具

有标准答案事实的题 122 道，另有 0 道工具输出没有 program_id、暂不可评。

| 指标 | 结果 |
|---|---|
| 整题事实全命中 | 98.4% |
| 事实召回 | 99.0% |
| 命中事实的来源一致 | 100.0% |

| 分组 | 题数 | row_pass | fact_recall | source_match |
|---|---|---|---|---|
| 切分 adversarial | 56 | 96.4% | 97.8% | 100.0% |
| 切分 dev | 16 | 100.0% | 100.0% | 100.0% |
| 切分 unsplit | 50 | 100.0% | 100.0% | 100.0% |
| 陷阱 boundary | 9 | 100.0% | 100.0% | 100.0% |
| 陷阱 cross_school | 9 | 100.0% | 100.0% | 100.0% |
| 陷阱 no_exam | 10 | 100.0% | 100.0% | 100.0% |
| 陷阱 out_of_scope | 3 | 66.7% | 83.3% | 100.0% |
| 陷阱 pool | 10 | 90.0% | 92.9% | 100.0% |
| 陷阱 privacy | 3 | 100.0% | 100.0% | 100.0% |
| 陷阱 upper_bound | 10 | 100.0% | 100.0% | 100.0% |
| 陷阱 year | 2 | 100.0% | 100.0% | 100.0% |

### L1 缺事实的题

| 题号 | 缺的事实 | 工具调用 |
|---|---|---|
| adv-oos-04 | sysu-771-085404 college 2026=335 | `get_score_lines({"school": "sysu", "college": "广工计算机学院", "code": "085404", "year": 2026}); search_programs({"school": "sysu", "college": "广工计算机学院", "code": "085404"})` |
| adv-pool-09 | jnu-044-0812Z3 college 2026=276 | `compare_programs({"fields": "score_lines", "program_ids": "jnu-010-081202,jnu-010-0812Z3"})` |

