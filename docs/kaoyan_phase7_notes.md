# 考研改造 K7：OCR / 视觉 + 前端 + 文档

- **日期：** 2026-10-07
- **分支：** `feat/kaoyan`
- **版本：** `0.4.0`
- **范围：** 图片表格和扫描 PDF 页接入 OCR（本地 `rapidocr`、OpenAI 兼容多模态 `vision`），6 张图片表格机器复现并与种子比对；扫描名单只统计人数；前端新增“专业筛选”页，演示剧本换成 18 条验收问句；README / `data/README.md` 更新。包名不改（等用户决定）

## 交付项

| 能力 | 实现 |
|------|------|
| OCR 后端 | `ingest/ocr.py`：`none`（默认，只标 `needs_ocr`）/ `rapidocr`（`requirements-ocr.txt`，`rapidocr_onnxruntime` 模型随 wheel，不在运行时下载）/ `vision`（`POST {VISION_BASE_URL}/chat/completions`，图片以 data URL 发送，要求模型把表格转写成 Markdown，合并格逐格重复，看不清写 `[?]`）；`paddleocr` 仍是“计划中”，选了会报错 |
| 缓存 | `CachedOCR`：`<OCR_CACHE_DIR>/<后端键>/<图片 sha256>.json`（`rapidocr` / `vision-<模型名>`），默认 `data/kaoyan/ocr_cache/`，已被 `data/kaoyan/.gitignore` 忽略；6 张图首次 6.5 s（含模型加载），命中缓存 0.2 s |
| 表格还原 | `ingest/ocr_table.py` `rebuild_table`：灰度 <160 视为墨迹；横线 = 长度 ≥ max(0.2·宽, 60px) 的连续墨迹，竖线 = ≥ max(0.2·高, 40px)；宽度 >6px 的实心带（蓝色表头）在上下边各算一条分隔线；文字框按中心落格，压在线上的归最近的格；相邻格之间没有线 = 合并格（并查集），合并文字填进覆盖的每一格，`origins` 记录合并来源（同 HTML `rowspan` 的展开方式）；表框外的文字框归正文 |
| 文字修正 | `fix_cjk_punct`：中文旁的半角括号 / 逗号改全角，去掉括号两侧空格（“英语 (一)”→“英语（一）”）；`join_pieces` 中文之间不加空格、英文单词之间加一个 |
| 加载 | `loaders.ocr_page`：vision 直接用 Markdown 表；box 后端走 `rebuild_table`；`load_image` 写 `meta.ocr_applied` / `ocr_error`，识别失败仍是 `needs_ocr`；扫描 PDF 页用 `pypdfium2` 按 2 倍渲染后 OCR（`render_pdf_pages`、`_ocr_pdf_pages`），识别成功的页从 `ocr_pages` 移出 |
| 隐私 | `pipeline.load_document`：`contains_personal_data` 的文件强制用 `NoOCR`，扫描名单永远不进索引；`kaoyan/roster.py` + `scripts/roster_stats.py` 只统计“恰好含一个专业代码的行”的行数，输出 `{total, by_program_code, pages, pages_failed}`，不含任何姓名 / 编号 / 分数，不写库（全校按专业代码计数会混合学院 / 联培，口径需要人定） |
| 抽取器 | `scut_baseline_img`（华工复试初试成绩基本要求表：学科门类 / 学科专业 / 总分 / 单科=100 / 单科>100；“各学科专业”行按门类代码出一条，列出专业代码的行每个代码一条）、`scut_subjects_img`（华工初试科目表：按“招生专业代码”合并格分组，一个合并格里的多个专业共用科目）；`sysu_retest_html` 同时匹配 `img` 格式（中大两张分数线 / 计划图的表头与 HTML 表相同） |
| 标记 | `run_extraction`：文档 `meta.ocr_applied` 非空时，该文档所有事实 `extraction_method=ocr`；入库规则沿用 K4：与同键种子逐字段相同才 `verified=1`，否则 `verified=0`，冲突只记录 |
| 脚本 | `extract_kaoyan.py` / `eval_extraction.py` 加 `--ocr {none,rapidocr,vision}`（覆盖 `.env` 的 `OCR_BACKEND`） |
| 配置 | `OCR_BACKEND`、`OCR_CACHE_DIR`、`VISION_BASE_URL`、`VISION_MODEL`、`VISION_API_KEY`、`VISION_TIMEOUT`（`.env.example` 留空）；`requirements.txt` 显式写出 `Pillow`、`pypdfium2`（原来经 pdfplumber 间接安装） |
| 前端 | `frontend/api_client.py`：`list_programs(**filters)`、`get_program`、`score_lines`、`list_documents`（空值不发、布尔转 `true/false`）；`frontend/kaoyan_view.py` 把 `/v1/programs` 展平成表格行（不依赖 streamlit，可单测）；`components/programs_panel.py`“专业筛选”页：学校 / 学位类型 / 学习方式 / 408 / 专业代码 / 关键词 / 统招 ≥ / 年份 筛选，表格列出复试线 + 口径、目录计划、统招（含派生公式）、三列来源链接，“无法判定的专业”单列原因，下方可看单个专业全部事实（口径、是否已核对、来源链接）；演示剧本换成 `kaoyan_qa.json` 的 18 问，企业问句收进“通用文档模式”；标题“广东四校计算机考研信息 Agent”；知识库页默认路径 `data/kaoyan/raw`，上传支持 HTML / xlsx / 图片 |
| 文档 | README 顶部介绍、启动步骤（种子 → 抽取 → 索引）、OCR / 采集可选步骤、“接口”表加 7 个考研接口、目录、测试、配置；`data/README.md` 加运行期目录表和 OCR / 名单说明 |

