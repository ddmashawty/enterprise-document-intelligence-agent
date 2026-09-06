# 阶段 5（三期）工程化说明

- **日期：** 2026-09-06  
- **版本：** `0.3.0`  
- **Streamlit：** 刻意后置（本阶段后端优先）

## 交付项

| 能力 | 实现 |
|------|------|
| 异步任务 | `POST /v1/chat/async` → `queued`；BackgroundTasks 执行；`GET /v1/tasks/{id}` 轮询 `running/done/error` |
| 轨迹查询 | `GET /v1/tasks`、`GET /v1/tasks/{id}`、`GET /v1/sessions/{id}` |
| 错误模型 | 统一 `{"error":{"code","message","details"}}`（校验/业务/未捕获） |
| 请求选项 | `options.max_tool_calls` / `temperature` 经 `runtime_options` 注入图节点 |
| 单元测试 | `tests/`（chunking / guardrails / memory / export / API errors） |
| 性能基线 | `scripts/perf_baseline.py` → `docs/perf_baseline.json` |
| 可复现脚本 | `scripts/demo_repro.sh` |

## 人工测试

逐步勾选：[`phase5_verification_checklist.md`](./phase5_verification_checklist.md)  
验收结论：[`phase5_verification_result.md`](./phase5_verification_result.md)（**2026-09-06 通过**）

| 小节 | 覆盖 |
|------|------|
| P0 | health / pytest / perf_baseline |
| P1 | 统一错误信封（400/404/422/503） |
| P2 | 同步 chat + `max_tool_calls` |
| P3 | `/v1/chat/async` 排队与轮询、导出、任务列表 |
| P4 | 会话轨迹 |
| P5 | 对比/导出/寒暄抽检 |

## 异步用法

```bash
curl -s localhost:8000/v1/chat/async -H 'Content-Type: application/json' \
  -d '{"message":"普通文档保存期限是多久？","session_id":"async-1"}'
# → {"task_id":"...","status":"queued","poll_url":"/v1/tasks/..."}

curl -s localhost:8000/v1/tasks/<task_id>
# status: queued → running → done|error
```

## 测试

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src pytest -q
```

## 说明

- 异步任务在**单进程 uvicorn** 内用 BackgroundTasks，适合演示；多 worker 需共享队列（Redis 等）属后续优化。
- 完整 chat E2E 仍依赖 DeepSeek +（可选）Ollama；单测不调用 LLM。
