# 考研结构化抽取评估报告（K4）

> 由 `scripts/eval_extraction.py` 生成：新建库 → 种子入库 → 规则抽取 → 与种子逐键比对。
> 只列键、计数与数值，不含证据原文，名单类文件不出现任何个人信息。

## 概览

- 种子事实：450，被规则逐值复现：363
- 写入的抽取事实：504（缺 `source_doc_id` / `evidence_text` 的：0）
- 抽取状态：match 363，new 141，unresolved 6817
  - match = 与种子同键同值（写入 verified=1）；new = 种子没有的事实（verified=0）；
  - conflict = 同键不同值（只记录、写入 verified=0，不覆盖种子）；
  - unresolved = 专业不在 37 个目标专业内（不写库）；duplicate = 同文档同键重复出现（只保留首条）。

## 验收：文本文档的种子事实须被规则逐值复现

图片来源（img / pdf-scan）的种子事实不计入验收，留到 K7 OCR。

| 类别 | 种子事实 | 规则命中 | 冲突 | 结果 |
|---|---:|---:|---:|---|
| 中大各学院复试线 | 14 | 14 | 0 | 通过 |
| 暨南 2027 目录计划 | 11 | 11 | 0 | 通过 |
| 华师目录总(推免) | 16 | 16 | 0 | 通过 |
| 华师 2027 推免数 | 7 | 7 | 0 | 通过 |

## 冲突

无。

## 未被规则复现的种子事实（按原因）

| 原因 | 事实数 |
|---|---:|
| 名单类统计（种子计数，规则不读名单） | 57 |
| 图片/扫描件，OCR 留到 K7 | 24 |
| 种子判断（科目未公布） | 5 |
| 暂无规则抽取器 | 1 |

## 按文档

| 文档 | 类型 | 运行状态 | 抽取器 | 种子 | 命中 | 新增 | 冲突 | 未解析 | 未复现原因 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| jnu-003 | retest_rules | ok | jnu_retest_xlsx | 18 | 18 | 0 | 0 | 18 |  |
| jnu-004 | retest_rules | ok | jnu_retest_xlsx | 6 | 6 | 0 | 0 | 6 |  |
| jnu-005 | retest_rules | ok | jnu_retest_xlsx | 6 | 6 | 0 | 0 | 0 |  |
| jnu-006 | retest_rules | ok | jnu_retest_xlsx | 3 | 3 | 0 | 0 | 12 |  |
| jnu-010 | catalog | ok | jnu_catalog_html | 11 | 11 | 63 | 0 | 1866 |  |
| jnu-012 | tm_policy | ok | jnu_tm_pdf | 6 | 6 | 0 | 0 | 12 |  |
| jnu-013 | tm_policy | ok | jnu_tm_pdf | 2 | 2 | 0 | 0 | 1 |  |
| jnu-014 | tm_policy | ok | jnu_tm_pdf | 2 | 2 | 0 | 0 | 0 |  |
| jnu-016 | catalog | ok | jnu_catalog_html | 74 | 74 | 0 | 0 | 1745 |  |
| scnu-018 | admission_list | no_extractor |  | 12 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 12 |
| scnu-019 | admission_list | no_extractor |  | 9 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 9 |
| scnu-020 | admission_list | no_extractor |  | 3 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 3 |
| scnu-022 | catalog | ok | scnu_zsml_html | 35 | 35 | 0 | 0 | 0 |  |
| scnu-024 | catalog | ok | scnu_zsml_html | 25 | 25 | 0 | 0 | 0 |  |
| scnu-026 | catalog | ok | scnu_zsml_html | 9 | 9 | 0 | 0 | 0 |  |
| scnu-034 | tm_catalog | ok | scnu_tm_xls | 11 | 10 | 16 | 0 | 393 | 种子判断（科目未公布） 1 |
| scnu-036 | retest_rules | ok | scnu_retest_html | 7 | 7 | 2 | 0 | 0 |  |
| scnu-037 | retest_rules | ok | scnu_retest_html | 14 | 14 | 2 | 0 | 0 |  |
| scnu-038 | retest_rules | ok | scnu_retest_html | 4 | 3 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 1 |
| scut-040 | score_line | no_extractor |  | 7 | 0 | 0 | 0 | 0 | 图片/扫描件，OCR 留到 K7 7 |
| scut-047 | brochure | no_extractor |  | 5 | 0 | 0 | 0 | 0 | 种子判断（科目未公布） 4；暂无规则抽取器 1 |
| scut-048 | plan_quota | ok | scut_plan_html | 5 | 5 | 0 | 0 | 128 |  |
| scut-053 | retest_list | no_extractor |  | 3 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 3 |
| scut-054 | retest_list | no_extractor |  | 3 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 3 |
| scut-055 | plan_quota | ok | scut_plan_html | 2 | 2 | 0 | 0 | 0 |  |
| scut-058 | admission_list | no_extractor |  | 7 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 7 |
| scut-060 | plan_quota | ok | scut_plan_html | 1 | 1 | 0 | 0 | 0 |  |
| scut-061 | subject_change | no_extractor |  | 4 | 0 | 0 | 0 | 0 | 图片/扫描件，OCR 留到 K7 4 |
| scut-063 | admission_list | no_extractor |  | 4 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 4 |
| scut-065 | retest_list | no_extractor |  | 6 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 6 |
| scut-067 | admission_list | no_extractor |  | 2 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 2 |
| sysu-070 | score_line | ok | sysu_baseline_pdf | 2 | 2 | 53 | 0 | 0 |  |
| sysu-072 | catalog | ok | sysu_catalog_pdf | 72 | 72 | 0 | 0 | 2607 |  |
| sysu-077 | retest_list | no_extractor |  | 1 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 1 |
| sysu-078 | retest_rules | ok | sysu_retest_html | 18 | 18 | 0 | 0 | 3 |  |
| sysu-079 | admission_list | no_extractor |  | 1 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 1 |
| sysu-081 | retest_rules | ok | sysu_retest_html | 10 | 10 | 0 | 0 | 3 |  |
| sysu-082 | admission_list | no_extractor |  | 2 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 2 |
| sysu-085 | retest_rules | ok | sysu_retest_html | 9 | 9 | 0 | 0 | 0 |  |
| sysu-088 | retest_rules | ok | sysu_retest_html | 0 | 0 | 4 | 0 | 8 |  |
| sysu-089 | retest_rules | no_extractor |  | 3 | 0 | 0 | 0 | 0 | 图片/扫描件，OCR 留到 K7 3 |
| sysu-091 | retest_rules | ok | sysu_retest_html | 3 | 3 | 1 | 0 | 3 |  |
| sysu-092 | retest_rules | no_extractor |  | 4 | 0 | 0 | 0 | 0 | 图片/扫描件，OCR 留到 K7 4 |
| sysu-093 | retest_list | no_extractor |  | 1 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 1 |
| sysu-095 | retest_rules | no_extractor |  | 6 | 0 | 0 | 0 | 0 | 图片/扫描件，OCR 留到 K7 6 |
| sysu-096 | retest_list | no_extractor |  | 2 | 0 | 0 | 0 | 0 | 名单类统计（种子计数，规则不读名单） 2 |
| sysu-097 | retest_rules | ok | sysu_retest_html | 10 | 10 | 0 | 0 | 12 |  |