## 6 张图片表格的结果

`--ocr rapidocr` 在新建库上跑这 6 个文档（`tests/test_kaoyan_ocr.py::test_real_ocr_extraction_matches_seeds` 同样断言）：

| 文档 | 内容 | 事实 | 与种子一致 | 种子没有（verified=0） | 37 个专业以外 |
|---|---|---:|---:|---:|---:|
| scut-040 | 华工复试初试成绩基本要求（jpg） | 16 | 2 | 14 | 0 |
| scut-049 | 华工 2027 初试科目调整（png） | 24 | 0 | 0 | 24 |
| scut-061 | 华工未来技术学院招生专业及初试科目（jpg） | 8 | 4 | 0 | 4 |
| sysu-089 | 中大电子与通信学院复试线（HTML 内嵌图） | 3 | 2 | 0 | 1 |
| sysu-092 | 中大软件工程学院复试线（png） | 3 | 3 | 0 | 0 |
| sysu-095 | 中大软件工程学院拟招生人数（png） | 7 | 6 | 1 | 0 |
| **合计** | | **61** | **17** | **15** | **29** |

- **0 冲突**：OCR 读出的每个数字只要种子里有同键事实，就完全一致。写库 32 条（计划 7、复试线 21、科目 4），其中 17 条 `verified=1`。
- 抽取评估报告（`docs/kaoyan_extraction_report.md`，带 `--ocr rapidocr` 重新生成）：种子 450 条里机器复现 380 条（K4 文字文档 363 + OCR 17），文字文档验收仍 4/4 PASS。
- 剩下 7 条图片来源的种子没复现，原因已写进报告：
  - scut-040 ×5：种子把学校基本线按专业展开（`program_id` 有值），OCR 抽到的是学科门类级的同值校线（`discipline_code` = 08 / 14），键不同所以不算命中。没把门类线展开到专业：展开是种子的编辑口径，抽取器不替人决定哪些专业适用哪条门类线。
  - sysu-089 ×1：少干计划人数不在这张图里（种子取自备注）。
  - sysu-092 ×1：专项计划人数在 sysu-095 那张图里，所以在 sysu-095 下算作“新事实”。
- scut-049 的 24 条、scut-061 的 4 条是 081100 / 085400 / 080900 等 37 个目标专业以外的专业，按 K4 规则记 `unresolved`、不写库。

## 约束落实

- **不编数字 / 已核对：** OCR 事实默认 `verified=0`，只有与人工种子同键同值才 `verified=1`；vision 提示词要求不推断、不补全，看不清写 `[?]`。
- **个人信息：** 名单类文件不 OCR 入库（`NoOCR`）；`roster_stats.py` 只输出计数；测试里的名单行是虚构的“张某 / 王某”+ 假编号，并断言输出不含“某”和编号。
- **不入库：** OCR 缓存在 `data/kaoyan/ocr_cache/`（已忽略）；`data/kaoyan_eval.db` 每次评估后删除（`*.db` 也已忽略）。
- **测试不联网、不调真实模型：** vision 用 `httpx.MockTransport`；rapidocr 真实识别只在装了可选依赖且本地有图片时跑（`pytest.importorskip` + 缺文件 `skip`）。

## 验收结果

`PYTHONPATH=src pytest -q`：**250 passed**（223 + 27）。新增 / 修改：

- `tests/test_kaoyan_ocr.py`（19）：PIL 画的合成线框表（蓝色表头带、纵向合并、横向合并、文字压线、表外脚注）还原；无线框 / 无文字框返回 None；`fix_cjk_punct` / `join_pieces` / `group_lines` / `markdown_tables`；后端注册表与缓存目录；vision 请求体（URL、Bearer、data URL、temperature 0）和解析；缓存命中不再调用；`load_image`（box 后端、vision 表格、后端异常）；扫描 PDF 页 OCR；名单文件不 OCR；华工两种图片表格抽取器；名单计数（行规则、失败页、扫描 PDF 只出计数）；真实 6 图 OCR 与种子比对。
- `tests/test_frontend_client.py`（+3）：`list_programs` 丢弃空参数、布尔转换；三个新方法的路径和参数；404 错误信封。
- `tests/test_frontend_kaoyan_view.py`（5）：表格行保留年份 / 口径 / 来源；未知不填；一级学科合计标注；无法判定行与详情行；演示问句与 `kaoyan_qa.json` 一致。
- `tests/test_kaoyan_tables.py`：OCR 注册表断言改为 rapidocr 可用、paddleocr 未实现；`tests/test_kaoyan_extract.py`：规则抽取器数 10 → 12。

前端手动检查：本机起 API + Streamlit，“专业筛选”页 37 个专业正常显示，暨南 0812 合计显示为“24（2027，0812 合计）”，推免上限的派生值显示为“54 − ≤41 = ≥13”，详情里的来源均为可点击链接。

## 未做 / 需要用户处理

- **vision 未真实调用过：** `.env` 没有配置 `VISION_*`，只用假传输测了请求和解析。配好一个多模态模型后，可以运行 `PYTHONPATH=src python scripts/eval_extraction.py --ocr vision` 和 rapidocr 结果对比。
- **scut-044（华工 2026 拟录取名单，扫描件 113 页 / 29MB）本机没有：** 属于本地专用文件；`roster_stats.py --doc scut-044` 现在会提示按 manifest 下载。下载后可得到按专业代码的人数，但它是全校口径，和 golden #17 的学院口径（085404 36 人、081200 23 人含南特 5）不一定相同，需要人工核对后再决定是否入库。
- **包改名**（如 `kaoyan_agent`）没有做，按 CURSOR_PROMPT 3.8 单独 PR、由用户决定；GitHub 仓库改名由用户自己操作。
