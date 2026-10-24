// MySQL 8.0 installation, recovery and multi-instance pack from user material.
// Lab commands involving passwords, data deletion or forced termination are guarded.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: 'mysql80.' + id, domain: 'mysql', platform: 'CentOS Stream 9 / MySQL 8.0',
  service: 'mysql', type: 'MYSQL 8.0 KNOWLEDGE', title, section, summary,
  content, tags: ['MySQL', 'MySQL 8.0', ...tags],
  source: '用户提供的 MySQL 8.0 安装部署与多实例材料',
  version: '8.0.40 binary/glibc 教学场景', risk, executionAllowed: false
})

export const mysql80Entries = [
  entry('positioning', 'MySQL、关系型数据库与 NoSQL 边界', '01 / 基础',
    'MySQL 是关系型数据库，使用 SQL 和表/行/列；Redis、MongoDB 等属于不同数据模型。',
    '[SRC] 数据库提供结构化数据的增删改查；关系型数据库以二维表和表关系组织数据，MySQL/Oracle/DB2 等是示例；NoSQL 可用 Key-Value 或文档模型表示。\\n[OPS] 看到“数据库”先识别产品、服务包、数据模型和客户端，不把 mysql 与 mariadb 当作同一服务体系。',
    ['SQL', '关系型', 'NoSQL', 'Redis', 'MongoDB', 'MariaDB']),
  entry('install-methods', 'MySQL 8.0 安装方式与版本选择', '02 / 安装',
    'yum、binary/glibc、源码安装的复杂度和可定制性不同；教学环境固定 MySQL 8.0.40。',
    '[SRC] 课程使用 MySQL Community Server 8.0.40，二进制包为 mysql-8.0.40-linux-glibc2.17-x86_64.tar.xz。yum 简单，binary 需手工初始化，源码定制能力强但复杂。\\n[OPS] 先确认 OS、CPU 架构、GLIBC、安装来源和现有 MySQL/MariaDB；不要因“最新版本”自动替换已验证版本。',
    ['yum', 'binary', 'glibc', 'source', 'MySQL 8.0.40']),
  entry('binary-layout', 'Binary 部署目录、依赖与 mysql 用户', '03 / 初始化',
    'basedir 是程序目录，datadir 是数据目录；服务应使用专用 mysql 系统账号。',
    '[SRC] 示例 basedir=/export/server/mysql、datadir=/export/server/mysql/data、端口 3306、socket=/tmp/mysql.sock；依赖 dnf -y install libaio；账号 useradd -r -s /sbin/nologin mysql。\\n[OPS] 安装前确认目录、磁盘、owner/group 和 GLIBC；清理旧 MariaDB、删除 /etc/my.cnf 或 data 属于高风险变更，必须确认业务、备份和维护窗口。',
    ['basedir', 'datadir', 'libaio', 'useradd', 'mysql.sock'], 'APPROVAL_REQUIRED'),
  entry('initialize', 'mysqld 初始化与临时密码', '04 / 初始化',
    'mysqld --initialize 执行结束不等于初始化成功，必须检查日志和数据目录。',
    '[SRC] bin/mysqld --initialize --user=mysql --basedir=/export/server/mysql --datadir=/export/server/mysql/data 2>&1 | tee /tmp/mysqld.log；初始化后检查 data/mysql、performance_schema、redo/temp 文件，并从日志识别 temporary password。mysql_ssl_rsa_setup 可创建 SSL/RSA 文件。\\n[OPS] 临时密码是敏感凭据，不在回答中回显，不应长期保存在 /tmp 或公开脚本。初始化失败先查日志、目录权限、已有 data、磁盘和二进制兼容性，不直接删除 data 重来。',
    ['mysqld --initialize', 'temporary password', 'mysql_ssl_rsa_setup', 'SSL/RSA', 'mysqld.log'], 'APPROVAL_REQUIRED'),
  entry('systemd', 'systemd 管理 mysqld', '05 / 服务',
    '自定义 unit 通过 daemon-reload、start、status、enable 建立服务生命周期。',
    '[SRC] /etc/systemd/system/mysqld.service 可使用 User=mysql、Group=mysql、ExecStart mysqld --daemonize、PIDFile、ExecStop mysqladmin shutdown、Restart=on-failure。命令：systemctl daemon-reload；systemctl start/status/enable mysqld。\\n[OPS] 分三层验证：systemctl status mysqld → ss -lntp 检查 TCP 监听 → mysql -uroot -p 验证客户端。active 不代表监听正确，也不代表认证成功；停止、重启、启用均应结合变更风险。',
    ['systemd', 'mysqld.service', 'daemon-reload', 'PIDFile', 'Restart']),
  entry('config-socket', 'my.cnf、Unix Socket 与 ERROR 2002', '06 / 配置与连接',
    '本地 socket 路径和服务端配置必须一致；ERROR 2002 需要区分服务、socket 和客户端配置。',
    '[SRC] [mysqld] 可配置 basedir、datadir、socket=/tmp/mysql.sock、character_set_server=utf8、collation-server=utf8_unicode_ci。ERROR 2002 Cannot connect through socket 可能表示 mysqld 未启动、启动异常、socket 未生成或客户端路径不一致。\\n[OPS] 先执行 systemctl status mysqld；ls -l /tmp/mysql.sock；grep -n socket /etc/my.cnf；再检查日志和客户端实际默认 socket。不要仅凭 ERROR 2002 直接删除 socket 或重装。',
    ['my.cnf', 'socket', '/tmp/mysql.sock', 'ERROR 2002']),
  entry('auth-remote', 'ERROR 1045、user@host 与远程访问', '07 / 认证',
    '认证失败要区分用户名、Host、密码、认证方式和权限；远程访问还需要网络与监听。',
    '[SRC] mysql -uroot -p 为本地连接；mysql -h<host> -P3306 -u<user> -p 为远程连接；SELECT user,host FROM mysql.user 查看账号匹配。\\n[OPS] 远程四层条件：网络可达、TCP/3306 可达、mysqld 监听目标地址/端口、用户存在且允许对应 host。ERROR 1045 不一定只有密码错误；root@localhost 与 root@% 是不同匹配项。root@% 不应作为生产默认方案，优先专用账号和最小授权。mysql_secure_installation 用于减少默认暴露。',
    ['ERROR 1045', 'user@host', '3306', 'remote access', 'GRANT', 'mysql_secure_installation'], 'APPROVAL_REQUIRED'),
  entry('client-library', '客户端动态库依赖错误', '08 / 客户端',
    'libncurses.so.5/libtinfo.so.5 缺失属于客户端动态库问题，不直接等同于 mysqld 未启动。',
    '[SRC] 教学环境遇到 shared libraries 报错，并示例兼容软链接。\\n[OPS] 先检查 mysql --version、ldd <mysql-binary> 和实际库文件，确认 binary 与系统兼容性。不要把 /lib64/libncurses.so.6 到 .5 的软链接当作所有系统的安全通用修复；生产优先使用匹配的软件包或重新选择兼容构建。',
    ['libncurses', 'libtinfo', 'ldd', 'shared libraries']),
  entry('password-recovery', '忘记密码与 skip-grant-tables 风险', '09 / 恢复',
    '密码恢复需要维护窗口、备份和短暂绕过认证；恢复后必须立即回到正常启动。',
    '[SRC] 教学流程为停止 mysqld → mysqld_safe --skip-grant-tables & → 恢复认证 → 停止恢复模式 → 正常启动。& 是 shell 后台 job，$! 是 PID，%1 是 job 编号。\\n[OPS] 先确认本机、版本、数据备份、维护窗口和恢复路径；skip-grant-tables 会绕过认证，只能临时使用。优先 systemctl stop，避免把 pkill/kill -9 当第一选择；TERM 无效且数据风险已评估后才讨论更强制方式。密码不可写入脚本、日志或最终回答。',
    ['mysqld_safe', '--skip-grant-tables', 'kill', 'SIGTERM', 'SIGKILL'], 'HIGH'),
  entry('automation', 'Shell 安装自动化与日志证据', '10 / 自动化',
    '安装脚本应按依赖、文件、用户、初始化、配置、systemd、启动、认证阶段检查返回值。',
    '[SRC] $? 判断上一命令退出状态；-f 判断普通文件；xargs -r 避免无输入时执行；2>&1 合并 stderr/stdout；tee 保存初始化日志。\\n[OPS] &>/dev/null 会丢失失败证据，与“失败可分析”冲突。脚本应保留阶段日志、退出码和错误上下文，敏感密码不得进入日志或 /tmp 明文文件。rm -rf /etc/my.cnf、卸载 MariaDB、删除 data 必须单独审批。',
    ['$?', '-f', 'xargs -r', '2>&1', 'tee', '&>/dev/null'], 'APPROVAL_REQUIRED'),
  entry('multi-instance', 'MySQL 多实例：端口、socket、配置和资源', '11 / 多实例',
    '多实例是独立进程、数据目录、配置、socket、PID、日志和端口的组合；逻辑隔离不等于资源隔离。',
    '[SRC] 示例 mysql1 使用 /export/server/mysql1、3306、mysql1.sock、mysql1.cnf、mysqld1.service；mysql2 使用对应独立路径和 3307。每个实例独立初始化、配置、启动和验证。\\n[OPS] 连接时明确 -S socket 或 -h host -P port，避免连错库。Address already in use 先查 ss -lntp 端口；再查 pid-file、socket、datadir 是否互相覆盖。实例 1 正常不证明实例 2 正常；CPU、内存、磁盘 I/O 和 innodb_buffer_pool_size 还会产生主机级资源竞争。',
    ['multi-instance', '3306', '3307', 'mysql1.cnf', 'mysql2.cnf', 'socket', 'resource contention']),
  entry('diagnosis', 'MySQL 安装与连接证据链', '12 / 故障诊断',
    '按安装、初始化、服务、监听、socket/TCP、认证、授权、SQL 阶段定位，避免跨层猜测。',
    '[OPS] 安装失败：依赖/GLIBC → 包与解压 → mysql 用户与权限 → basedir/datadir 初始化 → my.cnf → systemd。连接失败：本地 socket 或远程 IP/TCP → mysqld 状态与监听 → user@host → 密码和权限。证据优先级：实际错误输出、systemctl、MySQL 日志、配置、进程/监听、客户端测试、用户描述。\\n典型错误：ERROR 2002 先查服务/socket；ERROR 1045 查 user@host/密码/认证；shared library 查 ldd/库兼容；Address already in use 查端口冲突。复验需要服务状态、监听和客户端连接。',
    ['ERROR 2002', 'ERROR 1045', 'Address already in use', 'evidence chain', 'troubleshooting'])
]

export const mysql80Rules = Object.freeze([
  { id: 'MYSQL-001', trigger: 'ERROR 2002 socket', sequence: ['mysqld status', 'socket path', 'my.cnf', 'error log'] },
  { id: 'MYSQL-002', trigger: 'ERROR 1045 access denied', sequence: ['user', 'host', 'password', 'authentication', 'privilege'] },
  { id: 'MYSQL-003', trigger: 'remote login failed', sequence: ['DNS/IP', 'network', 'TCP/3306', 'listen/bind', 'user@host', 'grant'] },
  { id: 'MYSQL-004', trigger: 'multi-instance one failed', sequence: ['instance cnf', 'datadir', 'logs', 'pid', 'socket', 'port', 'unit'] },
  { id: 'MYSQL-005', trigger: 'installation failed', sequence: ['dependency', 'package', 'mysql user', 'initialize', 'config', 'systemd', 'client'] }
])
