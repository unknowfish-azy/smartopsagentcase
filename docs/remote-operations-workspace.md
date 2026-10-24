# Personal Operations Workspace：架构审计与实施计划

## A / 当前架构

Vue 3 + Vite + Pinia + xterm.js 浏览器前端；Spring Boot + Apache SSHD 后端；MySQL 会话持久化。未发现 Electron、Tauri 或 Wails 运行时。浏览器通过 REST 和 WebSocket 调用 Operations Bridge，不能直接访问 COM、WSL 或 OS 密钥库。

## B / 本地能力

SSH/SFTP 存在真实 Java 适配器，但 capabilities 当前仅声明适配器存在，不证明目标可连或服务健康。RDP/VNC/Serial/Mosh/WSL/FTP/S3/Telnet/Local Shell 无对应实现。不能展示虚构延迟、CPU、传输速度或集群健康。

## C / 协议策略

先以 SSH/SFTP 完成端到端工作台。RDP/VNC 需独立网关或桌面桥接；Serial/WSL/Local Shell 需受控本地运行服务；FTP/FTPS/S3 需独立传输适配器；Telnet 必须明文风险确认；Web 会话只允许 http/https 外部链接。各协议必须真实探测并分别验收。

## D / Session 模型

沿用 operation_session：id、user_id、group_id、name、protocol、host、port、username、credential_id、identity_path、jump_session_id、working_directory、tags_json、description、accent、favorite、status、last_connected_at 和时间戳。沿用现有表，不重建数据库。

会话配置与运行时分离：保存会话不等于建立连接。运行标签持有 runtimeId、会话快照、状态；切换选择不改变其他终端的目标。恢复工作区只能恢复布局和连接引用，重连需用户触发。

## E / Terminal

每个 runtime 只绑定一个 xterm 和 WebSocket。标签隐藏时保留实例和滚动记录；ResizeObserver 同步尺寸；分屏显示多个独立运行时，最多四屏。当前后端单 OutputListener 不支持同一 runtime 重复打开 socket。网络断开保留标签和输出；重新连接生成新 runtime，需要独立恢复协议才可声明无损自动恢复。

## F / File Transfer

复用 /api/operations/runtimes/{runtimeId}/files。第一阶段浏览、目录切换、下载、经确认上传；进度来自请求事件，仅服务端响应成功后标记完成。SFTP 服务目前下载先缓存整个文件，尚不具备大文件流式、断点续传、同步或后台队列。远程编辑、rename、chmod 和持久化传输管理作为后续阶段；不能用假进度替代。

## G / Credential

密码通过 AES-GCM 加密入库，密钥由 `SMARTOPS_API_KEY_ENCRYPTION_KEY` 提供；私钥只保存后端可访问路径。创建会话响应只返回 `****`，不再保存或返回密码末四位。尚未接入 Windows Credential Manager。多人身份仍依赖默认 userId/请求头，当前不具备企业级身份隔离，不应公网暴露。

## H / Agent Safety

Agent Context 提供允许动作和只读边界，不等于 AI 分析已实现。MultiExec 预览固定目标，编辑命令/目标须失效；二次确认必须由用户独立动作触发。SENT 只能表示已发送，不能宣称执行成功。原始 PTY 输入不能依赖前端字符串匹配实现完整命令防护。后续需后端持久审计、审批单次消费和身份认证加固。

## I / UI

克制深色、中文操作文案：左侧会话搜索/收藏筛选，顶部连接/分屏/文件/隧道，中央多标签终端，右侧真实会话信息与 Agent 上下文。知识关联以用户点击搜索为入口。所有列表明确加载、错误重试、空数据状态。

## J / 分阶段计划

1. 工作台基础：独立运行标签、最多四屏、关闭生命周期、断线显示、SFTP 浏览/上传/下载、初始化失败重试、协议能力禁用。补行为测试和浏览器接口模拟。
2. 会话数据：分组 CRUD、收藏更新、凭证引用管理、安全导入导出与布局恢复。跳板凭证和 host key 分别验证。
3. 执行能力：本地/远程/SOCKS 隧道独立适配、真实多目标预览/二次确认、审计与命令历史。生产标记不能仅依赖名称。
4. 文件能力：流式传输、队列/重试/取消、远程编辑版本冲突检测，权限修改审批。
5. 原生协议：逐一实现并验收 RDP/VNC/Serial/WSL/Mosh 等，缺适配器保持不可连接。
6. AI/知识/记忆：用户选择且脱敏的上下文 → 检索 → 建议 → 审批 → 执行 → 验证 → 草稿案例；禁止自动索引敏感路径。

## 验证边界

npm test/build/lint/typecheck、Maven 测试及 768/1024/1440/1920 浏览器检查。模拟接口只验证 UI/契约，不等于真实 SSH/SFTP 验收。实机需要明确授权的测试主机与凭证；未经真实连接不得宣称协议验收完成。
