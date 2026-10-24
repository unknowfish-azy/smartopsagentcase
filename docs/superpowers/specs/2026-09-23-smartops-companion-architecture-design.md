# SmartOps Companion Architecture Design

## 目标

将 Ops Spider 从单一悬浮 UI 升级为 SmartOpsAgent 的驻留式运维智能体入口，并统一 Spider、Jellyfish、Whale、VisualOps、Smart Inquiry、Knowledge Base、Remote Operations 和 Memory 的边界。

Phase 1 只实现观察、上下文、询问和知识关联，不执行任何远程或破坏性操作。

## 角色边界

### Spider / Perception

负责观察、检测、跟踪和提交证据：屏幕、页面、OCR、DOM、网络信号、终端或监控事件。Spider 只能提交观察结果和 Fault Event，不生成修复结论，也不调用远程执行工具。

### Jellyfish / Reasoning

负责理解上下文、生成问题、维护假设、检索知识和给出建议。Jellyfish 必须区分 Observed、Inferred、Hypothesis 和 Recommendation。

### Whale / Environment

负责承载系统、服务器、Kubernetes、Docker、数据库、网络和远程会话的环境状态。Whale 提供环境信号，不负责推理或执行。

### Knowledge Base

负责 Runbook、文档、历史事故和命令参考的检索与引用。知识结果必须包含来源、章节、匹配证据和风险信息。知识库不能直接触发命令。

### Remote Operations

负责未来的工具调用、风险评估、人工授权、执行和验证。Phase 1 不接入执行路径。

## Phase 1 范围

### 统一上下文

新增 `CompanionContext`，作为 Spider、Jellyfish、Whale、Knowledge 和未来 Remote Operations 的共享数据边界。至少包含：

- session / active page / active window
- visual observations 和证据
- infrastructure signals
- remote session references
- incidents、knowledge references
- questions、answers、hypotheses、recommendations
- current companion mode、attention policy 和 risk context
- execution permission，默认始终为 `false`

现有 `FaultEvent` 和 `InvestigationContext` 作为兼容输入，逐步映射到统一上下文；不重复建立平行调查数据模型。

### Companion Event Bus

建立轻量事件总线，使用明确事件名称传递事实，不让组件直接互相调用。Phase 1 事件包括：

`VISION_DETECTED`、`FAULT_DETECTED`、`INVESTIGATION_STARTED`、`QUESTION_REQUIRED`、`ANSWER_RECORDED`、`KNOWLEDGE_REFERENCED`、`RECOMMENDATION_READY`、`USER_CLICKED_SPIDER`。

事件记录 `id`、`type`、`timestamp`、`source`、`contextId` 和不可变 `payload`，为后续时间线、审计和回放保留基础。

### Companion 状态

状态与事件分离。Phase 1 状态包括：

- Spider：`SLEEPING`、`IDLE`、`OBSERVING`、`SUSPICIOUS`、`ANOMALY`、`INVESTIGATING`、`RECOVERING`
- Jellyfish：`WAIT`、`CONTEXT_BUILDING`、`TRIAGING`、`QUESTIONING`、`SEARCHING`、`RECOMMENDING`
- Whale：`STABLE`、`DEGRADED`、`UNKNOWN`
- Interaction：`FOCUS`、`QUIET`、`NORMAL`

状态只表达当前态，历史变化通过事件保存。

### Smart Inquiry 集成

现有 Smart Inquiry Drawer 继续作为用户入口。Fault Event 创建后：

```text
Spider detects
→ Companion Event Bus
→ CompanionContext
→ Smart Inquiry questions
→ user answer
→ Knowledge query
→ evidence-backed recommendation
```

问题优先按信息增益排序；用户答案保留原文、标准化结果和置信度。关闭调查只改变调查状态，不删除上下文和历史数据。

### 注意力和降级

新增 Attention Policy 数据结构，为 Focus、Quiet 和 Normal 模式提供统一规则。通知层与对话层分离：普通异常只产生视觉提示，用户主动打开后才进入调查。

AI、网络、知识检索或视觉能力不可用时，保留本地事件、规则和只读调查能力，并明确显示能力降级状态，不伪造分析或恢复结果。

## 数据流

```text
Observation
  ↓
Companion Event Bus
  ↓
CompanionContext
  ↓
Evidence Fusion
  ↓
Smart Inquiry
  ↓
Knowledge Evidence
  ↓
Hypothesis / Recommendation
```

Phase 1 的终点是 `RECOMMENDATION_READY`。`APPROVAL_REQUIRED`、`EXECUTION`、`VERIFICATION` 和 `MEMORY_LEARNING` 保留接口，但不实现自动执行。

## 安全边界

- 默认 `executionAllowed = false`。
- 不调用 SSH、Shell、kubectl、Docker、数据库写操作或网页自动点击。
- 不把视觉推断当作事实，不伪造 Kubernetes、服务器或告警数据。
- 任何未来执行都必须经过 Intent、Target、Precheck、Preview、Risk、Approval、Execute、Verify 的 Execution Contract。
- 当前知识库只提供证据、Runbook 和建议。

## 组件边界

Phase 1 建议新增或整理以下模块：

- `companion/eventBus.js`：事件发布、订阅和清理
- `companion/context.js`：上下文创建、合并和只读快照
- `companion/state.js`：角色状态和注意力状态
- `stores/companion.js`：Pinia 状态适配层
- `components/companion/CompanionStatus.vue`：能力和状态的最小展示

现有 `OpsSpiderPet` 只负责视觉与交互；`SmartInquiryDrawer` 只负责调查呈现；知识检索继续通过统一的 `searchKnowledgeEntries` 接口访问。

## 测试和验收

Phase 1 必须覆盖：

- 事件总线发布、订阅、取消订阅和 payload 不可变性
- CompanionContext 合并 Fault Event、用户答案和知识引用
- Spider/Jellyfish/Whale 状态转换与事件分离
- Focus / Quiet / Normal 注意力规则
- AI 或知识不可用时的降级状态
- executionAllowed 在所有路径中保持 `false`
- 现有 Smart Inquiry、Knowledge、Ops Spider 拖动和应用导航回归测试

验证命令：`npm test`、`npm run build`、`npm run lint`、`npm run typecheck`、`git diff --check`。

## 后续阶段

Phase 2：VisualOps Capture、DOM、Network、Console 和时间聚合。

Phase 3：Jellyfish Agent 推理循环、Hypothesis 和 Investigation Memory。

Phase 4：Tool Gateway、Remote Operations、Risk Engine 和 Approval。

Phase 5：Verification、Incident Memory、Wrong Answer 和 Knowledge Learning。

每个阶段必须复用 `CompanionContext` 和 Event Bus，禁止重新创建平行状态体系。
