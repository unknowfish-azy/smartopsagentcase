# 普通用户注册与管理员安全加固

日期：2026-10-02。用户已确认在双入口基础上开放普通账号注册，管理员更严格准入；不恢复任意凭据登录。

## 使用方式

1. 打开 `http://127.0.0.1:5173/login?portal=user`，点击「注册普通账号」。
2. 账号使用3–64位字母、数字、点、下划线或短横线；普通密码至少12字符，UTF-8不超过72字节，两次密码须一致。
3. 注册成功返回用户登录页，使用新账号登录。数据存入MySQL，密码为BCrypt哈希，不保存明文、不因服务重启清空。
4. 公开注册只能产生operator账户，不开放管理员注册；账号名`1`与密码`1`均不符合本轮规则，不存在可绕过认证的默认凭据。

## 管理员变化

- 账户管理增加「普通账号注册」开关，保存于registration_policy；已有用户不受关闭注册影响。
- 创建/启停/授权/重置账号、撤销会话、变更注册开关，必须再次输入当前管理员密码，并同时通过原CSRF与权限校验。表单退出/提交后清空复核密码，不将其保存到浏览器。
- 新建或修改管理员密码至少16字符；既有管理员原密码未重置。普通账号提升管理员后先改密，再访问管理业务。
- 管理入口会话空闲10分钟、用户入口30分钟。管理员账号无论选择哪个入口，账号级登录限额都为5次/15分钟；普通账号为10次/5分钟。
- 当前密码复核与自助改密共用账号级限额，管理员5次/15分钟；成功验证重置对应计数。注册每IP5次/10分钟，全局100次/分钟，IP已限流请求不占全局预算。
- 审计增加REGISTER、REGISTRATION_POLICY、ADMIN_VERIFY，只记录元数据。

## 安全复核

限定复核发现并修复了三项Important，主线程另修复一个相关旁路；均有失败回归证据：

- 原始URI前缀检查可被编码路径绕过：使用同一个MVC路径匹配器做授权与管理复核；真实服务也验证了`/api/%61dmin/registration`缺失二次密码返回403。
- 单个已限流IP仍扣全局注册额度：调整为先IP再全局，105次同来源请求不会封锁另一来源注册。
- 数据库认为等价的用户名却进入不同限流桶：先做IP防护，再按数据库返回的稳定账号ID限流，跨入口共享；H2集成中模拟数据库等价别名映射进行回归，不将其声称为完整MySQL排序规则实测。
- 自助改密可作为无限猜测当前密码的旁路：改密与管理员复核共用验证计数，切换用户入口无效。

修复后独立限定复核无未关闭Critical/Important。该结论仅覆盖本轮增量，不等于整个工作区或公网生产系统的全面安全验收。

## 验证结果

- 后端137项测试通过，零失败/错误，package成功；其中注册安全集成21项，覆盖真实H2写入、哈希、重新建立会话登录、并发重复账号、注册开关和权限边界。
- 前端247项单测通过，生产构建成功。保留既存大于500kB的bundle提示，未宣称构建零警告。
- 隔离注册/管理员确认浏览器流程通过；注册重载回用户登录、注册关闭、重复/弱密码/确认不一致、403/429、确认头和密码清空均有覆盖。
- 管理界面78项视觉/手机操作断言通过；原有聊天历史、桌宠、Harbor目录、可观测入口19项浏览器回归通过。
- 迁移脚本3项测试通过；三项迁移幂等复跑均校验和一致。
- 新后端部署后真实会话检查通过：原管理员登录、CSRF、两入口权限、原有2条模型连接、退出终端关闭与旧Cookie拒绝。
- 真实注册UI四张375/1440深浅截图、真实管理20张截图通过，无页面异常；未向真实数据库创建测试账号或修改用户密码，仅正常登录退出产生审计。
- 后端健康`/actuator/health`、AI健康`/api/health`均为UP；匿名注册策略实测enabled=true，12/16/72参数正确。

## 部署与证据

- 新增迁移 `backend/src/main/resources/db/migration/V003__registration_policy.sql`，没有修改已应用迁移。
- 迁移前备份 `.runtime/backups/smartops-20261002-132310-688.sql`；幂等复跑备份 `.runtime/backups/smartops-20261002-132503-621.sql`。
- 后端使用Java17由隐藏重启脚本加载，部署日志 `.runtime/logs/backend-secure-20261002-132413-287.*.log`。
- 后端绿灯 `.runtime/logs/registration-backend-package.log`；红灯 `registration-security-red.log`、`registration-review-red.log`、`registration-password-bypass-red.log`（同目录）。
- 前端 `.runtime/logs/registration-frontend-tests.log`、`registration-frontend-build.log`、`registration-browser.log`、`registration-admin-browser.log`、`registration-browser-regressions.log`。
- 隔离截图 `frontend/test-artifacts/registration-security/`，真实注册截图 `frontend/test-artifacts/registration-real/`，真实管理截图 `frontend/test-artifacts/admin-real/`。
- 凭据仍在本机被忽略的私有文件中；报告不包含密码、令牌或Cookie。

## 当前边界

注册开放、密码复核不等于MFA。当前为单节点内存限流，重启清空计数；账号、注册开关与审计在数据库持久化。公网部署还应单独验收TLS、共享限流/会话、网络访问策略、账号找回与MFA。邮箱/短信验证、找回密码、自动管理员注册本轮未提供，避免未接入服务被伪装成可用功能。
