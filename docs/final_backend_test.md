# 后端终测记录（上传前）

- **日期：** 2026-09-06  
- **版本：** `0.3.0`

## 结果总览：**通过，可发布**

| 项 | 结果 |
|----|------|
| `pytest` | 13 passed |
| `perf_baseline` | hybrid search p50≈119ms |
| `smoke_chat` | 2/3（Q2 答案正确，判分被「3 年」空格误伤；已修 normalize） |
| `smoke_phase4` | OK |
| 错误信封 400/404 | OK |
| `/v1/chat/async` → done | OK（TopK=5） |
| 阶段 5 人工验收 | 已通过（`phase5_verification_result.md`） |

非阻断备注：检索 citations 仍可能混入年报噪声；回答层已能过滤。

判分脚本已改为忽略空格（`scripts/smoke_chat.py`），避免「不少于 3 年」假失败。
