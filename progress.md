# 进度日志

## 会话：2026-09-28（考研改造 K2：多格式解析层）

### K2
- **状态：** complete（待提交到 `feat/kaoyan`）
- 新增 `ingest/{tables,ocr,redact}.py`、`kaoyan/privacy.py`、`collect/attachments.py`；`loaders.py` 支持 html / xlsx / xls / 图片与 PDF 抽表，`ParsedDocument` 带表格 / 图片 / `needs_ocr`
- 个人信息：名单文件在 `load_document` 里脱敏（姓+某、删编号列）；泄漏扫描发现并修复公示正文“拟录取X等N人”首名
- 临时库 ingest `data/kaoyan/raw`：96 文件，90 indexed / 0 failed / 7 needs_ocr / 26 redacted；4187 个姓名 0 泄漏
- `PYTHONPATH=src pytest -q`：100 passed（70 + 30）
- 文档：`docs/kaoyan_phase2_notes.md`

## 五问重启检查（K2）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K2 完成，等用户看 diff 摘要后提交 |
| 我要去哪里？ | K3：chunk 元数据（school / year / doc_type）、独立考研索引、表格按行切块 |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 名单以外的公示正文也会带姓名；泄漏扫描要扫全库而不是只扫名单文件 |
| 我做了什么？ | 多格式解析 + 表格模型、附件发现、OCR 接口、脱敏与统一入口、30 条新测试 |

## 会话：2026-09-27（考研改造 K1：种子库 + golden）

### K1
- **状态：** complete（已提交 `125b5a0`）
- 新增 `src/doc_agent/kaoyan/`（schema / db / models / normalize / seed）、`scripts/seed_kaoyan.py`、`scripts/verify_kaoyan_bundle.py`、`data/gold/kaoyan_qa.json`（18 条）、两组测试
- 联网下载中大 2026 目录 PDF（5.2MB，sha256 与 manifest 一致，本地专用不入库）；verify：96 ok / 1 missing(warn) / 0 bad
- 种子：37 专业、97 文档、`seed_only` 0；K1 七组断言全部通过；幂等
- `PYTHONPATH=src pytest -q`：70 passed（21 + 49）
- 文档：`docs/kaoyan_phase1_notes.md`

## 五问重启检查（K1）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K1 完成，等用户看 diff 摘要后提交 |
| 我要去哪里？ | K2：多格式解析层（html / xlsx / xls / 图片 / 扫描 PDF 识别、附件发现） |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 页面级 URL 对应多个文档，来源要按事实类型打分；一级学科统筹值要带 `pool_scope`，统计表也一样 |
| 我做了什么？ | 建结构化库与种子、备注窄正则（含真实字符串单测）、golden 18 条、包校验脚本 |

## 会话：2026-09-27（考研改造 K0：阅读 + 基线 + 计划）

### K0
- **状态：** in_progress（计划已写，等待用户确认）
- 种子包 `kaoyan_bundle_lite.zip` 解压到 `data/kaoyan/`；`git status` 80 个未跟踪文件，28 条忽略规则生效
- 基线 `PYTHONPATH=src pytest -q`：21 passed
- manifest：95/97 sha256 一致，缺 2 个 >3MB 本地专用文件（lite 包不含）
- 阶段 6 前端按代码核对：F1–F3 已完成，F4 未做；已更正 task_plan
- 计划：`task_plan.md` 阶段 K0–K7

## 五问重启检查（K0）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K0 完成计划，等用户确认 |
| 我要去哪里？ | 确认后执行 K1（种子库 + golden） |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 备注写法比需求里列的多（暨南 2026 统招计划、拟录取人数等），K1 正则要覆盖 |
| 我做了什么？ | 通读仓库与种子包、跑基线、写 K0–K7 计划 |

## 会话：2026-09-06（终测 + 前端计划）

### 后端终测
- **状态：** complete / 可发布
- pytest 13；phase4 smoke OK；async done；人工 P0–P4 通过
- 修复 smoke_chat 空格判分；结论见 `docs/final_backend_test.md`

### 阶段 6：前端
- **状态：** pending（计划已写）
- 文档：`docs/frontend_implementation_plan.md`

### 阶段 5
- **状态：** complete

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | 后端已终测可推送；前端计划已就绪 |
| 我要去哪里？ | 推送 GitHub 后实施 F1 |
| 目标是什么？ | Streamlit 可视化全流程 |
| 我学到了什么？ | 冒烟判分需归一化中文空格 |
| 我做了什么？ | 终测 + 前端计划 |

---
*每个阶段完成后或遇到错误时更新此文件*
