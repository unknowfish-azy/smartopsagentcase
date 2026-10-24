---
name: docker-deployment
version: 1.0.0
description: Docker部署与Compose配置检查
tags:
  - docker
  - compose
  - deployment
---

# Docker部署

## 检查顺序

1. 检查Compose文件。
2. 检查镜像。
3. 检查容器。
4. 检查端口。
5. 检查网络。
6. 检查日志。

## 安全

部署类操作可能影响运行中的服务。

所有：

```text
up
down
restart
rm