# 前端验证清单（阶段 6 / F1–F3）

后端先在 `8000` 启动。前端：`bash scripts/run_frontend.sh`，打开 http://127.0.0.1:8501 。

| # | 步骤 | 期望 |
|---|------|------|
| F0 | 侧栏健康徽章 | 显示 status、version、llm、chunks；后端没开时看到 `connection_error` |
| F1 | 同步提问「演示产品手册里 TopK 是多少？」 | 气泡有回答；可展开 Plan / Citations / Trace |
| F2 | 切到异步，问「保密等级分为哪几级？导出 Excel，文件名 demo_secrecy」 | 状态从 queued/running 到 done；Exports 里有路径；Trace 里有工具名 |
| F3 | 知识库导入 `data/raw/policies` | 显示 docs_indexed / chunks；失败文件带错误 |
| F4 | 任务中心 | 表格有 task_id、status、goal；点开能看到 answer 与 trace |
| F5 | 演示剧本 | 6 条问句可一键送入对话 |
| F6 | 空消息或错误 API 地址 | 界面显示 `code：message`，而不是整页堆栈 |
