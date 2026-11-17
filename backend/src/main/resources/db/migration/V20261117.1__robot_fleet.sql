-- 巡检机器人 M0：设备台账、命令审计、自主任务三张表。
-- 设计依据：docs/architecture/巡检机器人详细设计.md 第 2.1 节。
-- 遥测不入库（内存快照），此处仅持久化档案/审计/任务。

CREATE TABLE robot_device (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  device_key    VARCHAR(64)  NOT NULL UNIQUE COMMENT '业务主键，如 robot-car-01',
  name          VARCHAR(128) NOT NULL,
  form_factor   VARCHAR(16)  NOT NULL COMMENT 'CAR / SPIDER / DOG / ROBOT',
  capabilities  JSON         NOT NULL COMMENT '["MOVE","PTZ","MIC","SPEAKER","CAMERA","LIDAR"] 子集',
  transport     JSON         NOT NULL COMMENT '{"type":"BLE","mac":"AA:BB:CC:DD:EE:FF","protocolId":"generic-ble-car-v1"}',
  status        VARCHAR(16)  NOT NULL DEFAULT 'OFFLINE' COMMENT 'OFFLINE/IDLE/AUTONOMOUS/HUMAN_CONTROL/E_STOP/FAULT',
  enabled       TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '新设备默认禁用，显式启用后才可控制（fail-closed）',
  firmware      VARCHAR(64)  NULL,
  last_seen_at  DATETIME     NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT '巡检机器人设备档案';

CREATE TABLE robot_command_log (
  id           BIGINT PRIMARY KEY AUTO_INCREMENT,
  device_key   VARCHAR(64) NOT NULL,
  mode         VARCHAR(16) NOT NULL COMMENT 'AUTONOMOUS / HUMAN_CONTROL',
  op           VARCHAR(16) NOT NULL COMMENT 'MOVE/PTZ/SPEAK/CAPTURE/PATROL/STOP',
  params       JSON        NULL,
  accepted     TINYINT(1)  NOT NULL COMMENT '白名单/钳位校验结果',
  reject_code  VARCHAR(32) NULL COMMENT '拒绝规则码，不回显内部细节',
  operator     VARCHAR(64) NULL COMMENT '用户名或 brain:planId',
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_rcd_device_time (device_key, created_at)
) COMMENT '命令审计（M1 起写入，M0 仅建表）';

CREATE TABLE robot_task (
  id           BIGINT PRIMARY KEY AUTO_INCREMENT,
  device_key   VARCHAR(64) NOT NULL,
  plan_id      VARCHAR(64) NULL COMMENT 'agent 包 DAG 计划 ID，断点续跑复用',
  route        JSON NOT NULL COMMENT '[{"x":0,"y":0,"theta":0,"actions":["CAPTURE"]}]',
  status       VARCHAR(16) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/RUNNING/PAUSED/DONE/FAILED/CANCELLED',
  progress     INT NOT NULL DEFAULT 0 COMMENT '已完成路点数',
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_rt_device_status (device_key, status)
) COMMENT '自主态巡检任务（M3 起写入，M0 仅建表）';
