// Linux File / Network / Remote Operations v1.0. Reference data only.
export const linuxFileNetworkRemoteNodes = [
  {
    id: 'LINUX-FILE-001', title: '文件发现工具选择：which、whereis、find、locate', category: '09 文件发现', level: 'Junior',
    concept: 'which 解析当前 PATH 选中的可执行文件，whereis 查找二进制/源码/手册相关位置，find 实时扫描文件系统，locate 查询索引数据库。',
    architecture: 'Intent → scope → tool → evidence → verification',
    commands: [
      { command: 'which python', purpose: '确认当前 shell 通过 PATH 解析到的可执行文件', risk: 'READ_ONLY', parameters: 'PATH 和 shell 环境会影响结果。' },
      { command: 'find /var/log -type f -name "*.log" -mtime +30', purpose: '在限定目录中查找旧日志', risk: 'READ_ONLY', parameters: '先确认路径和时区；不要直接接删除动作。' },
      { command: 'locate hosts', purpose: '快速查询索引中的路径', risk: 'READ_ONLY', parameters: '数据库可能过期；新文件查不到不代表文件不存在。' }
    ],
    scenario: '命令存在但提示 command not found，或文件刚创建却无法被 locate 找到。',
    diagnosis: ['确认用户目标是命令解析还是文件系统搜索', '检查 which、echo $PATH、ls -l 和执行权限', '对实时状态使用限定范围的 find', '对 locate 结果注明索引新鲜度'],
    risk: 'find / 可能造成生产 I/O 压力；find -delete、-exec rm 等动作必须单独审批。', experience: '工具选择取决于问题，不要用 locate 的陈旧索引替代实时证据。', verification: '用绝对路径、文件属性和受控样本复核结果。', relatedIds: ['LINUX-STORAGE-001', 'LINUX-STORAGE-005'], tags: ['which', 'whereis', 'find', 'locate', 'PATH']
  },
  {
    id: 'LINUX-FILE-002', title: '归档、压缩与证据打包', category: '10 归档与压缩', level: 'Middle',
    concept: 'tar 负责归档，gzip/bzip2/xz 负责压缩；创建、检查、提取是不同阶段。ZIP 适合跨平台交换。',
    architecture: 'Select files → inspect scope → archive → checksum → transfer → verify',
    commands: [
      { command: 'tar -tf incident.tar.xz', purpose: '不解压检查归档内容', risk: 'READ_ONLY', parameters: '先检查路径穿越、敏感文件和覆盖风险。' },
      { command: 'tar -czf incident-logs.tar.gz /var/log/nginx', purpose: '打包指定日志证据', risk: 'LOCAL_WRITE', parameters: '检查剩余空间和敏感字段；不要无范围打包。' },
      { command: 'tar -xvf archive.tar.xz -C /tmp/verified', purpose: '提取到隔离目录', risk: 'CHANGE', parameters: '不可信归档不得直接解压到 /etc 或应用目录。' }
    ],
    scenario: '故障处理需要打包日志，但归档可能包含凭证、私钥或环境变量。', diagnosis: ['确认证据范围、敏感文件和目标空间', '先 tar -tf 检查，再创建归档', '必要时生成校验和并限制权限', '提取时使用隔离目录并验证内容'], risk: '路径穿越、意外覆盖、秘密泄露和磁盘耗尽。', experience: '检查归档内容优先于提取；命令成功不代表证据完整或安全。', verification: '检查文件存在、大小、校验和、权限及敏感信息处理结果。', relatedIds: ['LINUX-FILE-001', 'LINUX-STORAGE-001'], tags: ['tar', 'gzip', 'bzip2', 'xz', 'zip', 'backup', 'evidence']
  },
  {
    id: 'LINUX-NET-001', title: 'Linux 网络分层诊断与 NetworkManager', category: '11 网络基础', level: 'Middle',
    concept: '网络故障应从网卡、IP、路由、TCP、DNS、端口到应用响应逐层验证；ip 是现代工具族，nmcli 管理 NetworkManager。',
    architecture: 'NIC → IP → Route → TCP → DNS → Port → Application',
    commands: [
      { command: 'ip addr; ip route', purpose: '确认接口地址和路由', risk: 'READ_ONLY', parameters: '记录目标接口和默认路由。' },
      { command: 'nmcli device status', purpose: '查看 NetworkManager 设备状态', risk: 'READ_ONLY', parameters: '不同发行版可能未安装或未启用 NetworkManager。' },
      { command: 'nmcli connection down ens33', purpose: '断开指定连接', risk: 'HIGH', parameters: '远程执行可能立即中断 SSH，必须有带外恢复路径。' }
    ],
    scenario: '用户说服务器网络不通，不能第一步就重启网络服务。', diagnosis: ['确认影响范围和目标接口', '检查 ip addr、ip route 和网关连通性', '检查 DNS、TCP 端口和 ss -lntp', '最后用 curl 或业务探针验证应用层'], risk: 'nmcli down、修改路由或防火墙可能切断远程访问。', experience: '按层定位能区分网络不可达、端口拒绝、超时和应用无响应。', verification: '记录每层证据、延迟、错误类型和恢复后的业务响应。', relatedIds: ['LINUX-REMOTE-001'], tags: ['ip', 'ifconfig', 'nmcli', 'route', 'DNS', 'TCP']
  },
  {
    id: 'LINUX-REMOTE-001', title: 'SSH 连接诊断与安全边界', category: '12 远程访问', level: 'Senior',
    concept: 'SSH 链路依次经过网络、TCP 端口、sshd、主机密钥、认证和 shell；不同阶段失败需要不同证据。',
    architecture: 'Client → DNS/IP → TCP → sshd → Host Key → Authentication → Shell',
    commands: [
      { command: 'ss -lntp', purpose: '确认本机监听端口和进程', risk: 'READ_ONLY', parameters: '结合目标端口，不假设一定是 22。' },
      { command: 'sshd -t', purpose: '验证 sshd 配置语法', risk: 'VALIDATION', parameters: '不重启服务；需要与实际配置文件和发行版匹配。' },
      { command: 'journalctl -u sshd --since "15 minutes ago" --no-pager', purpose: '查看近期 sshd 诊断日志', risk: 'READ_ONLY', parameters: '输出需脱敏后保存。' }
    ],
    scenario: '连接中心无法连接服务器，先区分 DNS、TCP、端口、主机密钥、认证还是 sshd 故障。', diagnosis: ['记录 host、port、protocol 和错误阶段', '检查 DNS/IP、路由、防火墙和 TCP', '确认 sshd 状态并执行 sshd -t', '检查认证策略、账户限制和日志'], risk: '不要直接重启 sshd；生产禁止默认启用密码 root 登录，私钥和密码不得进入日志。', experience: '配置验证在服务动作之前；SSH 恢复必须有带外或跳板机回退路径。', verification: '验证 TCP、主机密钥、认证、shell 和业务操作结果。', relatedIds: ['LINUX-NET-001', 'LINUX-REMOTE-002'], tags: ['SSH', 'sshd', 'sshd -t', 'authentication', 'firewall', 'host key']
  },
  {
    id: 'LINUX-REMOTE-002', title: 'SCP、SFTP、rsync 与远程操作审计', category: '13 文件传输与远程运维', level: 'Senior',
    concept: '远程运维应建模为连接、认证、会话、命令、输出、证据、结果和审计链；SFTP 适合交互文件操作，rsync 适合增量同步。',
    architecture: 'Connection → Authentication → Session → Command/Transfer → Evidence → Audit',
    commands: [
      { command: 'sftp user@server', purpose: '建立受审计的交互式文件传输会话', risk: 'READ_ONLY', parameters: '凭证使用安全引用，不写入命令历史。' },
      { command: 'scp local.txt user@server:/tmp/', purpose: '执行单文件复制', risk: 'REMOTE_WRITE', parameters: '确认目标路径、覆盖策略和文件敏感性。' },
      { command: 'rsync -av --dry-run source/ user@server:/data/', purpose: '预览增量同步影响', risk: 'READ_ONLY', parameters: '正式同步前必须审查 dry-run 输出。' }
    ],
    scenario: '连接中心需要记录目标、命令、输出、退出码、风险、审批和结果，同时避免保存密码和私钥。', diagnosis: ['建立连接诊断事件和目标上下文', '只读预览文件与命令影响', '风险操作要求用户审批并记录', '传输或命令完成后验证结果并写入 Operational Memory'], risk: '远程删除、覆盖、批量同步和秘密文件传输必须确认；密码、私钥、token 不得进入日志。', experience: 'SFTP 浏览器和终端只是入口，真正的产品价值是证据链、风险控制和可复盘结果。', verification: '核对传输状态、校验和、权限、退出码及审计记录。', relatedIds: ['LINUX-REMOTE-001', 'LINUX-FILE-002'], tags: ['scp', 'sftp', 'rsync', 'dry-run', 'audit', 'remote operations']
  }
]

