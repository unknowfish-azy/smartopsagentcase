# Agent Architecture

## 1. 模块定位

Agent 是 SmartOpsAgent（智维Agent）的智能运维核心。

Agent 的职责不是单纯生成文本，而是将用户的自然语言运维需求转换为：

```text
任务理解
   ↓
任务规划
   ↓
风险判断
   ↓
工具选择
   ↓
安全执行
   ↓
结果验证
   ↓
审计留痕