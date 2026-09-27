# 演示数据说明

存放 Agent 本地开发与演示用的公开文档语料。详见 [SOURCES.md](./SOURCES.md)。

- `raw/annual_reports`：巨潮公开年报（主演示）
- `raw/policies`：制度/条款类
- `raw/manuals`：技术手册类
- `gold/`：可控评测问答（`sample_qa.json` 企业演示；`kaoyan_qa.json` 考研 18 条验收用例）
- `kaoyan/`：考研（硕士研招）种子包——官方来源清单、`majors.csv` 人工核对数据、原始文件与 manifest，详见 [kaoyan/README.md](./kaoyan/README.md)。结构化库 `kaoyan.db` 由 `python3 scripts/seed_kaoyan.py` 生成（不入库），`python3 scripts/verify_kaoyan_bundle.py` 按 manifest 校验 sha256

大型 PDF 若不便入库，可只提交 `SOURCES.md` 与下载脚本，本地执行：

```bash
python3 scripts/download_demo_data.py
```
