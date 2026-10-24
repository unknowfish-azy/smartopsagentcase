# Agent API

## 1. 模块定位

Agent API 是智维Agent智能运维能力的统一入口。

主要负责：

- 接收用户运维任务
- 创建 Agent Task
- 生成任务计划
- 调用 Knowledge
- 执行 Tool
- 返回执行结果
- 输出 Evidence / Citation / Trust Score
- 保存 Audit

---

## 2. 推荐接口

### 创建 Agent 任务

```http
POST /api/agent/tasks
Content-Type: application/json