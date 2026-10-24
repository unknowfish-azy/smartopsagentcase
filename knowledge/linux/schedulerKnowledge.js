// Linux Scheduler Engineering v1.0. Reference data; no command is executed automatically.
export const linuxSchedulerNodes = [
  {
    id: 'LINUX-SCHED-001', title: 'at 一次性任务与 atd 队列', category: '14 任务调度', level: 'Middle',
    concept: 'at 创建一次性任务定义，atd 负责在指定时间消费队列。创建任务、队列存在、实际执行和业务结果是不同事实。', architecture: 'at → queue → atd → process → output/error → result',
    commands: [
      { command: 'at now +5 minutes', purpose: '创建一次性任务', risk: 'MEDIUM', parameters: '创建任务前确认用户、目标时间和命令影响。' },
      { command: 'atq', purpose: '查看待执行的一次性任务', risk: 'READ_ONLY', parameters: '输出可能包含命令和敏感路径，保存时需脱敏。' },
      { command: 'atrm <job_id>', purpose: '删除待执行任务', risk: 'MEDIUM', parameters: '确认 job_id 和业务影响后再删除。' },
      { command: 'systemctl is-active atd', purpose: '检查 atd 是否运行', risk: 'READ_ONLY', parameters: '服务 active 不代表队列任务成功。' }
    ], scenario: 'at 提交失败、任务未进入队列，或队列中任务到点后没有结果。', diagnosis: ['区分命令不存在、服务不可用、权限拒绝和执行失败', '检查 at.allow/at.deny 与 atq', '确认 atd 状态、系统时间和执行用户', '检查输出、日志、退出码和最终结果'], risk: '删除队列或创建高权限一次性任务会改变生产行为；不得将 atd active 等同任务成功。', experience: '先看队列和执行上下文，再决定是否重启服务或重新提交。', verification: '确认任务进入队列、触发时间、进程、退出码和预期结果。', relatedIds: ['LINUX-SCHED-002'], tags: ['at', 'atq', 'atrm', 'atd', 'at.allow', 'at.deny']
  },
  {
    id: 'LINUX-SCHED-002', title: 'Cron、crond 与 crontab 生命周期', category: '14 任务调度', level: 'Middle',
    concept: 'crond 是周期调度 daemon，crontab 是管理任务定义的命令/任务表。daemon 正常不代表每个任务正常。', architecture: 'crontab -e → job definition → crond scan → expression match → process → exit/output → verification',
    commands: [
      { command: 'crontab -l', purpose: '查看当前用户的周期任务定义', risk: 'READ_ONLY', parameters: '优先使用该接口，不直接编辑 spool 文件。' },
      { command: 'crontab -e', purpose: '编辑当前用户任务定义', risk: 'MEDIUM', parameters: '变更前备份并审查表达式、用户、路径和输出。' },
      { command: 'systemctl is-active crond', purpose: '检查周期调度 daemon', risk: 'READ_ONLY', parameters: 'Debian 系可能使用 cron 服务名，需识别发行版。' },
      { command: 'journalctl -u crond --since "1 hour ago"', purpose: '查询调度日志', risk: 'READ_ONLY', parameters: '日志位置依发行版和日志系统而异。' }
    ], scenario: 'crontab 中有任务但没有结果，或手工执行成功而 cron 失败。', diagnosis: ['确认 scheduler、用户和 job definition', '解析五字段并计算下一次触发', '检查 cron.allow/cron.deny、脚本权限和 shebang', '比较 PATH、SHELL、HOME、PWD、环境变量和依赖', '检查 stdout/stderr、退出码和业务结果'], risk: 'root cron、自动删除、重启、防火墙和生产数据变更必须审批；不要直接修改 /var/spool/cron。', experience: 'crond active 只能证明调度器进程状态，不能证明触发、脚本成功或业务成功。', verification: '同时验证触发记录、进程、退出码、输出文件、业务结果和审计记录。', relatedIds: ['LINUX-SCHED-003', 'LINUX-SCHED-004'], tags: ['cron', 'crond', 'crontab', 'cron.allow', 'cron.deny', 'scheduler']
  },
  {
    id: 'LINUX-SCHED-003', title: 'Cron 表达式与执行上下文', category: '15 调度表达式', level: 'Middle',
    concept: '五字段为 minute、hour、day-of-month、month、day-of-week。表达式应双向解析，并结合实现、时区和复杂 DOM/DOW 语义验证。', architecture: 'Natural language ↔ cron expression ↔ next-run simulation ↔ timezone/context',
    commands: [
      { command: '*/5 * * * * /opt/scripts/job.sh', purpose: '每五分钟触发一次示例', risk: 'MEDIUM', parameters: '需考虑脚本耗时、并发和日志轮转。' },
      { command: '0 2 * * 5 /opt/scripts/backup.sh', purpose: '每周五 02:00 触发示例', risk: 'HIGH', parameters: '备份成功必须独立验证，不能只看调度日志。' },
      { command: 'command -v date', purpose: '确认执行环境中命令路径', risk: 'READ_ONLY', parameters: 'cron 环境 PATH 可能不同，关键任务使用明确路径。' }
    ], scenario: '表达式写错、时区误解、PATH 缺失、工作目录不同或脚本无 shebang。', diagnosis: ['将自然语言需求和表达式互相翻译', '计算下一次触发并标注时区', '检查 DOM+DOW 实现差异，不死记 AND', '明确 SHELL、PATH、HOME、PWD、USER 和依赖'], risk: '复杂表达式和错误时区可能造成漏跑或误跑；生产任务变更需审查 blast radius。', experience: '绝对路径是降低环境差异的手段，不是替代执行上下文建模的规则。', verification: '在目标实现和时区下模拟下一次执行，并用受控样本验证。', relatedIds: ['LINUX-SCHED-002', 'LINUX-SCHED-005'], tags: ['cron expression', 'PATH', 'SHELL', 'HOME', 'working directory', 'timezone']
  },
  {
    id: 'LINUX-SCHED-004', title: '计划任务输出、重叠与幂等性', category: '16 作业运行时', level: 'Senior',
    concept: '任务触发不等于成功；需要记录进程、退出码、stdout/stderr、结果和验证。调度间隔小于运行时长时会产生重叠。', architecture: 'Trigger → duration → next trigger → overlap/lock → exit code → output → business verification',
    commands: [
      { command: 'flock -n /var/run/job.lock /opt/scripts/job.sh', purpose: '避免同一任务并发执行', risk: 'MEDIUM', parameters: '确认锁路径权限、失败时行为和任务幂等性。' },
      { command: '*/5 * * * * /opt/scripts/job.sh >> /var/log/job.log 2>&1', purpose: '明确收集 stdout/stderr', risk: 'MEDIUM', parameters: '必须配置 logrotate 和 retention，避免日志无限增长。' },
      { command: 'ps -ef --forest', purpose: '只读观察任务进程和父子关系', risk: 'READ_ONLY', parameters: '仅用于证据收集，不代表业务成功。' }
    ], scenario: '每五分钟备份一次但单次耗时二十分钟，或 cron 有记录但备份文件为空/损坏。', diagnosis: ['比较 schedule interval 与历史 duration', '检查 lock、重复进程和 backlog', '判断退出码、输出、文件大小、完整性和远程复制', '设计幂等、超时、重试和告警策略'], risk: '重叠备份会放大 I/O、锁和存储压力；日志重定向本身也需要轮转和权限控制。', experience: '备份文件存在不等于可恢复，必须安排完整性和定期 restore 验证。', verification: '确认单实例、退出码、文件阈值、校验、保留策略和恢复抽样。', relatedIds: ['LINUX-SCHED-002', 'LINUX-STORAGE-005'], tags: ['flock', 'overlap', 'idempotent', 'backup', 'stdout', 'stderr', 'logrotate']
  },
  {
    id: 'LINUX-SCHED-005', title: 'systemd timer 与 anacron：现代调度选型', category: '17 调度器生态', level: 'Senior',
    concept: 'Linux 不只有 cron：systemd timer 可与 service unit 绑定，anacron 适合机器不持续在线且不要求精确分钟的周期任务。', architecture: 'timer unit ↔ service unit / anacron periodic catch-up',
    commands: [
      { command: 'systemctl list-timers --all', purpose: '查看 systemd timer 及下次触发', risk: 'READ_ONLY', parameters: '结合对应 service 的日志和结果。' },
      { command: 'systemctl cat backup.timer', purpose: '查看 timer 定义和日历语义', risk: 'READ_ONLY', parameters: '不要把 unit 文件内容当作实际成功证据。' },
      { command: 'cat /etc/anacrontab', purpose: '查看 anacron 周期定义', risk: 'READ_ONLY', parameters: '不同发行版默认配置可能不同。' }
    ], scenario: '需要选择 cron、systemd timer 或 anacron，并在迁移后保持可观测性。', diagnosis: ['识别调度器和关联 job/service', '检查下一次触发、持久化策略和时区', '关联 journald、退出码和业务验证', '迁移时保留回滚和重复执行防护'], risk: '同时启用多个调度器可能重复执行；迁移必须检查旧任务是否仍存在。', experience: '工具选型应基于精确时间、离线补偿、依赖管理和审计要求。', verification: '确认唯一调度源、触发时间、结果和长期运行基线。', relatedIds: ['LINUX-SCHED-002', 'LINUX-SCHED-004'], tags: ['systemd timer', 'anacron', 'OnCalendar', 'Persistent', 'scheduler selection']
  }
]

