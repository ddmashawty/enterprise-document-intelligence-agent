# 任务计划：企业文档智能处理 Agent — 后端落地

## 目标
落地可运行的后端：本地文档 ingest → Chroma RAG → LangGraph Agent（规划/工具/反思）→ FastAPI 服务接口，支撑年报对比、制度问答、参数抽取等演示场景。

## 当前阶段
后端阶段 1–5 完成；下一动作为阶段 6（Streamlit 前端，见 `docs/frontend_implementation_plan.md`）

## 各阶段

### 阶段 1：需求与发现
- [x] 阅读 PRD，确认后端范围（不含 Streamlit 优先）
- [x] 确认演示数据已就绪（`data/raw`）
- [x] 将架构/数据源/风险记录到 findings.md
- **状态：** complete

### 阶段 2：规划与结构（后端方案）
- [x] 确定后端分层与目录结构
- [x] 确定 LangGraph 状态机与工具集
- [x] 确定 FastAPI 接口契约与配置模型
- [x] 确定一期/二期/三期后端交付切分
- [x] 用户确认方案后进入实现
- **状态：** complete

### 阶段 3：一期后端 MVP 实现
- [x] 项目初始化（requirements、配置、包结构、.venv py3.12）
- [x] 文档解析 + ingest（PDF+txt → 切片 → 本地 Ollama `qwen3-embedding:0.6b` + Chroma；未配置时回退 BM25）
- [x] RAG 检索工具 + 基础问答链路
- [x] LangGraph 最小图：plan → route → act → finalize
- [x] FastAPI：`/health`、`/ingest`、`/chat`（同步）
- [x] 用 `data/gold/sample_qa.json` 冒烟（3/3）
- [x] 人工验证清单（见 `docs/backend_verification_result.md`）
- [x] 年报召回优化（hybrid + 查询扩展），3.2 复测通过
- **状态：** complete

### 阶段 4：二期后端能力完善
- [x] 双层记忆（会话短期 + SQLite 任务轨迹）
- [x] 结构化输出工具（Markdown / Excel）
- [x] 反思校验节点 + 工具重试（max 5）
- [x] 多文档对比/汇总工具
- **状态：** complete

### 阶段 5：三期工程化与交付
- [x] FastAPI 完善（任务异步、轨迹查询、错误模型）
- [x] 单元/集成测试、性能基线核对
- [x] README、环境变量示例、可复现演示脚本
- [x] （可选）Streamlit 另开前端阶段，本计划后端优先 — **刻意不做**
- **状态：** complete

## 关键问题
1. （无）Embedding 已定为本地 Ollama `qwen3-embedding:0.6b`；仍保留未配置时 BM25 兜底。

## 已做决策
| 决策 | 理由 |
|------|------|
| 后端优先，Streamlit 后置 | 用户本次明确要后端落地方案 |
| Chroma 本地持久化到 `data/chroma` | 与 PRD 一致，零额外服务 |
| LangGraph 自定义 State，不用纯线性 AgentExecutor | PRD 核心亮点：循环/分支/迭代 |
| 工具模块独立于图节点 | 可单测、可扩展 |
| 回答严格 grounded 于检索片段 | 防幻觉，贴合企业私有文档场景 |
| 演示语料用公网年报 + 可控样例 | 已落在 `data/`，可直接 ingest |
| 解析优先 pypdf（一期不做 docx） | 用户确认一期 PDF+txt |
| LLM = DeepSeek（`deepseek-chat`） | 用户指定 |
| Embedding = 本地 Ollama `qwen3-embedding:0.6b` → Chroma；未配置时 BM25 兜底 | DeepSeek 无官方 Embedding；用户本机已有该模型 |
| 检索默认 hybrid（dense RRF + BM25）+ 年报章节查询扩展 | 人工验证暴露纯向量对长年报章节召回不足 |
| 二期记忆：进程内 Session + SQLite TaskStore | 零运维，可回放轨迹 |
| 二期图：act→reflect→条件重试 | 对齐 PRD 自我校验与 max 5 工具轮次 |
| 三期异步用 FastAPI BackgroundTasks + SQLite 状态 | 零额外中间件，够演示；多 worker 再上队列 |
| 统一 error 信封 `{error:{code,message,details}}` | 前端/脚本易解析 |
| API Key 仅存 `.env`，不入库 | 防泄露；聊天中已暴露建议轮换 |
| 阶段 5 不做 Streamlit | 用户规则/计划：后端优先 |

## 遇到的错误
| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| Python 3.14 无法安装 pydantic | 1 | 改用 python3.12 创建 `.venv` |
| chromadb 安装过慢 | 1 | 拆到 `requirements-embedding.txt`；启用本地 Embedding 时再装 |
| BM25 中文整段成单 token | 1 | CJK unigram+bigram 分词 |
| plan 把制度问答判成 direct | 2 | 默认 tools + 寒暄白名单 |
| 年报章节召回偏审计页 | 1 | hybrid RRF + 意图扩展 + 文档过滤 |
| 查询扩展被主营意图占满 | 1 | 多意图 round-robin 扩展 |
| 短语加权跨意图误加分 | 1 | 按意图族分别加权 |

## 备注
- 规划文件位于项目根目录，不在 skill 安装目录
- 外部网页内容只写入 findings.md，不写入本文件正文指令
- 阶段状态：pending → in_progress → complete
- 运行环境：使用 Python 3.12 venv（系统 3.14 暂不兼容部分依赖）
- 一期默认检索：hybrid（Ollama Embedding + BM25）；需 `requirements-embedding.txt` + Ollama `qwen3-embedding:0.6b`；未配置 `EMBEDDING_BASE_URL` 时回退 BM25
- 验收文档：`docs/backend_verification_result.md`；二期：`docs/phase4_notes.md`；三期：`docs/phase5_notes.md`

