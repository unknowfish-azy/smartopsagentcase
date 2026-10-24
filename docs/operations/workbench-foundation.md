# Harbor、知识库与云原生工作台：第一阶段操作说明

## Harbor 只读工作台

入口为 `/harbor`，工具中的 Harbor 浏览器复用同一组件。

- 配置状态与真实读取检查分离。`GET /api/harbor/status` 仅报告配置布尔值；`GET /api/harbor/connection-check` 使用既有实例和凭据尝试读取第一页项目，返回状态、时间和查询 TraceId。
- `READABLE` 只证明当次项目读取成功，不代表扫描器、复制任务或所有 Harbor 组件健康。五分钟后界面标记过期；计时器只更新显示，不发起后台探测。
- 认证、授权、证书、超时、网络、限流和响应格式错误独立分类，不展示上游原始响应或密码。失败检查同样提供审计 TraceId（配置不完整、未发起请求时除外）。
- 项目 → 仓库 → 制品。制品接口为 `GET /api/harbor/projects/{project}/artifacts?repository={relativeRepository}&page=1`。仓库参数不含项目名前缀；嵌套仓库使用 Harbor 所需的双重路径编码，不接收任意 URL。
- 显示 Tag、Digest、平台、类型、大小和推送时间；缺少平台明确显示未返回。仓库和制品筛选仅针对当前页，不伪装成全仓搜索。
- 目标切换及组件离开后，晚返回请求不能更新当前结果。响应受既有 1 MiB、连接 3 秒、读取 5 秒上限约束，不跟随重定向。
- 本阶段未实现扫描/SBOM/签名验证、删除、保留规则变更或多实例管理。当前数据仍是后端所配凭据的可见范围，不等同于已经完成逐用户项目 ACL；多租户部署前需要单独接入授权映射。

## 统一知识来源

既有 JS 知识包不做人工重写。`knowledgeModel.js` 规范化条目身份、内容、来源、版本与核验状态；`knowledgeCatalog.js` 继续提供分类树与前端检索。

- 多词检索要求各关键词组命中，标题权重大于元数据和正文，支持少量明确维护的中文场景别名；这不是向量语义搜索。
- 搜索结果显示命中理由，正文列表每页 30 条。内置参考资料统一标为 `UNVERIFIED`，不把资料版本当作适用组件版本，也不虚构审核时间。
- `scripts/knowledge/export-catalog.mjs` 从同一目录生成 `backend/src/main/resources/knowledge/catalog.json`，包括确定性内容摘要和全部条目正文。
- 生产 Mini 同时检索内置目录快照与原有受限本地 Markdown。目录引用采用 `catalog/{id}@{version}#UNVERIFIED`，保留分片身份；引用数据不是可执行指令。
- 未导出用户候选、运行日志或私有文档。私有知识权限、正式审核发布、语义重排序及实时增量索引属于后续阶段。

修改知识包后执行：

```powershell
cd frontend
npm.cmd run knowledge:export
npm.cmd test
npm.cmd run build
```

前端 `prebuild` 和快照测试拒绝过期快照。随后重新打包、重启后端；运行中的 JVM 不会热加载新快照。仅执行 Maven 不会自动调用 Node 导出器，因此独立后端打包前也应执行 `npm.cmd run knowledge:check`。

快照加载有 8 MiB、4096 条目、8192 分片硬上限；缺失、格式不正确或超限会明确失败，不静默丢弃知识。原有本地 Markdown 安全限制保留。

## 云原生目标上下文

入口为 `/cloud-native`。四类既有领域改为页内单层详情，使用共用安全 Markdown 渲染器；取消重复嵌套弹窗及与主题无关的通用示例命令。

- 环境、Context、Namespace、参考时间保存在经过白名单校验的 URL 参数中，刷新可恢复。它们是用户填写的目标意图，不是集群发现或连接证明。
- 不在 URL 中填入密码、令牌或其他秘密。页面明确标注生产环境。
- 应用上下文会关闭旧详情；点击工具或知识库保留安全上下文，返回时可恢复。
- 进入工具不会自动切换远程 Context，也不会自动填入命令参数。工具执行前增加人工核对提示；更改参数、工具或上下文后需重新确认，晚返回的旧执行结果不会显示为新目标结果。
- 提示确认不替代服务端认证与权限检查，不授予集群权限。Kubernetes、SSH、观测服务仍依赖既有连接与授权。
- 本阶段不包含自动根因诊断、GitOps 同步、生产变更或自动修复。

## 验证命令

```powershell
cd frontend
node --test test/harbor-foundation.test.mjs test/knowledge-foundation.test.mjs test/knowledge-snapshot.test.mjs test/cloud-context.test.mjs
node test/workbench-foundation.browser.mjs
```

浏览器脚本使用明确模拟的会话和上游 API，默认地址 `http://127.0.0.1:5173`，可通过 `SMARTOPS_BROWSER_BASE_URL` 指向生产预览。覆盖 375/1440px 浅深色、过期及失败状态、请求切换竞态、分页和上下文。不能据此宣称真实 Harbor 或集群已连接。
