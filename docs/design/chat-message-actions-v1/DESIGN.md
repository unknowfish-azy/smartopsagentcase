# 聊天消息操作栏 + 反馈驱动知识复核 —— 方案 v1

- 日期：2026-11-16
- 状态：**已执行**（2026-11-16 16:11 用户给截图提需求；D1 裁决为 A「审核后入共享库」，其余按推荐执行）
- 用户诉求：在 AI 回答下方增加「复制 / 追问 / 收藏 / 转发 / 反馈」等操作；其中**反馈**意味着"原有知识出了问题"，需要 Agent 自己重新独立思考、学习、验证这个问题并标记，让所有用户都能看见；有问题的答案进入「待审核项」。
- 截图落位：`/chat` 会话页，AI 回答气泡下方（`AiChatPanel.vue` 消息循环末尾）。

---

## 一、现状取证

| 能力 | 现状 | 证据 |
|---|---|---|
| 消息渲染 | `AiChatPanel.vue:7-85`，每条 `<article class="ai-chat-message">`；有重试行、运行诊断、证据卡，**没有任何消息级操作栏** | `frontend/src/components/ai/AiChatPanel.vue` |
| 复制范式 | 已有 `copyDiagnostic(messageId, field, value)` + `copyFeedback` 状态（`:253-270`），可直接复用 | 同上 |
| 追问 | 输入框 `draft` + `sendMessage()`；消息对象保留 `prompt`（`:332`），可回填 | `stores/aiChat.js:282-333` |
| 收藏 / 转发 | **无任何现成后端落点**。前端有 `personal_knowledge_entry`（user_id 隔离），团队侧无共享资料写入接口 | `V20261004.4__personal_knowledge.sql`、`api/` 无对应函数 |
| 反馈 → 知识复核 | **不存在**。现有知识候选来源只有 `OPERATION_RUN` / `WEB_RESEARCH` 两种（source_type），由 `KnowledgeCandidateService` 生成 `PENDING_REVIEW` 候选 | `KnowledgeCandidateService.java:17-101` |
| 待审核项页面 | `KnowledgeCandidateReviewView.vue` 已成熟（列表 / 详情 / promote / reject），挂在「MEMORY / 知识审核」 | 693 行，API 在 `api/operations.ts:73-90` |
| 候选表约束 | `UNIQUE(user_id, source_run_id)` + `UNIQUE(user_id, source_task_id)`；`source_run_id` 已可为 NULL | `V20261002` / `V20261115.1` |
| 个人知识库 | `personal_knowledge_entry.library_id/user_id`，**物理隔离** | `V20261004.4` |
| Agent 决策闭环 | `DecisionLoopService` 有 ANALYZE/MEMORIZE/DECIDE/REVIEW/LEARNED 五态，`create/recall/decide/review` 四个入口，但**与聊天消息无关联** | `DecisionLoopService.java:29-161` |
| 检索验证 | 后端有 RAG 检索链（`ai-service`），聊天 metadata 带 `retrieval` / citations / inspection | `AiChatPanel.vue:233-241` |

---

## 二、必须先裁决的红线冲突（D1）

**冲突**：用户说「标记后所有用户都能看见」，但项目现有知识库、候选、个人资料**全部按 `user_id` 物理隔离**——这是"个人空间/团队空间资源独立"的核心卖点，也写进了竞赛材料口径。

| 选项 | 做法 | 影响 |
|---|---|---|
| **A（推荐）** | 反馈候选落 **PENDING_REVIEW 待审核项（仅本人可见）**；"所有用户可见"= 审核 promote 后进入**全局共享知识库**（新建 `shared_knowledge_entry`，与 personal 隔离），全员只读 | 保住隔离红线，又满足全员可见；需新增一张共享表 + 一个只读列表接口 |
| B | 反馈候选本身全用户可见（去掉 user_id 过滤） | **破坏隔离红线**，且未经审核的错误信息会扩散给全员，风险最高，不建议 |
| C | 反馈只在团队内可见（复用团队隔离） | 后端无团队共享资料写入接口，工作量大且不符合"所有用户" |

**默认按 A 执行**，除非用户明确选 B/C。

---

## 三、交互定义（五个按钮）

消息操作栏出现在**非流式、完成态的 assistant 消息**下方（`!pending && !streaming && !error`），五个按钮：

| 按钮 | 行为 | 数据落点 |
|---|---|---|
| 复制 | `navigator.clipboard.writeText(message.content)`，复用现有 `copyFeedback` 显示「已复制」 | 无后端 |
| 追问 | 把该消息对应的 `message.prompt` 回填到输入框，标 `引用上文` 芯片；用户可改后发送，发送时带上 `parentMessageId` | 仅前端会话上下文 |
| 收藏 | 把该回答写入个人知识库条目（标题=问题前 40 字，正文=回答 markdown，sourceType=`CHAT_SAVED`） | `personal_knowledge_entry`（本人可见） |
| 转发 | 生成本地会话导出文本 + 复制；若选中团队，走团队共享接口（D5 待裁决，默认先只做"复制可转发文本"） | 无/团队 |
| 反馈 | 打开反馈弹窗（选择问题类型 + 描述 + 可选正确信息）→ 提交后触发「Agent 复核链」 | 见第四节 |

