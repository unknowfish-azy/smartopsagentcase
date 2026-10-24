---
name: nginx-troubleshooting
version: 1.0.0
description: Nginx服务故障排查技能
tags:
  - nginx
  - linux
  - troubleshooting
  - web
---

# Nginx故障排查

## 适用场景

当用户出现：

- Nginx无法访问
- 502
- 503
- 服务启动失败
- 页面响应异常

## 排查顺序

1. 查询Nginx服务状态。
2. 查询监听端口。
3. 查看Nginx错误日志。
4. 检查配置文件。
5. 检查上游服务。
6. 验证业务访问。
7. 记录排查证据。

## 安全要求

默认不得自动：

- 停止Nginx
- 重启Nginx
- 修改Nginx配置
- 删除Nginx文件

高风险操作必须经过人工审批。

## 输出要求

最终结果至少包含：

- 故障现象
- 当前判断
- 排查步骤
- Evidence
- 版本信息
- 风险说明
- 下一步建议

## 禁止虚构

如果没有实际执行：

不要声称：

- Nginx已经重启
- 配置已经修改
- 故障已经修复