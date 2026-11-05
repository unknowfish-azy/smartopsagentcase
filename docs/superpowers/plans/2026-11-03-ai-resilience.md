# AI 服务故障透明化实施计划

> **For agentic workers:** 使用 executing-plans，在当前会话逐项执行并核验。用户已授权“按推荐来，先备份，然后执行”；本轮采用原生顺序执行。

**Goal:** 检索故障与空命中分开报告，真实模型流中断不混入 mock，界面进度与实际动作一致。

**Architecture:** 保持现有 FastAPI / ChatService / RAGService / LLMService 边界。为检索添加状态元数据；模型调用重置实例状态；流开始前失败允许显式降级，输出后失败发送 error 事件并结束，不发送 done。

**Tech Stack:** Python、FastAPI、httpx、pytest/pytest-asyncio。

**Spec:** 本计划中的目标、接口约束和验收用例共同描述本次有限修复；全项目路线图见 `docs/development/全面体检与优化方案-20261103.md`。

## Global Constraints

- 先创建源码快照与逐文件备份；保留工作区原有未提交改动。
- 本批修改 AI 三个服务文件及必要的前端流消费/消息状态两个文件，增加行为测试和文档；不迁移数据库，不重启现有服务。
- 不改变现有 answer、results、citations、trust_score 字段结构；只增加状态元数据。
- 检索 HTTP 请求 `trust_env=False`，不继承宿主代理配置。
- LLMService 按现有每请求创建实例的生命周期使用；本批不支持共享实例的并发调用。
- 不引入依赖，不调整评测样本，不恢复已删除的前端功能。

## Review Focus

1. Knowledge 超时、HTTP 错误、坏 JSON、错误结构：返回可解释的降级，不伪装空命中。
2. 同一 LLM 实例先失败后恢复：第二次调用没有上一轮降级标记。
3. 模型已产生真实 token 后断流：保留真实部分、发送 error、不拼入 mock、不发送 done。
4. 空流或缺失 Ollama done 标志：不报告真实模型正常完成。
5. 关闭 RAG、只传图像文件名：不展示实际未执行的检索、视觉识别、规划或风险判断。

## Task 1：检索故障可观测

Files：`ai-service/app/services/rag.py`、`ai-service/app/services/chat.py`、`ai-service/app/tests/test_resilience.py`。

- [x] 增加参数化行为测试：连接错误→unavailable；HTTP 503→unavailable；坏 JSON/非字典/错误列表或分数→invalid_response；有效空结果→empty；有效命中→ok。
- [x] 执行 `python -m pytest -p no:cacheprovider ai-service/app/tests/test_resilience.py -q`，记录当前实现失败。
- [x] `RAGService.retrieve` 禁用环境代理；验证下游所需字段；故障返回空证据加 `retrieval_status/degraded/degradation_reason`，原因使用类别，避免回显连接凭据。
- [x] Chat 非流与流 metadata 加 `rag_status/rag_degraded/rag_degradation_reason`；关闭 RAG 时状态 disabled。
- [x] 验证有效命中仍保留 citations/evidences，坏数据不触发服务 500。

## Task 2：模型恢复与流完整性

Files：`ai-service/app/services/llm.py`、`ai-service/app/services/chat.py`、同一测试文件。

- [x] 测试同实例失败→成功，分别覆盖非流与流。
- [x] 测试首 token 前失败允许 mock；首 token 后错误产生 LLMException，effective_provider 仍为 ollama。
- [x] 测试真实 NDJSON 解析路径的空响应、缺少 done、error 行；已有正常 NDJSON 测试继续通过。
- [x] 每次 generate/generate_stream 开始重置状态；流中断后若已有输出则抛错，尚无输出才降级到 mock。
- [x] Chat 捕获流生成异常，发送 `{event: error, data: {code: LLM_STREAM_INTERRUPTED, message: ...}}` 并 return；不输出 done。

## Task 3：进度真实性、文档与交付

Files：`ai-service/app/services/chat.py`、同一测试文件、体检/开源参考文档、比较记录。

- [x] 关闭 RAG 时只显示回答阶段；开启时显示检索结果摘要和回答；图片只说明文件名已接收。
- [x] 删除固定模拟规划/风险步骤与人为 sleep；检索结果摘要不声称已完成证据验证。
- [x] 执行全部 `ai-service/app/tests` 和 `tests/inspector tests/scripts`；记录命令、退出码与数量。
- [x] 输出体检报告、分阶段 backlog、开源候选表、可恢复网络后的 GitHub 元数据采集脚本。
- [x] 使用 `.runtime/health-audit-20261103-223606/change_bundle.py finalize` 生成改后文件包、差分与哈希；回滚命令为同脚本的 `rollback`，遇到后续文件变化会停止。

## 执行中确认的必要延伸：前端消费流式错误

实际前端原本忽略服务端 error，因此仅修服务端不足以实现故障透明化。已在改写前扩展逐文件备份，纳入 `frontend/src/api/stream.ts`、`frontend/src/stores/aiChat.js`、`frontend/test/stream-resilience.test.mjs` 和已有 `assistant-mini.test.mjs`。

- [x] 行为回归先复现 CRLF 分包、error、提前 EOF、坏 JSON 与丢弃部分回答的错误，同时保留正常 LF/尾事件和取消操作用例。
- [x] 失败通知后仍 reject；Chat store 统一标记失败并保留真实文本，避免 onError/catch 重复追加错误。
- [x] 流式回调校验账户代际；读取完成或失败后取消/释放 reader。
- [x] 定向 23 项通过；全量 471 项/469 通过/2 项原有失败；类型检查和两端独立目录构建通过。

## 验收命令

```powershell
python -m pytest -p no:cacheprovider ai-service/app/tests -q
python -m pytest -p no:cacheprovider tests/inspector tests/scripts -q
python .runtime/health-audit-20261103-223606/change_bundle.py finalize
```

不以修复鉴权测试的方法移除鉴权，也不把在线服务的旧进程视为已加载本轮修改。涉及运行时生效的验证另行标注。

## 独立审阅补充

审阅指出非有限 citation/evidence 分数与字符串 done 的边界。新增 5 个输入先复现失败，再拒绝非有限分数、错误 evidence 分数及非布尔 done；修复后 AI 全套 39 通过。详见 ai-review-boundaries-red.log 和 ai-tests-after.log。
