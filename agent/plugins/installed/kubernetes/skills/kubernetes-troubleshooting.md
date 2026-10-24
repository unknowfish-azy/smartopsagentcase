---
name: kubernetes-troubleshooting
version: 1.0.0
description: Kubernetes故障排查
tags:
  - kubernetes
  - pod
  - troubleshooting
---

# Kubernetes故障排查

排查顺序：

1. 查询Pod状态。
2. 查询Service。
3. Describe异常资源。
4. 查看Pod日志。
5. 检查事件。
6. 检查资源使用。
7. 建立Evidence。
8. 输出处理建议。

默认不自动执行：

- kubectl delete
- kubectl scale
- kubectl rollout restart

这些操作需要风险检查和人工审批。