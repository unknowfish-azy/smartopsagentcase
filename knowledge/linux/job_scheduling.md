# SmartOps Linux Job Scheduling Engineering v1.0

计划任务不是一行 crontab，而是一条可验证的运行链：

`Scheduler → Job Definition → Trigger → Execution Context → Process → Exit Code → Output/Error → Log → Business Result → Verification`

## 调度器模型

- `at` 创建一次性任务，`atd` 消费队列；`atq` 查询，`atrm` 删除。
- `crond` 是周期调度 daemon，`crontab` 管理任务定义。
- `systemd timer` 绑定 service unit；`anacron` 适合不要求精确分钟且机器可能离线的周期任务。

`crond active` 只证明 daemon 状态，不证明任务存在、表达式正确、脚本运行或业务成功。

## Cron 执行上下文

关键任务应明确 `SHELL`、`PATH`、`HOME`、用户、工作目录、环境变量和依赖路径。手工执行成功不代表 cron 成功。脚本要有 shebang、执行权限、明确输出和退出码。日志位置依发行版和日志系统变化，不能固定假设 `/var/log/cron`。

## 表达式与验证

五字段为 minute、hour、day-of-month、month、day-of-week。应支持自然语言与表达式双向解析，并计算下一次触发、时区和复杂 DOM/DOW 语义。`*/5` 仍需结合运行时长检查重叠风险。

## 幂等、备份与风险

当调度间隔小于历史运行时长时，使用 `flock` 或应用级幂等控制。备份验证必须覆盖触发、进程、退出码、文件存在、大小、完整性、远程复制、保留策略和恢复测试。密码、Token、私钥禁止进入 crontab、脚本、命令行和日志。

Agent 处理“计划任务异常”时遵循：识别调度器和用户 → 检查定义与表达式 → 检查权限与上下文 → 查看日志和运行时 → 检查退出码和输出 → 验证业务结果 → 评估重叠 → 审批变更 → 执行、验证、记录。
