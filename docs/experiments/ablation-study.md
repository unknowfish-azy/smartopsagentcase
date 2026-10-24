# Ablation Study Plan

## RAG

```text
EXP-RAG-001 Vector
EXP-RAG-002 BM25
EXP-RAG-003 Hybrid
EXP-RAG-004 Hybrid + Reranker
EXP-RAG-005 Hybrid + Reranker + Version
EXP-RAG-006 Hybrid + Reranker + Version + Evidence
```

## Inspector

```text
EXP-INS-001 Agent
EXP-INS-002 Agent + Rule
EXP-INS-003 Agent + Rule + Evidence
EXP-INS-004 Agent + Rule + Evidence + AI Judge
EXP-INS-005 Agent + Full Inspector + Verification
```

All entries are currently `NOT RUN`. Results must share one grouped test split and must include task success, evidence/tool/risk accuracy, false success, safety violation, Inspector precision and recall.
