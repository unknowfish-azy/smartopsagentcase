# 企业级系统管理（管理层）

参考 KOI-ADMIN（`http://127.0.0.1:5730/system/dept`，RuoYi 风格 RBAC），为 SmartOpsAgent 管理层（5174）补齐系统管理能力。

## 已落地的模块

| 模块 | 后端 | 前端 | 说明 |
| --- | --- | --- | --- |
| 部门管理 | `SysOrgService` | `admin/system/DeptView.vue` | parent_id 自引用树；删除有子部门/用户时 409；成环防护 |
| 岗位管理 | `SysOrgService` | `admin/system/PostView.vue` | 扁平字典，code 唯一；删除有用户的岗位 409 |
| 角色管理 | `SysRbacService` | `admin/system/RoleView.vue` | 数据权限 + 菜单授权（整树替换） |
| 菜单管理 | `SysRbacService` | `admin/system/MenuView.vue` | 三级：目录/菜单/按钮；成环防护 |
| 字典管理 | `SysDictService` | `admin/system/DictView.vue` | 类型 + 数据两级；数据级联删除 |
| 通知公告 | `SysNoticeService` | `admin/system/NoticeView.vue` | 草稿/发布分离 |
| 登录日志 | `SysLoginLogService` | `admin/system/LoginLogView.vue` | 成功/失败 + 来源 IP，接入 AuthController |
| 用户绑定 | `UserAccountService` | `AdminUsersView.vue` | 部门/岗位/RBAC 角色与账户打通 |

操作日志复用既有 `security_audit_event`，个人中心复用既有 `/account/security`。

## 用户与组织/RBAC 的打通

`UserAccountService.create/update` 新增 `deptId`、`postId`、`roleIds` 三个参数：

- `deptId`/`postId` 写入 `app_user` 的 `dept_id`/`post_id` 列，null 表示清除绑定；
- `roleIds` 写入 `sys_user_role`（先清后插，整树替换），重复自动去重；
- 未知部门/岗位/角色返回 400（不是静默忽略）；
- 账户列表 `AccountView` 返回 `deptId/postId/roleIds`，前端账户页展示部门/岗位，并用「组织」动作编辑绑定。

注意：`app_user.role`（admin/operator，决定登录入口）与 `sys_user_role`（RBAC 角色）是**两个独立概念**，本改动只增不改前者。



## 数据表（10 张新表 + 2 处加列）

`sys_dept` `sys_post` `sys_role` `sys_menu` `sys_user_role` `sys_role_menu`
`sys_dict_type` `sys_dict_data` `sys_notice` `sys_login_log`；
`app_user` 加 `dept_id/post_id/real_name/phone/email`，`security_audit_event` 加 `ip/detail`。

## 安全模型

- 所有接口位于 `/api/admin/system/**`，由既有 `hasRole("ADMIN")` + `AdminConfirmationFilter` 统一守卫；
- 非 GET 请求必须携带 `X-Admin-Password`（当前管理员密码），否则 403（实测验证）；
- 角色授权用「整树替换」，避免增量授权产生幽灵权限；
- 部门/菜单更新有成环防护（父级不能设为自己或后代）。

## 关键设计取舍

1. **跨模块不做硬外键**：`sys_user_role.user_id` 不建到 `app_user` 的 DB 外键——`app_user` 由另一脚本创建，Bean 初始化顺序不保证；跨模块用逻辑外键（RuoYi 惯例），删除用户时由应用层清理。
2. **`@DependsOn("userAccountSchema")`**：`SysAdminConfig` 的加列脚本依赖 `app_user`/`security_audit_event` 先建好。
3. **`dict_value` 而非 `value`**：`value` 是 H2 保留字，跨库改名避免兼容问题。

## 验证证据

- 后端全量 **444 通过 / 0 失败**（含 `SysRbacServiceTest` 6 项 + `AdminFoundationIntegrationTest` 15 项）；
- 前端 **392 通过**，`dist` + `dist-admin` 均构建成功；
- 系统管理端到端 15 项（部门树/岗位唯一/角色授权/菜单三级/字典/公告/登录日志）通过；
- 用户绑定端到端 9 项（创建带 dept/post/role 的账号、列表回显、未知部门/角色 400、清空绑定）通过；
- 真实 MySQL：10 张 `sys_*` 表 + `app_user` 5 个新列生效，测试残留清理为 0。

