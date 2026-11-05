// Linux 身份与访问管理知识包：对应 RH124/RH134 的用户、权限、ACL、SSH、
// 软件包管理和日志分析章节，并参考 jaywcjlove/linux-command 与 RHEL 官方文档。
export const linuxAccessProvenance = Object.freeze({
  source: '开源参考资料：RH124/RH134 课程目标、RHEL 9 官方文档、jaywcjlove/linux-command',
  references: ['Red Hat Enterprise Linux 9 Documentation', 'linux-command', 'OpenSSH Manual'],
  verification: '命令示例需结合实际发行版与版本核对'
})

const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: 'linux.access.' + id,
  domain: 'linux', platform: 'RHEL / CentOS / Ubuntu', service: 'identity-access',
  type: 'LINUX ACCESS CONTROL', title, section, summary, content,
  tags: ['Linux', '身份与访问', ...tags],
  source: linuxAccessProvenance.source,
  version: 'RHEL 9 / Ubuntu 22.04 通用原则', risk, executionAllowed: false
})

export const linuxAccessEntries = [
  entry('users-groups', '用户、组与账号数据库', '01 / 账号',
    '本地账号由 /etc/passwd、/etc/shadow、/etc/group 定义；服务账号应使用系统 UID 且不可登录。',
    '[SRC] /etc/passwd 保存用户名、UID、主组、家目录和登录 Shell；/etc/shadow 保存密码与策略；/etc/group 保存组与附加成员。useradd 创建账号，usermod 修改，userdel -r 删除家目录，groupadd/groupmod 管理组。getent passwd <user> 走 NSS 路径，比直接读文件更接近真实解析结果。\n[OPS] 修改账号前先确认用途、归属业务、登录方式和家目录；服务账号使用 useradd -r -s /sbin/nologin，禁止给服务账号配置可交互 Shell。删除账号前检查进程、cron、sudoers、文件和属主，避免遗留孤儿文件或权限断裂。',
    ['/etc/passwd', '/etc/shadow', '/etc/group', 'useradd', 'usermod', 'userdel', 'getent', 'system account'], 'APPROVAL_REQUIRED'),
  entry('password-policy', '密码策略、chage 与账号锁定', '02 / 密码策略',
    '密码策略作用于新密码设置；chage 管理过期与警告；锁定账号不等于删除账号。',
    '[SRC] passwd 修改当前用户密码，chage -l <user> 查看策略，chage -M/-m/-W 设置最大天数、最小天数、警告天数；usermod -L/-U 锁定和解锁。失败登录记录通常在 /var/log/secure 或 /var/log/auth.log。\n[VERIFY] 修改策略不会自动让旧密码立即失效；已登录会话可能继续存在。\n[OPS] 生产密码策略要与组织安全基线一致，避免长期无过期或过短周期。锁定、解锁、重置密码属于敏感操作，必须验证身份、记录工单并通知账号负责人。不要把明文密码写入脚本、聊天记录或知识库。',
    ['passwd', 'chage', 'usermod -L', '/var/log/secure', 'password policy'], 'APPROVAL_REQUIRED'),
  entry('permissions-umask', '权限位、特殊位与 umask', '03 / 权限模型',
    'rwx 作用于 owner/group/other；SUID、SGID、Sticky 有特定语义；umask 影响新建文件默认权限。',
    '[SRC] chmod 数字模式 755/644/600，符号模式 u+x、g-w、o=r；chown 修改属主属组，chgrp 只改组。SUID 让程序以文件属主运行，SGID 对目录使新文件继承组，Sticky 限制目录内只能删除自己的文件。umask 022 表示新文件默认 644、目录 755。\n[OPS] 权限问题先看最终生效位、父目录可执行位、进程运行用户和 SELinux 上下文，再考虑修改。禁止把 chmod -R 777 当作通用修复；SUID 程序属于提权面，发现异常 SUID 应先取证再处置。权限变更要记录原值、影响范围和回滚命令。',
    ['chmod', 'chown', 'chgrp', 'SUID', 'SGID', 'Sticky', 'umask', 'chmod 777 risk'], 'APPROVAL_REQUIRED'),
  entry('acl', 'ACL 精细授权与生效顺序', '04 / ACL',
    'ACL 为指定用户或组单独授权；mask 限制有效权限；默认 ACL 只对目录新建内容生效。',
    '[SRC] getfacl <path> 查看 ACL，setfacl -m u:alice:rx <path> 授权，setfacl -m d:g:dev:rwx <dir> 设置默认 ACL，setfacl -x 删除条目。ls -l 权限位后的加号表示存在 ACL。mask 是 ACL 的最大有效权限，修改 mask 会影响命名用户和组。\n[VERIFY] 默认 ACL 不会被已有文件继承；递归设置前必须确认目标范围和影响。\n[OPS] ACL 适用于“只给某账号访问某目录”的最小授权场景。排查权限拒绝时，用 getfacl 同时检查访问 ACL、默认 ACL 与 mask，并核对进程实际用户。批量 setfacl -R 属于变更操作，需备份现有 ACL 并验证回滚。',
    ['getfacl', 'setfacl', 'mask', 'default ACL', 'effective permission'], 'APPROVAL_REQUIRED'),
  entry('sudo', 'sudoers、visudo 与最小提权', '05 / 提权',
    'sudo 按 sudoers 规则授予特定命令；visudo 校验语法；NOPASSWD 与通配符会放大风险。',
    '[SRC] visudo 安全编辑 /etc/sudoers，也可在 /etc/sudoers.d/ 下分文件管理；规则格式为 用户 主机=(运行身份) 命令。别名 User_Alias、Cmnd_Alias 可复用。sudo -l 查看当前用户可执行命令。\n[OPS] 授权按“最小命令 + 最小参数”设计，避免 ALL=(ALL) NOPASSWD: ALL。允许脚本或解释器（如 bash、python）等于允许任意命令，需单独评估。排查 sudo 失败时检查规则匹配、用户组、命令绝对路径、requiretty 和日志 /var/log/secure。sudoers 语法错误可能导致无法提权，修改前保留可用的 root 会话。',
    ['visudo', '/etc/sudoers', 'sudoers.d', 'sudo -l', 'NOPASSWD', 'least privilege'], 'HIGH'),
  entry('ssh-access', 'SSH 密钥、sshd_config 与访问加固', '06 / 远程访问',
    '密钥认证依赖正确的文件权限与 authorized_keys；sshd_config 变更需要语法验证和保留管理通道。',
    '[SRC] 客户端 ssh-keygen -t ed25519 生成密钥，ssh-copy-id 复制公钥；服务端 ~/.ssh/authorized_keys 权限应为 600，.ssh 为 700，家目录不能对组或其他用户可写。sshd_config 常用项：Port、PermitRootLogin、PasswordAuthentication、PubkeyAuthentication、AllowUsers/AllowGroups。\n[OPS] 修改 sshd_config 前先备份并保留当前会话，执行 sshd -t 校验，再 reload 而非直接断开全部连接。禁用密码登录前必须验证密钥登录和应急控制台可用。排查失败看 /var/log/secure 与 sshd -T 实际生效配置，不要只读文件内容。防火墙和 SELinux 变更同样需要审批。',
    ['ssh-keygen', 'ssh-copy-id', 'authorized_keys', 'sshd_config', 'sshd -t', 'PermitRootLogin'], 'APPROVAL_REQUIRED'),
  entry('package-management', 'dnf/yum、rpm 查询与仓库边界', '07 / 软件包',
    'rpm 负责本地包数据库查询，dnf/yum 负责依赖解析与仓库事务；安装前确认来源与签名。',
    '[SRC] rpm -q <pkg> 查询是否安装，rpm -ql 列出文件，rpm -qf <path> 反查所属包；dnf repolist 查看仓库，dnf provides <path> 查找提供者，dnf history 查看事务，dnf history undo <id> 可回滚事务。RHEL 9 的 module streams 影响版本选择。\n[OPS] 只使用可信仓库并校验 GPG；第三方源与手工 rpm 可能破坏依赖一致性。安装、升级、卸载前记录当前版本、仓库来源和事务 ID；禁止在未确认依赖与业务影响时使用 -y 批量升级。CentOS 7 使用 yum，命令等价但参数略有差异。包管理器锁冲突先查进程与缓存，不要强行删除锁文件。',
    ['rpm -q', 'rpm -ql', 'rpm -qf', 'dnf repolist', 'dnf provides', 'dnf history', 'GPG', 'module stream'], 'APPROVAL_REQUIRED'),
  entry('log-analysis', 'journalctl、rsyslog 与 logrotate', '08 / 日志',
    'journalctl 查 systemd 日志，rsyslog 负责持久化与转发，logrotate 控制轮转和保留。',
    '[SRC] journalctl -u <service> --since "15 minutes ago" 查看服务日志；journalctl -p err -b 查看本次启动错误；--no-pager 便于保存。rsyslog 配置在 /etc/rsyslog.conf 与 /etc/rsyslog.d/，日志常落在 /var/log/messages、secure、cron。logrotate 配置在 /etc/logrotate.conf 与 /etc/logrotate.d/，支持 daily、rotate、compress、postrotate。\n[OPS] 排查先固定时间窗口和主机时区，再关联服务日志、系统日志和应用日志。持久化 journal 需要 /var/log/journal 与相应配置，否则重启后可能丢失。日志清理与轮转必须评估保留期、审计要求和磁盘余量；禁止直接 rm 正在写入的日志，优先轮转或归档。',
    ['journalctl', 'rsyslog', '/var/log/messages', 'logrotate', 'time window', 'persistent journal'], 'APPROVAL_REQUIRED'),
  entry('diagnosis', '权限拒绝与登录失败证据链', '09 / 故障诊断',
    'Permission denied 与登录失败分别属于授权和认证问题，先分层取证再修改。',
    '[OPS] Permission denied 排查顺序：进程实际用户 → 路径每一级的执行位 → 目标文件 owner/group/mode → ACL 与 mask → SELinux 上下文与 AVC → 挂载只读或空间。登录失败排查顺序：网络与端口 → sshd 服务与监听 → 认证方式 → 密钥权限或密码策略 → 账号锁定 → AllowUsers/AllowGroups → 日志记录。\n证据优先级：实际命令输出、服务日志、审计日志、配置文件、进程与监听、用户描述。修复优先最小权限，避免 chmod 777、关闭 SELinux、关闭防火墙等高风险捷径。变更后必须用原失败路径复验，并记录回滚方式。',
    ['Permission denied', 'authentication', 'authorization', 'ACL', 'SELinux AVC', 'evidence chain'], 'APPROVAL_REQUIRED')
]
