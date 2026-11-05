# 许可、血缘与撤回登记（完整版）

对应任务：DATA-P0-02（已完成登记表）
状态：**DONE** —— 已生成完整 registry，20 条 artifact 全部登记，关键问题（RH 许可违规）已标记 REJECTED

## 1. 目的

让每一条进入知识库 / 评测集 / 训练候选的资料都能回答三个问题：**许不允许用、从哪里来、撤回时影响谁**。缺少任一答案即保持 `pending`，不下载、不入库。

## 2. 登记表（已填充）

完整表格：[P0-DATA-02-artifact_registry.csv](P0-DATA-02-artifact_registry.csv)（20 条，可排序筛选）

**关键发现**：

| Artifact | 类型 | 许可 | PII | 状态 | 备注 |
|---|---|---|---|---|---|
| ART-001 RH124 | knowledge_corpus | **REJECTED** | clean_placeholder | REJECTED | 封面写 Internal use only + No retrieval system |
| ART-002 RH134 | knowledge_corpus | **REJECTED** | clean_placeholder | REJECTED | 同 RH124 系列 |
| ART-003 RH294 | knowledge_corpus | **REJECTED** | clean_placeholder | REJECTED | 封面全文禁止存入检索系统 |
| ART-004 云原生公开课 | knowledge_corpus | PENDING | clean | PENDING | 未找到许可 |
| ART-005 ops-knowledge-rag | knowledge_corpus | PENDING | clean | PENDING | 自编纂，缺内部授权 |
| ART-006 corpus manifest | manifest | 关联 ART-001~005 | N/A | PENDING | 含 rejected 源，需重建 |
| ART-007 false_success.json | eval_fixture | APPROVED | clean | **APPROVED** | 50 synthetic，冻结可作受控 prototype |
| ART-008 false_success_holdout.json | eval_fixture | APPROVED | clean | **APPROVED** | 20 留出，冻结不变 |
| ART-009 golden_set.json | retrieval_eval | PENDING | clean | PENDING | 非独立人工标注，需重标 |
| ART-010 sample_dataset.json | retrieval_eval | PENDING | clean | PENDING | 同上 |
| ART-011 Ollama qwen3:1.7b | model_provider | PENDING | N/A | PENDING | 许可链待补 |
| ART-012~020 代码/运行产物 | 各类 | APPROVED | N/A | APPROVED | 自研，无冲突 |

## 3. 许可合规检查命令

```powershell
# 一键扫描所有 source 目录，生成 registry diff
python scripts/check_corpus_licensing.py --registry docs/development/P0-DATA-02-artifact_registry.csv

# 重点：知识库许可合规（RH 必须移除）
python scripts/check_corpus_licensing.py --registry docs/development/P0-DATA-02-artifact_registry.csv --filter knowledge_corpus
```

## 4. Artifact 状态定义

| 状态 | 含义 | 允许入库？ | 允许进入评测分母？ |
|---|---|---|---|
| APPROVED | 许可 + PII + 血缘完整 | ✅ | ✅ |
| PENDING | 至少一项未完成 | ❌ | ❌ |
| REJECTED | 许可/内容明确不允许 | ❌ | ❌ |
| WITHDRAWN | 原 APPROVED 但需撤回 | ❌（删除并重建） | ❌（已撤回的 case 标记 invalid） |

## 5. 血缘记录

每个 APPROVED artifact 必须维护血缘链：

```text
origin_url / 采集记录
  → 加工步骤（脱敏、切分、转换，各步工具与版本）
  → 入库位置（索引名 / 数据集路径）
  → 每步输出 hash
```

缺失 → **不得置 APPROVED**。

## 6. 撤回影响图

撤回 ART-001/002/003（RH 语料）的影响：

| 影响项 | 数量 | 处置 |
|---|---:|---|
| Knowledge 检索命中 RH chunk 的历史证据 | 所有含 RH citation 的 run | invalidate |
| RAG 召回评估（当前 golden_set 可能依赖 RH） | ART-009 | verify，必要时重跑 |
| corpus_sha256 | 变更 | 重建 manifest |
| AI Service trust_score 基准 | 变更 | 重新校准 |

## 7. 回滚方式

登记表按版本管理；误登记撤回时整行标记 `withdrawn`（不删除历史行），派生物按 §6 影响图执行回滚。
