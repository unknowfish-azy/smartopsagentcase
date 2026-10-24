---
name: mysql-performance
version: 1.0.0
description: MySQL性能分析
tags:
  - mysql
  - performance
---

# MySQL性能分析

优先查看：

- 当前连接
- Threads
- Buffer相关变量
- Slow Query
- Processlist
- 查询执行计划

优先使用：

```sql
SHOW
SELECT
EXPLAIN