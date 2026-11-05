# Human Golden v1 标注协议（完整版）

对应任务：DATA-P0-01（建立独立标签、来源与强基线）
状态：`IN_PROGRESS`（协议冻结已完成，人工标注未启动；当前 50 synthetic 病例已冻结作受控 prototype，**不是**正式 Golden）

## 0. 现状审计结果（前置证据）

### 0.1 许可违规处置（紧急）

**RH124/RH134/RH294 红帽官方培训教材**：封面写 "Internal use only - Not For Sale" + "No part of this publication may be stored in a retrieval system"。当前知识库已把 45 个 RH 章节完整 ingest，RAG 检索**实际返回这些 chunk 给 LLM**——**许可违规**。

| 处置 | 执行 | 负责人 |
|---|---|---|
| 从索引移除 RH124/RH134/RH294 | Knowledge 语料剔除 + 重新 build manifest | DATA-P0-01 |
| 重新计算 corpus_sha256 | 验证剔除后 manifest 正确 | DATA-P0-01 |
| 评估检索召回率下降 | RAG-P1-01 | 后续 |
| 登记 ART-001/002/003 为 withdrawn | P0-DATA-02 registry | DATA-P0-01 |
| 替换为合法来源 | 找可用许可的运维知识材料（RH 公开文档、Ansible 官方 docs、Kubernetes docs 等） | VERSION-P0-01 |

### 0.2 PII 扫描结论

reference 语料 61 个 .md 文件，343 个 PII pattern 匹配：

- **email 75 个**：`bug-gzip@gnu.org`、`aes256-gcm@openssh.com`（开源协议）、`training@redhat.com`（版权联系）、`user@host.lab.example.com`（教学占位符）→ 全部是**教材中公开的或教学占位**，不是真实用户隐私
- **generic_secret 157 个**：`password:redhat`（RH 教材练习口令，公开）、`passwd:/usr/bin/passwd`（命令示例）→ 同上
- **SSN 2 个 + phone_cn 3 个**：MySQL 教材示例，非真实
- **IP 73 个（除 private 段 127/192.168/10/172.16-31 外） + IPv6 9 个**：公开文档示例 IP

**结论**：PII 状态 = `CLEAN_TRAINING_PLACEHOLDER`——教材示例中常见占位符，不是真实业务凭据。**RH 语料的处置原因是许可违规，不是 PII。**

### 0.3 三类数据来源分类

DATA-P0-01 分开治理三类：

| 来源类型 | 定义 | 当前状态 |
|---|---|---|
| **开发合成集** | ART-007/008 `false_success.json` + `false_success_holdout.json`，24—40 synthetic 病例 | ✅ 已冻结 50 synthetic + 20 留出 |
| **受控机制实验** | Knowledge 官方 golden_set.json（ART-009/010） | ⚠️ 未按协议双标，PENDING |
| **独立人工测试 + 真实业务观测** | 需真实故障 Runbook / 工单 | ❌ 未启动 |

## 1. 目的与适用范围

为评测面（P0-DATA-03）与 REAL baseline 提供可信的人工标注黄金集。本协议约束 case 采集、脱敏、双标、裁决、冻结与隔离，不约束任何模型训练行为（SFT/DPO 为 BLOCKED）。

**边界**：合成病例用于受控 prototype（24—40 例足够验证机制是否生效），**不宣称等效**人工 Golden。正式效果结论须有独立人工审核。

## 2. 角色与职责

| 角色 | 职责 | 禁止事项 |
|---|---|---|
| 数据治理（本协议撰写者） | 起草协议、汇总登记、生成 manifest 骨架 | 不得生成或批准标签 |
| 标注者 A / B（独立两人） | 互不交流地完成独立标注 | 不得查看对方结果 |
| 裁决专家 | 仅处理双标不一致条目 | 不得修改已一致条目 |
| 人工负责人 | 冻结签字、来源与许可最终确认 | 不得由任一模型替代 |

红线：任何模型不得读取或批准自己生成的标签（模型自审即阻断）。

## 3. Case 数据结构与必填字段（更新）

