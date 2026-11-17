# 第⑤步：纠错、知识候选与复盘沉淀写回记忆 — 实施计划

## Context

五步计划的最后一步。探索确认：控制台聊天纠错→知识候选链路（`ChatMessageActions.vue` → Java `ChatFeedbackService` 独立复核 → `knowledge_candidate` PENDING_REVIEW → 人工 promote → 共享知识）与 Java 侧复盘沉淀（`DecisionLoopService`/哨兵蒸馏 → `recordLearned`）已完整存在，**不重做**。真实缺口有两个：

1. **agent 层 PlanRunner 失败教训不落库**：`PlanRunner.run()` 失败终止后 `RunOutcome` 只留在内存，失败步骤/错误类别无法被 chat recall 召回。
2. **数字人聊天（小鱼）没有纠错入口**：`AgentPersonaView` 无反馈按钮，用户纠错进不了知识候选链路。

## 改动清单（新增 2 + 修改 3）

### 1. backend：新增内部复盘写回端点
- 修改 `backend/src/main/java/com/smartops/controller/InternalMemoryController.java`：新增 `POST /api/internal/memory/experience`，调既有 `OperatorMemoryService.recordLearned(userId, incidentKey, preferredAction, sourceRefs)`；userId 为 null 返回 success(null)（与 remember 一致）；新增 `ExperienceRequest` record。鉴权由既有 `/api/internal/**` INTERNAL 过滤器链自动覆盖，无需改 SecurityConfig。
- 新增测试 `backend/src/test/java/com/smartops/controller/InternalMemoryExperienceTest.java`：仿 `RecoveryContractSecurityTest`（@WebMvcTest + SecurityConfig + InternalTokenAuthenticationFilter），覆盖无 token 401 / 错 token 403 / 正确 token 参数透传。

### 2. agent 层：失败复盘上报 sink（fail-open）
- 新增 `agent/planner/experience.py`：`ExperienceSink`
  - urllib POST `{backend}/api/internal/memory/experience`，env 复用 `SMARTOPS_BACKEND_URL` / `SMARTOPS_INTERNAL_TOKEN`（import 自 `agent/recovery_contracts/publisher.py` 常量），header `X-SmartOps-Internal-Token`。
  - **全程 fail-open**：配置缺失、网络失败、非 2xx 一律 `logger.warning`（带 plan_id），不发也不抛。
  - `report(outcome, user_id)`：user_id 为 None/非数字、或 status 非失败态（failed / reflection_budget_exhausted）直接返回。
  - payload：`incidentKey` = goal 剥动词前缀（排查/检查/处理/修复等）后截断 40 字，适配 recall 的「incident_key ⊂ 用户句子」子串匹配；`preferredAction` = 教训句（失败步骤 tool_name + error_category + error，注明重规划仍未解决需人工介入）；`sourceRefs` = `PLAN_RUN:{outcome.plan_ids[-1]}` 幂等键。
- 修改 `agent/planner/runner.py`：`__init__` 加可选 `experience_sink=None`；两处失败终止点（failed、reflection_budget_exhausted）后调用 `self._report_failure(outcome, context)`，内部 `getattr(context, "user_id", None)` + try/except 包裹（RuntimeContext 已有 `user_id: str | None`）。
- 修改 `agent/planner/__init__.py`：导出 `ExperienceSink`。
- 新增 `tests/agent/test_experience.py`：mock 模式照搬 `tests/recovery_contracts/test_publisher.py` 的 `_FakeResponse` + monkeypatch urlopen。覆盖：失败两态均上报、成功不上报、user_id None/非数字跳过、sink 抛异常不冒泡、HTTP 失败吞掉、payload 字段与幂等键。

### 3. frontend：数字人聊天接入纠错
- 修改 `frontend/src/views/agent/AgentPersonaView.vue`：
  - assistant reply 初始对象补 `prompt: checked.text`（发送时的用户问题）。
  - assistant 消息 li 内嵌入既有 `<ChatMessageActions :message="message" conversation-id="persona" />`（仅 `role==='assistant' && content && !error` 时渲染），复用其反馈对话框/提交/状态展示，零新逻辑。
  - 补 import `ChatMessageActions` 组件。
- 已知降级：persona 的 messageId 是本地 UUID，跨会话回查反馈记录（getChatFeedbackByMessage）查不到会被组件 catch 吞掉，不阻塞提交与候选生成。

## 不做的事

- 不改 ChatFeedbackService / KnowledgeCandidateService（链路已完整）。
- 不给 PlanRunner 加重试之外的反思行为；sink 只读上报。
- 不动 ai-service（其偏好记忆闭环是第②步成果，保持现状）。

## 验证

1. `mvn -q "-Dtest=InternalMemoryExperienceTest,OperatorMemoryServiceTest" -DforkCount=0 test`
2. `python -m pytest tests/agent/test_experience.py tests/agent/test_plan_p1.py -q`
3. `cd frontend && npm run build`（嵌入组件编译通过）
4. 全量回归：`python -m pytest tests/agent -q`（243 项）、`npm test`（1010 项）

## 实施顺序

backend 端点+测试 → agent sink+测试 → runner 接线 → frontend 嵌入。
