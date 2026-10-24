# SmartOpsAgent Knowledge

`knowledge` 是 **智维Agent——面向中小企业的可信AI智能运维与知识协同平台**
的知识工程模块。

本模块负责将运维文档、日志、配置文件以及其他非结构化知识转换为可检索、
可引用、可评估的知识资源，并为后续 RAG、可信回答和 Agent 决策提供基础能力。

---

## 1. 核心目标

Knowledge 模块主要解决以下问题：

1. 运维知识来源分散，难以统一管理。
2. 不同操作系统、软件版本对应的运维方法可能不同。
3. 单纯向量检索容易遗漏明确的关键词和命令。
4. AI 回答缺少可验证的证据来源。
5. 无法通过统一数据集量化比较不同检索方案。

因此，本模块采用：

```text
文档解析
    ↓
知识入库
    ↓
文本切块
    ↓
Embedding
    ↓
Vector Retrieval + BM25
    ↓
Hybrid Retrieval
    ↓
Version Filter
    ↓
Reranker
    ↓
Evidence
    ↓
Trust Score
    ↓
Evaluation