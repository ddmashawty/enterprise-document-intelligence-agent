# 考研评测集

## `kaoyan_qa.json`

K1 的 18 道验收题。已经被调过参，只作旧集合。`scripts/smoke_kaoyan.py` 仍读这个文件。

## `kaoyan_eval_v2.jsonl`

一行一题，现在 188 道：dev 82、test 26、adversarial 80。

- 18 道 `v1-*`：从上面迁过来，`split=dev`。`expected_facts` 和核对人来自 `v1_review.json`；v1-11（筛选，答案是派生差值）和 v1-14（范围内没有该专业）没有事实。
- 50 道 `rv-*`：49 道从模板候选题核对后收进来，1 道是审查时手写补的（`origin=handwritten`），有核对人和依据。按下面“test 切分”分进 dev / test。
- 80 道 `adv-*`：手写对抗题，`split=adversarial`，8 类陷阱各 10 道，来自 `adversarial_m1.json`。
- 40 道 `sup-*`：用户出题的补充集，补对抗集的偏差（口语多意图、库外字段、政策口径、预测、错误前提、聚合、注入和路由），来自 `supplement_m1.json`，同样分进 dev / test。

字段：

| 字段 | 含义 |
|---|---|
| `id` | 稳定题号。迁移题是 `v1-01`，核对过的模板题是 `rv-…` |
| `split` | `dev` / `test` / `adversarial`。生成脚本里新写的行先标 `unsplit`，写文件时按 `split_m1.json` 落到 test 或 dev |
| `category` | `score_line` `plan` `subjects` `tm` `compare` `filter` `narrative` `export` `multi_turn` `out_of_scope` `privacy` `unknown_data` `year_mismatch` `cross_attribution` |
| `trap` | 只有手写题有。对抗集：`out_of_scope` `privacy` `year` `cross_school` `upper_bound` `pool` `boundary` `no_exam`；补充集：`colloquial` `missing_field` `policy` `prediction` `false_premise` `aggregate` `routing`。报告按它分组 |
| `turns` | 多轮时只评最后一轮 |
| `school` / `program_ids` / `year` | 题目范围 |
| `expected_intent` | 学校、代码、年份、操作。M0 迁移题的 `metrics` 留空 |
| `expected_facts` | 库里的键：`table`、`program_id`、`kind`、`year`、`value`、`source_doc_id`。`table` 是 `score_lines`（kind 为线的口径）、`plans`、`admission_stats`、`exam_subjects`（kind 为 `slot1`–`slot4`，value 为科目代码）或 `directions`（kind 为方向代码，value 为目录“导师”格原文，目前只有暨大）。单科线另带 `field`（`politics` / `foreign_lang` / `subject1` / `subject2`），没有 `field` 就是总分 |
| `expected_refusal` | `out_of_scope` / `privacy` / `unknown_data` / `null` |
| `expected_sources` | 事实应引用的 URL |
| `must_include` / `must_not_include` | 粗的字符串检查。`must_include` 里必须有每条 `expected_facts` 的数值。每项可以是字符串或备选列表（任一命中即可），匹配前用 `doc_agent.eval.metrics.normalize_text` 归一化（去空白、全角转半角、2.5万=25000、16,000=16000、两门=2门、不记入=不计入） |
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

## 手写题（对抗集、补充集）

`adversarial_m1.json`、`supplement_m1.json` 每题写问句、意图、拒答类型、`judge_rubric`，事实只写键 `program_id|table|kind|year[|source_doc_id][|field=politics][|checked]`。生成时脚本到库里取值和来源：只认 `verified=1` 的行，取到 0 条或两个不同的值就报错。`checked` 表示库里没有人工种子可比、已人工对照原文（`checked_notes` 写了对照的文件和原文）。`field=` 取单科线。

答案只在原文里、没有结构化事实的题（学费、复试成绩算法、同等学力），在 `sources` 里列文档 id，生成时并进 `expected_sources`。每个文件头写 `id_prefix` 和 `split`，生成时只替换该前缀的行。

```bash
python scripts/build_gold_candidates.py --specs   # 只替换 adv-* 和 sup-* 行；--db 可换库
```

手写题的 `expected_facts` 是工具必须查到的事实，不一定原样出现在回答里（统招 0 回答成“只招推免”，问句自带的人数不用复述），所以不要求事实数值都在 `must_include` 里。纯拒答题没有事实。

## 对抗集

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

## 补充集

用户看完对抗集后出的 40 道，补它的偏差：华工、华师题少，lookup 占 72 道，没有口语、多意图、库外字段和政策口径。每题保留用户写的期望行为（`user_label`）；库里或原文和它不一致的，改了并在 `label_change` 写依据。

