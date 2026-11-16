-- T33c 显式登录接续（D2 最小版）：一人一会话，重登覆盖。
-- storage state 经 AES-256-GCM 加密落库；明文 Cookie/token 不落库、不进日志、不回前端。
CREATE TABLE IF NOT EXISTS web_render_session (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    enc_storage_state TEXT NULL,
    display_hint VARCHAR(64) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    last_used_at TIMESTAMP NULL,
    CONSTRAINT uq_web_render_session_user UNIQUE (user_id)
);
