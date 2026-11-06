-- SEC-11 残余：清洗整改前写入的明文敏感数据。
-- OperationRedactor 在应用层已对新数据脱敏，但存量行（operation_command /
-- operation_run_output / operation_run_evidence）可能仍含 PEM 私钥、Bearer token 等。
-- 本迁移用 MySQL 8.0 / H2 均支持的正则（\s 匹配空白、[\s\S] 匹配含换行的任意字符）做脱敏。
-- 匹配模式与 OperationRedactor.java 对齐：
--   1. PEM 私钥块（-----BEGIN ... PRIVATE KEY----- ... -----END ... PRIVATE KEY-----）
--   2. Bearer token（Bearer <token>）
-- 注意：assignment（KEY=VALUE）模式因误伤面大，不在此迁移批量处理，
-- 仅处理明确为机密的 PEM 与 Bearer。

-- 1) operation_command.command_text
UPDATE operation_command
SET command_text = REGEXP_REPLACE(
        command_text,
        '-----BEGIN [A-Z ]*PRIVATE KEY-----[\\s\\S]*?-----END [A-Z ]*PRIVATE KEY-----',
        '[REDACTED]')
WHERE command_text LIKE '%PRIVATE KEY%';

UPDATE operation_command
SET command_text = REGEXP_REPLACE(
        command_text,
        '(Bearer\\s+)[A-Za-z0-9._~+/=-]+',
        '$1[REDACTED]')
WHERE command_text REGEXP 'Bearer\\s+[A-Za-z0-9]';

-- 2) operation_run_output.stdout_text / stderr_text
UPDATE operation_run_output
SET stdout_text = REGEXP_REPLACE(
        stdout_text,
        '-----BEGIN [A-Z ]*PRIVATE KEY-----[\\s\\S]*?-----END [A-Z ]*PRIVATE KEY-----',
        '[REDACTED]')
WHERE stdout_text LIKE '%PRIVATE KEY%';

UPDATE operation_run_output
SET stdout_text = REGEXP_REPLACE(
        stdout_text,
        '(Bearer\\s+)[A-Za-z0-9._~+/=-]+',
        '$1[REDACTED]')
WHERE stdout_text REGEXP 'Bearer\\s+[A-Za-z0-9]';

UPDATE operation_run_output
SET stderr_text = REGEXP_REPLACE(
        stderr_text,
        '-----BEGIN [A-Z ]*PRIVATE KEY-----[\\s\\S]*?-----END [A-Z ]*PRIVATE KEY-----',
        '[REDACTED]')
WHERE stderr_text LIKE '%PRIVATE KEY%';

UPDATE operation_run_output
SET stderr_text = REGEXP_REPLACE(
        stderr_text,
        '(Bearer\\s+)[A-Za-z0-9._~+/=-]+',
        '$1[REDACTED]')
WHERE stderr_text REGEXP 'Bearer\\s+[A-Za-z0-9]';

-- 3) operation_run_evidence.content
UPDATE operation_run_evidence
SET content = REGEXP_REPLACE(
        content,
        '-----BEGIN [A-Z ]*PRIVATE KEY-----[\\s\\S]*?-----END [A-Z ]*PRIVATE KEY-----',
        '[REDACTED]')
WHERE content LIKE '%PRIVATE KEY%';

UPDATE operation_run_evidence
SET content = REGEXP_REPLACE(
        content,
        '(Bearer\\s+)[A-Za-z0-9._~+/=-]+',
        '$1[REDACTED]')
WHERE content REGEXP 'Bearer\\s+[A-Za-z0-9]';
