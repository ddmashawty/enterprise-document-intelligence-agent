# 阶段 4 功能验证结论

- **验证人：** ddmashawty（的懒）  
- **日期：** 2026-09-06  
- **原始粘贴：** 根目录曾用 `B1-B4.md` 存放完整 `/v1/chat` JSON（体积过大，已改为本摘要；勿再把整包 JSON 入库）  
- **清单：** [`backend_verification_checklist.md`](./backend_verification_checklist.md) §B  

## 总评

| 模块 | 结果 | 说明 |
|------|------|------|
| B1 记忆 | ✅ 通过 | 同 session 多轮、task/session API 正常 |
| B2 反思 | ⚠️ 部分通过 | 有 reflection、iterations≤5；导出触发重试未真正落盘 |
| B3 对比/抽取 | ⚠️ 部分通过 | B3.3 抽取通过；B3.2 对比未调到制度片段 / 未用 `compare_docs` |
| B4 导出 | ❌ 未通过（人工 chat） | `exports=[]`，未生成 verify_* 文件；工具层冒烟仍可用 |
| B0 冒烟脚本 | ✅（同日早些） | `smoke_phase4.py` 曾 PASS（含 agent 导出） |

**结项建议：** 记忆与契约侧已达标；**导出与对比在人工路径上不稳定**，主因是工具轮次被 `list_documents` 空转耗尽（多次 `iterations=5` + reflection「已达工具调用上限」），计划里的 `export_*` / `compare_docs` 未执行。建议修 act/reflect 后再复测 B2.2、B3.2、B4。

按清单 §C 粗评：B1 达标；B2 达最低线（有反思+上限）；B3 未满（对比失败）；B4 人工未过。

---

## 分项摘要（只保留结论，不含完整 JSON）

### B1 双层记忆 — ✅

| # | 结果 | 要点 |
|---|------|------|
| B1.1 | ✅ | `session=verify-p4`，`task_id=4e2c314a-…`，答案 **TopK=5**，引用产品手册 |
| B1.2 | ✅ | 同 session 再确认 TopK=5，`task_id=1cfd7652-…` |
| B1.3 | ✅ | `GET /v1/tasks/4e2c314a-…` 回放 goal/answer/plan/trace |
| B1.4 | ✅ | `GET /v1/sessions/verify-p4` → **turns=4，tasks=2** |

备注：B1.1/B1.2 虽答对，但 `iterations=5`，trace 大量重复 `list_documents`（效率问题，不影响记忆验收）。

### B2 反思与重试 — ⚠️

| # | 结果 | 要点 |
|---|------|------|
| B2.1 | ✅ | 保存期限 3 年 / 10 年；`iterations=2`；有 `reflection` |
| B2.2 | ⚠️ | Markdown 内容正确，但 **`exports=[]`**，文内写「未成功导出」；触达上限停止重试 |
| B2.3 | ✅ | 「你好」`iterations=0`，不崩溃（措辞略提已导出，与 B2.2 事实不完全一致） |

### B3 对比 / 抽取 — ⚠️

| # | 结果 | 要点 |
|---|------|------|
| B3.1（记录标为 B2.4） | ✅ | 列出产品手册、制度、茅台年报等 |
| B3.2 | ❌ | 仅拿到产品手册；称制度「无片段」；**未出现 `compare_docs`**；`iterations=5` |
| B3.3 | ✅ | 普通≥3年、财务合规≥10年、保密四级均抽对 |

### B4 结构化导出 — ❌（本轮人工 chat）

| # | 结果 | 要点 |
|---|------|------|
| B4.1 | ❌ | 已能列出 TopK=5 / 切片=500，但未 `export_markdown`；`exports=[]`；`iterations=5` |
| B4.2 | ❌ | 已知四级名称，却以「缺细则」拒绝整理并 **未 `export_excel`**；`exports=[]` |
| B4.3 / B0 | ✅ | `data/exports/` 中仍有 `smoke_phase4` / `phase4_topk` 等脚本产物，说明**工具本身可用**，问题在 Agent 调度 |

本轮人工未生成 `verify_topk*` / `verify_secrecy*`。

---

## 发现的问题（供修复后复测）

1. **工具空转：** 多题反复 `list_documents`，耗尽 `MAX_TOOL_CALLS=5`，导致 export/compare 未执行。  
2. **过严拒答：** B4.2 在已有「公开/内部/秘密/机密」四级列表时仍拒导出。  
3. **对比召回：** B3.2 对制度文档检索失败（同日 B2.1/B3.3 能命中同一制度），稳定性差。  
4. **原始记录体积：** 完整 chat JSON 不宜进 git；结论用本文件即可。

## 建议复测命令（修复后）

```bash
# 必须重启 API 进程后再测（图有 lru_cache）
PYTHONPATH=src .venv/bin/python -m uvicorn doc_agent.api:app --host 0.0.0.0 --port 8000

PYTHONPATH=src python scripts/smoke_phase4.py
# 复测 B2.2 / B3.2 / B4.1 / B4.2，确认 exports 非空且 trace 含 compare_docs / export_*
```

## 修复说明（2026-09-06）

**根因：** act 轮次由 LLM 自由选工具，反复 `list_documents` 直到 `iterations=5`，`export_*` / `compare_docs` 从未执行。

**改动：**
- `guardrails.py`：导出/对比意图识别、文档名解析、重复 list 过滤、空转检测
- `act`：对比任务自动 `compare_docs`；需要导出且已有证据时强制 `export_*`；`list_documents` 最多 1 次
- `reflect`：缺导出时只允许 export 重试；禁止再建议 list_documents
- `FINAL_SYSTEM`：列举型事实足够即可整理，勿因缺细则拒答

**复测抽样：** `verify_secrecy_fix.xlsx` 已落盘；手册 vs 制度对比两边均有片段且调用了 `compare_docs`。
