# Nginx Troubleshooting Skill

## 1. Skill Identity

名称：

`nginx-troubleshooting`

版本：

`1.0.0`

用途：

针对 Nginx / OpenResty 反向代理、静态文件服务和 Web 接入异常，
执行安全、证据优先、可验证的故障分析。

本 Skill 主要负责：

- Nginx 服务状态分析
- Nginx 配置检查
- Nginx 错误日志分析
- Nginx 访问日志分析
- 监听端口检查
- 上游服务异常分析
- 反向代理链路分析
- 常见 HTTP 5xx 问题分析

本 Skill 不直接负责：

- 修改 Nginx 配置
- 删除日志
- 停止服务
- 重启服务
- kill Nginx 进程
- 修改防火墙规则
- 修改系统网络配置

任何改变系统状态的动作都必须经过：

Permission
→ Risk
→ Approval
→ SafeAgent
→ Sandbox
→ Execution
→ Verification
→ Audit

---

# 2. Core Principle

核心原则：

> 先取证，再分析；先验证，再执行；执行必须留痕。

故障分析顺序：

```text
症状
 ↓
服务状态
 ↓
监听状态
 ↓
配置有效性
 ↓
错误日志
 ↓
访问日志
 ↓
上游服务
 ↓
网络链路
 ↓
根因假设
 ↓
验证