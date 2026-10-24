// Shell functions, links, regular expressions and Expect automation.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: `shell.advanced.${id}`,
  domain: 'linux', platform: 'Linux / Bash', service: 'shell',
  type: 'SHELL ADVANCED AUTOMATION', title, section, summary, content,
  tags: ['Shell', 'Bash', ...tags], source: 'User-provided Shell functions, regex, links and Expect material',
  version: 'Reference pack', risk, executionAllowed: false
})

export const shellAdvancedEntries = [
  entry('functions', 'Shell 函数、参数与 return', '22 / 函数', '函数封装重复逻辑，参数化输入，并用 return 将成功或失败状态交给调用者。',
    '[SRC] function_name() { ... } 或 function function_name() { ... } 定义函数；定义不会执行，调用函数名才执行。函数参数使用 $1、$2，return 0 表示成功，非 0 表示失败；没有显式 return 时，函数状态通常是最后一条命令的状态。\n[OPS] 将采集、判断、告警和报告拆成职责单一的函数，调用后立即保存 $?；参数、空值和除数为零等边界必须校验。\n[VERIFY] 分别测试成功参数、错误参数、提前 return 和最后命令失败。',
    ['function', 'function parameters', 'return', '$1', '$2', '$?', 'modularization']),
  entry('function-ops', '函数化巡检与定时任务', '23 / 函数化运维', '用 check、alert、report 等函数组织磁盘检查、日志记录和邮件告警。',
    '[SRC] 典型链路是 check_disk_usage -> alert_disk_usage；df 逐行读取后提取分区和使用率，再按阈值记录日志或调用告警函数。crontab 可定期调用脚本。\n[OPS] sendmail、systemctl、crontab 和日志路径要先确认环境；告警函数不得吞掉采集错误，应保留时间、目标、退出码和原始证据。高风险的服务启停和邮件发送需要审批或明确运行边界。\n[VERIFY] 在隔离环境验证低/高阈值、无效 df 输出、日志权限和重复告警。',
    ['check_disk_usage', 'alert_disk_usage', 'df', 'crontab', 'sendmail'], 'APPROVAL_REQUIRED'),
  entry('links-inode', '软链接、硬链接与 inode', '24 / 文件系统链接', 'ln -s 创建路径引用，ln 创建硬链接；inode 用于理解硬链接共享关系和软链接失效。',
    '[SRC] ln -s target link 创建软链接，通常显示 l 和 ->；ln target link 创建硬链接。ls -i 查看 inode。软链接保存目标路径，目标删除后会失效；硬链接与原文件共享 inode，删除一个名字不影响其他链接访问数据。\n[OPS] 创建或切换软件版本前确认源路径、目标路径、权限和跨文件系统限制；不要把软链接存在误判为目标可用。目录硬链接通常受文件系统限制。\n[VERIFY] 用 ls -l、readlink、ls -i 和 test -e 分别验证类型、目标、inode 和断链状态。',
    ['ln', 'ln -s', 'symbolic link', 'hard link', 'inode', 'readlink']),
  entry('regex', '正则表达式、grep -E/-P 与 awk', '25 / 正则', '用 BRE/ERE/PCRE、字符簇、数量限定、定位、分组和反向引用检索日志与配置。',
    '[SRC] . 匹配任意字符；[] 是字符簇；^/$ 是行首行尾；*、+、?、{m,n} 控制数量；grep -E 使用扩展正则，grep -P 使用 PCRE；awk 的 $5 ~ /pattern/ 按字段匹配。\n[OPS] 先明确查什么、查多少、从哪里查；\. 匹配普通点，^ 在 [] 内是取反。\\d、\\w、\\b 依赖 PCRE/工具支持。IP、日期和邮箱示例多为格式匹配，不等于严格业务校验。\n[VERIFY] 用正例、反例、边界和真实输入逐步验证，并确认 grep 方言和大小写选项。',
    ['regex', 'grep', 'grep -E', 'grep -P', 'ERE', 'PCRE', 'awk', 'metacharacter']),
  entry('regex-logs', '正则与日志分析流水线', '26 / 正则日志', 'grep 正则筛选、awk 字段提取、sort/uniq 统计构成常用日志分析链。',
    '[SRC] 常见链路：grep "404" access.log | awk "{print $7}" | sort | uniq -c | sort -nr；也可用 ^/dev、^#|^$、\\d{1,3}(\\.\\d{1,3}){3} 等模式。\n[OPS] 先确认日志格式、字段位置、编码和轮转文件；uniq 统计前必须排序，字段提取结果要抽样核验。敏感日志输出需脱敏并限制权限。\n[VERIFY] 对原始行、提取字段、计数结果分别核对，避免将匹配成功当成完整语义验证。',
    ['log analysis', 'awk', '404', 'IP regex', 'date regex', 'uniq -c']),
  entry('expect-core', 'Expect 状态机：spawn、expect、send', '27 / Expect', 'Expect 通过等待提示并发送输入自动化 SSH、密码和确认交互。',
    '[SRC] spawn 启动程序；expect 等待输出；send 发送输入，\\r 表示回车；exp_continue 继续匹配；interact 把会话交给用户；expect eof 等待程序结束。set timeout、argv 和 lindex 可参数化超时、主机和认证信息。\n[OPS] interact 适合登录后人工操作，expect eof 适合自动执行后退出。提示符、大小写、额外空格和超时都可能导致卡住。明文密码可能出现在脚本、历史或进程中，不应作为生产默认方案。\n[VERIFY] 记录实际交互输出，分别测试首次 yes/no、password、远程提示符、认证失败和连接超时。',
    ['Expect', 'spawn', 'expect', 'send', 'interact', 'exp_continue', 'expect eof', 'timeout']),
  entry('shell-expect', 'Shell + Expect 多服务器自动化', '28 / Shell + Expect', 'Shell 负责列表、循环、函数和并发，Expect 负责单次 SSH 交互与远程命令。',
    '[SRC] while read ip pass; do /usr/bin/expect <<-EOF ... EOF; done < servers.txt 将每行参数注入 Expect；后台执行可配合 & 和 wait。Expect 内部通常 spawn ssh、处理 yes/no 和 password、等待提示符、发送命令、exit、expect eof。\n[OPS] IP/密码文件应限制权限，私钥优先于明文密码；StrictHostKeyChecking=no 会削弱主机身份校验。批量执行前先单机验证，限制并发，记录成功/失败主机，破坏性命令必须确认目标路径并审批。\n[VERIFY] 验证单机、认证失败、命令失败、并发收敛、退出码和结果日志。',
    ['SSH', 'Shell + Expect', 'while read', 'here document', 'ssh automation', 'wait'], 'HIGH'),
  entry('advanced-diagnosis', '函数、正则与 Expect 故障诊断', '29 / 高级故障诊断', '按语法、状态、匹配和交互层逐层定位高级 Shell 自动化问题。',
    '[OPS] 函数不工作：查定义、调用、参数、提前 return 和最后命令状态；grep 匹配不到：查实际输入、BRE/ERE/PCRE、转义、定位符、大小写和字段；Expect 卡住：查 spawn、实际提示、expect 模式、timeout、yes/no、password、远程提示符及 interact/eof 选择。链接异常：查目标存在、权限、inode 和跨文件系统。\n[VERIFY] 使用 bash -n 做语法检查、bash -x 观察路径，保留原始输出和最小复现；先只读诊断，再提出变更。',
    ['bash -n', 'bash -x', 'troubleshooting', 'regex debugging', 'Expect debugging', 'inode'])
]

export const shellAdvancedRules = Object.freeze([
  { id: 'SHELL-ADV-001', trigger: '函数化脚本', sequence: ['single responsibility', 'validate parameters', 'return status', 'caller checks $?'] },
  { id: 'SHELL-ADV-002', trigger: '正则匹配失败', sequence: ['inspect input', 'identify dialect', 'check escaping/anchors', 'test positive and negative cases'] },
  { id: 'SHELL-ADV-003', trigger: 'Expect 卡住', sequence: ['inspect actual prompt', 'check spawn', 'match yes/no/password', 'adjust timeout', 'choose interact or eof'] },
  { id: 'SHELL-ADV-004', trigger: '批量 SSH', sequence: ['single host test', 'protect credentials', 'limit concurrency', 'record per-host result', 'verify'] }
])
