# 执行审批与验收整改计划

用户已授权沿方案继续。先备份当前工作区，再修复本轮范围，不重置其他改动。

## 设计约束

保持 Python 本地运行时的边界：ApprovalManager 只接受可信宿主调用创建/批准/拒绝，不能把模型或 HTTP metadata 作为批准依据。审批状态保存在管理器内部，返回的 dataclass 是只读快照；任意自造结果对象不获得权限。管理器与 PolicyEngine 显式注入同一个实例，未配置时高风险默认拒绝。此阶段不新增对外审批接口或数据库表，进程重启后审批全部失效。

新批准绑定 request_id、user_id、environment、step_id、tool_name、action 与 canonical JSON 参数；有效期默认 300 秒。批准只允许一次实际执行；dry_run 仅预检、不消费、不调用工具。拒绝/过期/参数修改/跨用户或请求/重复执行均拒绝。CRITICAL 维持拒绝；tool.risk_level、tool.requires_approval 和 step.requires_approval 均不得降低分类器要求。

Executor 深拷贝步骤和上下文，验证并消费批准后执行同一份参数。消费与状态转换在锁内；失败也消耗批准，重试需重新审批。工具返回含 success 字段时必须为 bool，False 传递为执行失败；普通无 success 字段查询结果保持兼容。审计与结果同一成功标记。

## 步骤

- [x] 保存本批精确前像与源码快照。
- [x] 新增行为回归复现 requires_approval 被当成已批准、工具返回失败被包装成功。
- [x] 实现绑定审批、期限/拒绝/防重放与并发单次消费，覆盖参数快照。
- [x] 接入 PolicyEngine 与 Executor，验证风险优先级、dry_run 与审计契约。
- [x] 退役已删除心跳组件的孤立测试；同步 Guardian 菜单预期与分组导航测试，不恢复被删除产品功能。
- [x] 运行 Python 相关回归、完整前端测试/typecheck；全量 Python 保留真实鉴权契约失败，不批量 skip。
- [x] 只读独立审阅；默认 Knowledge 已切换并通过就绪/RAG 检查；本轮自动审批成功，未修改全局配置。
- [x] 完成 10 个官方仓库 README/metadata/LICENSE 原文调研，形成分批路线。
- [x] 交付改后文件、差分、验证记录、哈希保护回滚工具并在副本演练；12 路径哈希/归档有效、原字节还原与后续修改保护均通过（见本批 bundle-validation.json）。

## 边界与验收

新 Python 执行授权不等同于后端团队/哨兵审批，本批不把两者混成已统一工作流。旧 ApprovalManager 的 create_request/approve/reject 保留信息记录接口，但未绑定步骤的记录不放行工具。可信宿主需使用 create_for_step(context, step) 返回的 approval_id 完成批准，再将该 ID 通过 ExecutionContext.approval_id 传给执行器。不得暴露可由终端用户任意选择 reviewer 的公开接口。

知识服务旧 PID 已经核对归属后经自动审批停止；默认 8002 新实例仅监听 127.0.0.1，61 篇语料、2465 chunks，真实 RAG 命中 3 条。本轮未修改全局审批配置。数据库、模型选择/history 和爬取整改留给后续独立批次，顺序见 GitHub 调研与后续路线。
