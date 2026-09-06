# 阶段 5 人工验证结论（三期工程化）

- **验证人：** ddmashawty  
- **日期：** 2026-09-06  
- **版本：** `0.3.0`  
- **原始勾选：** [`phase5_verification_checklist.md`](./phase5_verification_checklist.md)  

## 总评：**阶段 5 人工验收通过**

| 模块 | 结果 | 说明 |
|------|------|------|
| P0 环境/基线 | ✅ 3/3 | health `0.3.0`；pytest 13 passed；perf p50≈127ms |
| P1 错误模型 | ✅ 3/3 | 400 / 404 / 422 均带 `error.code` |
| P2 同步+选项 | ✅ 3/3 | TopK=5；`max_tool_calls=2` 可用；任务回放成功 |
| P3 异步 | ✅ 5/5 | queued→done；异步导出；任务列表 |
| P4 会话 | ✅ 2/2 | 同 session 再确认 TopK；turns/tasks 非空 |
| P5/P6 | 未测（可选） | 不影响结项 |

---

## 分项摘要

### P0 ✅
- `/health`：`ok`，hybrid，chunks=293，`version=0.3.0`，`memory_db=data/memory.db`
- `pytest`：13 passed（1 条 starlette DeprecationWarning）
- `perf_baseline`：`rag_search` p50≈127.38ms，已写 `docs/perf_baseline.json`

### P1 ✅
| 用例 | HTTP | code |
|------|------|------|
| 空 message | 400 | `empty_message` |
| 不存在 task | 404 | `task_not_found` |
| 非法 JSON | 422 | `validation_error` |

### P2 ✅
- TopK 默认 **5**（`task_id=e45903ba-…`，`session=verify-p5`）
- `options.max_tool_calls=2` 保存期限问答正确
- `GET /v1/tasks/{id}` 可回放 goal/answer/trace/`created_at`
- 备注：citations 仍可能混入年报噪声；回答层已过滤到产品手册（与二期现象同类，非阻断）

### P3 ✅
- async 立即返回 `queued` + `poll_url`
- 轮询可达 `done`，答案非空
- 异步导出 `p5_async_retention` 通过
- `GET /v1/tasks?session_id=verify-p5-async` 列表可见

### P4 ✅
- 同 session「刚才 TopK」能答出 5
- `/v1/sessions/verify-p5`：turns≥2、tasks 非空

---

## 结项

P0–P4 均达清单最低线 → **阶段 5 可结项**。  
可选后续：P5 回归抽检、推送 GitHub、或另开 Streamlit 前端阶段。
