// Shell flow control, batching and monitoring reference pack.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: `shell.flow.${id}`,
  domain: 'linux', platform: 'Linux / Bash', service: 'shell',
  type: 'SHELL FLOW AUTOMATION', title, section, summary, content,
  tags: ['Shell', 'Bash', 'automation', ...tags],
  source: 'User-provided Shell flow control and automation material',
  version: 'Reference pack', risk, executionAllowed: false
})

export const shellFlowEntries = [
  entry('structures', 'Shell 三大流程结构', '10 / 流程控制', '顺序、选择和循环把单条 Linux 命令组织为可判断、可重复的自动化流程。',
    '[SRC] 顺序结构按代码顺序执行；选择结构包括 if、elif、else、case；循环结构包括 while 和 for。\n[OPS] 先明确输入、状态和退出条件，再选择分支或循环。流程控制不能替代命令结果校验。\n[VERIFY] 用最小输入分别覆盖成功、失败、边界和退出路径。',
    ['sequence', 'selection', 'loop', '流程控制']),
  entry('if-read', 'if 条件判断、read 输入与阈值告警', '11 / if', '使用 if、read 和数值比较处理用户输入、磁盘使用率等运维条件。',
    '[SRC] 基本形式：if [ "$value" -ge 18 ]; then ...; elif [ ... ]; then ...; else ...; fi。read -r -p "提示" value 读取输入。磁盘告警通常是 df 采集、去掉百分号、与阈值比较。\n[OPS] 变量应加引号；输入为空、非数字或 df 输出格式变化时先拒绝或记录，不能直接执行比较。嵌套 if 只有进入外层分支后才会执行。\n[VERIFY] 测试低于、等于、高于阈值及无效输入。',
    ['if', 'elif', 'else', 'read', 'disk threshold', 'validation']),
  entry('command-status', '命令退出状态与检查-操作-验证', '12 / 命令状态', '通过 $?、ping、pgrep、id 和 rpm -q 根据命令成功或失败决定后续动作。',
    '[SRC] $? 是上一条命令的退出状态；通常 0 表示成功，非 0 表示失败。ping -c1 检查连通性，pgrep 检查进程，id 检查用户，rpm -q 查询软件包。\n[OPS] 需要立即保存 $?，避免中间命令覆盖它。自动化采用“检查 -> 操作 -> 再验证”模式；rpm、yum、dnf、systemctl 的参数和可用性要结合发行版确认。\n[VERIFY] 记录原始命令、退出码、stderr 和最终状态。',
    ['$?', 'ping -c1', 'pgrep', 'id', 'rpm -q', 'exit status']),
  entry('redirect', '标准输入输出、错误输出与重定向', '13 / I/O', '理解 stdin/stdout/stderr、文件描述符 0/1/2、2>&1 和 &> /dev/null。',
    '[SRC] 0 是 stdin，1 是 stdout，2 是 stderr；2>&1 将错误输出并入标准输出；command &> /dev/null 丢弃两类输出。\n[OPS] /dev/null 只适合明确不需要证据的探测命令。巡检和故障诊断应保留 stderr，例如 command >> "$LOG_FILE" 2>&1 或 command 2>&1 | tee -a "$LOG_FILE"。重定向顺序会影响结果。\n[VERIFY] 分别验证正常输出、错误输出和日志文件内容。',
    ['stdin', 'stdout', 'stderr', '0', '1', '2', '2>&1', '&>', '/dev/null', 'tee']),
  entry('case-menu', 'case 参数分派与交互式运维菜单', '14 / case', 'case 适合动作分派、服务管理和 read + while 菜单。',
    '[SRC] case "$1" in start|S) ... ;; stop|T) ... ;; *) ... ;; esac。;; 结束分支，* 是默认分支，| 表示多个模式。菜单通常是 cat <<EOF、while true、read、case，q 分支使用 exit。\n[OPS] 参数缺失、未知动作和服务名必须有明确提示；systemctl 等改变状态的命令属于高风险操作，先展示目标和预期结果并要求审批。\n[VERIFY] 覆盖每个动作、未知动作、空输入和 q 退出。',
    ['case', 'service management', 'menu', 'while true'], 'APPROVAL_REQUIRED'),
  entry('while-control', 'while、sleep 与 continue/break/exit', '15 / while', 'while 适合计数、持续监控和交互循环；continue、break、exit 的作用域不同。',
    '[SRC] while [ "$i" -le 5 ]; do ...; i=$((i + 1)); done。while true 需要 sleep、break 或外部终止机制。continue 跳过本轮，break 结束当前循环，exit 结束整个脚本。\n[OPS] 生成 while 时检查初始化、条件更新和最大运行时间，避免死循环；持续监控要考虑采集失败、告警限频和恢复状态。\n[VERIFY] 测试零次、一次、边界值、异常跳过和可控退出。',
    ['while', 'sleep', 'continue', 'break', 'exit', '监控']),
  entry('for-batch', 'for、列表、位置参数与数组遍历', '16 / for', 'for 适合列表、数组、位置参数和 C 风格计数循环的批量处理。',
    '[SRC] for x in {1..10..2}; do ...; done；for ((i=1; i<=5; i++)); do ...; done；不带 in 的 for x 遍历脚本位置参数。数组应使用 for server in "${SERVERS[@]}"。seq 可生成列表。\n[OPS] 明确边界、步长、空列表和参数引用；使用 "$@" 保留参数边界，不要无引号展开路径或主机名。\n[VERIFY] 覆盖空列表、单元素、倒序和最后一个边界值。',
    ['for', 'for in', 'C-style for', 'seq', 'array', 'position parameters']),
  entry('concurrency', '后台任务、并发探测与 wait', '17 / 并发', '使用 & 并发执行批量任务，并用 wait 等待后台任务完成。',
    '[SRC] command & 将任务放入后台；wait 等待后台任务。批量 ping 可按主机启动后台子任务，再 wait 汇总结果。$! 是最近后台进程 PID。\n[OPS] 并发会带来输出顺序变化、共享文件竞争、资源耗尽和退出码丢失；需要限制并发数、使用临时文件或锁，并明确收集每个任务的状态。\n[VERIFY] 检查所有任务是否完成、成功/失败数量和日志完整性。',
    ['&', 'wait', 'parallel', 'batch ping', 'concurrency']),
  entry('batch-ops', '批量用户、IP 与 SSH 自动化', '18 / 批量运维', '将组、用户、网络探测和 SSH 公钥分发抽象为可验证的批量流程。',
    '[SRC] groupadd/useradd/ passwd 可批量创建账号；ping 可将主机分为 up/down；ssh-keygen 生成密钥，ssh-copy-id 分发公钥，数组保存服务器列表。expect 仅用于说明交互自动化边界。\n[OPS] 这些命令可能改变账户、权限或远程访问，默认不执行。私钥不可分发；StrictHostKeyChecking=no 会降低主机身份校验；密码不应明文写入脚本或日志；生产执行需要审批、最小权限和回滚方案。passwd --stdin、yum/dnf 参数需按发行版验证。\n[VERIFY] 先在隔离环境验证，记录目标、退出码、账号和 SSH 审计结果。',
    ['useradd', 'groupadd', 'passwd', 'ping', 'ssh-keygen', 'ssh-copy-id', 'expect', 'batch'], 'HIGH'),
  entry('monitoring', 'CPU、I/O 监控、bc 浮点比较与告警', '19 / 监控告警', '采集、校验、计算、阈值判断、告警和 sleep 构成监控闭环。',
    '[SRC] top -bn1、uptime、free -h、df -h、iostat 可采集指标；%iowait 较高时关注 I/O。bc -l 支持浮点计算和比较；[[ "$value" =~ ^[0-9]+(\\.[0-9]+)?$ ]] 可校验数字；sendmail 可发送告警。\n[OPS] 先检查空值和格式，再计算 100 - cpu_idle；while true + sleep 需要告警限频、恢复通知和停止机制。sendmail、bc、sysstat、stress-ng 是否安装必须先确认，邮件内容和编码需验证。\n[VERIFY] 使用安全的测试负载，验证正常、超阈值、采集失败、恢复和重复告警抑制。',
    ['CPU', 'iostat', '%iowait', 'bc', 'sendmail', '=~', 'alert', 'sleep'], 'APPROVAL_REQUIRED'),
  entry('random-data', 'RANDOM、随机数据与密码生成边界', '20 / 随机化', '使用 $RANDOM、取模、字符串切片和 pwgen 生成测试数据或抽样结果。',
    '[SRC] $RANDOM 通常产生 0..32767 的伪随机整数；RANDOM % N 产生 0..N-1；${value:7:4} 做字符串切片；pwgen 可生成随机密码。\n[OPS] $RANDOM 不是密码、令牌或密钥的安全随机源；抽奖要处理重复行和文件变化，手机号示例只适合测试数据。生成账号密码时禁止将明文密码写入共享日志。\n[VERIFY] 检查数量、格式、重复率和敏感数据泄露。',
    ['$RANDOM', 'modulo', 'string slice', 'pwgen', 'test data']),
  entry('diagnosis', 'Shell 流程控制故障树', '21 / 故障诊断', '按解释器、输入、条件、循环、命令状态、并发和环境逐层定位脚本问题。',
    '[OPS] if 不执行：检查变量、数字比较、方括号空格、then/fi；case 报错：检查 in、pattern)、;;、esac；while 不退出：检查初始化、更新、sleep、break；for 边界错误：检查列表、数组和步长；后台结果缺失：检查 wait 和退出码。\n[VERIFY] 使用 bash -n script.sh 做语法检查，bash -x script.sh 观察执行路径，保留原始报错、输入、环境、命令和日志。不要在缺少证据时重写整段脚本。',
    ['bash -n', 'bash -x', 'troubleshooting', 'if', 'case', 'while', 'for', 'wait'])
]

export const shellFlowRules = Object.freeze([
  { id: 'SHELL-FLOW-001', trigger: '自动化脚本', sequence: ['input', 'validate', 'collect', 'branch/loop', 'operate', 'verify', 'log', 'exit'] },
  { id: 'SHELL-FLOW-002', trigger: '命令结果判断', sequence: ['run command', 'capture $? immediately', 'handle success/failure', 'verify'] },
  { id: 'SHELL-FLOW-003', trigger: '后台并发', sequence: ['limit concurrency', 'start with &', 'collect status', 'wait', 'summarize'] },
  { id: 'SHELL-FLOW-004', trigger: '高风险批量操作', sequence: ['preview target', 'confirm approval', 'least privilege', 'execute', 'audit', 'rollback/verify'] }
])
