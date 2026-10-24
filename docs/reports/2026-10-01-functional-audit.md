# SmartOpsAgent 功能体检与优化建议

日期：2026-10-01。对象：当前工作区及本机运行实例。

## 结论

目前属于“基础服务在线、主要页面可展示、部分业务链路尚未打通”的开发版本，不宜直接作为多人生产系统或开放公网。

已确认两类业务阻塞：数据库缺表，以及前端聊天调用与内部认证边界不匹配。登录和权限目前仍是前端预览机制。不能用健康检查返回 UP、页面能打开或模拟接口测试通过代替业务验收。

本次未修改业务代码、数据库或真实远程主机。新增本报告，保留测试日志和诊断截图。未调用真实收费模型。浏览器诊断使用独立测试上下文，不改用户日常浏览器中的登录和历史记录。

## 一、检查范围和结果

| 范围 | 实测结果 | 限制 |
| --- | --- | --- |
| 前端 5173 | HTTP 200 | 当前是开发服务器 |
| 后端 8080 | Actuator UP | 不代表所有业务表、认证配置正常 |
| AI 服务 8001 | `/api/health` UP | 该接口只返回固定服务状态，未验证模型/RAG依赖 |
| MySQL | Actuator 数据库校验 UP | 日志确认仍缺业务表；独立全库表清单未完成 |
| Redis | Actuator UP，直接 PING 得到 PONG | 未做负载或故障恢复测试 |
| 页面巡检 | 24 个桌面入口 + 12 个移动端/主题场景，共 36 次 | 未发现页面级 JS 异常或文档级横向溢出；仍有遮挡和对比度问题 |
| 前端全量单元/源码测试 | 225 项：223 通过，2 失败 | 部分测试是源码字符串断言，不是完整交互验证 |
| Java 后端测试 | 89 项全部通过 | 测试环境使用 H2，不代表运行中的 MySQL 已完成迁移 |
| Python 选定测试 | 89 项全部通过 | 覆盖 agent、knowledge、inspector、training、model security；有 pytest 缓存目录警告 |
| 聊天与桌宠浏览器测试 | 首轮 16 项：15 通过，1 失败 | 桌宠菜单出现一次 2px 位置差异；隔离重跑该项 3 次均通过，仍应追踪稳定性 |
| 可观测查询浏览器脚本 | 通过 | 使用模拟接口，覆盖未配置、预设、空结果和错误清理 |
| Harbor 浏览器脚本 | 原脚本失败 | 错误提示实际存在；诊断确认失败来自 alert 的可访问名称定位方式 |
| 前端生产构建 | 通过 | 主包 2147.99 kB，gzip 677.94 kB；模型分析包 503.50 kB，有体积警告 |

桌面巡检入口：`/`、`/chat`、`/servers`、`/inspector`、`/inspector/statistics`、`/agent`、`/agent/trace`、`/knowledge`、`/knowledge/review`、`/plugins`、`/skills`、`/connections`、`/harbor`、`/cloud-native`、`/tools/processes`、`/tools/prometheus-query`、`/tools/loki-log-query`、`/tools/harbor-browser`、`/operations/runs`、`/model-settings`、`/model-strength`、`/token-usage`、`/admin`、`/architecture`。

## 二、已确认问题与优先级

### P0：上线前必须解决的身份与权限问题

**现象与证据**

- 在隔离浏览器中填写不存在的账号和任意非空密码，选择管理员后可以进入 `/admin`。登录过程没有发出后端认证请求。
- `frontend/src/views/auth/LoginView.vue:131` 的 submit 直接写入 localStorage；角色由表单选择。
- `frontend/src/router/index.js` 的守卫检查本地预览标记和本地角色。
- `backend/src/main/java/com/smartops/config/SecurityConfig.java:45` 对一般 `/api/**` 放行。服务器列表、模型连接列表等接口实测无需用户认证即可读取。
- 多个业务控制器信任客户端 `X-User-Id`，未提供时默认为 1，例如 `OperationSessionController.java:20`。

**影响**：界面的“管理员/运维用户”目前不是可靠的权限边界，历史记录的本地账号区分也不能代替服务器数据隔离。

**建议**：接入真实登录、服务端身份和权限校验，用户 ID 从可信认证上下文取得；管理角色不能由登录者自行选择；增加未登录、普通用户越权、跨账号读取的负向测试。在此之前限制为可信本地开发使用。

### P1：数据库缺表导致连接中心和知识审核不可用

**实测**

