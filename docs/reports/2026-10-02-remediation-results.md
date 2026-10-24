# 体检整改交付记录

日期：2026-10-02（本机时间）。依据用户确认的体检方案，完成首批关键业务、安全边界和可见性整改；未把后续外部集成与增强功能计为完成。

## 已落地

1. **数据库**：备份后增量补齐运维会话、运行记录、知识候选、账号等表；迁移有版本及 SHA256 记录。重复执行先备份，校验一致后跳过，不重建已有数据。真实接口恢复成功，原有两条模型连接保留。
2. **真实身份**：账户存 MySQL，密码 BCrypt，HttpOnly / SameSite=Lax 会话 Cookie；登录轮换会话 ID 和 CSRF。取消本地存储鉴权与自选管理员；服务端分配 admin/operator。普通用户不能调用账户管理或修改服务器资产。
3. **身份边界**：业务控制器取可信会话用户，不能通过 X-User-Id 冒充其他账号。模型连接和远程会话按账号归属。服务器资产、巡检记录仍属共享工作区，不宣称实现多租户隔离。
4. **聊天调用**：浏览器使用 `/api/chat/connections/{id}/invoke`，不再调用内部令牌接口。未登录/缺 CSRF 被拒绝；不存在或不属于自己的模型返回 404，且不触达模型服务商。内部调用继续要求独立凭据。
5. **终端会话**：WebSocket 使用登录身份；开发环境 HTTP 与 WebSocket 统一走同源代理，避免 localhost 与 127.0.0.1 混用丢失 Cookie。退出、会话销毁或 ID 轮换时关闭关联终端连接；登记与每帧处理时还会复核实时 HTTP 会话，覆盖握手期间退出的竞态。
6. **可见性**：非工具页展开主导航时为内容预留宽度；连接中心补齐浅色面板、输入框、标题、协议和状态文字；管理台账户入口和接入检查接上真实接口，审计入口跳转运行记录。
7. **错误与状态**：业务异常返回对应 HTTP 状态；关键表纳入健康检查。管理台区分“未配置”和“已配置但未验证连通性”，移除固定在线的误导性标签。

## 使用方式

- 前端：`http://127.0.0.1:5173/login`；后端仅监听 `127.0.0.1:8080`。
- 初始账号为 `admin`，随机密码只在本机 `.runtime/secrets/bootstrap.env` 的 `SMARTOPS_BOOTSTRAP_PASSWORD` 字段中，不在报告或聊天中复述。
- 该文件仅在空账户表首次启动时引导创建管理员；修改此文件不会重置已有账户密码。当前只支持创建账号，密码重置、禁用、细粒度权限等生命周期管理仍需后续实现。
- `.runtime/` 被 Git 忽略，但不等于磁盘加密。应妥善保管引导凭据和数据库备份，限制本机文件访问，不向仓库提交。
- 进入管理台可创建真实用户、检查数据库与外部接入配置。聊天历史仍保存在对应账号的浏览器本地，不会自动跨设备同步。

### 数据库迁移

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/windows/migrate-local.ps1
```

脚本从本机 `.env` 读取 MySQL 凭据，使用本机 MySQL 8 工具，备份成功且非空后才迁移。首次迁移前备份：`.runtime/backups/smartops-20261002-002023-466.sql`。

重复执行验证备份：`.runtime/backups/smartops-20261002-010206-554.sql`；结果为 `Migration already applied with matching checksum`。本轮没有执行备份恢复演练。

### 构建与重启

```powershell
cd backend
mvn.cmd -s .mvn/smartops-settings.xml -o -Dmaven.compiler.fork=false package
cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/windows/restart-local-backend.ps1
cd frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

需要 Java 17、MySQL、Redis；首次构建未缓存依赖时去掉 Maven 的 `-o`。后台重启脚本先确认端口进程属于本项目，再替换服务；运行使用 `.runtime/backend/` 中的独立 JAR 副本，避免 Windows 锁定构建产物。旧副本保留，不自动递归清理。

