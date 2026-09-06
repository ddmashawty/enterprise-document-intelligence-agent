# 后端功能验证清单

服务地址：`http://127.0.0.1:8000`  
检索：hybrid（Ollama `qwen3-embedding:0.6b` + BM25）· LLM：DeepSeek `deepseek-chat`  
版本：`0.2.0`（含阶段 4）

**结论汇总：** `[backend_verification_result.md](./backend_verification_result.md)`（一期）· `[phase4_notes.md](./phase4_notes.md)`（二期说明）  
**规则：** 不要把完整 `/v1/chat` JSON 贴进本文件；只勾选结果，并可选写 `answer` / `task_id` / 导出路径摘要。

---

## 启动前准备

```bash
# 1) 依赖与索引（首次或换模型后）
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-embedding.txt
# ollama serve && ollama pull qwen3-embedding:0.6b
PYTHONPATH=src python scripts/ingest_demo.py   # 或 --reindex

# 2) 启动 API
PYTHONPATH=src python -m uvicorn doc_agent.api:app --host 0.0.0.0 --port 8000

# 3) 可选一键冒烟
PYTHONPATH=src python scripts/smoke_chat.py      # 一期 gold 3 题
PYTHONPATH=src python scripts/smoke_phase4.py    # 二期：导出+记忆+会话
```

通用 chat 助手（打印摘要，避免刷屏）：

```bash
chat() {
  curl -s http://127.0.0.1:8000/v1/chat \
    -H 'Content-Type: application/json' \
    -d "$1" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print("session=",d.get("session_id")); print("task=",d.get("task_id")); print("status=",d.get("status"),"iter=",d.get("iterations")); print("reflection=",(d.get("reflection") or "")[:200]); print("exports=",d.get("exports")); print("---"); print((d.get("answer") or "")[:1500])'
}
```

---



## A. 一期回归（可选，改代码后建议跑）



### A0. 环境


| #    | 操作                              | 预期                                                                                           | 结果  |
| ---- | ------------------------------- | -------------------------------------------------------------------------------------------- | --- |
| A0.1 | `GET /health`                   | `status=ok`，`llm=configured`，`retrieval_backend` 含 hybrid/embedding，`chunks>0`，有 `memory_db` | ☐   |
| A0.2 | Ollama 有 `qwen3-embedding:0.6b` | 正常                                                                                           | ☐   |


```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```



### A1–A6. 核心问答


| #    | 提问 / 操作                              | 期望                   | 结果  |
| ---- | ------------------------------------ | -------------------- | --- |
| A1.1 | DocMind Agent Pro 的 TopK 和切片大小分别是多少？ | TopK=5，切片=500 tokens | ☐   |
| A1.2 | 普通文档与财务合规文档的保存期限分别是多久？               | ≥3 年 / ≥10 年         | ☐   |
| A1.3 | 保密等级分为哪几级？                           | 公开、内部、秘密、机密          | ☐   |
| A2.1 | 当前知识库里有哪些文档？                         | 列出已入库文档              | ☐   |
| A2.2 | 你好                                   | 问候、不崩溃               | ☐   |
| A3.1 | 根据已入库年报，这份报告是哪家公司、哪一年度的？             | 贵州茅台 / 2024          | ☐   |
| A3.2 | 从茅台2024年报中概括主营业务和主要风险因素，用条目列出并标注页码   | 有业务+风险+页码            | ☐   |
| A4   | 世界人权宣言中生命/自由/人身安全条款                  | 第三条相关                | ☐   |
| A5   | DocMind Agent Pro 售价多少人民币？           | 依据不足，不编价格            | ☐   |
| A6   | `POST /v1/ingest` 重复导入制度 txt         | 成功                   | ☐   |


```bash
chat '{"message":"DocMind Agent Pro 的 TopK 和切片大小分别是多少？"}'
# ingest 示例：
curl -s http://127.0.0.1:8000/v1/ingest -H 'Content-Type: application/json' \
  -d '{"paths":["data/raw/policies/演示企业文档管理制度.txt"],"reindex":false}' | python3 -m json.tool
```

---



## B. 阶段 4 功能验证（本阶段重点）

阶段 4 测四块：**双层记忆**、**反思重试**、**多文档对比**、**结构化导出**。建议固定一个 `session_id`（如 `verify-p4`），便于查历史。

### B0. 一键冒烟（推荐先跑）


| #    | 操作                                              | 预期                           | 结果  |
| ---- | ----------------------------------------------- | ---------------------------- | --- |
| B0.1 | `PYTHONPATH=src python scripts/smoke_phase4.py` | 全部 PASS / `phase4 smoke: OK` | ☐   |


覆盖：本地 MD/Excel 落盘、chat 产生 `task_id`、SQLite 可读、同会话多轮、agent 导出（或 WARN）。

---



### B1. 双层记忆（会话短期 + SQLite 任务轨迹）

