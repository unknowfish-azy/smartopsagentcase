# Linux 进程管理知识模块

模块 ID：`LINUX-PROCESS-001`

分类：Linux 系统管理 / 性能排查 / 生产运维

## 基本概念

程序是磁盘上的静态可执行文件；进程是程序运行后的实例。进程有 PID、PPID、生命周期、状态、地址空间和资源占用。线程是进程内的执行单元。Linux 进程通常由父进程通过 `fork()` 创建，PID 1 通常是 `systemd`（老版本可能是 `init`）。

## 进程状态

- `R`：正在运行或等待 CPU 调度。
- `S`：可中断睡眠，等待网络、定时器或其他事件。
- `D`：不可中断睡眠，常见于磁盘或存储 IO 等待，信号不能立即终止。
- `T`：暂停，常见于 `SIGSTOP` 或终端 `Ctrl+Z`。
- `Z`：僵尸进程，已退出但父进程尚未回收退出状态。
- `X`：已终止，通常不会长期出现在列表中。

D 状态应优先检查存储延迟、挂载、内核日志和硬件；Z 状态应找到 PPID 并修复父进程回收逻辑。

## 查看与性能命令

`ps aux` 查看所有用户进程及 CPU、内存、STAT 和命令；`ps -ef` 查看 PID/PPID 父子关系；`ps axo user,pid,ppid,%mem,command` 输出自定义字段。`ps aux --sort=-%cpu` 和 `ps aux --sort=-%mem` 分别定位 CPU、内存消耗者。`top` 动态观察进程，`P` 按 CPU 排序，`M` 按内存排序。`uptime` 查看 1/5/15 分钟 load average；`iostat` 判断 IO 等待；`free -h` 查看内存和 swap；`dmesg --level=err,warn` 查看内核告警。

## 信号与终止策略

`SIGTERM`（15）请求正常退出，允许清理资源；`SIGKILL`（9）强制终止，无法被捕获或清理，可能造成数据丢失；`SIGHUP`（1）常用于重新加载配置；`SIGSTOP` 暂停，`SIGCONT` 继续。生产环境先收集证据，优先正常停止并等待；只有确认影响、替代方案和数据风险后才升级到强制终止。不要把 `kill -9` 当作第一排查动作。

## 优先级、作业与 `/proc`

`nice` 启动时设置优先级，`renice` 调整运行中进程；nice 通常为 -20 到 19，数值越小优先级越高。`jobs`、`fg`、`bg` 管理前后台任务，`Ctrl+C` 发送中断，`Ctrl+Z` 暂停。`/proc/cpuinfo`、`/proc/meminfo`、`/proc/<pid>/status` 和 `lscpu` 可只读确认 CPU、内存和进程状态。

## 生产排查路径

服务器变慢时先确认影响范围和开始时间，再按顺序取证：`uptime` 确认 load；`top -b -n 1` 查看 CPU、内存、swap、IO wait 和状态；使用 `ps aux --sort=-%cpu`、`ps aux --sort=-%mem` 定位资源消耗者；用 `iostat`、`free -h` 判断 IO 与内存；用 `ps -eo state,pid,ppid,cmd` 统计 D/Z 状态并追溯父进程；最后对照发布、流量、日志和监控时间线形成可验证假设。

CPU 100% 可能来自死循环、流量突增、恶意进程或 IO 误判；D 状态通常需要存储和内核证据；大量 Z 状态通常是父进程 bug。修复后验证 CPU/load、业务延迟、错误率、进程状态和告警恢复。

## SmartOpsAgent 诊断规则

用户说“服务器卡”时，先询问 CPU、内存、load average、磁盘 IO、受影响服务和最近变更；不要直接建议重启服务器。所有命令先以只读预览展示，输出必须标注证据目的、风险和验证方法。题库覆盖程序与进程、`ps`/`top`、CPU 100%、D 状态、Z 状态、信号选择、优先级和生产风险判断。关联模块：`LINUX-MEMORY`、`LINUX-CPU`、`LINUX-DISK`、`LINUX-SYSTEMD`、`LINUX-SHELL`、`LINUX-PERFORMANCE`。
