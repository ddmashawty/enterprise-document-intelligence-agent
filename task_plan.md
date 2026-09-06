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
- [x] （可选）Streamlit 另开前端阶段 — **已拆到阶段 6**
- **状态：** complete

### 阶段 6：Streamlit 前端（可视化）
- [ ] F1 骨架联通（health + 同步 chat）
- [ ] F2 全流程可视化（trace/异步/任务中心）
- [ ] F3 Ingest + 演示剧本 + 验证清单
- [ ] （可选）F4 文档列表 API / 导出下载
- **状态：** pending
- **计划文档：** `docs/frontend_implementation_plan.md`


