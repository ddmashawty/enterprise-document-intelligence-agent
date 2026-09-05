# 进度日志

## 会话：2026-09-05（续）

### 阶段 2：规划与结构
- **状态：** complete
- 用户确认：DeepSeek / PDF+txt / 远程 Embedding（无独立 Embedding Key 时 BM25）

### 阶段 3 后续：Ollama Embedding + GitHub
- **状态：** complete
- 执行的操作：
  - Embedding 切换为本地 `qwen3-embedding:0.6b`（Ollama `/v1`）
  - 安装 chromadb，reindex 293 chunks，retrieval=`chroma+qwen3-embedding:0.6b`
  - gold 冒烟 3/3
  - 初始化 git 并推送到 GitHub（不含 `.env` 与大 PDF）
- 仓库：https://github.com/ddmashawty/enterprise-document-intelligence-agent


## 测试结果
| 测试 | 输入 | 预期结果 | 实际结果 | 状态 |
|------|------|---------|---------|------|
| gold Q1 | TopK/切片 | 5 / 500 tokens | 命中 | pass |
| gold Q2 | 保存期限 | 3年 / 10年 | 命中 | pass |
| gold Q3 | 保密等级 | 公开内部秘密机密 | 命中 | pass |
| GET /health | - | llm configured | ok | pass |

## 错误日志
| 时间戳 | 错误 | 尝试次数 | 解决方案 |
|--------|------|---------|---------|
| 12:15 | py3.14 装不上 pydantic | 1 | 换 3.12 venv |
| 12:20 | chromadb 安装过慢 | 1 | 可选依赖 + BM25 |
| 12:35 | 中文 BM25 失效 | 1 | CJK n-gram |
| 12:40 | plan→direct 跳过检索 | 2 | 默认 tools |

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | 阶段 3 完成 |
| 我要去哪里？ | 阶段 4 二期，或继续年报演示 |
| 目标是什么？ | 可运行后端 Agent |
| 我学到了什么？ | DeepSeek 无 Embedding；中文需 n-gram BM25 |
| 我做了什么？ | 一期 MVP 已可服务 |

---
*每个阶段完成后或遇到错误时更新此文件*
