// Shell/Bash, text processing and operations inspection pack.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: 'shell.' + id, domain: 'linux', platform: 'Linux / Bash', service: 'shell',
  type: 'SHELL KNOWLEDGE', title, section, summary, content,
  tags: ['Shell', 'Bash', ...tags], source: '用户提供的 Shell 基础与运维巡检材料',
  version: 'Reference pack', risk, executionAllowed: false
})

export const shellCoreEntries = [
  entry('execution', 'Shell、交互式与非交互式执行', '01 / 基础', 'Shell 是命令解释器；脚本把命令、变量、判断和工具组织成非交互式自动化。',
    '[SRC] 交互式命令逐条输入并立即返回；bash script.sh 由新的 Shell 执行脚本。#!/bin/bash 声明解释器。\\n[OPS] 脚本失败先确认执行方式、解释器、权限、当前目录、PATH 和原始错误。手工执行正常不代表 cron/子 Shell 环境相同。',
    ['interactive', 'non-interactive', 'shebang', 'bash -x', 'cron']),
  entry('variables-env', 'Shell 变量、环境变量与配置加载', '02 / 变量与环境', '普通变量只在当前 Shell 使用；export 变量可传给子 Shell；永久配置取决于 profile 加载链。',
    '[SRC] name=\"Tom\"；引用变量使用 \"$name\"。export MY_VAR=test 后子 Shell 可读；unset MY_VAR 不带 $。常见 HOME、PATH、SHELL、USER、PWD、UID；env/printenv 查看环境。\\n登录环境涉及 /etc/profile、/etc/profile.d/*、~/.bash_profile、~/.bashrc、/etc/bashrc；source 重新加载。export 不等于永久配置。\\n[OPS] 变量不生效检查定义、拼写/大小写、export、父子 Shell、登录类型和 source。',
    ['variable', 'export', 'unset', 'PATH', 'HOME', 'bashrc', 'bash_profile', 'profile.d']),
  entry('quotes-substitution', '单引号、双引号与命令替换', '03 / Shell 语法', '单引号保留字面量，双引号展开变量；$(command) 是推荐的命令替换写法。',
    '[SRC] 单引号包裹的变量保持字面量，双引号包裹的变量会展开。CMD=$(pwd)、CURRENT_DATE=$(date +%F) 获取命令结果；反引号是旧式写法。\\n[OPS] 路径、文本和变量默认使用双引号，避免空格和通配符拆分；需要字面 $ 时用单引号或反斜杠。命令替换的 stderr 需明确重定向。',
    ['single quote', 'double quote', 'command substitution', '$( )', 'backtick']),
  entry('parameters-status', '位置参数、退出状态与进程变量', '04 / 参数与状态', '$0/$1/$#/$@/$* 用于脚本参数；$? 表示上一条命令状态，$$ 和 $! 表示进程标识。',
    '[SRC] $0 是脚本名，$1...$n 是参数，$# 是参数数量；\"$@\" 保留每个参数独立性，\"$*\" 更倾向作为整体；$? 为上一命令退出码；$$ 为当前 Shell PID，$! 为最近后台进程 PID。\\n[OPS] 校验参数数量和必填项；在执行会改变 $? 的命令前保存状态。job 编号如 %1 与 PID 不同。',
    ['$0', '$1', '$#', '$@', '$*', '$?', '$$', '$!']),
  entry('arithmetic-test', 'Shell 算术、文件测试与逻辑判断', '05 / 判断', '$(( )) 做整数运算；test/[ ]/[[]] 做条件判断；数值比较和字符串比较使用不同操作符。',
    '[SRC] $((1+1))、let i++；浮点可用 bc。文件测试 -e/-f/-d/-L/-s/-S/-c/-b、-r/-w/-x、-nt/-ot/-ef；数值 -eq/-ne/-gt/-lt/-ge/-le；字符串 -z/-n、=、!=。条件方括号两侧必须有空格；&& 为与，|| 为或，! 取反。\\n[OPS] -eq 是数值比较，= 是字符串比较；文件、目录、socket 和权限判断应使用引号包裹变量。',
    ['$(( ))', 'let', 'bc', 'test', '[ ]', '[[ ]]', '-f', '-d', '-S', '-eq', '-z', '&&', '||']),
  entry('text-tools', 'cut、sort、uniq、tee、diff、paste、tr', '06 / 文本处理', '这些工具完成字段提取、排序统计、屏幕与文件分流、差异比较、逐行合并和字符转换。',
    '[SRC] cut -d: -f1 取列，-c 按字符取位；sort -n/-r/-t/-k/-u 排序；uniq 只处理连续重复，统计前通常 sort | uniq -c；tee 同时输出屏幕和文件；diff -r 比目录、diff -u 生成补丁；paste 逐行合并；tr -d 删除、-s 压缩重复。\\n[OPS] 日志频次链：grep → cut → sort → uniq -c → sort -nr。sort 默认字符排序，不要默认数字顺序。',
    ['cut', 'sort', 'uniq', 'tee', 'diff', 'patch', 'paste', 'tr']),
  entry('log-analysis', 'Shell 日志分析与 SSH 失败 IP 统计', '07 / 日志', '用过滤、字段提取、排序、计数和降序组合从日志中提取高频对象。',
    '[SRC] grep \"Failed password\" /var/log/secure 过滤 SSH 失败，再用 cut 提取 IP，sort 排列，uniq -c 计数，sort -nr 按次数降序。\\n[OPS] 先确认日志格式和字段位置，抽样验证提取结果，再做统计；确认日志权限、轮转和脱敏，输出可用 tee -a 保存。',
    ['grep', 'Failed password', '/var/log/secure', 'SSH', 'log analysis']),
  entry('health-check', 'Shell 自动化巡检脚本', '08 / 运维巡检', '用 Shell 采集负载、CPU、内存、磁盘、进程、网络、日志、安全和 Cron，并保留日志。',
    '[SRC] 常见命令：uptime、top -bn1、free -h、df -h、ps aux --sort=-%cpu、ss -tunlp、journalctl -n 10、dnf check-update、sestatus、firewall-cmd --state、lsblk、crontab -l、hostname、uname -a。日志可用 LOG_FILE、date、命令替换和 >> 追加。\\n[OPS] 巡检是采集→格式化→记录→复查；命令可能不存在或返回非零，不能把所有非零都当灾难。记录命令、退出码和时间，避免 &>/dev/null 丢证据。',
    ['health check', 'uptime', 'free', 'df', 'ps', 'ss', 'journalctl', 'sestatus', 'firewall-cmd'], 'APPROVAL_REQUIRED'),
  entry('debugging', 'Shell 脚本故障诊断与 AI 辅助开发', '09 / 调试', '脚本失败要从解释器、权限、路径、变量、环境、引号、判断、重定向和日志逐层定位。',
    '[OPS] 最小验证：bash -x script.sh；pwd；which command；echo \"$PATH\"；echo \"$VAR\"；echo \"$?\"；检查 #!/bin/bash、chmod +x、条件空格、数值/字符串操作符和 stdout/stderr。建议 command >> \"$LOG_FILE\" 2>&1 或 command 2>&1 | tee -a \"$LOG_FILE\"。AI 生成脚本前先明确输入、输出、路径、退出状态、错误处理、日志和权限，再人工检查、测试和复验。',
    ['bash -x', 'debug', 'exit status', 'stderr', 'AI ops', 'automation'])
]

export const shellCoreRules = Object.freeze([
  { id: 'SHELL-001', trigger: '脚本失败', sequence: ['interpreter', 'permission', 'path', 'variable', 'environment', 'command status', 'condition', 'log'] },
  { id: 'SHELL-002', trigger: '变量不生效', sequence: ['defined', 'spelling/case', 'export', 'child shell', 'profile source'] },
  { id: 'SHELL-003', trigger: '统计日志频次', sequence: ['grep', 'cut', 'sort', 'uniq -c', 'sort -nr', 'verify field'] },
  { id: 'SHELL-004', trigger: '配置文件不一致', sequence: ['diff', 'diff -r', 'diff -u', 'review patch', 'apply with approval'] },
  { id: 'SHELL-005', trigger: '自动巡检', sequence: ['collect', 'timestamp', 'log stdout/stderr', 'record exit code', 'review exceptions'] }
])
