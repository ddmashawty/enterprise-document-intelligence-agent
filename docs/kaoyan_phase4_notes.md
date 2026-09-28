# 考研改造 K4：结构化抽取说明

- **日期：** 2026-09-28
- **分支：** `feat/kaoyan`
- **范围：** 规则抽取不联网、不调 LLM；LLM 兜底只在显式 `--llm` 时运行，测试用假模型。抽取结果写入 `data/kaoyan.db` 的五张事实表，每条带 `source_doc_id + evidence_text`，和种子逐键比对，冲突只记录不覆盖

## 交付项

| 能力 | 实现 |
|------|------|
| 抽取协议 | `kaoyan/extract/base.py`：`ExtractContext`（来自 `sources.json` 的 doc_id / 学校 / 年份 / 类型 / 格式 / 学院）、`ProgramRef`（按原文写法指代专业：学院代码或名称 + 6 位专业代码，或 4 位一级学科代码 = 该学院下全部二级学科）、`Fact`、`FactSet`（`plan / line / stat / subjects / no_exam / direction` 构造器）、`Extractor` 协议和表头定位工具 |
| 规则抽取器（10 个） | 中大：`sysu_retest_html`（学院细则：复试线表 + 总计划 / 已招推免 / 公开招考；少干 / 退役按备注归专项）、`sysu_baseline_pdf`（学校基本线，一行多个学科门类各出一条）、`sysu_catalog_pdf`（2026 目录 PDF：拟招人数、初试科目、方向、“仅招收推免生”→ `no_exam`）；暨南：`jnu_catalog_html`（目录三级表；学院备注“计算机科学与技术指标为24个…按一级学科统筹”→ `pool_scope='0812'`）、`jnu_retest_xlsx`（2026 各学院复试方案，只读第一张计划表，名单 sheet 不读）、`jnu_tm_pdf`（2027 推免方案，`≤N` 上限、一级学科共用名额）；华师：`scnu_zsml_html`（目录系统“总(推免)”、方向、科目；“不招推免生”→ 推免 0）、`scnu_tm_xls`（2027 推免目录，ffill 合并单元格）、`scnu_retest_html`（学院复试方案计划表 + 复试线表，考生表整张跳过）；华工：`scut_plan_html`（学院通知“统考招生计划” + 学校“统考可用计划”） |
| 解析 / 比对 / 写库 | `kaoyan/extract/apply.py`：`ProgramResolver` 只把事实挂到库里已有的 37 个专业（学院按 id / 代码 / slug / 名称匹配；一级学科代码展开到该学院全部二级学科；非一级学科命中多个 → `ambiguous` 不写）；按自然键与种子比对 → `match / conflict / new / unresolved / duplicate`；一个事务里先删这些文档上次的 `rule/llm/ocr` 行再插入，种子行不动 |
| 运行 | `kaoyan/extract/run.py` `run_extraction(store, settings, doc_ids=, extractors=, llm_model=, write=)`：遍历 `sources.json` 里有本地文件的文档，经 `load_document`（抽表 + 脱敏）后交给匹配的抽取器 |
| LLM 兜底 | `kaoyan/extract/llm_fallback.py`：仅对“没有规则事实的文字类文档”（复试细则 / 分数线 / 计划 / 推免政策 / 通知）运行，名单文件和图片永不送模型；模型输出 JSON，每条必须带证据原文片段：片段须在文档文本里（忽略空白和表格分隔符）、数值须出现在片段里、类别合法、专业代码 6 位，否则丢弃并记录原因；`extraction_method='llm'` |
| 评估 | `kaoyan/extract/evaluate.py` + `scripts/eval_extraction.py`：新建临时库 → 种子 → 规则抽取 → 比对，生成 `docs/kaoyan_extraction_report.md`（只含键、计数、数值，不含证据原文） |
| 脚本 | `scripts/extract_kaoyan.py [--db] [--docs …] [--llm] [--dry-run] [--verbose]`：幂等，需先跑 `seed_kaoyan.py` |
| schema | `directions`、`exam_subjects` 加 `evidence_text` 列；`KaoyanStore.init_schema()` 对老库自动 `ALTER TABLE`；新增 `delete_extracted_facts()`；`v_program_facts` 同一“值@文档”只列一次（种子和规则并存时不重复），`subject_codes` 取最新年份 |

## 设计要点

