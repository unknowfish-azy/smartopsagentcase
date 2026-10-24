# 三工作台第一阶段基础版验收

本地执行记录：2026-10-03，Asia/Shanghai。对应设计与计划：`docs/superpowers/specs/2026-10-03-workbench-foundation-design.md`、`docs/superpowers/plans/2026-10-03-workbench-foundation.md`。

## 已实现

1. Harbor 配置与真实项目读取检查分离；状态分类、时间、五分钟过期、成功及失败 TraceId。只读制品分页包含 Tag、Digest、平台、大小、类型与推送时间；支持安全编码嵌套仓库，筛选明确限定当前页，切换目标屏蔽旧响应。
2. 695 条内置目录统一模型及确定性 Mini 快照，原有本地 Markdown 检索保留。页面提供多关键词加权、场景别名、命中原因、未核验标识及每页 30 条结果。构建前检查快照一致性，不增加搜索基础设施或第三方依赖。
3. 云原生四领域改为页内单层详情，复用安全 Markdown 渲染；环境、Context、Namespace 和参考时间保存在经校验的 URL 中。工具与知识库保留返回上下文；工具参数不会自动填充，需人工核对当前远程会话。
4. 新控件使用语义主题变量，浅深色同步；无新增生产写操作、后台轮询或外部模型请求。

## 验证证据

| 检查 | 结果 |
| --- | --- |
| 前端 `npm.cmd test` | 297 项通过，0 失败 |
| 后端 Maven `package`（包含全量测试） | 220 项，219 通过、1 跳过，0 失败/错误；打包成功 |
| 前端 `npm.cmd run build` | 成功，知识快照一致性检查通过 |
| 新浏览器验收：开发服务 | 375/1440px × 浅/深色均通过 |
| 新浏览器验收：生产预览 | 375/1440px × 浅/深色均通过 |
| 既有 Harbor 浏览器回归 | 未配置、项目/仓库读取及失败状态通过 |
| 本地新后端 | 已启动 PID 69648；`/actuator/health` 返回 `UP` |
| 新接口匿名访问 | 后端直连及 5173 代理的连接检查、制品接口均返回 HTTP 401 |

后端跳过项仍是 `MiniAssistantEngineTest` 的 Windows 符号链接场景。测试/打包使用本机 IntelliJ JBR 21，编译目标保持 Java 17，不修改系统 Java 设置。

新浏览器验收包含制品筛选、读取过期、认证失败、快速切换项目竞态、上下文跳转与再次确认、单层详情、知识分页和别名检索；使用模拟会话与 API，断言未发起写请求。浏览器页面无运行时错误；已人工查看浅色桌面 Harbor 和小屏云原生截图。

## 构建和日志

- `vendor-three` 仍为 519.71 kB / gzip 129.56 kB，原有警告保留，没有提高阈值。
- `MainLayout` JavaScript 44.42 kB / gzip 16.51 kB；云原生页面 10.71 kB，知识页面 17.97 kB（不含各自异步/公共依赖）。
- 日志：`test-artifacts/foundation-frontend-test.log`、`foundation-backend-package.log`、`foundation-build.log`、`foundation-browser.log`、`foundation-preview-browser.log`、`foundation-harbor-browser-regression.log`、`foundation-live-activation.log`，均位于 `test-artifacts/`。
- 截图：`frontend/test-artifacts/foundation-*.png`；启动日志：`.runtime/logs/backend-secure-20261003-005059-465.*.log`。

## 明确尚未完成的范围

- 未使用真实账号登录 Harbor 或集群；本次不以模拟结果宣称真实连接、镜像可拉取或业务健康。
- 本阶段仍复用管理员配置凭据的既有可见范围，没有新增逐用户项目 ACL；多租户生产部署前需单独完善授权映射。筛选不是跨页全局搜索。
- 知识正式审核发布、私有知识权限、向量检索、实时索引更新属于后续阶段；当前内置资料不宣称人工核验。
- 集群上下文只是显式意图，不是集群发现、权限证明或自动 Context 切换。五类诊断闭环、GitOps 审批与治理动作尚未启动。
- 未修改真实账号密码、连接配置或白名单；没有手工数据库变更。未提交、建分支、重置或清理已有工作区。