```text
case_id          稳定唯一 ID（冻结后不可变，格式 case-{family}-{n:04d}）
source_ref       artifact 登记号（指向 P0-DATA-02 registry）
license_ref      许可登记号；pending/rejected artifact 的 case 不得进入正式集
pii_status       clean / redacted / pending / rejected
evidence_hash    原始证据 SHA-256（冻结后不可变）
family           故障/问题族（6 类，见 §4）
expected_outcome 业务真值（Oracle，独立于被测契约）
annotator_a      标注者 A 结论（冻结后不可变）
annotator_b      标注者 B 结论（冻结后不可变）
adjudication     裁决结论（仅不一致时填写）
split            train / holdout / withdrawn（冻结时指定）
oracle_health    Oracle 契约：完整 / degraded / insufficient / unknown（冻结时指定）
proof_sufficient 证据契约：yes / partial / no（冻结时指定）
```

## 4. 故障族定义（6 类）

| 代码 | 族 | 示例 |
|---|---|---|
| F-NET | 网络连通性 | timeout / 502 / DNS 失败 |
| F-HTTP | HTTP 协议 | 502 bad gateway / 503 unavailable / 404 false |
| F-L4 | OS 进程/服务 | 进程挂死 / systemctl 状态 / 日志中断 |
| F-DB | 数据库/缓存 | MySQL 主从延迟 / Redis 未响应 |
| F-SSH | 远程接入 | SSH key 过期 / 密码失败 |
| F-CONF | 配置/资源 | 端口冲突 / 磁盘满 / OOM |

派生问法（"nginx 502" vs "网关返回 502" vs "502 bad gateway 怎么办"）**不**当作独立 case，同一故障族下的表达变体归为同一 case_id。

## 5. Oracle 契约（关键冻结）

> **不复用被测契约求值代码作 oracle** — 任务书 §3.1 明确要求。

### 5.1 oracle_health 四级

| 级别 | 含义 | 判定 |
|---|---|---|
| complete | 真实业务观测，有可验证 runbook 或监控截图 | 正式 Golden 来源 |
| degraded | 真实场景但证据链不全（缺截图、缺 runbook 编号） | 回归线索，不作正式评测分母 |
| insufficient | 只有文字描述，无 runbook / 工单 / 证据链 | 拒绝进入正式集 |
| unknown | 来源不明（匿名 issue 等） | 拒绝 |

### 5.2 proof_sufficient 三级

| 级别 | 含义 |
|---|---|
| yes | 有截图 / 日志片段 / runbook 编号，可人工还原 |
| partial | 有部分证据但链不完整 |
| no | 纯文字，无法验证 |

### 5.3 冻结机制

- 每批 case 的 oracle_health + proof_sufficient 在双标前**一次性冻结**，后续任何人（包括裁决专家）不得更改；
- 冻结记录随 manifest 一起入库，字段 `oracle_frozen_at` + `oracle_frozen_by`；
- 任何"事后觉得这个 case 的 Oracle 不够强"的情况 = **整批重跑**，不局部修补。

## 6. 三类 Case 的数据来源与状态（DATA-P0-01 增量）

### 6.1 开发合成集（已冻结，受控 prototype）

| 项 | 值 |
|---|---|
| case 数 | 50（train=30 positive + 10 distractors，holdout=20） |
| family | 6 类全部覆盖 |
| oracle_health | **degraded**（synthetic fixture，非真实业务观测） |
| proof_sufficient | partial（有 probe 字段但无真实 runbook） |
| source_ref | ART-007 / ART-008 |
| 状态 | **已冻结，可作机制验证，不作正式效果宣称** |

冻结命令：

```powershell
python .runtime/score-p0-01/verify_frozen.py --fixture tests/fixtures/defense/false_success.json
python .runtime/score-p0-01/verify_frozen.py --fixture tests/fixtures/defense/false_success_holdout.json
```

### 6.2 受控机制实验（待重新标注）

- ART-009/010 golden_set.json 来自 `build_golden_set.py`，非独立人工标注；
- **DATA-P0-01 处置**：回炉按协议重新双标；旧 golden_set 保留作 baseline（schema_version=1，标记 deprecated）。

