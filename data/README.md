# 演示数据说明

存放 Agent 本地开发与演示用的公开文档语料。详见 [SOURCES.md](./SOURCES.md)。

- `raw/annual_reports`：巨潮公开年报（主演示）
- `raw/policies`：制度/条款类
- `raw/manuals`：技术手册类
- `gold/`：可控评测问答

大型 PDF 若不便入库，可只提交 `SOURCES.md` 与下载脚本，本地执行：

```bash
python3 scripts/download_demo_data.py
```