- `/api/operations/sessions`：HTTP 200，但业务 `code=500`。
- `/api/knowledge/candidates`：HTTP 200，但业务 `code=500`。
- 后端日志明确指出 `smartops.operation_session` 和 `smartops.knowledge_candidate` 不存在。
- 浏览器中的连接中心、知识候选审核均显示加载失败。
- 当前实例运行的是 dev profile；仓库存在相关建表脚本，但不能据此认为数据库已执行迁移。

**建议**：先备份，再核对现有 schema 与版本化迁移，补齐缺失表及关联表；统一启动前数据库预检。不要直接删库重建，也不要把表缺失显示成“暂无数据”。

**验收**：两条列表接口返回成功数组；连接会话保存、刷新恢复、知识候选列表和详情通过真实 MySQL 的集成测试。

相关位置：`backend/src/main/resources/db/local-schema.sql`、`backend/src/main/java/com/smartops/mapper/OperationSessionMapper.java`。

### P1：真实聊天调用被内部认证配置阻塞

**实测与代码路径**

- 模型连接列表可读取，当前有 2 条连接；这不代表模型可以调用。
- 对不存在模型 ID 0 的 runtime/invoke 进行安全探测，均在认证层返回 HTTP 503：`Internal authentication is not configured`，没有触发真实模型调用。
- `frontend/src/stores/aiChat.js:109` 通过浏览器直接调用 `/api/model-connections/{id}/invoke`。
- `InternalTokenAuthenticationFilter.java:35` 将 runtime/invoke 视为内部接口；第 56 行在内部 Token 未配置时返回 503。前端调用没有提供该内部凭据。

**根因**：不仅是缺一个配置，还存在“用户聊天接口复用了服务间内部接口”的边界问题。仅在后端填入 Token，现有浏览器请求仍会因缺少内部凭据而被拒绝。

**建议**：提供受用户鉴权的聊天入口，由服务端调用模型服务；内部 Token 仅用于可信服务间调用。不要把内部 Token 写入前端，也不要以全局关闭认证作为修复。

**验收**：先用本地模型替身覆盖真实 HTTP 链路，再由用户确认后进行少量真实模型验收；覆盖未配置、无权限、超时、额度不足等情况。

### P1：浅色模式仍有低对比度，主导航仍遮挡其他页面

**实测**

- 1440px、主菜单展开时，知识库、连接中心、插件中心的标题左边界为 x=168，主菜单右边界为 x=272；点击命中检查确认标题被导航覆盖。
- AI 对话页已经单独避让，但其他页面还没有统一处理。
- 连接中心浅色模式的“选择一个连接开始工作”实际颜色为 `rgb(220,229,233)`，位于白色工作区；错误提示和若干标题也仍使用深色界面的浅色文字。
- `ConnectionsView.vue:1023` 等样式写死颜色；页面同时混用黑色侧面板与白色主体。

**建议**：统一主布局展开/收起时的内容占位，避免逐页特判；连接中心把文字、边框、表单、状态统一改用语义主题变量。终端内容可以保留独立深色，但应与外围操作面板区分。

**验收**：1440/1024/768/375px 下按钮可点、标题无遮挡；双主题检查错误提示、禁用态、焦点态、弹层，而不只检查背景。

相关位置：`frontend/src/layouts/MainLayout.vue:163`、`frontend/src/views/operations/ConnectionsView.vue:43`、`:1023`。

### P1：管理台存在看起来可用、实际无动作的按钮

`frontend/src/views/admin/AdminControlCenterView.vue:9` 的四个管理入口按钮没有点击处理或路由。实测“用户与权限”按钮点击后无页面跳转、弹窗或请求。

**建议**：实现真实入口；尚未实现的明确标为“规划中”并禁用，给出说明。登录页“安全/就绪”、侧栏固定 ONLINE 等状态也应区分静态描述与实时检测结果。

### P1：监控和镜像仓库处于未配置状态

- `/api/observability/sources`：Prometheus、Loki 均 `configured=false`。
- `/api/harbor/status`：`configured=false`、`credentialsConfigured=false`。
- `/api/servers` 返回空数组，没有可用于真实资产监控验收的服务器。
- 远程能力接口标记 SSH/SFTP 支持，其余 9 种协议需要后续原生适配；本次没有真实 SSH/SFTP 环境可用于验证连接、文件传输和隧道。

**建议**：提供统一“接入检查”页，按未配置、已配置、可达、鉴权失败、无数据区分状态。先接入一台受控测试服务器和只读监控/仓库账号，再验收数据流。不能把示例视图当作已完成外部集成。

### P2：接口失败被包装为 HTTP 200，掩盖业务故障

