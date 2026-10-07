# 演示数据说明

存放 Agent 本地开发与演示用的公开文档语料。详见 [SOURCES.md](./SOURCES.md)。

- `raw/annual_reports`：巨潮公开年报（主演示）
- `raw/policies`：制度/条款类
- `raw/manuals`：技术手册类
- `gold/`：可控评测问答（`sample_qa.json` 企业演示；`kaoyan_qa.json` 考研 18 条验收用例）
- `kaoyan/`：考研（硕士研招）种子包——官方来源清单、`majors.csv` 人工核对数据、原始文件与 manifest，详见 [kaoyan/README.md](./kaoyan/README.md)。结构化库 `kaoyan.db` 由 `python3 scripts/seed_kaoyan.py` 生成（不入库），`python3 scripts/verify_kaoyan_bundle.py` 按 manifest 校验 sha256

### 考研数据的运行期目录（都不入库）

| 路径 | 内容 | 生成方式 |
|---|---|---|
| `kaoyan.db` | 结构化库：专业、计划、复试线、科目、文档、采集记录 | `scripts/seed_kaoyan.py` + `scripts/extract_kaoyan.py` |
| `chroma_kaoyan/` | 考研检索索引 | `scripts/ingest_kaoyan.py` |
| `kaoyan/cache/` | 采集下载的页面和附件（按 sha256 命名） | `scripts/crawl_kaoyan.py --no-dry-run` |
| `kaoyan/ocr_cache/` | OCR 结果，按图片 sha256 缓存 | `OCR_BACKEND=rapidocr` 或 `--ocr rapidocr` |

- 图片表格（中大软件工程 / 电子与通信学院分数线、华工校线和科目图片，共 6 张）用 `--ocr rapidocr` 可以机器复现；抽出的事实标 `extraction_method=ocr`，与人工种子同键同值才是 `verified=1`。
- 名单类文件（`contains_personal_data=true`，大多只在本地，见 `kaoyan/.gitignore`）不做 OCR 入库，问答里也只给统计。扫描名单的人数用 `scripts/roster_stats.py --doc <doc_id>` 统计，只输出每个专业代码的行数。
- 采集下载的新名单类文件同样只放在 `kaoyan/cache/`，不要移到 `raw/` 再提交。

大型 PDF 若不便入库，可只提交 `SOURCES.md` 与下载脚本，本地执行：

```bash
python3 scripts/download_demo_data.py
```
