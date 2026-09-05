# 后端功能验证清单（一期 MVP）

服务地址：`http://127.0.0.1:8000`  
检索：本地 Ollama `qwen3-embedding:0.6b` + BM25 hybrid · LLM：DeepSeek `deepseek-chat`

**验收结论请写在 / 查阅：** [`backend_verification_result.md`](./backend_verification_result.md)  
请勿把完整 `/v1/chat` JSON 粘贴进本文件（体积过大）；只保留 `answer` 摘要与勾选结果。

---

## 0. 环境自检

| # | 操作 | 预期 | 结果 |
|---|------|------|------|
| 0.1 | `GET /health` | `status=ok`，llm configured，retrieval 含 embedding/hybrid，chunks>0 | ☐ |
| 0.2 | Ollama 可见 `qwen3-embedding:0.6b` | 正常 | ☐ |

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

## 1. 可控样例

| # | 提问 | 期望要点 | 结果 |
|---|------|----------|------|
| 1.1 | DocMind Agent Pro 的 TopK 和切片大小分别是多少？ | TopK=5，切片=500 tokens | ☐ |
| 1.2 | 普通文档与财务合规文档的保存期限分别是多久？ | ≥3 年 / ≥10 年 | ☐ |
| 1.3 | 保密等级分为哪几级？ | 公开、内部、秘密、机密 | ☐ |

## 2. 工具链

| # | 提问 | 期望 | 结果 |
|---|------|------|------|
| 2.1 | 当前知识库里有哪些文档？ | 列出已入库文档，不编造 | ☐ |
| 2.2 | 你好 | 正常问候、不崩溃 | ☐ |

## 3. 年报

| # | 提问 | 期望 | 结果 |
|---|------|------|------|
| 3.1 | 根据已入库年报，这份报告是哪家公司、哪一年度的？ | 贵州茅台 / 2024 | ☐ |
| 3.2 | 从茅台2024年报中概括主营业务和主要风险因素，用条目列出，并标注页码 | 有业务+风险条目与页码；勿胡编 | ☐ |

## 4–6. 其他

| # | 提问 / 操作 | 期望 | 结果 |
|---|-------------|------|------|
| 4 | 世界人权宣言中生命/自由/人身安全条款 | 第三条相关，有引用 | ☐ |
| 5 | DocMind Agent Pro 售价多少人民币？ | 依据不足，不编价格 | ☐ |
| 6 | `POST /v1/ingest` 重复导入制度 txt | 成功、不崩溃 | ☐ |

## curl 模板

```bash
curl -s http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"把你的问题粘在这里"}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("answer","")[:2000])'
```

## 验证记录

| 日期 | 验证人 | 通过项/总项 | 备注 |
|------|--------|-------------|------|
| 2026-09-05 | ddmashawty | 见 result 文档 | 初测通过；3.2 经 hybrid 复测通过 |
