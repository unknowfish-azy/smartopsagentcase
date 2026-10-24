# Knowledge API

## 1. 接口定位

Knowledge API 是智维Agent知识服务的统一接口，负责向 AI Service 和 Agent 提供：

- 知识检索
- 混合检索
- 版本过滤
- 重排序
- Evidence
- Citation
- Trust Score

Knowledge 不负责最终自然语言生成，最终回答由 `ai-service` 中的 LLM 服务完成。

---

## 2. 核心请求流程

```text
用户问题
   ↓
Knowledge API
   ↓
Query Processing
   ↓
Embedding
   ↓
┌───────────────┐
│               │
▼               ▼
Vector         BM25
│               │
└───────┬───────┘
        ↓
     Hybrid
        ↓
Version Filter
        ↓
Reranker
        ↓
Evidence
        ↓
Citation
        ↓
Trust Score
        ↓
返回 AI Service / Agent