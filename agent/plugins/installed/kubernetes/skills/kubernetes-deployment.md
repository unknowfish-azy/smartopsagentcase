---
name: kubernetes-deployment
version: 1.0.0
description: Kubernetes部署排查和发布辅助
tags:
  - kubernetes
  - deployment
  - release
---

# Kubernetes部署

优先执行只读检查：

- Deployment
- ReplicaSet
- Pod
- Service
- Events
- Logs

变更操作必须：

```text
Plan
↓
Risk
↓
Approval
↓
Execute
↓
Verification