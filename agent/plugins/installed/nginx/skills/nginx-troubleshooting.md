---
name: nginx-troubleshooting
version: 1.0.0
description: Nginx故障排查
tags:
  - nginx
  - web
  - troubleshooting
---

# Nginx故障排查

标准顺序：

1. 检查Nginx状态。
2. 检查配置。
3. 查看错误日志。
4. 查看访问日志。
5. 检查监听端口。
6. 检查上游服务。
7. 判断502/503/504等问题。
8. 提供Evidence。
9. 给出下一步建议。

未经审批不得自动：

- reload
- restart
- stop
- 修改配置