export const linuxFileNetworkRemoteIncidents = [
  { id: 'INCIDENT-SSH-FIREWALL', title: '防火墙变更后 SSH 中断', runbook: ['确认带外路径', '验证网络与 TCP 端口', '核对最近防火墙变更', '恢复最小必要规则', '验证认证并记录结果'], risk: 'HIGH', relatedKnowledge: ['LINUX-NET-001', 'LINUX-REMOTE-001'] },
  { id: 'INCIDENT-DISK-EVIDENCE', title: '磁盘高使用率与证据打包', runbook: ['df 确认文件系统', 'du/find 定位范围', '检查 deleted-open 文件', '评估归档或扩容', '验证空间和业务'], risk: 'MEDIUM', relatedKnowledge: ['LINUX-FILE-001', 'LINUX-FILE-002', 'LINUX-STORAGE-005'] }
]

export const linuxFileNetworkRemoteDecisionRules = [
  { trigger: 'SSH 连接不上', sequence: ['environment', 'impact', 'DNS/IP', 'route', 'TCP/port', 'firewall', 'sshd', 'authentication', 'logs'], defaultRisk: 'READ_ONLY' },
  { trigger: '磁盘满', sequence: ['df', 'mount', 'du', 'find', 'owner', 'deleted-open', 'archive/cleanup/expand', 'verification'], defaultRisk: 'READ_ONLY' },
  { trigger: '命令找不到', sequence: ['which', 'PATH', 'permissions', 'alias/function', 'shell cache'], defaultRisk: 'READ_ONLY' }
]