**反馈弹窗最小字段**：问题类型（事实错误 / 引用错误 / 答案不完整 / 过时 / 其他）、问题描述（必填，≥10 字）、期望修正（选填）。禁止空提交。

---

## 四、反馈 → Agent 自主复核 → 待审核（核心链路）

按用户原话拆解成四个**真实发生**的步骤，任何一步失败都要如实标注，不能假装"已验证"：

```
用户点「反馈」并提交
   ↓ ① 建关联：以 message.id / conversationId / prompt / answer 建 chat_feedback 记录（status=REVIEWING）
   ↓ ② Agent 独立复核（真调用，不合成）：
        a) 把原问题 + 原回答 + 用户反馈交给 Agent，要求"先放下原答案独立作答"
        b) 强制走真实检索（RAG / 已授权知识库），拿到 citations
        c) 生成「复核结论」：确认有误 / 无法确认 / 原答案正确
   ↓ ③ 判定：
        - 确认有误 → 生成修正答案 + 引用，写回 feedback 记录的 revision
        - 无法确认 / 原答案正确 → 也写回结论，如实标注（不硬造"错误"）
   ↓ ④ 入待审核项：
        KnowledgeCandidateService 新增 source_type='CHAT_FEEDBACK'，
        生成 PENDING_REVIEW 候选（标题=问题摘要，正文=复核结论+修正答案+引用+反馈详情）
   ↓ ⑤ 标记可见：
        审核员 promote 后 → 写入共享知识库（D1-A），全员只读可见；
        原消息上显示「已复核」标记（绑 feedback.status）
```

**关键红线**：
1. **Agent 必须真独立思考**：复核 prompt 明确要求忽略原回答；记录 `independent_reasoning` 字段与真实 citations；无检索结果就写「无法确认」，禁止编造修正。
2. **不能直接信任用户反馈**：用户说错时结论可以是「原答案正确」，这就阻止了错误扩散。
3. **不自动发布**：复核结果**永远先入 PENDING_REVIEW**，必须人工 promote 才全员可见（这是"学习"与"发布"的闸门）。
4. **状态可解释**：消息上的标记分「复核中 / 已确认有误 / 无法确认 / 原答案正确 / 已发布」，全程可点开看依据。
5. **不新增 @Scheduled**、不改 poller（沿用引擎可观测的零侵入原则）。

---

## 五、数据契约（新增，最小）

| 表 / 字段 | 用途 |
|---|---|
| `chat_feedback`（新）：`id, user_id, conversation_id, message_id, prompt, original_answer, issue_type, description, expected, status, review_conclusion, revision, citations_json, created_at, updated_at` | 反馈 + Agent 复核全过程留痕 |
| `knowledge_candidate` 新增 `source_message_id VARCHAR(64) NULL`（或复用 `trace_id` 前缀 `chat-feedback-`） | 关联反馈候选，去重键 `(user_id, source_message_id)` |
| `shared_knowledge_entry`（新，D1-A）：`id, candidate_id, title, content_markdown, citations_json, published_by, published_at` | promote 后全员只读可见 |
| `personal_knowledge_entry` | 收藏落点，无需改表 |

**后端接口**（沿用登录态 + internal token，不新开无鉴权口子）：
- `POST /api/chat-feedback`（创建 + 触发复核）
- `GET /api/chat-feedback?messageId=`（查单条消息复核状态）
- `GET /api/shared-knowledge`（全员只读列表）
- `KnowledgeCandidateService.createFromChatFeedback(userId, feedbackId)` → `PENDING_REVIEW`

**幂等**：同一 message_id 只允许一条活跃反馈；重复提交返回 409 或更新描述（默认 409 + 前端提示已有复核）。

---

## 六、工作包

- **T1** 后端：`chat_feedback` 迁移 + Controller + Service（复核编排调用 ai-service，真检索真引用）+ 候选新增 source_type + 共享知识表与列表接口 + 单测/集成测试。
- **T2** 前端消息操作栏：五按钮 UI + 复制/追问/收藏/转发（先做本地文本）+ 反馈弹窗 + `messageFeedback` 状态映射，接 `AiChatPanel.vue:84` 之后。
- **T3** 待审核页：让 `CHAT_FEEDBACK` 来源候选在「知识审核」正常显示（source_type 标签 + 复核引用展示），promote 后写共享库。
- **T4** 共享知识只读视图：入口放「知识中心」分组（新子页），全员可见、只读、带引用。
- **T5** 门禁：单测（复核结论三态、幂等、候选生成）+ 浏览器（五按钮、反馈弹窗校验、消息标记、审核 promote 后共享可见）+ a11y + 双 build。

---

## 七、验收门禁