`backend/src/main/java/com/smartops/exception/GlobalExceptionHandler.java:17` 等处理器返回错误对象但没有相应 HTTP 状态。实测缺表时即为 HTTP 200 + `code=500`。

**建议**：统一 HTTP 与业务错误语义，补充 Trace ID 和用户可操作提示；增加业务就绪检查，检查关键表、内部认证和必需依赖。现有 Actuator UP 只能证明有限依赖检查成功。

### P2：测试与质量门禁存在失真

- `cloud-engineering-tools.test.mjs:18` 仍要求旧版云原生侧栏子入口，而当前云原生/Harbor 已调整为独立工作台。
- `operations-process-tool.test.mjs:22` 精确匹配旧 v-if 字符串；当前增加了 `!isHarborBrowser`，仍保留禁止进程诊断执行的条件。
- Harbor 脚本用 `getByRole('alert', { name: 'Harbor 不可达' })` 查找文本；实际 alert 存在但没有该可访问名称。仅在临时诊断中改为按提示文本定位后，错误状态及旧结果清理得到验证，源测试未修改。
- 桌宠菜单在并行运行浏览器与构建时出现一次 2px 几何差异，隔离重试 3 次通过。建议记录布局稳定时机，区分 ResizeObserver 更新与真实 hover 位移，不能简单放宽断言掩盖回归。
- 部分浏览器脚本写死 5173、5174、5180，不具备统一运行入口。
- `frontend/package.json:10` 的 lint 和 typecheck 实际都只对 `whaleQuality.js` 做 `node --check`，不是全项目 lint/类型检查。

**建议**：优先修正过期断言，增加真实 MySQL 迁移和用户聊天边界测试；统一测试地址和只读/模拟/真实集成分组；建立全项目质量检查。测试报告应明确 mock 范围，避免“所有测试通过”的误导性结论。

### P2：性能与多账号持久化还有优化空间

- 生产主包约 2.15 MB，gzip 约 678 kB；建议按重型组件、图表和知识数据拆分加载，区分首页必需资源与后续路由资源。
- 现有聊天历史按用户保存在浏览器；插件和 Skill 仍使用固定 localStorage 键，账号切换后的工作区隔离策略不一致。
- 聊天当前自动选取第一条启用模型连接，没有显式模型选择；记录仅本地保存，清除网站数据即丢失。未提供流式输出、停止生成和会话导出。

**建议**：先统一账号/工作区存储契约和错误提示；再增加模型选择、停止生成、导出/导入。只有明确需要跨设备时才建设服务器会话存储，避免一次引入过多复杂度。

## 三、建议执行顺序与验收目标

1. **恢复业务可用性**：数据库迁移预检、修复连接/知识审核缺表、正确划分用户聊天与内部模型接口。
2. **补齐上线安全门槛**：真实身份认证、服务端角色授权、可信用户 ID；任何外网或多人正式使用之前完成。
3. **消除误导和界面阻碍**：主导航占位、连接中心双主题、静态管理按钮、实时状态与规划状态区分。
4. **验证一条真实闭环**：受控测试服务器 → 只读采集 → 分析 → 审批边界 → 验证 → 运行记录 → 知识候选。真实执行和模型费用须单独确认。
5. **巩固质量与体验**：稳定全量测试、完善业务就绪检查、拆包，再迭代聊天增强和跨设备需求。

不建议此时优先扩大功能入口或继续堆叠视觉效果；优先让已有关键入口可用、状态可信、权限可控。

## 四、证据与未覆盖范围

- 前端测试：`.runtime/logs/audit-frontend-tests.log`。
- 后端测试：`.runtime/logs/audit-backend-tests.log`。
- Python 测试：`.runtime/logs/audit-python-tests.log`。
- 页面结果：`.runtime/logs/audit-pages.json`。
- 聊天/桌宠首轮：`.runtime/logs/audit-chat-pet-browser.log`。
- 构建：`.runtime/logs/audit-frontend-build.log`。
- 运行时缺表错误：`.runtime/logs/backend.out.log`。
- 示例截图：`test-artifacts/audit-1440-light-_connections.png`。

未验证：真实收费模型回复质量和计费、真实远程主机写操作、实际 SSH/SFTP/隧道、已接入 Prometheus/Loki/Harbor 的端到端数据、备份恢复、长期稳定性、并发压力、外部依赖漏洞扫描。页面巡检不是所有按钮和所有分支的穷举验证。独立 MySQL 表清单探测因 Python 驱动缺失未完成；缺失的两张表由真实接口及后端 SQL 错误确认。
