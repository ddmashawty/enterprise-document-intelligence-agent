# Enterprise Document Intelligence Agent

基于 DeepSeek + LangGraph 的企业文档智能处理 Agent（一期后端 MVP）。

## 已确认配置

- LLM：DeepSeek（`deepseek-chat`）
- 文档：一期仅 PDF + txt
- 检索：本地 Ollama `qwen3-embedding:0.6b` → Chroma；未配置 Embedding 时回退 BM25

> DeepSeek 无官方 Embedding。默认使用本机 Ollama 的 OpenAI 兼容接口。

## 快速开始

```bash
# 建议 Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-embedding.txt   # Chroma（稠密检索）

cp .env.example .env
# 填写 LLM_API_KEY；Embedding 默认已指向本地 Ollama

# 确保 Ollama 已启动：
#   ollama pull qwen3-embedding:0.6b

# 可选：下载公网年报等演示 PDF
# python scripts/download_demo_data.py

PYTHONPATH=src python scripts/ingest_demo.py --reindex
PYTHONPATH=src python scripts/smoke_chat.py

PYTHONPATH=src python -m uvicorn doc_agent.api:app --host 0.0.0.0 --port 8000
```

健康检查 / 问答：

```bash
curl -s localhost:8000/health
curl -s localhost:8000/v1/chat -H 'Content-Type: application/json' \
  -d '{"message":"演示产品手册里 TopK 和切片大小分别是多少？"}'
```

## 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康与配置状态 |
| POST | `/v1/ingest` | 导入文档到本地索引 |
| POST | `/v1/chat` | 自然语言任务（Agent） |

## 目录

```
src/doc_agent/   # 后端代码
data/raw/        # 演示文档（大 PDF 默认不入库，见 SOURCES.md）
scripts/         # ingest / smoke / 下载脚本
task_plan.md     # 规划文件
```

## 安全

- API Key 只放在 `.env`，已加入 `.gitignore`
- 大体积演示 PDF 不提交；用 `scripts/download_demo_data.py` 本地拉取