**40 道里有 7 道的期望被原文推翻**（sup-02、08、09、10、12、21、29），说明这批题是对着库和原文逐题核过的，不是照出题人的印象收的：

| 题 | 原期望 | 原文 / 库里实际 |
|---|---|---|
| sup-02 | 华工初试科目能答 | 计算机、软件两个学院 4 个专业的科目在库里都是未取得，改为 `unknown_data` |
| sup-08 | 华师学费未知 | 2026 招生简章（scnu-030）第十一节有学费表 |
| sup-09 | 华工学制、奖学金都未知 | 学费学制一览表（scut-042）有学制，招生章程（scut-047）有奖助种类，只有金额未知 |
| sup-10 | 导师未知 | 暨大 2026、2027 目录都有“导师”列；另外三校目录没有 |
| sup-12 | 能算报录比 | 报名人数表（scnu-017）是 2025 年入学那一届，和 2026 拟录取数不是同一届，不能相除 |
| sup-21 | 同等学力只指向简章 | 暨大 2027 目录逐专业写了是否接收和加试科目 |
| sup-29 | 两校 2027 目录都已出 | 暨大出了，华师只有 2027 推免目录 |

sup-12 的核对顺带改了库：`sources.json` 里 scnu-017 的招生年份从 2026 改为 2025，并补上来源页。依据是它发在“往年数据”栏、发布时间 2025-10-15 08:48，正是 2026 届网报第一天；2024 年那张表发在 2024-09-02。

| 类 | 题数 | 考什么 |
|---|---|---|
| `colloquial` | 7 | 简称（计科、软工、网安、SYSU）、一句话多问、同校两学院相减 |
| `missing_field` | 9 | 学费、学制、奖学金、导师、机试、报录比、淘汰率、就业、宿舍；有原文的照原文答，没有的说未取得 |
| `policy` | 5 | 单科线、退役专项、非全日制、联培、同等学力 |
| `prediction` | 5 | 能不能上、哪个好考、调剂、涨不涨、哪个好；不预测、不评价，只并列事实 |
| `false_premise` | 6 | 错误数字、名称和代码不匹配、“今年”“明年”、口径不同的数直接比、追问来源 |
| `aggregate` | 4 | 计数、排序、整校列表、反向筛选；未取得的要单列 |
| `routing` | 4 | 提示注入、导出不留空、通用文档题、复习资料 |

## test 切分

2026-10-11 抽定并冻结，记录在 `split_m1.json`：

- 从 90 道已核对的 `rv-*` 和 `sup-*` 里，按“学校 × 类别”分层抽 30%，共 26 道。学校取 `expected_intent.schools`，单校记该校，多校记 `multi`，没有学校记 `none`。每层按比例取整，剩下的名额给余数最大的层，层内顺序由固定种子 `kaoyan-test-m1` 的哈希决定，可复现。
- 4 道不进 test，直接放 dev：sup-07、sup-29、sup-36 已被点名作 L1 修复目标，sup-10 要给导师试点补事实。对着它们改代码，再放进 test 就不干净了。
- `v1-*` 已经调过参，`adv-*` 单独报告，都不参与抽样。
- 文件里记了每道 test 题的内容哈希（不含 `split`）。改了 test 题，`tests/test_m0_gold.py` 会失败；确实要改，在 PR 里单独写理由，再跑 `scripts/build_gold_candidates.py --rehash-test`，它会列出改了哪几道。`--freeze-test` 只能跑一次，文件存在就拒绝。

评测脚本默认不跑 test。要跑就显式加 `--split test`（只在里程碑验收时），报告只给 test 的总分：不列逐题结果，test 题也不进陷阱分组。冻结前已经看过逐题结果的题（补充集里 L0 没对上的那些）也在 test 里，只能以后不再逐题看；修 L0 时按能力修规则，不对着单题打补丁。

## 回退门槛

`docs/eval/baseline.json` 除了各分组的比例，还存一份已知失败清单 `known_failures`：L0 记每道失败题错的字段，L1 记每道失败题缺的事实。CI 用 `--baseline` 比较时：

- 比例：总体、每个切分、每类陷阱各自下降超过 2 个百分点就失败；
- 逐题：清单外的题失败，或清单里的题多错了一个字段、多缺了一条事实，都算新失败；
- 清单里的题修好了（整题或其中一个字段）也让 CI 失败，提示重写基线。这样清单只会在有人主动重写时缩小，不会留着过期条目替以后的回退打掩护。

`--write-baseline` 遇到清单要新增条目时会拒绝写入，除非加 `--accept-new-failures`，新增的条目要在 PR 里列出来。
