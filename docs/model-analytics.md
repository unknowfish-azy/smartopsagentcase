# 模型强度与 Token 用量

## 入口与功能

侧栏「模型中心」包含模型接入、模型强度、用量与额度，桌面和移动导航均可进入。

- `/model-strength`：调用次数、成功率、成功调用平均完整响应耗时、待确认数，以及每日成功率和耗时折线图。
- `/token-usage`：输入 / 输出 / 总 Token 折线图、模型明细、按月保存或取消自设额度、已知剩余与超额提醒。
- `/model-health`：兼容旧链接，重定向到模型强度。

模型强度目前按实际调用表现实现，不提供未验证的能力评分或推理 effort 设置。可按月份、模型连接筛选。额度始终覆盖当月全部连接，不随模型筛选改变。额度是提醒预算，不是服务商余额，不限制请求。

## 统计口径

账本覆盖 `ModelConnectionService.invoke` 发起的调用，自功能启用开始记录，不回填旧记录，不包含绕过该入口的模型消耗。调用前写入 PENDING，返回非空回复视为 SUCCESS，异常或空回复视为 FAILED。成功率分母为已完成调用；pending 不算失败。耗时为成功请求的完整响应时间，不是首 Token 时间，也不是模型能力评测。

仅接受服务商 usage 中非负整数 `prompt_tokens`、`completion_tokens`、`total_tokens`。total 缺失且输入输出均有效时，推导其和。未上报字段保持 null，聚合只累加已知部分；未知总量调用和 pending 单独计数。无调用日过去日期用量为 0，未来日期留空；没有成功样本时成功率和耗时留空。孤立的有效样本显示点，缺失值不连线。图表数据表也显示真实零值。

日期统一使用 UTC；数据库 `started_at` 为 DATETIME，存 UTC 墙钟值，JDBC 使用 LocalDateTime，避免 JVM / MySQL session 时区改变日月归属。模型连接删除后保留账本，不保存 prompt、回复、Base URL 或密钥。

调用前无法写账本会阻止本次请求；调用成功但最终记账失败时保留 PENDING，不把已付费成功调用变成可重试错误。pending 也可能表示未完成或进程中断，不自动宣称失败。需运维排查此类记录。

## 后端部署

新增表定义：`backend/src/main/resources/db/model-analytics.sql`。默认启动时仅执行 `CREATE TABLE IF NOT EXISTS`，不会修改已有业务表。生产环境可先由迁移账户执行该 SQL，再设置 `smartops.model-analytics.initialize-schema=false`，让运行账户无需建表权限。若曾运行开发中的旧版 TIMESTAMP 账本，需要单独核对既有数据的时区语义后迁移；初始化脚本不会自动改列。

接口：

```text
GET /api/model-analytics?month=2026-09&connectionId=1
PUT /api/model-analytics/budget
{"month":"2026-09","tokenLimit":1000000}
```

tokenLimit 为 null 时取消该月额度，0 是有效额度，上限 1,000,000,000,000；小数、负数、溢出被拒绝。月份限定 2000-01 至 2100-12。

沿用项目已有 X-User-Id（默认 1）身份机制，尚未增加账户认证。内部调用仍需要现有内部令牌，不能向浏览器暴露内部令牌。H2 测试与模拟 API 浏览器测试不证明真实服务商连通性；启动新版后端并经可信 Runtime 调用后，统计页才有实际数据。

## 组件与技术栈适配

当前项目为 Vue 3 + Vite + Element Plus + JavaScript，已有 ECharts，不是 React / shadcn / Tailwind / TypeScript 项目。将所给线图的细线、横向网格、悬浮提示和主题样式适配为 `frontend/src/components/ui/v-chart-4.vue`，复用 ECharts，没有安装无法直接在 Vue 中挂载的 Recharts/React。组件接收日期、数据序列、单位和可选最大值；视图持有请求状态，无新 provider 或全局状态依赖。

UI 组件放 `frontend/src/components/ui/`，与项目既有 src 结构一致，方便集中复用；不在仓库根目录新建第二套 components。业务页面放 `frontend/src/views/model/`，全局样式和主题在 `frontend/src/assets/styles/{global,variables}.css`。页面 CSS 局部作用域，图表响应 ResizeObserver、主题和减少动态效果设置，无远程图片或新图标依赖。

若需另建 React 参考项目，以下为独立目录的初始化步骤（不要在当前 Vue frontend 内运行）：

```sh
npm create vite@latest react-chart-preview -- --template react-ts
cd react-chart-preview
npm install
npm install tailwindcss @tailwindcss/vite
npm install -D @types/node
```

在 `vite.config.ts` 添加 `tailwindcss()` 插件，并将 `@` alias 指向 `./src`；在根 tsconfig 和 tsconfig.app.json 的 compilerOptions 增加 `baseUrl: "."`、`paths: { "@/*": ["./src/*"] }`。入口 CSS 加入 `@import "tailwindcss";`，然后：

```sh
npx shadcn@latest init
npx shadcn@latest add chart
npm install recharts
```

在 components.json 将 ui alias 配为 `@/components/ui`，TSX 放 `src/components/ui`。官方配置参考：`https://ui.shadcn.com/docs/installation/vite`。以上仅为用户要求的 React 初始化说明，本次没有执行迁移。

## 验证

```sh
# frontend
npm test
npm run build
node test/model-analytics.browser.mjs
# backend
mvn -q -Dtest=ModelAnalyticsServiceTest,ModelAnalyticsControllerTest,ModelInvocationAnalyticsTest,ModelRuntimeSecurityTest,ModelProviderClientTest test
```

浏览器脚本使用受控模拟 API 检查 1440px / 375px、深浅主题、筛选和请求竞态、零额度与取消额度、保存失败、重新加载、空数据、接口异常及菜单跳转。后端测试覆盖真实 H2 持久化、用户/月/模型过滤、UTC 月界、未知字段、预算边界、调用记账顺序与失败处理，以及现有内部接口鉴权。
