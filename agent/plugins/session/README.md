# Session Plugin

Session Plugin 是 SmartOps Harness 的会话持久化扩展层。

它负责为 Agent Runtime 提供统一的 Session 存储接口，使上层 Agent 不需要关心底层究竟使用：

```text
File
SQLite
MySQL
PostgreSQL
Redis