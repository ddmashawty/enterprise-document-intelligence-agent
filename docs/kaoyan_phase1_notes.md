# 考研改造 K1：种子库 + golden 说明

- **日期：** 2026-09-27
- **分支：** `feat/kaoyan`
- **范围：** 不联网、不调 LLM；只把 `data/kaoyan/`（sources.json + majors.csv）落成结构化库 `data/kaoyan.db`

## 交付项

| 能力 | 实现 |
|------|------|
| 结构化库 | `src/doc_agent/kaoyan/schema.sql`：schools / colleges / documents / programs / directions / exam_subjects / plans / score_lines / admission_stats / crawl_runs + 视图 `v_program_facts` |
| 数据访问 | `kaoyan/db.py`：`KaoyanStore`（sqlite3 + 锁，事务上下文），`find_programs` / `plans_for` / `score_lines_for` / `school_baselines` / `subjects_for` / `stats_for` / `program_facts`；`get_kaoyan_store()` |
| 模型 | `kaoyan/models.py`：pydantic 模型 + `SeedReport` |
| 规范化 | `kaoyan/normalize.py`：`48(17)`、`同上`、`≤41`、`（0812合计≤19）`、科目串拆分、408 判断、代码换行合并、单科线、学院名（含校区）、学校别名 |
| 种子 | `kaoyan/seed.py` + `scripts/seed_kaoyan.py`：幂等（每次先删种子事实再写），单事务 |
| 包校验 | `scripts/verify_kaoyan_bundle.py`：按 `raw/manifest.csv` 校验 sha256；缺失的本地专用文件只警告 |
| Golden | `data/gold/kaoyan_qa.json`：CURSOR_PROMPT 第 6 节 18 条，含 `must_include` / `must_not_include` / `expect_unknown` / `sources`（doc_id + URL） |
| 配置 | `KAOYAN_DB`、`KAOYAN_DATA_DIR`（`config.py` / `.env.example`） |

## 事实模型要点

- 每条事实（plans / score_lines / admission_stats / exam_subjects / directions）都有 `source_doc_id`、年份、`definition`（口径）、`evidence_text`、`extraction_method`、`verified`。
- **同一专业、同一年、同一口径可以有多条来源**（如华师 019 081200 的 2026 推免：目录 17 / 复试方案 16），全部保留，不覆盖。
- `is_upper_bound`：暨南推免 `≤N`；`pool_scope`：一级学科统筹值（暨南 0812），plans 和 admission_stats 都有这一列。
- 分数线 `scope`：`college` / `school_baseline` / `special_veteran` / `special_minority`；学校基本线另存一份 `program_id IS NULL` 的学校级记录（中大 08 学硕 280、0854 300；华工 08 305、14 320）。
- 科目 `status`：`known` / `unknown`（原因取自备注，如华工“统一认证网关拦截”）/ `no_exam`（中大 757 083900 仅招推免）。

## 备注列窄正则

`extraction_method='seed_note_regex'`，覆盖 CURSOR_PROMPT 4 节列出的全部写法，另外补了 37 行备注里出现的变体：

- 暨南 2026：`2026：目录N；统招计划N，复试N人`、`2026：0812按一级学科复试，统招计划N人，复试N人`、`2026目录中分专业计划：081201 5、…`、`2027目录只给出0812合计24人（含推免）`
- 华师：`复试方案：已招推免N`、`2027推免目录：推免N`、`含退役大学生士兵计划N`
- 学校基本线：`工学[08]学硕 280/45/60`、`08工学：总分305，单科满分100的50，满分>100的70`、`14交叉学科320/50/75`
- 统计：`复试名单N人（min–max）`、`统考拟录取N（初试min–max）`、`复试名单N，拟录取N`

拆分口径的写法（“拟录取13（普通）+2（退役）”“66普通+4少干+3退役”）**不抽**，留在 notes 里。

## 来源选择

`majors.csv` 的 `来源URL` 只到页面级，一页可能对应多个文档（华师目录页 → 6 个学院文档；暨南复试方案页 → 通知 + 4 个学院 xlsx）。种子按“事实类型 → 允许的 doc_type 优先级”打分：行内候选 +20、学院一致 +30 / 不一致 −50、年份一致 +10 / 不一致 −40、标题关键词 +15、非全日制匹配、标题里写了**别的**专业代码 −50（华工 081200 / 085404 两份复试名单）、含个人信息 −3。备注里紧跟在事实后面的括号 URL 优先。结果：97 个文档全部来自 sources.json，`seed_only` 为 0。

## 验收结果

```
schools 4 · colleges 16 · documents 97 · programs 37 · directions 67
exam_subjects 130 · plans 144 · score_lines 49 · admission_stats 60 · seed_only 0
verify_kaoyan_bundle: 97 条，96 ok，1 缺失（本地专用：scut 拟录取名单扫描件），0 不一致
```

| 断言 | 结果 |
|------|------|
| 中大 670 085404 college 线 379（50/50/60/60），来源 `cse.sysu.edu.cn/article/3475` | ✅ sysu-078 |
| 暨大 052 085412 线 348、2027 catalog_total 62、tm 25 | ✅ |
| 华师 019 085404 线 348 + special_veteran 288（30/30/48/48） | ✅ |
| 华工 085404 科目 unknown、school_baseline 305、college_exam_plan 35 与 available_exam 21 并存 | ✅ |
| 暨大 010 081201–081203、0812Z3：无专业级 2027 catalog_total；tm ≤19 且 pool 0812 | ✅ |
| 中大 757 083900 no_exam | ✅ |
| 二次种子计数不变（幂等） | ✅ |

**口径说明：** 验收里“暨大 0812 四个二级学科 `catalog_total` 为空”理解为 **2027 年无专业级数值**。2027 目录只给 0812 合计 24（存为 `pool_scope='0812'`）；备注里另有 2026 目录的分专业计划（081203 为 6），golden #7 允许作为补充，因此按 2026 年份保存，不与 2027 混用。

## 测试

```bash
PYTHONPATH=src pytest -q          # 70 passed（原 21 + 新 49）
python3 scripts/seed_kaoyan.py     # 生成 data/kaoyan.db
python3 scripts/verify_kaoyan_bundle.py
```

- `tests/test_kaoyan_normalize.py`：规范化函数。
- `tests/test_kaoyan_seed.py`：每个备注正则变体都用真实字符串测一遍；对已提交的种子包做全量种子（`tmp_path`），核对验收断言、视图、golden 来源可解析、幂等。

## 说明

- `data/kaoyan.db`、`data/chroma_kaoyan/` 不入库；中大 2026 目录 PDF（5.2MB）已下载并通过 sha256 校验，按 `data/kaoyan/.gitignore` 只留本地。
- 个人信息：名单类文档只作为统计来源（人数、分数区间），库里没有姓名 / 考生编号。K2/K3 入索引前按“姓+某”脱敏、删除考生编号列。
- `requirements-embedding.txt` 补齐了 `python-docx`、`openpyxl`（与 `requirements.txt` 同步）；K1 没有新增依赖。
