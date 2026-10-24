---
name: docker-troubleshooting
version: 1.0.0
description: Docker容器故障排查
tags:
  - docker
  - container
  - troubleshooting
---

# Docker故障排查

## 标准顺序

1. 查询容器状态。
2. 获取容器Inspect信息。
3. 查看容器日志。
4. 检查端口和网络。
5. 检查资源状态。
6. 形成Evidence。
7. 给出处理方案。
8. 操作后进行Verification。

## 安全要求

默认不执行：

- docker restart
- docker stop
- docker rm
- docker system prune

高风险操作必须经过人工审批。

## 输出

必须说明：

- 当前状态
- 发现的问题
- Evidence
- 建议
- 风险
- 是否需要审批

禁止声称没有执行过的操作已经完成。