# 前端实现计划（Streamlit 可视化）

> 后端三期已交付（FastAPI `0.3.0`）。本计划对应 PRD「三期：Streamlit 可视化页面」，单独作为**阶段 6**实施。

## 1. 目标

做一个可演示的 Streamlit 前端，让用户：

1. 配置/查看服务连接与健康状态  
2. 上传或选择本地文档并触发 ingest  
3. 用自然语言对话（同步 / 异步）  
4. 查看 Agent 全流程：plan → tools/trace → reflection → answer → citations → exports  
5. 回放会话与历史任务  

**非目标（首版不做）：** 独立 React SPA、登录权限体系、多租户、Human-in-the-loop 审核台。

## 2. 技术选型

| 项 | 选择 | 理由 |
|----|------|------|
| UI | Streamlit | 与 PRD 一致；Python 同仓；迭代快 |
| 调用 | `httpx` → 本机 FastAPI | 前后端解耦，可换远程 base_url |
| 状态 | `st.session_state` | 保存 session_id、聊天历史、选中 task |
| 布局 | 宽屏 + 侧栏 | 侧栏配置；主区对话；下方/右侧轨迹 |

目录建议：

```
frontend/
  app.py                 # Streamlit 入口
  api_client.py          # 封装 /health /ingest /chat /chat/async /tasks /sessions
  components/
    chat_panel.py
    trace_panel.py
    ingest_panel.py
    health_badge.py
  requirements-frontend.txt   # streamlit, httpx, pandas
scripts/
  run_frontend.sh
```

后端仍用现有 `src/doc_agent`；前端只做 HTTP 客户端。

## 3. 页面信息架构

### 3.1 侧栏（全局）

- API Base URL（默认 `http://127.0.0.1:8000`）  
- 健康徽章：`/health`（llm / retrieval / chunks / version）  
- `session_id`（可新建 / 粘贴）  
- 模式：同步 Chat / 异步 Chat  
- （可选）`max_tool_calls` slider 1–5  

### 3.2 Tab A — 对话（默认）

- 聊天消息列表（user / assistant）  
- 输入框 + 发送  
- 助手气泡下方折叠：**Plan / Reflection / Citations / Exports / Trace**  
- 异步模式：提交后显示 `task_id`，自动轮询至 `done/error`（2s 间隔，超时提示）  

### 3.3 Tab B — 知识库

- 展示 `list`：调用一次轻量 chat「当前知识库有哪些文档？」**或**后续加 `GET /v1/documents`（若实现）  
- 路径 ingest：输入 `data/raw/...` 或上传到临时目录后 `POST /v1/ingest`  
- 显示最近 ingest 结果（docs_indexed / chunks）  

### 3.4 Tab C — 任务中心

- `GET /v1/tasks?session_id=` 表格：task_id / status / created_at / goal 摘要  
- 点击行：展示完整 answer、trace、exports（可下载 `data/exports` 相对路径提示）  
- `GET /v1/sessions/{id}`：turns 时间线  

### 3.5 Tab D — 演示剧本（加分）

一键填入清单问句：

1. TopK / 切片  
2. 保存期限  
3. 保密等级  
4. 年报主营业务与风险  
5. 手册 vs 制度对比  
6. 导出 Markdown / Excel  

便于答辩/录屏。

## 4. 与后端 API 映射

| UI 动作 | API |
|---------|-----|
| 健康检查 | `GET /health` |
| 同步提问 | `POST /v1/chat` |
| 异步提问 | `POST /v1/chat/async` → poll `GET /v1/tasks/{id}` |
| 任务列表 | `GET /v1/tasks` |
| 会话历史 | `GET /v1/sessions/{id}` |
| 导入文档 | `POST /v1/ingest` |
| 错误展示 | 解析 `{"error":{"code","message"}}` |

## 5. 实施阶段（建议 2–3 天）

### F1 — 骨架联通（0.5 天）

- [ ] `frontend/requirements-frontend.txt` + `run_frontend.sh`  
- [ ] `api_client.py`：health / chat / async / get_task  
- [ ] 单页：输入问题 → 显示 answer + 原始 error  
- [ ] README 增加「启动前端」一节  

**验收：** 能连上本地 8000 并完成一轮 TopK 问答。

### F2 — 全流程可视化（1 天）

- [ ] 聊天 UI + session_id 持久化  
- [ ] 展开 Plan / Trace / Citations / Reflection / Exports  
- [ ] 异步轮询与状态徽章（queued/running/done/error）  
- [ ] 任务中心表  

**验收：** 异步导出题可在 UI 看到 exports 路径；trace 可见工具名。

### F3 — Ingest + 演示打磨（0.5–1 天）

- [ ] Ingest 面板（路径 + reindex 开关）  
- [ ] 演示剧本按钮  
- [ ] 基础样式：清晰层级，避免仪表盘堆砌；首屏以对话为主  
- [ ] 简短 `docs/frontend_verification_checklist.md`  

**验收：** 按剧本 6 问可录屏演示；失败时错误码可读。

### F4 —（可选）增强

- [ ] 后端补 `GET /v1/documents` 免聊天列库  
- [ ] 导出文件通过 API 下载（避免只显示路径）  
- [ ] 流式输出（需后端 SSE，非必须）  

## 6. 运行方式（目标形态）

```bash
# 终端 1 — 后端
source .venv/bin/activate
PYTHONPATH=src python -m uvicorn doc_agent.api:app --host 0.0.0.0 --port 8000

# 终端 2 — 前端
pip install -r frontend/requirements-frontend.txt
streamlit run frontend/app.py --server.port 8501
```

打开 http://127.0.0.1:8501 。

## 7. 风险与约束

| 风险 | 缓解 |
|------|------|
| 异步仅单进程 BackgroundTasks | UI 文案提示勿多 worker；轮询超时友好 |
| 大 JSON 卡顿 | Trace/citations 默认折叠、截断预览 |
| CORS | 同机 Streamlit→FastAPI 无浏览器 CORS 问题（服务端 httpx） |
| 无鉴权 | 仅本地演示；README 标明勿公网裸奔 |

## 8. 完成定义（DoD）

1. 不改后端契约即可完成演示（现有 API 足够 F1–F3）  
2. 同步 + 异步两条路径均可在 UI 跑通  
3. 能展示 plan/trace/citations/exports 至少三类  
4. 有启动脚本与前端验证清单  
5. 推送到 GitHub（`frontend/` 目录）  

## 9. 下一步

用户确认本计划后，从 **F1 骨架联通** 开始编码。