### 6.3 独立人工测试 + 真实业务观测（未启动）

- 需要真实故障 Runbook / 工单 / 监控截图；
- 缺条件时 **formal 指标为 null**（不编造）；
- 启动标志：至少 2 名独立标注者已到位，30+ case 的 oracle_health=complete。

## 7. 双人独立标注流程（更新）

1. 数据治理**只分发脱敏 case + evidence_hash + 冻结的 Oracle**，不展示预期标签；
2. A/B 同时独立标注，互不交流；
3. 双方提交后由治理模型计算一致率（**不暴露对方答案**）；
4. 不一致条目交裁决专家，裁决记录并入 case（**必须保留"不一致"原始状态，不得覆盖**）；
5. 每批标注记录原始文件与 hash，禁止事后改答案。

## 8. 一致性度量与放行门槛

- 核心字段（故障族 + 期望结论）一致率 ≥ 90%，或 Cohen's kappa ≥ 0.75；
- 未达标批次：回炉培训并修订 §4 定义，整批重标；
- 度量原始输出（混淆矩阵或等效表）必须作为验收证据保存（`data/golden/v1/agreement_matrix-{batch_id}.csv`）。

## 9. 训练 / Test 隔离规则

- 按 **family + source + time** 三维隔离，任一维度重叠即视为泄漏；
- 冻结后 test split 只读，任何复测使用同一 evidence_hash 校验；
- 40 个 synthetic candidate 不得转入本黄金集（§6.1 已明确）；
- ART-009/010 旧 golden_set 若被新版本替换，必须在 manifest 登记 deprecation_date 和原因。

## 10. 冻结与 manifest

冻结时输出 manifest（JSON + CSV 两份）：

```json
{
  "schema": "smartops.golden.v1",
  "batch_id": "golden-v1-20261105",
  "frozen_at": "2026-11-05T00:00:00Z",
  "frozen_by": "human_owner_tbd",
  "case_count": 0,
  "split_distribution": {"train": 0, "holdout": 0},
  "family_distribution": {"F-NET": 0, "F-HTTP": 0, "F-L4": 0, "F-DB": 0, "F-SSH": 0, "F-CONF": 0},
  "oracle_health_distribution": {"complete": 0, "degraded": 0, "insufficient": 0, "unknown": 0},
  "agreement_rate": null,
  "cohens_kappa": null,
  "corpus_version": "smartops.corpus.v1",
  "corpus_hash": "8fdc937e…",
  "notes": "RH124/RH134/RH294 已剔除，manifest 需重新构建"
}
```

manifest 本身计算 hash 并入库登记。DATA-P0-02 registry 登记一条 artifact 指向该 manifest。

## 11. 失败与撤回

| 失败类型 | 处置 |
|---|---|
| 许可违规（如 RH） | ART 标记 withdrawn，关联 case 全部 withdrawn，manifest 标记 invalid |
| Oracle 冻结后发现不纯 | 整批重跑；已产出的评测结论同步标记 invalid |
| 双标一致率不达标 | 回炉培训，整批重标 |
| 来源可追溯性断裂 | artifact 标记 pending，case 同步 pending |

## 12. 验收命令与证据

```powershell
# 冻结 manifest（需人工负责人批准）
python scripts/freeze_golden.py --manifest data/golden/v1/manifest.json --owner human_tbd

# 校验 manifest hash 与一致性
python scripts/verify_golden_manifest.py --manifest data/golden/v1/manifest.json

# 一致性度量
python scripts/measure_agreement.py --batch data/golden/v1/annotations.csv --output data/golden/v1/agreement_matrix.csv

# PII 扫描（reference 语料）
python .runtime/data-p0-01/scan_pii.py

# 许可合规检查（artifact registry 对照 corpus）
python scripts/check_corpus_licensing.py --registry docs/development/P0-DATA-02-artifact_registry.csv --corpus knowledge/reference/
```

## 13. 回滚方式

以 manifest 版本为单位回滚：撤回冻结即宣布该 manifest 作废并登记原因；任何已基于该集产出的评测结论同步标记 invalid。**不做文件级 patch 回滚**，只做整批 manifest replacement。
