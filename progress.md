# 进度日志

## 会话：2026-09-05

### 阶段 1–2：需求与方案
- **状态：** complete
- 确认：DeepSeek chat、一期 PDF+txt、本地 Ollama embedding

### 阶段 3：一期后端 MVP
- **状态：** complete
- ingest + LangGraph + FastAPI；gold 3/3；GitHub 初推

### 人工验证
- **状态：** complete
- 结论：`docs/backend_verification_result.md`
- 初测核心通过；3.2 年报开放汇总召回不足

### 年报召回优化
- **状态：** complete
- hybrid(dense+bm25) + 查询扩展 + 文档过滤 + 短语加权
- 复测：主营业务/四类风险带页码通过
- 文件：`query_expand.py`、`store.py`、`registry.py`

### 文档同步并推送 GitHub
- **状态：** complete

## 测试结果
| 测试 | 输入 | 预期结果 | 实际结果 | 状态 |
|------|------|---------|---------|------|
| gold Q1–Q3 | 可控样例 | 命中原文 | 命中 | pass |
| GET /health | - | hybrid 后端 | hybrid(qwen3-embedding:0.6b+bm25) | pass |
| 年报 3.2 复测 | 主营业务+风险 | 有条目与页码 | p9/p15/p22/p56 等 | pass |

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | 一期 MVP + 年报召回优化完成，文档待推送 |
| 我要去哪里？ | 阶段 4 二期能力 |
| 目标是什么？ | 可运行、可验证的企业文档 Agent 后端 |
| 我学到了什么？ | 长年报需 hybrid，不能只靠稠密向量 |
| 我做了什么？ | 见上方各阶段 |

---
*每个阶段完成后或遇到错误时更新此文件*
