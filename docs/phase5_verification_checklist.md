# 阶段 5 人工功能验证清单（三期工程化）

服务地址：`http://127.0.0.1:8000`  
版本：`0.3.0` · LLM：DeepSeek · 检索：hybrid  
说明文档：`[phase5_notes.md](./phase5_notes.md)`

**规则：** 不要粘贴完整 `/v1/chat` JSON；只勾选 ☐/✅，并可写 `task_id`、`status`、`error.code`、导出路径摘要。  
**结论可记在：** 文末「验证记录」或另建 `phase5_verification_result.md`。

---

## 启动前准备

```bash
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -r requirements-embedding.txt   # 若用稠密检索
# ollama serve && ollama pull qwen3-embedding:0.6b

PYTHONPATH=src python scripts/ingest_demo.py
# 自动化基线（建议先跑）
pytest -q
PYTHONPATH=src python scripts/perf_baseline.py

# 单进程启动（异步任务依赖 BackgroundTasks，勿用多 worker 演示）
PYTHONPATH=src python -m uvicorn doc_agent.api:app --host 0.0.0.0 --port 8000
```

浏览器可打开：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)  
注意：Swagger 里 `message` **只写一层字符串**，禁止 `"message": "message": "..."`。

摘要助手：

```bash
chat() {
  curl -s http://127.0.0.1:8000/v1/chat \
    -H 'Content-Type: application/json' -d "$1" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print("task=",d.get("task_id"),"status=",d.get("status"),"iter=",d.get("iterations")); print((d.get("answer") or "")[:800]); print("exports=",d.get("exports"))'
}

poll() {
  curl -s "http://127.0.0.1:8000/v1/tasks/$1" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print("status=",d.get("status"),"iter=",d.get("iterations")); print((d.get("answer") or d.get("reflection") or "")[:600])'
}
```

---



## P0. 环境与自动化基线


| #    | 操作                         | 预期                                                                         | 结果  |
| ---- | -------------------------- | -------------------------------------------------------------------------- | --- |
| P0.1 | `GET /health`              | `status=ok`，`version` 含 `0.3`，有 `memory_db`、`retrieval_backend`、`chunks>0` | ✅  |
| P0.2 | `pytest -q`                | 全部 passed（当前约 13）                                                          | ✅  |
| P0.3 | `scripts/perf_baseline.py` | 生成/更新 `docs/perf_baseline.json`；`rag_search` p50 有数值                       | ✅  |


```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
pytest -q
PYTHONPATH=src python scripts/perf_baseline.py
```

> 实测：health ok / pytest 13 passed / perf p50≈127ms。见 result 文档。

---



## P1. 统一错误模型


| #    | 操作                                     | 预期                                                                      | 结果  |
| ---- | -------------------------------------- | ----------------------------------------------------------------------- | --- |
| P1.1 | `POST /v1/chat`，body `{"message":" "}` | HTTP **400**；JSON 形如 `{"error":{"code":"empty_message","message":...}}` | ✅  |
| P1.2 | `GET /v1/tasks/not-exist-id`           | HTTP **404**；`error.code=task_not_found`                                | ✅  |
| P1.3 | 非法 JSON：`curl ... -d '{bad'`           | HTTP **422**；`error.code=validation_error`                              | ✅  |
| P1.4 | （可选）临时去掉/清空 `LLM_API_KEY` 后 chat       | HTTP **503**；`error.code=llm_not_configured`（测完恢复 Key）                  | ☐   |


```bash
curl -s -w "\nHTTP %{http_code}\n" http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' -d '{"message":"   "}'

curl -s -w "\nHTTP %{http_code}\n" http://127.0.0.1:8000/v1/tasks/not-exist-id

curl -s -w "\nHTTP %{http_code}\n" http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' -d '{bad'
```

**通过标准：** 错误一律带顶层 `error` 对象，含 `code` + `message`（不要再是纯字符串 detail）。

---



## P2. 同步 Chat + 请求选项


| #    | 操作                                    | 预期                                                 | 结果  |
| ---- | ------------------------------------- | -------------------------------------------------- | --- |
| P2.1 | 同步问：TopK 默认多少（`session_id=verify-p5`） | 200；答案含 **5**；有 `task_id`；`status=done`            | ✅  |
| P2.2 | 带 `options.max_tool_calls: 2` 问制度保存期限 | 200；`iterations ≤ 2`；答案仍合理（3年/10年）或明确依据不足          | ✅  |
| P2.3 | `GET /v1/tasks/{P2.1的task_id}`        | 回放 `user_goal` / `answer` / `trace` / `created_at` | ✅  |


