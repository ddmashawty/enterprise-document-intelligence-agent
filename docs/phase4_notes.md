# 阶段 4（二期）能力说明

- **日期：** 2026-09-06  
- **版本：** `0.2.0`

## 交付项

| 能力 | 实现 |
|------|------|
| 双层记忆 | `SessionMemory`（进程内近期轮次）+ `TaskStore`（SQLite `data/memory.db` 任务轨迹与轮次归档） |
| 结构化导出 | `export_markdown` / `export_excel` → `data/exports/` |
| 反思与重试 | 图节点 `reflect`；不足且 `iteration < MAX_TOOL_CALLS(5)` 则回 `act` |
| 多文档对比 | `compare_docs`（按文档名分组检索证据）+ `extract_fields` |

## 图拓扑

```
START → plan → (direct? finalize : act) → reflect → (retry? act : finalize) → END
```

## 如何测试

逐步勾选清单见 [`backend_verification_checklist.md`](./backend_verification_checklist.md) **§B 阶段 4**：

| 小节 | 覆盖 |
|------|------|
| B0 | `scripts/smoke_phase4.py` 一键冒烟 |
| B1 | 同 `session_id` 多轮 + `GET /v1/tasks` / `sessions` |
| B2 | `reflection` / `iterations≤5` / 导出触发重试 |
| B3 | `compare_docs` 或多文档表格对比 |
| B4 | Markdown / Excel 落盘到 `data/exports/` |
| B5 | chat 增量字段与 404 契约 |

## 冒烟

```bash
PYTHONPATH=src python scripts/smoke_phase4.py
# 期望：export 落盘、task_id 入库、同 session 多轮、可选 agent 导出
```

2026-09-06 实测：`phase4 smoke: OK`；`smoke_chat.py` 仍为 `3/3`。  
人工 B1–B4 初测：[`phase4_verification_result.md`](./phase4_verification_result.md)  
修复后复测：[`phase4_retest_result.md`](./phase4_retest_result.md) — **B2.2 / B3.2 / B4.1 / B4.2 全部通过，阶段 4 可结项。**

## API 增量

- `ChatResponse`：`task_id` / `exports` / `reflection`
- `GET /v1/tasks/{task_id}`
- `GET /v1/sessions/{session_id}`
- `HealthResponse.memory_db`
