-- ============================================================
-- OPS-15：安全与配置报告接入（Trivy / kube-bench / Falco）
-- ============================================================
-- 原则：
--   1. 每条报告必须带工具、工具版本、扫描范围、目标、起止时间与结果摘要，缺少任何一项都拒绝入账；
--   2. finding_key = sha256(tool|target|ruleId|location)，由服务端计算，跨报告去重；
--   3. 每条观察记录都保留 first_seen_at / last_seen_at / seen_count / last_report_id，去重不等于丢弃次数；
--   4. 修复复测必须引用"同工具同目标且更新"的报告，报告里仍存在则 REOPENED，不存在才 FIXED；
--   5. 例外必须写明到期时间与理由，到期后自动转 EXPIRED，不无限期静默。
-- 全部语句幂等。

CREATE TABLE IF NOT EXISTS security_scan_report (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  report_ref      VARCHAR(128) NOT NULL,
  tool            VARCHAR(32)  NOT NULL,
  tool_version    VARCHAR(64)  NOT NULL,
  scope           VARCHAR(200) NOT NULL,
  target          VARCHAR(200) NOT NULL,
  started_at      DATETIME     NOT NULL,
  finished_at     DATETIME     NOT NULL,
  source_ref      VARCHAR(256) NULL,
  content_sha256  VARCHAR(64)  NOT NULL,
  finding_count   INT          NOT NULL,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_security_report (user_id, report_ref),
  KEY idx_security_report_target (user_id, target, finished_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS security_finding (
  id                BIGINT       NOT NULL AUTO_INCREMENT,
  user_id           BIGINT       NOT NULL,
  finding_key       VARCHAR(64)  NOT NULL,
  tool              VARCHAR(32)  NOT NULL,
  rule_id           VARCHAR(256) NOT NULL,
  title             VARCHAR(512) NULL,
  severity          VARCHAR(16)  NOT NULL,
  target            VARCHAR(200) NOT NULL,
  location          VARCHAR(512) NULL,
  image_digest      VARCHAR(128) NULL,
  asset_id          VARCHAR(200) NULL,
  status            VARCHAR(16)  NOT NULL,
  first_seen_at     DATETIME     NOT NULL,
  last_seen_at      DATETIME     NOT NULL,
  seen_count        INT          NOT NULL,
  last_report_id    BIGINT       NOT NULL,
  exception_until   DATETIME     NULL,
  exception_reason  VARCHAR(512) NULL,
  fixed_at          DATETIME     NULL,
  verified_at       DATETIME     NULL,
  updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_security_finding (user_id, finding_key),
  KEY idx_security_finding_state (user_id, status, severity),
  KEY idx_security_finding_target (user_id, target)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 报告与命中的关联：修复复测需要"这份新报告里到底还有没有这条命中"。
CREATE TABLE IF NOT EXISTS security_report_finding (
  id           BIGINT      NOT NULL AUTO_INCREMENT,
  report_id    BIGINT      NOT NULL,
  finding_key  VARCHAR(64) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_security_report_finding (report_id, finding_key),
  KEY idx_security_report_finding_key (finding_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
