# SmartOpsAgent Agent

`agent` 是智维Agent的智能执行核心。

负责：

- 任务规划
- 风险判断
- 权限控制
- 工具调用
- 执行
- 验证
- 记忆
- 审计

核心目标：

> 让 AI 不只是“回答问题”，而是能够在安全约束下完成运维任务。

---

## 1. Agent 整体架构

```text
用户请求
   ↓
Planner
   ↓
Agent Plan
   ↓
Policy Engine
   ↓
Risk / Permission
   ↓
Human Approval
   ↓
Tool Registry
   ↓
Executor
   ↓
Tool
   ↓
Execution Result
   ↓
Audit
   ↓
Memory