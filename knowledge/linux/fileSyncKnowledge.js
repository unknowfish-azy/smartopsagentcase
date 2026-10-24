// Linux file transfer and synchronization pack, normalized from user-provided
// training examples. Commands are guidance only; no executor is attached.
const node = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: 'linux.sync.' + id, domain: 'linux', platform: 'Linux',
  service: 'file-sync', type: 'FILE SYNC KNOWLEDGE', title, section, summary,
  content, tags: ['scp', 'rsync', 'SSH', ...tags],
  source: '用户提供的 Linux 文件同步训练样本', version: 'Reference pack',
  risk, executionAllowed: false
})

export const fileSyncEntries = [
  node('transfer-mode', '一次性文件传输：scp', '01 / 一次性传输',
    '单文件传输使用 scp；目录用 -r；非默认 SSH 端口使用 -P。',
    '[SRC] scp test.txt root@10.1.1.100:/root 是一次性文件传输的最小命令；目录传输可加 -r，SSH 端口可用 -P <port>。\n[OPS] 先确认源文件、目标主机、远端目录、覆盖风险和认证方式。scp 成功只证明本次复制返回成功，仍应复核远端文件存在、大小、权限，敏感文件不要写入命令历史或日志。',
    ['scp', 'single file', 'directory', 'remote write']),
  node('rsync-cron', '重复目录备份：rsync + cron', '02 / 定时备份',
    '每日备份是重复性任务，rsync 负责增量同步，cron 负责触发。',
    '[SRC] /app/java_project -> rsync -> Backup，再由 crontab 每天 01:03 触发。\n[OPS] crontab 的 3 1 * * * /root/rsync_java.sh 只证明触发时间，不证明备份成功。验证 cron 服务、脚本可执行性、绝对路径、环境变量、非交互 SSH 认证、rsync 退出码与真实日志。不要用 &>/dev/null 丢弃 stdout/stderr；失败分析需要保留日志并设置权限。',
    ['rsync', 'cron', 'crontab', 'backup', 'logging']),
  node('trailing-slash', 'rsync 源路径末尾斜杠', '03 / 路径语义',
    'rsync -av /dir1/ /dir2 同步目录内容；rsync -av /dir1 /dir3 同步目录本身。',
    '[SRC] source 末尾的 / 改变目标目录结构。\n[OPS] 执行前用 rsync -avn --itemize-changes 预览，确认 source、destination、方向和目标目录。生产不要仅凭命令表面判断覆盖范围。',
    ['source path', 'trailing slash', 'dry-run', 'itemize-changes']),
  node('delete', 'rsync --delete 的镜像清理风险', '04 / 删除与覆盖',
    '--delete 会删除目标端中源端不存在的多余文件，路径写反会造成破坏。',
    '[SRC] rsync -av --delete 的删除行为可能是参数本身导致的。\n[OPS] 先确认同步方向、源和目标是否写反，再用 --dry-run 逐项审查删除列表；目标目录必须明确允许被镜像清理。删除、覆盖和批量同步属于有副作用动作，需要审批、备份或回滚路径。',
    ['--delete', 'dry-run', 'mirror', 'approval'], 'APPROVAL_REQUIRED'),
  node('ssh-port', '非默认 SSH 端口下的 rsync', '05 / SSH 连接',
    'SSH 能用 66 端口而 rsync 失败，常见原因是 rsync 仍尝试默认端口。',
    '[SRC] ssh -p 66 root@192.168.126.182 成功时，rsync 应显式指定 -e "ssh -p 66"。\n[OPS] 先单独验证 ssh -p <port>，再执行 rsync -e "ssh -p <port>" -av SRC root@host:/path；确认 shell quoting、目标目录权限、远端 rsync 可用及退出码。域名已解析不等于 SSH 或 rsync 正常。',
    ['-e', 'ssh -p', 'port', 'TCP']),
  node('noninteractive', 'cron 与 SSH 非交互认证', '06 / 自动化认证',
    'cron 卡在密码输入，说明自动任务缺少非交互认证或环境配置。',
    '[SRC] 手工执行正常、cron 要求密码时，先验证 ssh root@<backup-host> 是否仍要求密码；训练样本采用 ssh-keygen -t rsa -P ""、ssh-copy-id root@<backup-host>。\n[OPS] 生产优先使用受限密钥、专用账户、known_hosts 和最小权限，避免把私钥、密码写进脚本或日志。验证 SSH 非交互登录、rsync、cron 环境和日志；不要把密钥配置自动扩散到未知主机。',
    ['cron', 'ssh-keygen', 'ssh-copy-id', 'passwordless', 'known_hosts'], 'APPROVAL_REQUIRED'),
  node('daemon-module', 'rsync daemon/module 模式', '07 / rsyncd',
    'HOST::module 是 daemon/module 模式，与 SSH 的 HOST:/path 语法不同。',
    '[SRC] rsync -a root@192.168.126.171:: 能列出 app，说明服务端至少发布了 app module；并不等于具体同步必然成功。\n[OPS] 发现 module 后，继续验证 rsync -av root@host::app /backup/app1_java 的错误、module path、daemon ACL、源目录权限、目标权限、rsyncd 日志和服务状态。不要把 module 发现成功当作文件传输成功。',
    ['rsync daemon', 'module', 'rsyncd', 'HOST::']),
  node('realtime', 'inotifywait + while + rsync 实时同步', '08 / 实时同步',
    'inotify 发现事件，Shell while 触发逻辑，rsync 执行数据同步，日志记录结果。',
    '[SRC] /app/java_project 创建文件后未同步，排查 ps -ef | grep inotify、cat /var/log/rsync.log、ps -ef | grep rsync，再手工执行 rsync。\n[OPS] 把链路拆成三层：事件是否发现、while 是否执行、rsync 是否成功。注意编辑器原子替换、目录递归监听、事件去重、并发 rsync、网络短暂失败和日志轮转。inotify 不是备份工具；它只负责事件发现。',
    ['inotifywait', 'inotify', 'while', 'event', 'real-time sync', '日志']),
  node('background', '后台任务与 nohup', '09 / 进程生命周期',
    '& 只让程序进入后台，nohup 用于终端关闭后继续运行；两者都需验证进程和日志。',
    '[SRC] ./inotify.sh & 可能随终端结束；nohup ./inotify.sh & 用于脱离终端继续运行。\n[OPS] 用 ps -ef | grep inotify、pgrep -af inotify、日志和实际事件验证。生产长期任务应考虑 systemd、Restart 策略、资源限制和日志轮转，不能只凭命令返回判断存活。',
    ['&', 'nohup', 'systemd', 'pgrep']),
  node('evidence-chain', '文件同步分层故障诊断', '10 / 证据链',
    '按模式、方向、连接、认证、传输、目标和调度逐层缩小范围。',
    '[OPS] 1. 识别一次性 scp、SSH rsync、daemon/module、cron 或 inotify；2. 确认 source/destination 方向与末尾斜杠；3. 检查 getent/DNS（若用域名）；4. 验证 ssh host/port 或 rsyncd module；5. 预览 rsync --dry-run；6. 检查权限、磁盘、日志、退出码和目标文件；7. cron 任务再检查服务、环境与非交互认证；8. 实时任务拆分 event → shell → rsync。\n证据优先级：实际命令输出、rsync 退出码、SSH/daemon/cron/inotify 日志、配置、进程状态、用户描述。域名解析成功只排除 DNS 层，不能证明 rsync 成功。',
    ['diagnosis', 'evidence chain', 'exit code', 'source', 'destination'])
]

export const fileSyncRules = Object.freeze([
  { id: 'SYNC-001', trigger: '一次性传一个文件', mode: 'scp', verify: ['source exists', 'SSH host/port', 'remote path', 'remote file'] },
  { id: 'SYNC-002', trigger: '每天备份目录', mode: 'rsync + cron', verify: ['cron trigger', 'non-interactive SSH', 'exit code', 'real log', 'destination'] },
  { id: 'SYNC-003', trigger: '实时同步没发生', mode: 'inotify + shell + rsync', verify: ['event', 'while process', 'rsync process/log', 'manual sync'] },
  { id: 'SYNC-004', trigger: 'rsync 删除目标文件', mode: 'direction and --delete', verify: ['source/destination', 'dry-run delete list', 'approval'] },
  { id: 'SYNC-005', trigger: 'rsync daemon module', mode: 'HOST::module', verify: ['module listing', 'module path', 'daemon ACL', 'permissions', 'logs'] }
])