- **verified 规则：** 机器抽取的行与同键种子行字段逐一相同才写 `verified=1`；种子没有的事实（`new`）和不同值（`conflict`）都写 `verified=0`。冲突在报告里列出，种子不被覆盖。
- **比对键：** plans `(program, year, kind, doc)`；score_lines `(school, program, year, scope, discipline_code, doc)`；admission_stats `(program, year, kind, doc)`；exam_subjects `(program, year, slot, status, doc)`；directions `(program, year, code, doc)`。种子为空的字段不比；单科线是可选细节，抽取没给不算冲突。
- **按原文口径写 `definition`：** 如“学院2026复试细则“已招推免””、“2027推免生复试方案中的推免数（“≤N”为上限）；0812一级学科合计上限”、“学校“统考可用计划”（2025-10-22 公布）”，与种子口径一致，K5 可以并列展示不同来源。
- **专项与特殊行：** 中大细则的“少干计划 / 退役士兵计划”在双层表头的上一行“备注”列；华师计划表括号说明区分“含联培专项”（主计划）、“退役大学生士兵计划”（专项）和“立功表彰免初试”（跳过）；华工“中法南特联培项目”行跳过；中大基本线只读学术学位 / 专业学位行（“单独考试”复用学科代码，属于另一条通道）。
- **个人信息：** 名单表（表头含“考生姓名 / 初试成绩”）整张跳过；暨南 xlsx 只读计划 sheet；证据文本来自计划 / 分数线表的行，不含姓名、编号、个人分数；LLM 兜底拒收含 15 位以上数字的证据。

## 验收结果

`python scripts/eval_extraction.py`（报告：`docs/kaoyan_extraction_report.md`）：

| 类别（文字类文档） | 种子事实 | 规则逐值命中 | 冲突 |
|------|------|------|------|
| 中大各学院复试线 | 14 | 14 | 0 |
| 暨南 2027 目录计划 | 11 | 11 | 0 |
| 华师目录总(推免) | 16 | 16 | 0 |
| 华师 2027 推免数 | 7 | 7 | 0 |

- 全部 450 条种子事实中，规则逐值复现 363 条，**冲突 0**；有规则抽取器且有本地文件的文档里，种子只剩 2 条未复现：华师 046 的“复试名单 26 人”（种子从名单表计数）和华师 019 085410 2027 科目 unknown（种子判断）。
- 其余 85 条未复现：名单类统计 57（名单文件不做规则抽取）、图片 24（中大 725 / 765 分数线与计划、华工图片表，K7 OCR）、种子判断 5、华工招生简章 1。
- 写入 504 条规则事实（363 条 `verified=1`、141 条 `new`），全部带 `source_doc_id + evidence_text`。`new` 主要是种子没收录的：2026 暨南目录的科目 / 方向、中大其他学科门类的学校基本线、华师 2027 更多专业的方向、中大 765 2025 年细则（往年参考）。
- 6817 条 `unresolved`：目录 / 细则里 37 个目标专业以外的专业（如 070102、081000），不写库。
- 二次运行各表行数不变；种子行数与内容不变。本机正式库 `data/kaoyan.db` 已重新种子并抽取：504 条写入，0 冲突。

## 测试

```bash
PYTHONPATH=src pytest -q          # 139 passed（原 113 + 新 26）
```

- `tests/test_kaoyan_extract.py`（26）：
  - 合成表（结构抄自真实文件）：中大双层表头 + 专项备注、中大计划表、基本线跳过单独考试、华师计划表括号说明与考生表跳过、华师目录“不招推免生”、华工学院通知跳过联培行、华工统考可用计划、暨南推免一级学科上限；
  - 写库：match / conflict / new / unresolved、种子不变、上次规则行被替换、一级学科展开与无学院时拒绝；
  - LLM 假模型：6 条输出只收 2 条有证据的，4 条按原因丢弃；名单文件和图片不调用模型；
  - 老库迁移补 `evidence_text` 列；
  - 真实文档（临时库种子 + 全量抽取）：0 冲突、四类验收通过、每行有来源和证据、中大 670 / 基本线、暨南 2027 目录合计 24 与推免 ≤19、华师目录 48(17) / 推免 0 / 2027 方向、华工三类计划、幂等、报告无个人信息；
  - 依赖本地专用文件的用例（中大 2026 目录 PDF `sysu-072`、暨南 2026 复试方案 xlsx `jnu-003`）缺文件时 `pytest.skip`；验收所用文档均已入库。

## 说明

- 规则抽取器按学校 + 文档类型 + 格式匹配，换年份后表头关键词不变即可复用；表头找不到时不产出事实，不会猜列。
- 华师 2026 学院复试方案（scnu-036/037/038）含名单，本地专用；它们的计划 / 分数线事实在本机被规则复现，干净检出时只剩种子。
- LLM 兜底需要 `LLM_API_KEY`（`build_chat_model`）；本阶段没有用真实模型跑，`--llm` 产出的事实默认 `verified=0`。
