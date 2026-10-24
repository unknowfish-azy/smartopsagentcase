// DataGrip and MySQL SQL core pack from user-provided teaching material.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: 'mysql.sql.' + id, domain: 'mysql', platform: 'MySQL / DataGrip',
  service: 'mysql-sql', type: 'MYSQL SQL KNOWLEDGE', title, section, summary,
  content, tags: ['MySQL', 'SQL', 'DataGrip', ...tags],
  source: '用户提供的 DataGrip 与 MySQL SQL 核心知识材料',
  version: 'Reference pack', risk, executionAllowed: false
})

export const mysqlSqlEntries = [
  entry('datagrip-connection', 'DataGrip 连接 MySQL 的分层链路', '01 / DataGrip',
    'DataGrip 是数据库客户端；驱动、网络、3306、mysqld、user@host、密码和权限必须逐层满足。',
    '[SRC] DataGrip 需要 MySQL Driver，并填写 Host/IP、Port、User、Password、Database。教学账号示例为 root@%（生产不推荐）。\\n[OPS] 连接失败按 DataGrip 驱动 → DNS/IP → 网络 → TCP/3306 → mysqld 监听 → 远程账号 → 密码/权限排查。ping 通不等于 3306 通，3306 通不等于登录成功，连接失败也不等于 SQL 有问题。服务端只读证据：ss -nltp | grep 3306；SELECT user,host FROM mysql.user。',
    ['driver', 'remote connection', '3306', 'user@host', 'SELECT user,host']),
  entry('sql-categories', 'SQL 四大分类：DDL、DML、DQL、DCL', '02 / SQL 基础',
    'DDL 定义结构，DML 修改记录，DQL 查询数据，DCL 控制用户与权限。',
    '[SRC] DDL 包含 CREATE、ALTER、DROP；DML 包含 INSERT、UPDATE、DELETE；DQL 核心为 SELECT；DCL 用于 CREATE USER、GRANT 等账号权限控制。SQL 语句通常以分号结束，可换行缩进；MySQL 关键字大小写通常不影响语义，但方言和标识符规则需确认。\n[OPS] 生成 SQL 前先识别数据库类型、对象、SQL 分类和副作用；不同数据库方言不能默认完全兼容。',
    ['DDL', 'DML', 'DQL', 'DCL', 'CREATE', 'ALTER', 'DROP', 'SELECT']),
  entry('database-table', 'MySQL Database、Table、Field、Row 模型', '03 / 对象结构',
    'MySQL DBMS 包含多个 Database；Database 包含 Table；Table 由字段和记录组成。',
    '[SRC] SHOW DATABASES 查看数据库；CREATE DATABASE IF NOT EXISTS db_lhp DEFAULT CHARACTER SET utf8 创建；USE db_lhp 选择上下文；SELECT DATABASE() 查看当前数据库。表操作包括 SHOW TABLES、DESC table、SHOW CREATE TABLE table。\n[OPS] 创建表失败先确认当前数据库；表或字段不存在先查 SHOW TABLES、DESC、SHOW CREATE TABLE，不凭记忆改 SQL。DROP DATABASE/DROP TABLE 会破坏结构和数据，必须确认目标、环境和备份。',
    ['database', 'table', 'field', 'row', 'SHOW DATABASES', 'USE', 'DESC'], 'APPROVAL_REQUIRED'),
  entry('types-constraints', '字段类型与约束设计', '04 / 表结构',
    '类型按范围、精度和长度选择；主键、唯一、非空、默认、外键共同约束数据。',
    '[SRC] 数值包括 INT、TINYINT、FLOAT、DOUBLE、DECIMAL；字符串包括 CHAR、VARCHAR、TEXT；日期包括 DATE、TIME、DATETIME、TIMESTAMP；ENUM 从预定义值中选一个。DECIMAL(10,2) 适合金额，TINYINT UNSIGNED 可表示 0~255。\n约束包括 PRIMARY KEY（唯一非空，通常一个表一个）、UNIQUE（可多个）、NOT NULL、DEFAULT、FOREIGN KEY；AUTO_INCREMENT 常用于主键但删除中间 ID 不会保证序列连续。\n[OPS] INSERT 失败按 PRIMARY KEY、UNIQUE、NOT NULL、ENUM、类型范围和精度定位。',
    ['INT', 'TINYINT', 'DECIMAL', 'VARCHAR', 'TEXT', 'DATE', 'ENUM', 'PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY', 'AUTO_INCREMENT']),
  entry('alter-table', 'ALTER TABLE 与结构变更风险', '05 / DDL',
    'ADD、CHANGE、MODIFY、DROP 字段和 RENAME TABLE 都改变结构，需先确认表和兼容性。',
    '[SRC] ALTER TABLE t ADD field TYPE；ADD ... FIRST/AFTER；CHANGE old new TYPE 同时改名和类型；MODIFY field TYPE 主要改类型；DROP field 删除列；RENAME TABLE old TO new。\n[OPS] DDL 可能锁表、破坏依赖或丢失列数据。先 SHOW CREATE TABLE、评估外键/应用依赖和备份，再分阶段执行并复验 DESC 与 SHOW CREATE TABLE。DROP COLUMN、DROP TABLE、DROP DATABASE 标记为高风险。',
    ['ALTER TABLE', 'ADD', 'CHANGE', 'MODIFY', 'DROP', 'RENAME TABLE'], 'APPROVAL_REQUIRED'),
  entry('dml-safety', 'INSERT、UPDATE、DELETE 与高风险检查', '06 / DML',
    'DML 修改记录；UPDATE/DELETE 执行前先用相同条件 SELECT 预览目标集。',
    '[SRC] INSERT 支持指定字段、默认值和批量 VALUES；UPDATE 使用 SET 与 WHERE；DELETE FROM table WHERE condition；TRUNCATE 清空整表且不支持 WHERE，材料中归为 DDL。\n[OPS] UPDATE/DELETE 省略 WHERE 可能影响整表，TRUNCATE、DELETE FROM table、DROP 属于破坏性操作。标准流程：确认数据库/表 → SELECT * FROM table WHERE condition 预览 → 备份或审批 → 执行 → SELECT 复验。不要把密码写入 SQL、脚本或日志。',
    ['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'WHERE', 'dry-run'], 'APPROVAL_REQUIRED'),
  entry('select-filter', 'SELECT、WHERE、LIKE、NULL 与别名', '07 / DQL',
    'DQL 从表读取数据，WHERE 过滤原始记录；LIKE、IN、BETWEEN 和 IS NULL 处理常见条件。',
    '[SRC] SELECT fields FROM table；DISTINCT 去重；比较运算符 =、!=、<>、>、<、>=、<=；BETWEEN、IN、AND/OR/NOT；LIKE 中 % 表示任意数量字符、_ 表示一个字符；AS 给字段或表达式起别名。\n[OPS] NULL 不能用 = NULL，必须 IS NULL/IS NOT NULL。执行失败先确认当前数据库、表名、字段名、字段类型和分号。查询中的 price+10 只改变结果表达式，不修改原始数据。',
    ['SELECT', 'WHERE', 'LIKE', 'IN', 'BETWEEN', 'NULL', 'IS NULL', 'DISTINCT', 'AS']),
  entry('aggregate-group', '聚合函数、GROUP BY 与 HAVING', '08 / 聚合查询',
    'COUNT、SUM、AVG、MAX、MIN 汇总多行；WHERE 先过滤，GROUP BY 分组，HAVING 过滤分组结果。',
    '[SRC] COUNT(*) 统计记录，COUNT(column) 主要统计非 NULL；SUM 求和；AVG 平均；MAX/MIN 极值；ROUND 可保留小数。SELECT gender, COUNT(*) FROM student GROUP BY gender；分组结果可用 HAVING COUNT(*) > 1 过滤。\n[OPS] GROUP BY 时 SELECT 字段要么出现在 GROUP BY，要么被聚合函数包裹。原始行过滤使用 WHERE，统计结果过滤使用 HAVING。GROUP BY 查询异常先检查分组字段、聚合字段和 SQL mode。',
    ['COUNT', 'SUM', 'AVG', 'MAX', 'MIN', 'ROUND', 'GROUP BY', 'HAVING']),
  entry('order-limit', 'ORDER BY、LIMIT 与分页/Top N', '09 / 结果集',
    'ORDER BY 决定排序，LIMIT 限制返回数量；“第几名”必须有稳定排序。',
    '[SRC] ORDER BY price ASC/DESC；多字段排序按前一字段相同后再比较下一字段；LIMIT M,N 中 M 是偏移量、N 是数量；分页 offset=(current_page-1)*page_size；Top N 常用 ORDER BY score DESC LIMIT N。\n[OPS] 没有 ORDER BY 时 LIMIT 结果顺序不应被当作稳定排名。分页故障检查当前页、每页大小、offset、limit 和排序字段；第二名示例 LIMIT 1,1 依赖明确排序。',
    ['ORDER BY', 'ASC', 'DESC', 'LIMIT', 'pagination', 'Top N']),
  entry('troubleshooting', 'DataGrip 与 SQL 执行故障证据链', '10 / 故障诊断',
    'SQL 失败按数据库、对象、语法、类型、约束、权限和数据阶段定位。',
    '[OPS] 标准流程：确认 MySQL 与当前数据库（SELECT DATABASE()）→ 确认表/字段（SHOW TABLES、DESC、SHOW CREATE TABLE）→ 识别 DDL/DML/DQL/DCL → 检查分号、方言、类型、WHERE、GROUP BY/HAVING/ORDER BY 顺序 → 检查约束和权限 → 执行 → 用 SELECT/SHOW 复验。\nDataGrip 连接错误先排连接层，再看 SQL。UPDATE/DELETE 先 SELECT 目标集；INSERT 对照约束；GROUP BY 检查非聚合字段；分页检查排序。证据优先于“重新执行”。',
    ['SQL troubleshooting', 'SHOW TABLES', 'DESC', 'SHOW CREATE TABLE', 'SELECT DATABASE()', 'constraint error'])
]

export const mysqlSqlRules = Object.freeze([
  { id: 'SQL-001', trigger: 'DataGrip cannot connect', sequence: ['driver', 'IP/DNS', 'network', 'TCP/3306', 'mysqld', 'user@host', 'password', 'privilege'] },
  { id: 'SQL-002', trigger: 'UPDATE or DELETE', sequence: ['database/table', 'SELECT target set', 'WHERE', 'approval', 'execute', 'verify'] },
  { id: 'SQL-003', trigger: 'INSERT constraint error', sequence: ['PRIMARY KEY', 'UNIQUE', 'NOT NULL', 'DEFAULT', 'ENUM', 'type/range'] },
  { id: 'SQL-004', trigger: 'GROUP BY result/error', sequence: ['group fields', 'aggregate fields', 'WHERE before grouping', 'HAVING after grouping'] },
  { id: 'SQL-005', trigger: 'pagination or ranking', sequence: ['ORDER BY', 'page size', 'offset formula', 'LIMIT', 'stable result'] }
])
