# 比赛调整方案清单（Adjustment Plan）

> 来源：WorkBuddy 对话（根据比赛要求制定的调整方案）+ 对照赛事页面（`boxuegu.com/matchTrack/detail/?id=10037`）的合规整改。
> 更新日期：2026-10-24

## 赛事硬性要求（对照基线）

| 要求 | 本项目状态 |
| --- | --- |
| 团队 1–3 名同校学生，≤2 名指导教师 | 待团队填写（`project-plan.md` / `defense.md` 已留位置） |
| 代码仓库（公开或向评审授权） | 本地就绪，待推送 GitHub |
| 5–8 分钟 MP4 演示视频（1080p） | 脚本就绪（`demo-script.md`），待录制 |
| PDF 技术文档 ≤30 页 | 已生成 18 页（`technical-document.pdf`） |
| 主题：AI Native Web（LLM/Agent/RAG/多模态） | 已满足（Agent + RAG + SSE + 多模态） |
| 省赛提交截止 2026-11-18 | 材料收口进行中 |

## 决策记录

| 决策项 | 结论 |
| --- | --- |
| 托管平台 | 公开 GitHub 仓库（由团队手动推送，AI 不持有凭据） |
| TypeScript 改造深度 | 部分改造：仅共享逻辑层（`api/`、`domain/`、`utils/`、`types/`） |
| 多模态方向 | 语音输入（Web Speech API）+ 图像证据（截屏/拍照/图片附件） |
| 演示视频 | 团队提供录制文件，AI 协助剪辑 |
| 团队与组别 | 待补充 |
| 在线演示 | 可选，待补充 |
| 图像内容理解 | 当前仅文件名级参与链路，路线图接入 OCR/多模态模型（文档如实声明） |

## 任务清单（第一轮：工程化改造）

- [x] **P1 仓库就绪**：`.gitignore` 补齐；取消跟踪 `backend/.m2`、`frontend/.vite-once-cache`、`components.d.ts`、用户运行时知识库数据。
- [x] **P2 SSE 流式对话 + AI 思考可视化**：`thinking / token / done` 三类事件；前端逐事件渲染。
- [x] **T3 TypeScript 部分改造**：共享逻辑层 48 个模块迁移 `.js → .ts`；`npm run typecheck` 纳入门禁。
- [x] **T4 多模态**：语音输入（浏览器内识别）+ 图像证据（仅文件名）+ 附件隐私隔离。
- [x] **T5 性能（构建分包）**：`manualChunks` 收敛至 `vite.shared.mjs`；zrender 拆出（510 kB → 346 kB）；Three.js 懒加载。
- [x] **T6 技术文档 PDF**：由 `technical-document.html` 经 `scripts/export-technical-pdf.mjs` 导出。
- [ ] **T7 演示视频**：等待团队录制（阻塞项，需人工）。
- [ ] **T8 在线演示**：可选，待补充（阻塞项，需人工决策）。
- [ ] **T9 推送 GitHub**：由团队手动执行（阻塞项，凭据自持）。
- [ ] **团队与组别信息**：待补充（阻塞项，需人工填写）。

## 任务清单（第二轮：比赛合规整改与本地跑通）

- [x] **D1 数据库 schema 自愈**：新增 `AssistantWorkspaceConfig`，启动时幂等补齐 `chat_conversation` / `chat_message` / `chat_attachment` / `vision_event` / `operator_memory` / `personal_knowledge_*` / `artifact_draft` 共 8 张表；加列脚本改为"探测列后执行"以兼容 MySQL 8.0；本地 67 → 80 张表，`ChatAttachmentRetention` 报错消失。
- [x] **D2 Vite `/ai` 代理修复**：代理缺失 `rewrite` 导致 `/ai/api/chat/stream` 被原样转发 → 404；用户层也改为使用共享 `devProxy()`，修复后 SSE 全链路 200。
- [x] **D3 竞赛四件套重写**：`project-plan.md`、`innovation.md`、`demo-script.md`、`defense.md` 由残句补全为完整文档（含评分维度对齐、分镜时码、问答准备）。
- [x] **D4 技术文档扩写**：14 章、18 页，覆盖架构/时序/AI 设计/实现细节/创新/安全/数据/工程/测试/部署/演示/局限/附录；PDF 已重新导出。
- [x] **D5 最终测试**：前端 （前端构建 + 测试门禁） 通过 + typecheck + 双构建；后端 444 项通过；ai-service 8 项通过；浏览器端登录与对话链路通过；后端接口冒烟通过。
- [x] **D6 代理相关测试同步**：`session-security`、`model-api-connectivity`、`admin-service-contract` 三个契约测试改为断言共享工厂，避免"配置下沉后测试失真"。

## 质量验证（每次改动后执行）

```powershell
cd frontend
npm test            # node --test（563 项）
npm run typecheck   # tsc --noEmit
npm run build       # 用户层构建
npm run build:admin # 管理员层构建

cd ../backend
mvn test            # JUnit 5 + H2（444 项）

cd ../ai-service
python -m pytest    # 8 项
```

本地技术文档重新导出：

```powershell
node scripts/export-technical-pdf.mjs
```

## 演示动线（多模态 + 可信 AI）

1. 启动后端（8080）、ai-service（8001）与前端（5173）；知识库（8002）可选。
2. 进入 AI 对话：语音描述故障（如"MySQL 连接数打满"）。
3. 添加图像证据，发送后观察六阶段思考：图像证据解析 → 知识检索 → 证据验证 → Agent 规划 → 风险判定 → 生成回答。
4. 展示引用证据与可信度评分；切换到附件会话演示"私有保存、不分析"的隐私边界。
5. 进入 Agent 指挥中心：高风险步骤人工审批 → 执行轨迹 → inspector 核查 → 运行记录与审计。

## 剩余阻塞项（需人工）

| 项 | 责任方 | 截止 |
| --- | --- | --- |
| 团队/组别/指导教师信息填写 | 团队 | 提交前 |
| GitHub 仓库推送与访问权限 | 团队 | 2026-11-18 前 |
| 演示视频录制与剪辑 | 团队 | 2026-11-18 前 |
| 在线演示地址（可选加分） | 团队 | 提交前 |
