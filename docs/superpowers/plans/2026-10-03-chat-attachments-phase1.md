# 聊天附件第一批 Implementation Plan

**Goal:** 交付服务端私有附件会话、权限隔离和聊天文件选择 / 粘贴 / 拖放，保留原有文本会话。

**Architecture:** 独立附件会话 API 与关系数据库私有二进制存储；附件消息返回明确的保存回执，不调用模型或声称完成 OCR。现有本地文本会话不隐式迁移。附件会话可从服务端恢复，前端仅暂存待发送 File / Blob。

**Tech Stack:** Spring Boot / JdbcTemplate / MySQL（测试 H2）、Vue / Pinia、Node test / Playwright。

**Spec:** `docs/superpowers/specs/2026-10-03-visual-agent-attachments-design.md`

## Global Constraints

- 不创建分支或提交，不覆盖现有修改。不采集相机 / 屏幕，不调用外部模型处理附件。
- 单图 10 MB、单文档 20 MB、一次 5 个 / 40 MB；首批安全支持 PNG / JPEG、UTF-8 TXT / LOG / MD。WebP 待服务端安全解码适配，不假装支持。
- 每个空间附件总量首批 200 MB；每会话最多 200 条消息，最多 100 个附件会话。数据库存储为本地部署的过渡实现，后续可迁移私有对象存储。
- 团队接口显式 teamId 并重新鉴权；本次现有 AI 聊天页面只展示个人附件会话，不冒充交付团队聊天 UI。
- 不将原有本地会话自动上传，不把附件或提取内容发模型，后续 OCR / 视觉单独交付。

## Review Focus

- 附件 ID、下载、消息绑定跨账号 / 空间泄露：后端集成测试覆盖。
- 团队只读角色、移除、冻结和写入竞争：范围锁和重新鉴权测试。
- 重试重复保存 / 错绑消息：请求标识唯一，载荷冲突返回 409。
- 伪造图片、超大像素、主动内容、UTF-8 错误：后端内容校验测试。
- 会话切换 / 退出时晚到响应、预览 URL 清理：前端队列行为测试及浏览器检查。

## 执行步骤

- [x] 1. 建立失败回归：`ChatAttachmentIntegrationTest` 与 `chat-attachments.test.mjs`。
- [x] 2. 实现 `ChatAttachmentService` / `ChatAttachmentController` / 文件校验，V007 数据表及迁移注册；鉴权、配额、幂等、删除和过期暂存清理。
- [x] 3. 实现 `domain/chat/attachments.js`、附件 API、预览组件和聊天输入交互；接入 aiChat store 的服务端附件会话恢复 / 删除，不迁移旧文本。
- [ ] 4. 跑定向与完整测试、生产构建、浏览器上传 / 粘贴 / 拖放 / 主题检查；记录真实边界。
- [ ] 5. 验证后备份迁移 / 更新本地后端；只读运行检查，不自动向真实账号上传测试文件。

## 暂缓项

截图 / 相机、本地 OCR、WebP / PDF / DOCX、安全裁剪 / 遮盖编辑器、团队会话 UI、模型附件分析、知识入库及生成资产仍未完成。附件预览提示用户先在本地脱敏；界面不放虚假可用按钮。
