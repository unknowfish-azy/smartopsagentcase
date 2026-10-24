-- ============================================================
-- 企业级系统管理：部门 / 岗位 / 角色 / 菜单 / 字典 / 公告 / 登录日志
-- ============================================================
-- 参考 KOI-ADMIN（RuoYi 风格 RBAC）补齐管理层能力。
-- 设计原则：
--   1. 操作日志复用既有 security_audit_event（不新造日志表）；
--   2. 部门用 parent_id 自引用树，删除受保护（有子部门或用户时 RESTRICT）；
--   3. 角色-菜单、用户-角色是多对多，权限标识 perms 采用 system:module:action 三段式；
--   4. 所有实体带 sort 排序、status 启停，符合企业化惯例（软删除而非物理删除）。
-- 幂等：CREATE TABLE IF NOT EXISTS；app_user / security_audit_event 的加列由
-- Java 侧先探测再执行（H2/MySQL 无通用 ADD COLUMN IF NOT EXISTS）。

-- 部门：自引用树
CREATE TABLE IF NOT EXISTS sys_dept (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    parent_id BIGINT NOT NULL DEFAULT 0,
    name VARCHAR(64) NOT NULL,
    sort INT NOT NULL DEFAULT 0,
    leader VARCHAR(32),
    phone VARCHAR(32),
    status TINYINT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sys_dept_parent (parent_id)
);

-- 岗位：可被多个部门/用户复用
CREATE TABLE IF NOT EXISTS sys_post (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(64) NOT NULL,
    sort INT NOT NULL DEFAULT 0,
    status TINYINT NOT NULL DEFAULT 1,
    remark VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 角色：RBAC 核心
CREATE TABLE IF NOT EXISTS sys_role (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    code VARCHAR(64) NOT NULL UNIQUE,
    sort INT NOT NULL DEFAULT 0,
    data_scope TINYINT NOT NULL DEFAULT 1,
    status TINYINT NOT NULL DEFAULT 1,
    remark VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 菜单/权限：type 1=目录 2=菜单 3=按钮
CREATE TABLE IF NOT EXISTS sys_menu (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    parent_id BIGINT NOT NULL DEFAULT 0,
    name VARCHAR(64) NOT NULL,
    type TINYINT NOT NULL DEFAULT 2,
    path VARCHAR(200),
    component VARCHAR(200),
    perms VARCHAR(200),
    icon VARCHAR(64),
    sort INT NOT NULL DEFAULT 0,
    visible TINYINT NOT NULL DEFAULT 1,
    status TINYINT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sys_menu_parent (parent_id)
);

-- 用户-角色 多对多
-- 注意：不建到 app_user 的数据库外键 —— app_user 由另一脚本创建，Bean 初始化顺序
-- 不保证先于本脚本；跨模块用逻辑外键（RuoYi 惯例），删除用户时由应用层清理绑定。
CREATE TABLE IF NOT EXISTS sys_user_role (
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_user_role_role FOREIGN KEY (role_id) REFERENCES sys_role(id) ON DELETE CASCADE
);

-- 角色-菜单 多对多
CREATE TABLE IF NOT EXISTS sys_role_menu (
    role_id BIGINT NOT NULL,
    menu_id BIGINT NOT NULL,
    PRIMARY KEY (role_id, menu_id),
    CONSTRAINT fk_role_menu_role FOREIGN KEY (role_id) REFERENCES sys_role(id) ON DELETE CASCADE,
    CONSTRAINT fk_role_menu_menu FOREIGN KEY (menu_id) REFERENCES sys_menu(id) ON DELETE CASCADE
);

-- 字典类型
CREATE TABLE IF NOT EXISTS sys_dict_type (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    type VARCHAR(100) NOT NULL UNIQUE,
    status TINYINT NOT NULL DEFAULT 1,
    remark VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 字典数据
CREATE TABLE IF NOT EXISTS sys_dict_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    type VARCHAR(100) NOT NULL,
    label VARCHAR(100) NOT NULL,
    dict_value VARCHAR(100) NOT NULL,
    sort INT NOT NULL DEFAULT 0,
    status TINYINT NOT NULL DEFAULT 1,
    remark VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sys_dict_data_type (type),
    CONSTRAINT fk_sys_dict_data_type FOREIGN KEY (type) REFERENCES sys_dict_type(type) ON DELETE CASCADE
);

-- 通知公告：type 1=通知 2=公告，publish 通过 published_at 控制
CREATE TABLE IF NOT EXISTS sys_notice (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    type TINYINT NOT NULL DEFAULT 1,
    status TINYINT NOT NULL DEFAULT 1,
    publisher_id BIGINT,
    publisher_name VARCHAR(64),
    published_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sys_notice_type (type, status)
);

-- 登录日志：记录成功与失败，含来源 IP
CREATE TABLE IF NOT EXISTS sys_login_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT,
    username VARCHAR(64) NOT NULL,
    ip VARCHAR(64),
    status TINYINT NOT NULL DEFAULT 1,
    message VARCHAR(255),
    login_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sys_login_log_time (login_at),
    INDEX idx_sys_login_log_username (username)
);
