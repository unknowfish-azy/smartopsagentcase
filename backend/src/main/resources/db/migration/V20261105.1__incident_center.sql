-- ============================================================
-- P0-01 事件 / 工单中心（Incident / Ticket Center）
-- ============================================================
-- 设计目标：
--   把告警、AI 分析、审批、执行和复盘统一成一次故障处理闭环。
--
-- 状态机：OPEN -> ACK -> MITIGATING -> RESOLVED -> CLOSED
--   - OPEN       新建，未确认
--   - ACK        已确认（有人接单）
--   - MITIGATING 处置中
--   - RESOLVED   已解决，待关闭（关闭时必须填写根因与复盘）
--   - CLOSED     已关闭
--
-- 原则：
--   1. 不改动既有表；既有 sentinel_alert.ticket_id 引用本 incident.id。
--   2. 所有状态流转必须写入 incident_event 时间线，不可修改。
--   3. incident_relation 统一关联告警、Agent Run、知识条目、执行证据。
-- 全部语句幂等，可由 Flyway / ResourceDatabasePopulator 重复执行。

-- 1) 事件 / 工单主表
CREATE TABLE IF NOT EXISTS incident (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  title               VARCHAR(200) NOT NULL,
  description         TEXT         NULL,
  status              VARCHAR(16)  NOT NULL DEFAULT 'OPEN',
  severity            VARCHAR(4)   NOT NULL DEFAULT 'P3',
  priority            VARCHAR(4)   NOT NULL DEFAULT 'P3',
  source              VARCHAR(24)  NOT NULL DEFAULT 'MANUAL',
  category            VARCHAR(64)  NULL,
  tags                VARCHAR(500) NULL,
  reporter_id         BIGINT       NULL,
  assignee_id         BIGINT       NULL,
  related_asset_id    BIGINT       NULL,
  related_asset_type  VARCHAR(32)  NULL,
  related_service     VARCHAR(128) NULL,
  sla_target_minutes  INT          NULL,
  sla_deadline        DATETIME     NULL,
  acknowledged_at     DATETIME     NULL,
  mitigated_at        DATETIME     NULL,
  resolved_at         DATETIME     NULL,
  closed_at           DATETIME     NULL,
  root_cause          TEXT         NULL,
  resolution          TEXT         NULL,
  postmortem          TEXT         NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_incident_status (status, severity, created_at),
  KEY idx_incident_assignee (assignee_id, status),
  KEY idx_incident_reporter (reporter_id, created_at),
  KEY idx_incident_sla (sla_deadline, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2) 事件时间线（状态流转、评论、系统记录；不可修改）
CREATE TABLE IF NOT EXISTS incident_event (
  id           BIGINT       NOT NULL AUTO_INCREMENT,
  incident_id  BIGINT       NOT NULL,
  at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actor_id     BIGINT       NULL,
  kind         VARCHAR(32)  NOT NULL,
  detail       VARCHAR(1000) NULL,
  PRIMARY KEY (id),
  KEY idx_incident_event_incident (incident_id, at),
  CONSTRAINT fk_incident_event_incident FOREIGN KEY (incident_id) REFERENCES incident (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3) 事件关联（告警、Agent Run、知识条目、执行证据等）
CREATE TABLE IF NOT EXISTS incident_relation (
  id            BIGINT       NOT NULL AUTO_INCREMENT,
  incident_id   BIGINT       NOT NULL,
  relation_type VARCHAR(32)  NOT NULL,
  ref_id        BIGINT       NOT NULL,
  ref_type      VARCHAR(32)  NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_incident_relation (incident_id, relation_type, ref_id),
  KEY idx_incident_relation_ref (relation_type, ref_id),
  CONSTRAINT fk_incident_relation_incident FOREIGN KEY (incident_id) REFERENCES incident (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