开发模式忽略旧 `VITE_API_BASE_URL`，走 Vite 同源 `/api`、`/ws` 代理。正式部署应同源反向代理并支持 WebSocket Upgrade；外网必须配置 HTTPS、`SMARTOPS_SECURE_COOKIE=true`、精确来源策略、密钥管理及独立安全审查，不能直接把本地开发服务暴露公网。

## 验证证据

最终本机复核：5173（前端）、8080（后端）、8001（AI 服务）、3306（MySQL）、6379（Redis）端口在监听；后端 `/actuator/health` 与 AI 服务 `/api/health` 均返回 HTTP 200 / UP。服务进程存活不代表外部数据源或内部服务联动已完成验收。

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 前端单元/契约测试 | 229 项通过 | `.runtime/logs/remediation-frontend-tests.log` |
| 后端测试 | 100 项通过，0 失败、0 错误 | `.runtime/logs/remediation-backend-package.log` |
| 前端生产构建 | 成功，仍有大 chunk 警告 | `.runtime/logs/remediation-frontend-build.log` |
| 后端打包 | 成功 | `.runtime/logs/remediation-backend-package.log` |
| 桌宠、聊天历史、Harbor、监控页面回归 | 19 项通过，涉及外部数据的请求为测试替身 | `.runtime/logs/remediation-browser-regression.log` |
| 真实登录与布局浏览器验收 | 伪造本地身份被拒、错误/正确密码、会话轮换、CSRF、可信用户 ID、缺表恢复、模型保留、终端握手/退出、Cookie 重放、桌面/移动端双主题 | `.runtime/logs/remediation-real-session.log` |

真实登录浏览器脚本为 `frontend/test/session-security.browser.mjs`；只读本机业务数据，不创建测试账户，不执行 SSH，不调用真实模型。它读取本机引导凭据；在不同环境可用 `SMARTOPS_TEST_URL` 设置入口，但需匹配账号与模型数据基线。

独立代码复核提出的终端握手/退出竞态已通过三项失败测试复现，随后修复并纳入全量回归；失败证据 `.runtime/logs/remediation-terminal-race-red.log`，用例 `OperationsTerminalSecurityTest`。没有通过放宽断言处理该问题。

截图位于 `frontend/test-artifacts/remediation-admin-light.png`、`frontend/test-artifacts/remediation-connections-light.png` 及对应深色/移动端文件。验证了文字颜色、标题不被主导航覆盖、375px 无页面横向溢出；不代表所有控件已做完整无障碍认证。

工作区原先已有大量未提交改动，本次未重置、未提交。全局 `git diff --check` 仍提示原有桌宠文件末尾空行；本批新增核心文件无新增空白错误。此前 Python 体检结果不作为本批重新运行的证据。

## 下一步建议（未执行）

1. **P1：真实集成验收**。提供受控测试主机以及 Prometheus/Loki/Harbor 的只读地址和凭据，逐项验证“连接—读取—审批—记录”。服务间内部令牌当前未配置，对应内部接口按设计拒绝调用，需统一配置各服务后再验收联动。
2. **P1：账户生命周期**。补充改密/重置/禁用、登录事件审计、账户及资源更细的授权；正式多人使用前开展独立渗透和权限检查。
3. **P2：质量门禁与性能**。统一历史浏览器脚本端口与运行入口；建立覆盖全项目的 lint/typecheck，拆分图表、知识数据等大包。当前命名为 lint/typecheck 的脚本不等于全量检查。
4. **P2：聊天增强**。显式模型选择、流式输出、停止生成、导入导出；有跨设备需求后再建设服务端历史。插件/Skill 本地存储的账号隔离也需统一。
5. **P2：长期运行验证**。备份恢复、并发、超时、会话失效、断线恢复和依赖漏洞扫描。

本轮没有收费模型调用、真实远程写操作、端到端外部监控/仓库联调、压力测试或生产环境验收；不能据此声称“所有功能完全可用”。