**测什么：** 同 `session_id` 多轮能关联上下文；每轮有 `task_id`；可用 API 回放。


| #    | 操作                                     | 预期                                                 | 结果  |
| ---- | -------------------------------------- | -------------------------------------------------- | --- |
| B1.1 | 第 1 轮：固定 `session_id=verify-p4`，问 TopK | 返回 `session_id`、`task_id`；答案含 5                    | ☐   |
| B1.2 | 第 2 轮：同一 session，说「刚才那个 TopK 数值再确认一次」  | `status=done`；能答出 5（用到会话上下文或再检索均可）                 | ☐   |
| B1.3 | `GET /v1/tasks/{task_id}`（用 B1.1 的 id） | 有 `user_goal`、`answer`、`plan`、`trace`、`created_at` | ☐   |
| B1.4 | `GET /v1/sessions/verify-p4`           | `turns` ≥ 2；`tasks` 非空                             | ☐   |
| B1.5 | （可选）确认 `data/memory.db` 已生成            | 文件存在                                               | 存在  |


```bash
# B1.1
chat '{"session_id":"verify-p4","message":"演示产品手册里 TopK 默认是多少？"}'
# 记下打印的 task=...

# B1.2
chat '{"session_id":"verify-p4","message":"刚才那个 TopK 数值再确认一次"}'

# B1.3 / B1.4（把 TASK_ID 换成真实值）
curl -s http://127.0.0.1:8000/v1/tasks/TASK_ID | python3 -m json.tool | head -n 40
curl -s http://127.0.0.1:8000/v1/sessions/verify-p4 | python3 -c \
  'import sys,json; d=json.load(sys.stdin); print("turns",len(d.get("turns",[])),"tasks",len(d.get("tasks",[]))); print([t.get("task_id") for t in d.get("tasks",[])])'

ls -la data/memory.db
```

**通过标准：** B1.1–B1.4 全过即可；进程重启后 B1.4 的 `turns` 仍应能从 SQLite 读出（短期内存会丢，持久层应在）。

---



### B2. 反思校验 + 工具重试（max 5）

**测什么：** 响应含 `reflection`；困难/缺证据或要求导出未完成时可能 `iterations>1`；不会无限循环（`iterations ≤ 5`）。


| #    | 操作                          | 预期                                                              | 结果  |
| ---- | --------------------------- | --------------------------------------------------------------- | --- |
| B2.1 | 普通有答案问题（如保存期限）              | `status=done`；有 `reflection` 字段（可为空串或简短说明）；`iterations` 在 1–5   | ☐   |
| B2.2 | 明确要求导出但首次可能未落盘的问法，或故意模糊：见下方 | 最终 `done`；若曾重试则 `iterations≥2` 或 `trace` 中工具轮次更多；`iterations≤5` | ☐   |
| B2.3 | 寒暄「你好」                      | `route` 偏 direct / 少工具；不崩溃；`iterations` 很小                      | ☐   |


```bash
# B2.1
chat '{"session_id":"verify-p4-reflect","message":"普通文档与财务合规文档的保存期限分别是多久？"}'

# B2.2：强制导出路径（更容易触发 reflect「缺导出则重试」）
chat '{"session_id":"verify-p4-reflect","message":"把制度里保存期限整理成 Markdown 报告并导出到文件，文件名 verify_retention"}'

# B2.3
chat '{"session_id":"verify-p4-reflect","message":"你好"}'
```

**如何看重试：** 看返回的 `iterations`、`trace` 长度、`reflection` 文案（如「尚未生成文件」「建议重试检索」）。不必强求每次都重试，但 **上限不被突破** 必须满足。

---



### B3. 多文档对比 / 字段抽取

**测什么：** Agent 能调用 `compare_docs`（或多次 `rag_search`）做对比；回答 grounded；可选 `extract_fields`。

**前置：** 知识库至少 2 篇可对比文档。仅茅台年报时，可用「制度 txt + 产品手册 txt」对比参数/期限类问题；若已 ingest 多份年报，再用营收对比。


| #    | 操作                               | 预期                                            | 结果  |
| ---- | -------------------------------- | --------------------------------------------- | --- |
| B3.1 | 先问：当前知识库有哪些文档？                   | 记下至少 2 个 `doc_name`                           | ☐   |
| B3.2 | 对比题（二选一，见下方）                     | 回答分文档/表格；有引用；`trace` 中出现 `compare_docs` 或多次检索 | ☐   |
| B3.3 | （可选）抽取题：从制度中抽取「普通文档保存期限」「保密等级列表」 | 有字段结论或明确依据不足；不编造                              | ☐   |


