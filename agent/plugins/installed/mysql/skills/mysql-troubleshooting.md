---
name: mysql-troubleshooting
version: 1.0.0
description: MySQL故障排查
tags:
  - mysql
  - database
  - troubleshooting
---

# MySQL故障排查

推荐顺序：

1. 检查数据库服务。
2. 检查连接。
3. 检查系统变量。
4. 检查连接数。
5. 检查慢查询。
6. 检查错误日志。
7. 检查资源。
8. 输出Evidence。

默认只使用只读查询。

禁止自动执行：

- DROP
- TRUNCATE
- DELETE
- UPDATE
- ALTER