```bash
chat '{"session_id":"verify-p5","message":"演示产品手册里 TopK 默认是多少？"}'

chat '{"session_id":"verify-p5","message":"普通文档与财务合规文档保存期限分别多久？","options":{"max_tool_calls":2}}'

# poll <task_id>

> 原始完整 JSON 已省略。结论：P2.1–P2.3 通过；示例 `task_id=e45903ba-6b9b-4b19-8e17-82d6d1ebe6bf`（TopK=5）。详见 [`phase5_verification_result.md`](./phase5_verification_result.md)。

---



## P3. 异步任务（本阶段重点）


| #    | 操作                                                                 | 预期                                                                   | 结果  |
| ---- | ------------------------------------------------------------------ | -------------------------------------------------------------------- | --- |
| P3.1 | `POST /v1/chat/async`，message=保存期限类问题，`session_id=verify-p5-async` | 立即返回：`task_id`、`status=queued`、`poll_url`                            | ✅  |
| P3.2 | 提交后马上 `GET poll_url`                                               | `status` 为 `queued` 或 `running`（偶发已 `done` 也可）                       | ✅  |
| P3.3 | 每隔 2s 轮询，最多 ~60s                                                   | 最终 `status=done`；`answer` 非空；有 citations 或 grounded 说明               | ✅  |
| P3.4 | 异步要求导出：`导出 Markdown，文件名 p5_async_retention`                        | 最终 `done`；`exports` 非空或 `data/exports/` 出现 `*p5_async_retention*.md` | ✅  |
| P3.5 | `GET /v1/tasks?session_id=verify-p5-async`                         | `count≥1`；列表含刚创建的 task                                               | ✅  |


```bash
curl -s http://127.0.0.1:8000/v1/chat/async \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"verify-p5-async","message":"普通文档保存期限是多久？"}' \
  | python3 -m json.tool
# 记下 task_id，然后：
# poll <task_id>

curl -s http://127.0.0.1:8000/v1/chat/async \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"verify-p5-async","message":"把制度里保存期限整理成 Markdown 并导出，文件名 p5_async_retention"}'

curl -s "http://127.0.0.1:8000/v1/tasks?session_id=verify-p5-async&limit=10" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("count",d["count"]); print([t["task_id"][:8]+"…/"+t["status"] for t in d["tasks"]])'
```

**注意：** 必须用**单进程** uvicorn；改代码后需重启服务，否则 BackgroundTasks / 图缓存仍是旧逻辑。

---



## P4. 会话轨迹


| #    | 操作                                         | 预期                     | 结果  |
| ---- | ------------------------------------------ | ---------------------- | --- |
| P4.1 | 同 `session_id=verify-p5` 再问一句「刚才 TopK 是多少」 | 200；能答出 5              | ✅  |
| P4.2 | `GET /v1/sessions/verify-p5`               | `turns` ≥ 2；`tasks` 非空 | ✅  |


```bash
chat '{"session_id":"verify-p5","message":"刚才那个 TopK 数值再确认一次"}'
curl -s http://127.0.0.1:8000/v1/sessions/verify-p5 \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("turns",len(d["turns"]),"tasks",len(d["tasks"]))'
```

---



## P5. 回归抽检（可选，各 1 题即可）


| #    | 操作                            | 预期                                                    | 结果  |
| ---- | ----------------------------- | ----------------------------------------------------- | --- |
| P5.1 | 对比手册 vs 制度（保存/参数）             | 表格；trace 含 `compare_docs` 或双边引用                       | ☐   |
| P5.2 | 导出保密等级 Excel，文件名 `p5_secrecy` | `exports` 有 excel；`data/exports/*p5_secrecy*.xlsx` 存在 | ☐   |
| P5.3 | 寒暄「你好」                        | 不崩溃；`iterations` 很小                                   | ☐   |


更完整的一期/二期项见 `[backend_verification_checklist.md](./backend_verification_checklist.md)`。

---



## P6. 可复现脚本（可选）


| #    | 操作                           | 预期                                            | 结果  |
| ---- | ---------------------------- | --------------------------------------------- | --- |
| P6.1 | `bash scripts/demo_repro.sh` | ingest + pytest 通过；有 Key 时跑 smoke；打印启动 API 提示 | ☐   |


---



## C. 汇总打分（阶段 5）


| 模块       | 建议最低通过        | 你的结果 |
| -------- | ------------- | ---- |
| P0 环境/基线 | 3/3           | ✅ 3/3 |
| P1 错误模型  | 3/3（P1.4 可选）  | ✅ 3/3 |
| P2 同步+选项 | 3/3           | ✅ 3/3 |
| P3 异步    | 4/5（P3.4 建议过） | ✅ 5/5 |
| P4 会话    | 2/2           | ✅ 2/2 |
| P5 回归    | 可选            | 未测   |


**结项建议：** P0+P1+P2+P3（含至少一次 async done）+P4 全过 → 阶段 5 人工验收通过。

---



## 验证记录


| 日期 | 验证人 | 通过项 | 备注 |
|------|--------|--------|------|
| 2026-09-06 | ddmashawty | P0–P4 全过 | 见 [`phase5_verification_result.md`](./phase5_verification_result.md) |


