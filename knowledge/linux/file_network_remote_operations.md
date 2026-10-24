# SmartOps Linux Engineering Knowledge

## File Discovery / Archive / Network / SSH / Remote Operations

本模块把命令、原理、故障路径、风险、Runbook 和 Agent 决策连接起来。命令卡不是自动执行授权。

### 工具选择

`which` 解析当前 `PATH` 的可执行文件；`whereis` 查找二进制、源码和手册相关位置；`find` 实时按路径、类型、大小、时间、属主或权限搜索；`locate` 查索引，速度快但可能过期。生产环境优先限定搜索路径和深度，避免无理由执行 `find /`。

### 归档安全

`tar` 负责归档，gzip、bzip2、xz 负责压缩。提取前先 `tar -tf` 检查路径穿越、覆盖和敏感文件；证据打包前确认范围、剩余空间、权限和秘密字段。私钥、token、密码文件和 `.env` 不得盲目归档。

### 网络诊断

按 `NIC → IP → Route → TCP → DNS → Port → Application` 分层。现代系统优先使用 `ip addr`、`ip route`；NetworkManager 环境使用 `nmcli device status`。`nmcli connection down`、路由和防火墙变更都可能切断远程会话，必须有带外恢复路径。

### SSH / SFTP

SSH 链路为 `DNS/IP → TCP → sshd → Host Key → Authentication → Shell`。连接失败时记录失败阶段，先检查网络、端口、sshd 状态、`sshd -t`、认证策略和日志，不要直接重启服务。生产优先个人账户、最小权限、密钥认证和审计；禁止默认启用密码 root 登录。

SFTP 适合交互式文件操作，SCP 适合简单复制，rsync 适合增量同步。大规模同步先使用 `--dry-run`；删除、覆盖、批量同步和敏感文件传输需要明确目标、风险和审批。

### Agent 决策

- “SSH 连接不上”：环境 → 影响 → DNS/IP → 路由 → TCP/端口 → 防火墙 → sshd → 认证 → 日志。
- “磁盘满”：`df` → 挂载点 → `du` → `find` → 属主 → deleted-open → 归档/清理/扩容 → 验证。
- “命令找不到”：`which` → `PATH` → 权限 → alias/function → shell 缓存。

所有远程动作遵循：观察、测量、假设、验证、审批、执行、验证、记录。密码、私钥和 token 不进入命令历史、会话日志或知识库。
