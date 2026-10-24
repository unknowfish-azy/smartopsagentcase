# Nginx Error Codes Reference

## 1. 文档说明

本文件是 SmartOps Agent 的 Nginx 故障诊断参考知识。

主要用于：

- HTTP 状态码分析
- Nginx error.log 分析
- upstream 故障分析
- 监听端口问题分析
- 配置错误分析
- 反向代理故障分析
- 故障证据关联
- Root Cause Hypothesis 生成

本文件属于知识参考。

它不代表某一台真实服务器的当前状态。

SmartOps Agent 必须优先使用：

```text
实际命令输出
实际日志
实际配置
实际监控数据