export const linuxSchedulerIncidents = [
  { id: 'INC-CRON-001', title: 'Cron 任务未执行', risk: 'LOW', runbook: ['检查 crond/cron 状态', '查看 crontab -l', '解析表达式和下一次触发', '检查权限、脚本、shebang、环境', '检查日志、退出码和业务结果'], relatedKnowledge: ['LINUX-SCHED-002', 'LINUX-SCHED-003'] },
  { id: 'INC-CRON-002', title: 'Cron 已触发但业务结果缺失', risk: 'MEDIUM', runbook: ['确认进程和退出码', '检查 stdout/stderr', '检查权限、磁盘、依赖和网络', '验证输出完整性和业务结果'], relatedKnowledge: ['LINUX-SCHED-004'] },
  { id: 'INC-CRON-003', title: '手工执行成功但 Cron 失败', risk: 'MEDIUM', runbook: ['比较用户、PATH、SHELL、HOME、PWD', '比较环境变量和依赖路径', '以相同用户和环境受控重现', '修正后验证并记录'], relatedKnowledge: ['LINUX-SCHED-003'] },
  { id: 'INC-CRON-004', title: 'Cron 任务重叠', risk: 'HIGH', runbook: ['比较间隔和运行时长', '检查重复进程', '增加 flock 或幂等保护', '验证单实例、吞吐和告警'], relatedKnowledge: ['LINUX-SCHED-004'] },
  { id: 'INC-AT-001', title: 'At 任务无法提交或未执行', risk: 'MEDIUM', runbook: ['区分命令、权限、atd、队列和执行错误', '检查 at.allow/at.deny', '检查 atq 和系统时间', '验证结果'], relatedKnowledge: ['LINUX-SCHED-001'] }
]

export const linuxSchedulerWrongAnswers = [
  { id: 'WRONG-CRON-DAEMON', misconception: 'crond active 就代表所有 cron 任务正常', correction: '只能证明调度器进程状态；还需验证定义、表达式、权限、上下文、退出码和业务结果。' },
  { id: 'WRONG-CRON-MANUAL', misconception: '脚本手工成功就代表 cron 成功', correction: '必须比较用户、PATH、SHELL、HOME、PWD、环境变量和依赖。' },
  { id: 'WRONG-BACKUP-LOG', misconception: 'cron 日志有执行记录就代表备份成功', correction: '还要验证退出码、文件、大小、完整性、传输、保留和恢复。' },
  { id: 'WRONG-CRON-OVERLAP', misconception: '每五分钟执行不需要考虑上一次是否完成', correction: '需比较执行时长与间隔，并使用锁或幂等策略防止重叠。' }
]

export const linuxSchedulerDecisionRules = [{ trigger: '计划任务异常', sequence: ['identify scheduler', 'identify user/job', 'parse schedule', 'check permissions', 'check execution context', 'check logs/runtime', 'check exit code/output', 'verify business result', 'evaluate overlap', 'approve change', 'execute', 'record'], defaultRisk: 'READ_ONLY' }]
