# SmartOpsAgent Demo

本目录用于保存智维Agent的演示场景、测试案例以及 Demo 运行结果。

Demo 的主要目的不是保存生产环境数据，而是通过标准化场景展示：

- AI 故障分析
- Knowledge RAG 检索
- Evidence 证据引用
- Agent 任务规划
- Risk Policy 风险判断
- Tool Calling 工具调用
- Executor 执行
- Verification 验证
- Audit 审计留痕

---

## 1. 目录结构

```text
demo/
├── README.md
├── outputs/
│   └── README.md
└── scenarios/
    ├── docker/
    │   ├── problem.json
    │   └── expected.json
    ├── mysql/
    │   ├── problem.json
    │   └── expected.json
    └── nginx/
        ├── problem.json
        └── expected.json