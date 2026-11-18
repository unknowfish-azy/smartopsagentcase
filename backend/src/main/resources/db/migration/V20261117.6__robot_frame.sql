-- 机器人视觉数据资产：关键帧落盘登记表
--
-- 背景：M2 视觉巡检只把关键帧放在内存里（RobotFrameService.latestFrames），
-- 帧不落盘 → 没有样本资产 → 无法做数据蒸馏、标注、YOLO 训练。
-- 本表登记每张已归档关键帧的元数据，实际图片文件落在 smartops.robot.frame-archive.dir。
--
-- 设计要点：
-- 1) sha256 + device_key 唯一：同一设备重复回传同一张图只记一次（天然去重）；
-- 2) file_path 存相对路径，迁移目录时不用改库；
-- 3) target 保留巡检目标，蒸馏时可据此分层抽样；
-- 4) distilled_at 由 Python 蒸馏脚本回写，避免后端耦合训练侧逻辑。

CREATE TABLE robot_frame (
    id BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    device_key VARCHAR(64) NOT NULL,
    target VARCHAR(128) NULL,
    file_path VARCHAR(512) NOT NULL,
    sha256 CHAR(64) NOT NULL,
    bytes INT NOT NULL,
    width INT NULL,
    height INT NULL,
    quality VARCHAR(16) NULL,
    simulated TINYINT(1) NOT NULL DEFAULT 0,
    captured_at TIMESTAMP NOT NULL,
    distilled_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_frame_sha_device (sha256, device_key),
    KEY idx_frame_device_time (device_key, captured_at),
    KEY idx_frame_target (target)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
