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
```

---

## 2. 向量后端

| 后端 | 说明 | 适用场景 |
|---|---|---|
| `hash`（默认） | 哈希词袋，256 维，零依赖、零下载 | 本地演示、无模型环境 |
| `bge` | 本地 `BAAI/bge-small-zh-v1.5`，512 维，CLS pooling + L2 归一化 | 需要语义召回 |

切换方式：

```powershell
$env:KNOWLEDGE_EMBEDDING_BACKEND = "bge"
$env:KNOWLEDGE_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
uvicorn knowledge.server:app --host 127.0.0.1 --port 8002
```

BGE 依赖 `transformers` + `torch`，并从 HuggingFace 缓存离线加载；
依赖或模型缺失时自动回退到 `hash` 并在日志中告警，服务不会启动失败。

> 实测（61 篇 / 2465 chunks，CPU）：
>
> | 场景 | 模型加载 | 语料摄入 | 合计 |
> |---|---|---|---|
> | 首次（无缓存） | 21.3s | 101.0s | ~122s |
> | 再次启动（命中缓存，新进程） | 14.8s | 0.1s | ~15s |
>
> 向量缓存默认落在 `knowledge/.cache/vectors.sqlite3`，
> key = `sha256(模型名 + chunk 文本)`：语料改动只重算变化部分，换模型自动全部失效。
> 关闭缓存：`KNOWLEDGE_VECTOR_CACHE=off`。
> 剩余 15s 基本是模型加载，可后续用 ONNX / 更小模型进一步压缩。

---

## 3. 检索评测

```powershell
# 1) 从 reference 语料重新生成黄金集（新增语料后执行）
python -m knowledge.evaluation.build_golden_set

# 2) 对比两种向量后端
python -m knowledge.evaluation --top-k 5 --json knowledge/evaluation/latest_results.json
```

评测集由 `verbatim`（保留标题原词）与 `paraphrase`（同义改写 + 正文小节话题）
两组共 114 条用例组成，判定口径为稳定的 `source` 路径。

本机基线（2026-11-04，114 条，top-5）：

| 后端 | hit@5 | recall@5 | MRR | nDCG@5 | p50 延迟 |
|---|---|---|---|---|---|
| hash | 0.754 | 0.754 | 0.688 | 0.705 | 124 ms |
| bge | 0.851 | 0.851 | 0.754 | 0.779 | 292 ms |

改写组（paraphrase，58 条）提升最明显：hit@5 由 0.690 → 0.776，
说明 BGE 带来的主要收益是"用户不按文档标题提问"时的语义召回。

> 该集合由脚本自动生成，仅衡量改写鲁棒性，不能替代人工标注的黄金集。

---

## 4. 访问控制

默认情况下 `/api/documents`（写入）是**关闭**的，`/api/search` 保持开放，
避免端口可达即可被污染知识库或拉走全部资料。

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `KNOWLEDGE_API_KEY` | 空 | 设置后 `/api/search` 与 `/api/documents` 都必须携带 `X-API-Key` 头，否则 401 |
| `KNOWLEDGE_ALLOW_INGEST` | `0` | 未配置 key 时，是否允许匿名写入（仅本地演示建议设为 `1`） |

```powershell
$env:KNOWLEDGE_API_KEY = "<随机串>"
uvicorn knowledge.server:app --host 127.0.0.1 --port 8002

# 调用方（AI Service）读取同名变量，自动附加请求头
Invoke-RestMethod http://127.0.0.1:8002/api/search `
  -Method Post -Headers @{ "X-API-Key" = $env:KNOWLEDGE_API_KEY } `
  -ContentType "application/json" -Body '{"query":"nginx 启动失败"}'
```

`/api/health` 暴露 `auth_required` 字段，便于启动脚本判断当前是否已开启鉴权；
`/health` 是它的同内容别名（不进 OpenAPI 文档），方便通用探针直接使用。
存活与就绪要分开看：`/api/health` 只说明进程在跑，`/api/ready` 才说明索引已加载可检索。