# 模型接入中心

入口：侧栏「模型中心 → 模型接入」，路由 `/model-settings`。

## 实现与目录

当前项目是 Vue 3 + Vite + Element Plus，使用 JavaScript 和主题 CSS，并非 React / shadcn / Tailwind / TypeScript 项目。本次将提供的 Integration Card 布局、节点和连线动画适配成 Vue，不混入无法由 Vue 挂载的 TSX 或重复的 React 运行时。

- 可复用卡片：`frontend/src/components/ui/integration-card.vue`。UI 目录集中存放与页面无关的组件，也与参考组件的职责划分对应。
- 业务卡片和表单规则：`frontend/src/components/model/`。
- 页面：`frontend/src/views/model/ModelSettingsView.vue`。
- 全局样式：`frontend/src/assets/styles/global.css`，主题变量：同目录 `variables.css`。
- 本次使用已有 Element Plus 图标、弹窗和 CSS 动画，无新增 npm 依赖或远程图片请求。

## 可用功能

连接的新增、修改、启停和删除使用已有 `/api/model-connections` 接口。搜索支持名称、服务商标识和模型 ID，也可按启用状态过滤。上方图展示前六个已保存连接，其余连接仍显示在完整列表中。启用连线只表示配置状态，不代表调用成功。

测试操作通过 `POST /api/model-connections/{id}/invoke` 发送用户填写的 prompt，展示返回文本、浏览器测得的请求耗时，以及服务商返回的 total_tokens（若有）。请求超时比连接配置多预留 5 秒，避免 HTTP 客户端默认 15 秒超时提前终止长请求。测试不自动触发，不执行模型返回的命令，可能产生服务商用量费用。

当前后端仅实现兼容 Chat Completions 的协议，自动在 Base URL 后追加 `/chat/completions`。服务商字段是标识，不是协议适配器。其他原生协议需要兼容网关；未新增原生 Claude 等协议支持或模型自动发现功能。

首次创建需要 API Key；编辑时留空保留原密钥。列表仅显示脱敏值，密钥不写入浏览器持久存储，关闭配置弹窗后清空输入值。服务端沿用既有加密存储。

## 验证

- `npm test`：表单校验、更新负载和筛选测试，以及原有项目测试。
- `node test/model-integrations.browser.mjs`：在 1440px / 375px、深浅主题下使用受控模拟 API 验证增删改、筛选、测试请求、错误状态与密钥处理。
- `npm run build`：生产构建。

浏览器模拟测试不等于真实模型连通性验证。实际使用需要启动后端、配置存储与加密配置，并提供可用的服务地址和模型凭据。现有 `/invoke` 接口受内部令牌保护；浏览器没有该令牌时，测试调用会被拒绝。不要把内部令牌放入前端或为此关闭鉴权。真实调用由可信内部 Runtime 发起。

模型健康旧地址现在转到实际调用统计 `/model-strength`；Token 统计与自设额度在 `/token-usage`。统计范围和部署说明见 `docs/model-analytics.md`。
