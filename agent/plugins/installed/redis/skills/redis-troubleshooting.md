---
name: redis-troubleshooting
version: 1.0.0
description: Redis服务故障排查
tags:
  - redis
  - cache
  - troubleshooting
---

# Redis故障排查

## 适用场景

当用户遇到：

- Redis无法连接
- Redis响应异常
- Redis服务不可用
- Redis连接数异常
- Redis内存异常
- Redis性能下降

## 排查流程

第一阶段：服务状态

1. 检查Redis是否运行。
2. 检查Redis监听端口。
3. 检查Redis连接状态。

第二阶段：运行信息

使用：

```text
redis.info