# SmartOps Linux Core Knowledge v0.1

版本：0.1。来源：用户提供的 Linux Shell 课程，经过工程化整理。适用：Linux；Bash、GNU 工具扩展均在命令卡注明。

结构化主数据为本目录 `coreKnowledge.js`，供前端知识目录直接加载；知识库中选择「Linux 基础」即可搜索、打开和逐条阅读。数据不会执行命令，也未接入模型训练或自动诊断。

## 知识格式

每条节点包含稳定 id、title、category、level、concept、architecture、commands、scenario、diagnosis、risk、experience、verification、relatedIds、tags。

命令卡包含 command、purpose、parameters、risk。命令风险区分 READ_ONLY、LOCAL_WRITE、OVERWRITE、VALIDATION；正文说明环境与副作用，不能把整个采集流程笼统标为只读。

## 已收录

| 节点 | 资料 |
|---|---|
| LINUX-FD-001 | FD 与日志去向 |
| LINUX-FD-002 | FD 限制与泄漏排查教学案例 |
| LINUX-IO-001 | 重定向顺序及日志丢失案例 |
| LINUX-IO-002 | 管道、tee 与失败状态 |
| LINUX-IO-003 | xargs 与安全文件名处理 |
| LINUX-IO-005 | wc 统计口径、date 时间戳 |
| LINUX-SERVICE-001 | Nginx 服务状态与业务验证 |

## 诊断输出约定

先说明已有事实和未知信息，再列出待验证假设、证据需求、分支步骤、风险和验证方法。询问目标环境、时间、影响和最近变更。不得把知识中的示例当作实时测量结果；没有证据时不宣布根因。

后续课程按「元数据 → 概念 → 原理 → 命令 → 场景 → 排查 → 风险 → 经验 → 验证 → 关联」追加。进程管理、文件系统、性能专题后续补充，不创建虚假的已完成资料。

## 数据集

`SmartOps-Dataset/Linux/` 提供四个 JSONL 草稿样本文件。每行记录 schemaVersion、status、knowledgeIds、instruction、response。response 是可审核的诊断建议，不是隐藏推理过程。教学案例不冒充真实事故；需人工审核、许可检查及脱敏后再用于训练。当前没有执行 LoRA、模型上传或生产命令。
