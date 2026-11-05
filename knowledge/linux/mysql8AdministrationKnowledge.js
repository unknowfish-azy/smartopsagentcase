// MySQL 8 数据服务管理知识包：参考 MySQL 8.0 官方文档与
// 开源运维手册，覆盖账号权限、备份恢复、复制、性能与安全加固。
export const mysqlAdminProvenance = Object.freeze({
  source: '开源参考资料：MySQL 8.0 Reference Manual、MySQL Community 文档',
  references: ['MySQL 8.0 Reference Manual', 'MySQL Backup and Recovery', 'MySQL Replication'],
  verification: '涉及备份、复制与参数变更的步骤必须在实验环境演练'
})

const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: 'mysql8.admin.' + id,
  domain: 'mysql', platform: 'MySQL 8.0', service: 'mysql-admin',
  type: 'MYSQL DATA SERVICE', title, section, summary, content,
  tags: ['MySQL 8.0', '数据服务管理', ...tags],
  source: mysqlAdminProvenance.source,
  version: 'MySQL 8.0.30+ 通用原则', risk, executionAllowed: false
})

export const mysql8AdminEntries = [
  entry('account-privilege', '账号、Host 匹配与最小授权', '01 / 账号权限',
    'MySQL 账号由 user@host 唯一确定；授权按数据库、表、列和例程粒度收敛，优先使用角色管理。',
    '[SRC] CREATE USER <user>@<host> IDENTIFIED BY ...；GRANT <priv> ON <db>.<table> TO <user>@<host>；REVOKE 收回权限；SHOW GRANTS FOR <user>@<host> 查看授权。MySQL 8.0 支持 CREATE ROLE 与 SET DEFAULT ROLE。mysql.user 中 user 与 host 共同构成账号匹配条件。\n[OPS] 禁止用 root@% 作为业务账号；按应用、环境和最小权限拆分账号。改权限前先导出当前授权，确认影响范围并保留回滚 SQL。Host 使用 localhost、具体网段或受控主机名，不要为了“能连上”直接放开所有来源。账号清理前检查是否有活动连接与定时任务依赖。',
    ['CREATE USER', 'GRANT', 'REVOKE', 'SHOW GRANTS', 'role', 'user@host', 'least privilege'], 'APPROVAL_REQUIRED'),
  entry('auth-plugin', '认证插件、密码策略与连接失败', '02 / 认证',
    'caching_sha2_password 是默认认证插件；客户端兼容性和密码策略会直接影响连接结果。',
    '[SRC] MySQL 8.0 默认 caching_sha2_password，旧客户端可能不支持；mysql_native_password 可兼容旧版本但安全性较低。ALTER USER ... IDENTIFIED WITH ... 可调整插件。validate_password 组件可配置长度、复杂度和字典策略。ERROR 1045 表示认证或授权失败，不等同于服务未启动。\n[OPS] 连接失败先区分网络、端口、服务、认证插件、密码和授权，再看客户端错误码。修改认证插件需要评估所有客户端与应用驱动，避免部分系统无法连接。密码轮换要有双写或灰度窗口，禁止把明文密码写入知识库、脚本或日志。启用密码策略前先确认业务账号批量重置流程。',
    ['caching_sha2_password', 'mysql_native_password', 'ERROR 1045', 'validate_password', 'ALTER USER'], 'APPROVAL_REQUIRED'),
  entry('backup-logical', 'mysqldump 逻辑备份与一致性', '03 / 逻辑备份',
    '逻辑备份需保证一致性；InnoDB 使用 --single-transaction，同时备份例程、触发器和事件。',
    '[SRC] 常用参数：mysqldump --single-transaction --routines --triggers --events --set-gtid-purged=OFF <db> > backup.sql；--single-transaction 为 InnoDB 提供一致性快照，不适合混合非事务引擎。恢复使用 mysql <db> < backup.sql。\n[VERIFY] 备份文件生成成功不等于可恢复，必须定期做恢复演练并校验表数量、行数和关键数据。\n[OPS] 备份要考虑字符集、时区、存储过程、DEFINER 和 GTID 语义。备份文件属于敏感数据，需加密、访问控制与保留策略。生产备份窗口、锁影响和 I/O 压力要提前评估；恢复前必须确认目标实例、库名和覆盖风险。',
    ['mysqldump', '--single-transaction', '--routines', '--triggers', 'restore drill'], 'APPROVAL_REQUIRED'),
  entry('backup-physical', '物理备份、Clone Plugin 与冷备边界', '04 / 物理备份',
    '物理备份复制数据文件，速度快但一致性要求高；运行中不能直接复制 datadir。',
    '[SRC] 物理备份可通过文件系统快照、企业版工具或 Clone Plugin 实现；Clone Plugin 支持本地或远程克隆实例数据。冷备要求停库后复制数据目录，并保证权限、配置和文件完整。\n[OPS] 直接拷贝运行中的 InnoDB 数据文件可能得到不一致副本；文件系统快照必须配合刷盘或数据库静默点。物理备份恢复要匹配版本、配置、redo/undo 与 binlog 状态，恢复后执行一致性检查。克隆会占用磁盘和网络，需评估容量与源库压力。任何覆盖式恢复都要先隔离旧数据并保留回滚副本。',
    ['physical backup', 'Clone Plugin', 'cold backup', 'snapshot', 'datadir'], 'HIGH'),
  entry('restore-drill', '恢复演练、校验与时间点恢复', '05 / 恢复',
    '恢复能力由演练证明；完整恢复需要备份、binlog 和一致的时间点，恢复后必须校验业务数据。',
    '[SRC] 恢复流程通常为：准备空实例或隔离环境 → 还原基础备份 → 按需回放 binlog → 校验库表与业务数据 → 切换流量。mysqlbinlog 可解析 binlog，按时间或位置回放。\n[OPS] 恢复前明确 RPO/RTO、目标时间点、允许丢失的数据范围和审批人。恢复环境要与生产隔离，避免误覆盖。校验至少包括表数量、行数、关键主键、索引与业务抽样查询。恢复后检查复制状态、定时任务、账号权限和应用连接配置。禁止在未备份当前数据的情况下直接覆盖生产库。',
    ['restore', 'mysqlbinlog', 'point-in-time recovery', 'RPO', 'RTO', 'validation'], 'HIGH'),
  entry('binlog', 'Binlog 格式、保留与安全', '06 / Binlog',
    'binlog 记录数据变更，用于复制和时间点恢复；格式、保留期和访问权限需要统一管理。',
    '[SRC] log_bin 开启二进制日志，binlog_format 常见为 ROW；expire_logs_days 或 binlog_expire_logs_seconds 控制保留；SHOW BINARY LOGS 查看文件，SHOW MASTER STATUS 查看当前位点。mysqlbinlog 可解析内容。\n[OPS] binlog 包含数据变更细节，属于敏感审计数据，访问权限要收敛。保留期过短会缩短可恢复窗口，过长会占用磁盘。删除 binlog 前确认复制消费位点与备份链完整性，不要手工 rm。格式变更需评估复制兼容性、工具解析和存储增长。开启 GTID 后位点语义变化，恢复与复制步骤要按 GTID 设计。',
    ['log_bin', 'binlog_format', 'ROW', 'expire_logs_days', 'SHOW BINARY LOGS', 'GTID'], 'APPROVAL_REQUIRED'),
  entry('replication', '主从复制、GTID 与延迟诊断', '07 / 复制',
    '复制依赖 binlog、复制账号和中继日志；GTID 简化位点管理，延迟要结合线程状态与业务时间线判断。',
    '[SRC] 复制账号需要 REPLICATION SLAVE 权限；CHANGE REPLICATION SOURCE TO 配置源端；START REPLICA 启动；SHOW REPLICA STATUS 查看 IO/SQL 线程、Last_Error 与延迟字段。GTID 模式下使用 gtid_executed 与 auto_position。\n[OPS] 复制延迟常见原因包括大事务、从库资源不足、网络、单线程回放和锁等待。不要只看单一延迟字段，要结合 Seconds_Behind_Source、Relay_Log 位点与业务读写时间。修复前先确认数据一致性，避免盲目跳过事务或重建复制。主从切换涉及数据校验、流量切换、只读设置和回滚，必须演练并审批。',
    ['replication', 'GTID', 'SHOW REPLICA STATUS', 'CHANGE REPLICATION SOURCE', 'replication lag'], 'HIGH'),
  entry('performance', '慢查询、EXPLAIN 与性能证据', '08 / 性能',
    '性能问题先用慢日志和 performance_schema 定位，再用 EXPLAIN 验证执行计划，不能凭感觉调参。',
    '[SRC] slow_query_log 与 long_query_time 记录慢查询；performance_schema 提供等待、语句和锁指标；EXPLAIN 查看访问类型、索引使用与扫描行数，EXPLAIN ANALYZE 提供实际执行时间。SHOW GLOBAL STATUS 查看连接、QPS、缓冲池命中。\n[OPS] 先固定时间范围、接口和影响范围，再对比执行计划、索引、数据量和资源。索引变更要评估写入放大、磁盘与回滚；参数调整要有基线、压测和观察窗口。禁止在生产直接做未验证的大表 DDL。优化后用 p95 延迟、错误率、扫描行数和业务指标复验。',
    ['slow_query_log', 'performance_schema', 'EXPLAIN', 'EXPLAIN ANALYZE', 'index', 'baseline'], 'APPROVAL_REQUIRED'),
  entry('innodb-transactions', 'InnoDB 事务、锁与死锁排查', '09 / 事务与锁',
    '事务隔离级别、锁粒度和执行顺序共同决定阻塞；死锁应分析等待图而不是直接杀会话。',
    '[SRC] InnoDB 支持事务与行级锁；常见隔离级别为 REPEATABLE READ。SHOW ENGINE INNODB STATUS 查看最近死锁与等待；performance_schema.data_locks、data_lock_waits 可查锁关系；information_schema.innodb_trx 查看活动事务。\n[OPS] 死锁排查要找出两个事务各自持有的锁、请求的锁、执行语句和业务顺序，优先通过调整访问顺序、缩短事务和索引优化解决。KILL 会话只能解除当前阻塞，不能防止复现，且可能造成业务中断。长事务会放大 undo、锁等待和复制延迟，需要监控与阈值。任何 kill、参数变更和结构变更都要审批并记录影响。',
    ['InnoDB', 'transaction', 'isolation', 'deadlock', 'data_locks', 'KILL session'], 'HIGH'),
  entry('security-hardening', '网络暴露、TLS 与安全基线', '10 / 安全',
    '数据库不应默认对公网开放；TLS、最小权限、审计和文件权限共同构成安全基线。',
    '[SRC] bind-address 控制监听地址；require_secure_transport 强制 TLS；ssl_ca/ssl_cert/ssl_key 配置证书；secure_file_priv 限制导入导出路径；local_infile 默认关闭。审计可通过审计插件或外部日志实现。\n[OPS] 先确认监听地址、防火墙/安全组、账号 Host 和 TLS 状态，再评估暴露面。关闭不必要的网络入口优于仅依赖密码。证书更新要验证客户端兼容性与到期监控。数据目录、备份文件和 binlog 的权限应限制到数据库账号与运维账号。安全加固变更需灰度、回滚和业务复验，禁止关闭 TLS 或放宽 Host 作为临时修复。',
    ['bind-address', 'require_secure_transport', 'TLS', 'secure_file_priv', 'audit', 'exposure'], 'HIGH'),
  entry('operations-evidence', '服务启停、升级与连接排障证据链', '11 / 运维证据',
    '数据库运维按服务、监听、认证、授权、SQL、资源与复制分层取证，避免跨层猜测。',
    '[OPS] 启动失败：systemctl status → 错误日志 → 配置语法 → datadir 权限与磁盘 → 端口冲突。连接失败：网络与端口 → 监听地址 → 认证插件与账号 Host → 密码与授权 → 连接数上限。性能异常：慢日志 → 执行计划 → 锁等待 → 资源与复制延迟。升级前记录版本、参数、账号、备份与回滚包，升级后验证连接、SQL、复制和业务。\n证据优先级：实际错误输出、数据库错误日志、systemctl、performance_schema、配置、监听与客户端测试。生产操作默认只读观察，重启、参数变更、DDL、恢复与切换必须审批、备份、验证和留痕。',
    ['systemctl', 'error log', 'connection chain', 'upgrade', 'evidence chain'], 'APPROVAL_REQUIRED')
]