```bash
# B3.1
chat '{"session_id":"verify-p4-cmp","message":"当前知识库里有哪些文档？列出文件名"}'

# B3.2a — 可控样例（推荐，不依赖第二份年报）
chat '{"session_id":"verify-p4-cmp","message":"对比《演示产品参数手册》和《演示企业文档管理制度》：分别列出与“保存/参数/期限”相关的关键数字或条款，用表格，并标注来源"}'

# B3.2b — 若已入库多份年报
chat '{"session_id":"verify-p4-cmp","message":"对比茅台与五粮液2024年报中披露的主营业务要点（有依据才写，缺失写依据不足），用表格"}'

# B3.3
chat '{"session_id":"verify-p4-cmp","message":"从制度文档抽取字段：普通文档保存期限、财务合规保存期限、保密等级列表；没有依据的字段标 null"}'
```

**通过标准：** 表格/分列清晰；数字来自文档；缺失处写「依据不足」而非编造。

---



### B4. 结构化导出（Markdown / Excel）

**测什么：** `exports` 非空或回答给出路径；`data/exports/` 下确有文件；Excel 可打开。


| #    | 操作            | 预期                                          | 结果  |
| ---- | ------------- | ------------------------------------------- | --- |
| B4.1 | 要求导出 Markdown | `exports` 含 `format=markdown` 与 `path`；文件可读 | ☐   |
| B4.2 | 要求导出 Excel 表格 | `exports` 含 `format=excel`；`.xlsx` 存在       | ☐   |
| B4.3 | （离线）直接跑工具冒烟   | `smoke_phase4.py` 前两项 PASS                  | ☐   |


```bash
# B4.1
chat '{"session_id":"verify-p4-export","message":"根据演示产品手册，用 Markdown 写一份 TopK 与切片参数说明，并导出文件，文件名 verify_topk"}'
# 检查：
#   打印的 exports=[{... path: data/exports/...md }]
ls -la data/exports/ | tail
# head -n 20 data/exports/<刚生成的>.md

# B4.2
chat '{"session_id":"verify-p4-export","message":"把保密等级四级整理成表格并导出 Excel，文件名 verify_secrecy"}'
ls data/exports/*.xlsx | tail
# 可用 Excel / LibreOffice 打开抽查表头
```

**若 LLM 未调 export_*：** 看 `reflection` 是否提示重试；可再发一轮「请务必调用 export_markdown 落盘」。最终以 **文件出现在** `data/exports/` 或 **B0/B4.3 离线工具 PASS** 为准（工具本身可用）。

---



### B5. 接口契约抽查（阶段 4 增量字段）


| #    | 操作                           | 预期                                                           | 结果  |
| ---- | ---------------------------- | ------------------------------------------------------------ | --- |
| B5.1 | 任意成功 chat                    | 响应含 `task_id`、`exports`（数组）、`reflection`（字符串）、`plan`、`trace` | ☐   |
| B5.2 | 错误 `GET /v1/tasks/not-exist` | HTTP 404                                                     | ☐   |
| B5.3 | `GET /health`                | 含 `memory_db`（如 `data/memory.db`）                            | ☐   |


```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/v1/tasks/not-exist
# 期望 404
```

---



## C. 汇总打分（阶段 4）


| 模块    | 项数             | 建议最低通过     | 你的结果 |
| ----- | -------------- | ---------- | ---- |
| B0 冒烟 | 1              | 1          | ✅ 1 |
| B1 记忆 | 4（B1.5 可选）     | 4          | ✅ 4 |
| B2 反思 | 3              | 2（B2.1+上限） | ✅ 复测 B2.2 导出通过（见 phase4_retest） |
| B3 对比 | 2（B3.3 可选）     | 2          | ✅ 复测 B3.2 通过（compare_docs） |
| B4 导出 | 2（B4.3 可并入 B0） | 2          | ✅ B4.1/B4.2 合法 JSON 复测通过 |
| B5 契约 | 3              | 3          | （B1.3/B1.4 已覆盖 task/session） |


**结项建议：** B0 + B1 + B4 + B5 全过，且 B2/B3 至少达到上表最低线 → 阶段 4 功能验收通过。  
**2026-09-06 最终：** 修复后复测 B2.2 / B3.2 / B4.1 / B4.2 全部通过 → 见 [`phase4_retest_result.md`](./phase4_retest_result.md)。

---



## 验证记录


| 日期         | 验证人        | 范围            | 通过项/总项          | 备注              |
| ---------- | ---------- | ------------- | --------------- | --------------- |
| 2026-09-05 | ddmashawty | 一期 A          | 见 result        | 3.2 hybrid 复测通过 |
| 2026-09-06 | （脚本）       | B0            | smoke_phase4 OK | 自动化冒烟           |
| 2026-09-06 | ddmashawty | 阶段 4 人工 B1–B4 | 见 phase4 result | 原始 JSON 已摘要；B4/B3.2 待修后复测 |
| 2026-09-06 | ddmashawty | 修复后复测 B2.2/B3.2/B4 | 全部通过 | 见 [`phase4_retest_result.md`](./phase4_retest_result.md) |


