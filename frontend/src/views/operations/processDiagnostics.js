export const processDiagnosticScenarios = [
  {
    id: 'server-slow',
    label: '服务器响应慢',
    symptoms: ['请求延迟升高', 'load average 增长', '用户报告卡顿'],
    evidence: ['影响范围与开始时间', 'CPU、内存、swap 与 IO wait', '最近发布、流量与告警时间线'],
    commands: [
      { command: 'uptime', purpose: '查看 1/5/15 分钟 load 趋势', readOnly: true },
      { command: 'top -b -n 1', purpose: '采集一次 CPU、内存、swap 和进程状态快照', readOnly: true },
      { command: 'iostat', purpose: '判断磁盘 IO 等待是否造成 load 增长', readOnly: true },
      { command: 'free -h', purpose: '确认内存与 swap 压力', readOnly: true }
    ],
    risk: '只读检查。不要因单个指标异常直接重启服务器或终止进程。',
    verification: ['load 和 IO wait 回落', '业务延迟与错误率恢复', '告警关闭且时间线已记录'],
    escalation: '证据显示存储、内核或硬件异常时，升级给主机/存储负责人。'
  },
  {
    id: 'cpu-high',
    label: 'CPU 使用率过高',
    symptoms: ['CPU 接近 100%', '应用响应变慢', '单个进程持续占用 CPU'],
    evidence: ['高 CPU 进程 PID、用户和命令', '线程、发布和流量变化', 'CPU 与 IO wait 的区别'],
    commands: [
      { command: 'top -b -n 1', purpose: '确认用户态、内核态和 IO wait', readOnly: true },
      { command: 'ps aux --sort=-%cpu', purpose: '按 CPU 找出资源消耗者', readOnly: true },
      { command: 'ps -eo pid,ppid,stat,pcpu,pmem,cmd', purpose: '保留 PID、父进程和状态证据', readOnly: true }
    ],
    risk: '只读检查。没有确认进程归属、影响范围和替代方案前，不建议终止进程。',
    verification: ['CPU/load 恢复趋势', '业务延迟和错误率恢复', '异常进程原因已记录'],
    escalation: '疑似恶意进程、死循环或发布回归时，升级给服务负责人并保留现场。'
  },
  {
    id: 'process-d-state',
    label: 'D 状态进程',
    symptoms: ['进程长期处于 D', '进程对普通信号无响应', '服务出现 IO 超时'],
    evidence: ['进程 PID/PPID 和命令', '磁盘延迟、挂载和内核告警', '存储或网络文件系统状态'],
    commands: [
      { command: 'ps -eo state,pid,ppid,cmd', purpose: '定位 D 状态进程和父子关系', readOnly: true },
      { command: 'iostat', purpose: '确认设备和 IO wait 指标', readOnly: true },
      { command: 'dmesg --level=err,warn', purpose: '查看内核、磁盘和驱动告警', readOnly: true },
      { command: 'cat /proc/<pid>/status', purpose: '查看指定进程的只读状态信息', readOnly: true }
    ],
    risk: 'D 状态通常来自内核或存储等待，强制终止未必生效且可能扩大数据风险。',
    verification: ['IO 延迟和 D 状态数量下降', '挂载与存储告警恢复', '业务读写成功率恢复'],
    escalation: '存储、文件系统或硬件证据明确时，升级给主机/存储负责人。'
  },
  {
    id: 'process-zombie',
    label: '僵尸进程',
    symptoms: ['STAT 出现 Z', '僵尸数量持续增长', '进程表或监控出现异常'],
    evidence: ['僵尸 PID 与 PPID', '父进程是否仍存活', '应用是否正确 wait 回收子进程'],
    commands: [
      { command: 'ps -eo state,pid,ppid,cmd', purpose: '列出 Z 状态进程并找到父进程', readOnly: true },
      { command: 'ps -p <ppid> -o pid,stat,cmd', purpose: '确认父进程状态和命令', readOnly: true },
      { command: 'cat /proc/<pid>/status', purpose: '读取僵尸进程状态信息', readOnly: true }
    ],
    risk: '僵尸本身已退出，直接反复处理子进程不能修复根因；应避免无证据重启父服务。',
    verification: ['僵尸数量停止增长', '父进程回收逻辑恢复', '服务指标和日志正常'],
    escalation: '持续增长或父进程异常时，升级给应用负责人修复子进程回收逻辑。'
  }
]

export function getProcessDiagnosticScenario(id) {
  return processDiagnosticScenarios.find(scenario => scenario.id === id) || null
}
