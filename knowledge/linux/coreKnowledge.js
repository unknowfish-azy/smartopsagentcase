// Linux Core Knowledge v0.1: declarative reference data, never executable tasks.
export const linuxCoreNodes = [
  {
    id: 'LINUX-FD-001', title: '文件描述符与日志去向', category: '02 文件描述符', level: 'Junior',
    concept: 'FD 是进程文件描述符表中的整数索引，可指向文件、管道、套接字和设备。0、1、2 通常分别是标准输入、标准输出、标准错误，也可能被关闭或重新指向。',
    architecture: '进程 → FD 表 → 打开的文件描述 → 文件 / 套接字 / 管道',
    commands: [{ command: 'ls -l /proc/<PID>/fd', purpose: '查看目标进程的 FD 指向', risk: 'READ_ONLY', parameters: '<PID> 必须替换为已确认的进程号；访问受权限限制。' }],
    scenario: '服务没有输出日志时，先确认 stdout/stderr 指向终端、管道、日志文件还是 /dev/null。',
    diagnosis: ['确认服务 PID 和启动方式', '查看 FD 1、2 指向', '对照 systemd 日志、容器日志或应用日志配置'],
    risk: '文件名、套接字信息可能含敏感数据，导出前脱敏；不要读取或修改未知 FD。',
    experience: 'FD 指向管道不意味着日志丢失，还需检查日志收集进程。',
    verification: '用同一时间段的应用事件与目标日志核对输出链路。',
    relatedIds: ['LINUX-FD-002', 'LINUX-IO-001'], tags: ['FD', 'stdin', 'stdout', 'stderr', '/proc', '日志去向']
  },
  {
    id: 'LINUX-FD-002', title: 'Too many open files：限制还是泄漏', category: '06 故障排查', level: 'Senior',
    concept: 'EMFILE 通常是单进程 FD 达到限制；ENFILE 是系统级打开文件表耗尽。错误文本需要结合 errno 和系统证据判断。',
    architecture: '请求增长 / 资源未释放 → FD 数量增长 → 达到限制 → 打开文件或连接失败',
    commands: [
      { command: 'cat /proc/<PID>/limits', purpose: '读取运行中进程的 Max open files', risk: 'READ_ONLY', parameters: '使用实际服务 PID；不是当前终端 shell 的限制。' },
      { command: 'ls -1U /proc/<PID>/fd | wc -l', purpose: '估算当前 FD 数量并多次采样', risk: 'READ_ONLY', parameters: '检查 ls 的退出状态和权限错误；并发打开/关闭会导致采样变化。' },
      { command: 'cat /proc/sys/fs/file-nr', purpose: '查看系统级文件句柄使用情况', risk: 'READ_ONLY', parameters: '结合系统最大值和同时间段指标解释。' }
    ],
    scenario: '教学案例：Java 服务运行一天后无法打开文件，出现 Too many open files。尚未确认是泄漏。',
    diagnosis: ['确认影响范围、开始时间和最近发布', '读取目标进程限制，区分进程级与系统级耗尽', '持续采样 FD 数量并分类文件/套接字，与请求量对照', '负载回落后仍持续增长时，检查连接池、流和文件句柄释放路径'],
    risk: 'ulimit -n 只反映当前 shell；修改它不会改变已运行服务。提高 nofile 或重启需要评估容量、审批与回滚，不能作为已证实的根因修复。',
    experience: '不要只提高限制；先区分合理并发增长和资源泄漏。',
    verification: '相同负载下 FD 曲线趋于稳定，打开文件错误消失，业务延迟和成功率恢复。',
    relatedIds: ['LINUX-FD-001', 'LINUX-IO-005'], tags: ['Too many open files', 'FD泄漏', 'EMFILE', 'ENFILE', 'nofile', 'ulimit', 'Java']
  },
  {
    id: 'LINUX-IO-001', title: '重定向顺序与部署日志保存', category: '03 Shell 输入输出', level: 'Middle',
    concept: '> 覆盖标准输出，>> 追加，2> 覆盖错误输出，2>> 追加错误输出，< 从文件读取输入。2>&1 把 FD 2 指向执行该重定向时 FD 1 的目标。',
    architecture: 'shell 从左到右应用重定向 → 创建输出文件 → 启动命令',
    commands: [
      { command: 'command >> deploy.log 2>&1', purpose: '追加保存正常和错误输出', risk: 'LOCAL_WRITE', parameters: 'command 为待审核命令占位符；deploy.log 应换为获准目录下的日志路径。' },
      { command: 'command > output.log 2>&1', purpose: '合并输出到文件', risk: 'OVERWRITE', parameters: '覆盖旧文件；command 2>&1 > output.log 则通常仍把 stderr 发往原 stdout。' }
    ],
    scenario: '教学事故：部署失败且错误输出被丢弃到 /dev/null，无法回溯失败原因。',
    diagnosis: ['检查使用的 shell 与重定向顺序', '确认目录权限、剩余空间和日志敏感字段', '保存输出并检查原命令退出码'],
    risk: '&> 是 Bash 等 shell 的扩展，不能默认适用于 POSIX sh。日志写入不是只读操作；不能用 /dev/null 无条件隐藏部署错误。',
    experience: '日志为空也可能是命令未运行、缓冲未刷新或输出目标错误，不代表成功。',
    verification: '分别用已知 stdout/stderr 的本地实验验证两类输出都进入目标文件；核对退出码。',
    relatedIds: ['LINUX-FD-001', 'LINUX-IO-002'], tags: ['重定向', '2>&1', '&>', '/dev/null', '部署日志', 'Bash']
  },
  {
    id: 'LINUX-IO-002', title: '管道、tee 与失败状态保留', category: '03 Shell 输入输出', level: 'Middle',
    concept: '| 将前一个命令的 stdout 接到后一个命令的 stdin，默认不传递 stderr。tee 同时输出到终端和文件，默认覆盖文件，-a 追加。',
    architecture: '命令 stdout → 管道缓冲区 → tee stdin → 终端 + 文件',
    commands: [{ command: 'set -o pipefail\ncommand 2>&1 | tee -a evidence.log', purpose: 'Bash 中收集证据并保留管道失败信号', risk: 'LOCAL_WRITE', parameters: '在专用脚本或子 shell 中使用；command 是占位符。pipefail 返回最右侧非零退出状态。' }],
    scenario: '采集脚本前面的命令失败，但 tee 成功，流水线误报成功。',
    diagnosis: ['检查 shell 类型', '检查 stderr 是否合并', '开启 Bash pipefail 或立即保存 PIPESTATUS 各阶段退出状态', '分别验证命令和日志写入是否成功'],
    risk: '日志可含密码或业务数据；tee 写文件可能覆盖、写满磁盘或因权限失败。pipefail 不是所有 sh 都支持；与 head 等提前退出的消费者组合时注意 SIGPIPE。',
    experience: '屏幕看到输出和管道返回零都不等于原命令成功。',
    verification: '在本地测试中让前段返回非零，确认采集流程报告失败且保留证据。',
    relatedIds: ['LINUX-IO-001', 'LINUX-IO-005'], tags: ['管道', 'tee', 'pipefail', 'PIPESTATUS', '日志采集']
  },
  {
    id: 'LINUX-IO-003', title: 'xargs：安全处理文件名', category: '03 Shell 输入输出', level: 'Middle',
    concept: 'xargs 把输入转换为命令参数。默认按空白、引号和反斜杠解析，文件名含空格或换行时容易拆错。',
    architecture: 'find 输出 NUL 分隔路径 → xargs -0 解析 → 分批调用统计命令',
    commands: [{ command: 'find ./logs -type f -name "*.log" -print0 | xargs -0 -r wc -c --', purpose: '对已确认目录内的日志做字节统计', risk: 'READ_ONLY', parameters: 'GNU/Linux 示例：-0 使用 NUL 分隔，-r 在无输入时不执行，-- 终止选项解析；扫描大目录有 I/O 成本。' }],
    scenario: '日志名含空格时，默认 xargs 把一个路径拆成多个参数。',
    diagnosis: ['确认目标目录范围', '使用 -print0 和 -0 保留文件名边界', '先进行只读统计并检查每阶段退出状态'],
    risk: '不提供 find / | xargs rm 等广域删除模板。文件枚举与操作之间仍有竞态；NUL 分隔不解决权限或路径替换问题。',
    experience: '先验证目标列表；参数转换能力本身不构成批量变更授权。',
    verification: '在临时实验目录验证空格、换行文件名和零匹配情况。',
    relatedIds: ['LINUX-IO-002', 'LINUX-IO-005'], tags: ['xargs', 'find', '-print0', 'NUL', '文件名', '批量统计']
  },
  {
    id: 'LINUX-IO-005', title: 'wc 与 date：统计口径和证据时间', category: '03 Shell 输入输出', level: 'Junior',
    concept: 'wc -l 统计换行符，-w 统计单词，-c 统计字节，-m 统计字符。无末尾换行时逻辑上的最后一行不会被 -l 计入。',
    architecture: '原始输出 → 过滤与去表头 → 明确单位 → 计数 + 采集时间',
    commands: [
      { command: 'wc -l -w -c evidence.log', purpose: '统计日志换行、单词和字节', risk: 'READ_ONLY', parameters: '文本编码影响字符与字节差异。' },
      { command: 'date -u "+%Y-%m-%dT%H:%M:%SZ"', purpose: '记录 UTC 采集时间', risk: 'READ_ONLY', parameters: '不同主机可能时钟偏移；时间戳不证明时钟已同步。' }
    ],
    scenario: 'ps aux | wc -l 把标题计入进程数；ls | wc -l 对含换行的文件名统计错误。',
    diagnosis: ['确认统计对象是行、文件、进程还是字符', '排除表头并检查上游命令是否成功', '记录时间、主机和采样范围'],
    risk: '不要把统计值当成业务健康证明。读取大型日志也会产生磁盘负载。',
    experience: '数字只有在采样口径一致时才可比较。',
    verification: '用已知行数、无末尾换行及中文样本核对结果。',
    relatedIds: ['LINUX-FD-002', 'LINUX-IO-003'], tags: ['wc', 'date', '统计', '字节', '换行', 'UTC']
  },
  {
    id: 'LINUX-SERVICE-001', title: 'Nginx 启动了吗：从服务状态到业务验证', category: '06 故障排查', level: 'Senior',
    concept: '进程存在、服务 active、端口监听与业务可用是不同层次。先确认 systemd、容器或其他启动方式。',
    architecture: '启动方式 → 服务状态 → 日志 / 配置 → 监听与依赖 → 真实业务请求',
    commands: [
      { command: 'systemctl status nginx --no-pager', purpose: 'systemd 环境中确认服务状态', risk: 'READ_ONLY', parameters: '非 systemd 环境应改用对应容器或进程管理器。' },
      { command: 'journalctl -u nginx --since "15 minutes ago" --no-pager', purpose: '查看近期服务日志', risk: 'READ_ONLY', parameters: '时间窗口按实际故障发生时间调整，输出需脱敏。' },
      { command: 'nginx -t', purpose: '校验配置语法及引用文件可访问性', risk: 'VALIDATION', parameters: '可能需要权限并尝试打开配置引用文件；不重载服务，不能证明 upstream 可用。' }
    ],
    scenario: '用户询问 nginx启动了吗 或 nginx打不开，尚无目标环境和故障范围。',
    diagnosis: ['询问目标、启动方式、时间、影响和最近变更', '检查管理器状态与近期日志', '配置异常时验证配置，上游异常时检查监听、依赖和网络', '用目标域名、路径与预期状态码验证业务'],
    risk: '不要直接 restart；ps aux | grep nginx 可能匹配 grep 自身，不能验证服务健康。',
    experience: '命令建议需附证据需求和判定分支；不能把未执行的检查显示成通过。',
    verification: '服务状态、日志、监听与业务请求结果相互吻合，再形成结论。',
    relatedIds: ['LINUX-FD-001', 'LINUX-IO-002'], tags: ['nginx启动了吗', 'nginx打不开', 'systemctl', 'journalctl', 'nginx -t', '进程', '服务健康']
  }
]