- 前端 `npm test` / typecheck / lint 0 error / build；后端 `mvn test` 全绿。
- 浏览器 mock：复制成功提示、追问回填、收藏进个人知识库、反馈空描述被拦、三态结论展示、候选出现在待审核、promote 后在共享页可见。
- **真实性核查逐条**：每条"复核结论"必须能追到一次真实 Agent 调用 + 真实 citations；无检索结果时必须显示「无法确认」。
- **隔离核查**：普通用户列表只含共享库条目；个人知识库/候选仍按 user_id 隔离；未 promote 的反馈内容对他人不可见。

---

## 八、待裁决（D1 必答，其余默认执行）

- **D1（红线）**：「所有用户都能看见」采用 A / B / C？**默认 A：审核通过后入全局共享知识库；待审核阶段仅本人+审核员可见**。
- **D2**：追问是否带 `parentMessageId` 形成会话树？（默认：带，但仅用于上下文，不做树状 UI）
- **D3**：收藏是否允许重复？（默认：同一消息只收藏一次，按钮变「已收藏」）
- **D4**：转发范围？（默认：先做"复制可转发文本"，团队共享留后续）
- **D5**：复核用的 Agent 是否复用当前会话的 provider？（默认：复用，且记录实际 provider；失败时状态标「复核失败」而非静默重试）

---

## 九、执行结果（2026-11-16 16:11–16:35）

**用户裁决**：D1 = **A 审核后入共享库**（反馈先入本人待审核项；审核员 promote 后全员只读可见），隔离红线保住。D2–D5 按推荐执行（追问回填带引用文字、收藏去重由知识库侧处理、转发先做本地可转发文本、复核复用 mini 引擎）。

**落地文件**
- 后端：迁移 `V20261116.3__chat_feedback_and_shared_knowledge.sql`；`ChatFeedbackService.java`（真调用 `MiniAssistantEngine.generate` 独立复核 + 三态结论 + 幂等）；`KnowledgeCandidateService` 加 `createFromChatFeedback` / `listShared`，promote 时仅 CHAT_FEEDBACK 来源写共享库；`ChatFeedbackController.java`；`ChatFeedbackServiceTest.java`（4 条三态单测）。
- 前端：`api/chatFeedback.ts`；`components/ai/ChatMessageActions.vue`（五按钮 + 反馈弹窗 + 三态标记 + 重试）；`AiChatPanel.vue` 接入 + 追问回填；`views/knowledge/SharedKnowledgeView.vue`；路由/导航/知识页 zone-tabs 挂载；待审核页标「聊天反馈复核」来源。

**浏览器实测**（dev 5173，mock API）
- 共享页标题「共享知识」、审核后条目可见。
- 操作栏 1 个、五按钮 `[复制, 追问, 收藏, 转发, 反馈]`、反馈弹窗可开、空描述被拦（「问题描述至少需要 10 个字」）、提交后状态「已确认有误 · 待审核」、`page errors: none`。
- 截图 `frontend/test-artifacts/chat-actions-feedback.png`（gitignore）。

**门禁**：后端 `mvn test` **864/0/1 skipped**、前端单测 **823/825**（2 条失败均非本次：① 已修正的知识子项断言 ② TRAE 并行写的 `re-workbench-radiation.test.mjs` 自身 `CY is not defined`，未擅自改）、typecheck 0、lint 0 error、build 通过。

**已知限制（诚实标注）**
- 复核判定是**基于真实 citations + 明确措辞的三态启发式**（CONFIRMED / UNCONFIRMED / ORIGINAL_OK），不是语义推理模型；措辞模糊且有引用时归 CONFIRMED，靠人工审核兜底。
- 反馈提交是**同步复核**（mini 引擎一次生成），耗时取决于该引擎；超时返回 REVIEW_FAILED，需手动"重试复核"，不静默重试。
- 转发当前只做"复制可转发文本"，团队内共享留后续（D4）。
- `shared_knowledge_entry` 全员只读，但列表接口走登录态——未登录用户看不到（不是公开页面）。

**关键坑**：
1. `knowledge_candidate` 新增 `source_message_id` 列 + 唯一索引后才能保证同一消息只有一个复核候选；promote 写共享库用 `INSERT IGNORE` + `candidate_id` 唯一键幂等。
2. 共享知识页用 `v-html="renderMarkdown(...)"`，**必须同时 `import '../../components/ai/markdown.css'`**——v-html 后代没有 scoped 属性，写在 `<style scoped>` 里的 markdown 样式永远匹配不到（沿用 `346ab03` 的全站修复口径）。
3. 后端 Service 内部 record 写法曾被误插到 `promote` 方法体内导致 30+ 编译错；新增 record/方法后先 `mvn -q -DskipTests compile` 验语法再跑测试。
4. 并行代理日志里出现同名文件观察时注意甄别——本轮核对确认 `ChatFeedbackController` / `V20261116.3` 均为本方案唯一实现，未发生覆盖。
