# Human Golden v1 标注协议（模板骨架）

对应任务：P0-DATA-01（建立 Human Golden v1）
状态：`NOT_STARTED` —— 本文件仅为协议骨架。**未生成、未批准任何 Golden 数据**；真实事故/Runbook 来源与人工负责人尚未确认。

## 1. 目的与适用范围

为评测面（P0-DATA-03）与 REAL baseline（P0-MODEL-01）提供可信的人工标注黄金集。本协议约束 case 的采集、脱敏、双标、裁决、冻结与隔离，不约束任何模型训练行为（SFT/DPO 仍为 `BLOCKED`）。

## 2. 角色与职责

| 角色 | 职责 | 禁止事项 |
|---|---|---|
| 数据治理模型 | 起草协议、汇总登记、生成 manifest 骨架 | 不得生成或批准标签 |
| 标注者 A / B（独立两人） | 互不交流地完成独立标注 | 不得查看对方结果 |
| 裁决专家 | 仅处理双标不一致条目 | 不得修改已一致条目 |
| 人工负责人 | 冻结签字、来源与许可最终确认 | 不得由任一模型替代 |

红线：任何模型不得读取或批准自己生成的标签（模型自审即阻断）。

## 3. Case 数据结构与必填字段

```text
case_id          稳定唯一 ID（冻结后不可变）
source_ref       来源登记号（指向 P0-DATA-02 artifact registry 条目）
license_ref      许可登记号（同上；pending 许可的 case 不得进入正式集）
pii_status       PII 审查结论：clean / redacted / pending / rejected
evidence_hash    原始证据内容 hash（SHA-256）
family           故障/问题族（用于隔离与分层统计）
annotator_a      标注者 A 结论
annotator_b      标注者 B 结论
adjudication     裁决结论（仅不一致时填写）
split            train / test 归属（冻结时指定）
```

## 4. 标注字段定义

（骨架，待标注者培训时补充示例与反例）

- 期望结论类别：______
- 关键证据区间：______
- 难度分层：______

## 5. 双人独立标注流程

1. 数据治理模型分发脱敏 case，A/B 同时独立标注；
2. 双方提交后由治理模型计算一致率，不暴露对方答案；
3. 不一致条目交裁决专家，裁决记录并入 case；
4. 每批标注记录原始文件与 hash，禁止事后改答案。

## 6. 一致性度量与放行门槛

- 核心字段一致率 ≥ 90%，或 Cohen's kappa ≥ 0.75；
- 未达标批次：回炉培训并修订第 4 节定义，整批重标；
- 度量原始输出（混淆矩阵或等效表）必须作为验收证据保存。

## 7. 训练 / Test 隔离规则

- 按 family + source + time 三维隔离，任一维度重叠即视为泄漏；
- 冻结后 test split 只读，任何复测使用同一 hash 校验；
- 40 个 synthetic candidate 不得转入本黄金集（见任务清单"当前不安排的操作"）。

## 8. 冻结与 manifest

冻结时输出 manifest：case 总数、每 case 的 evidence_hash、split 划分、双标/裁决覆盖率、签名人、日期。manifest 本身计算 hash 并入库登记。

## 9. 验收命令与证据要求

（骨架）一致性度量命令、manifest 校验命令与原始输出，随首批数据补录。

## 10. 回滚方式

以 manifest 版本为单位回滚：撤回冻结即宣布该 manifest 作废并登记原因；任何已基于该集产出的评测结论同步标记 invalid。
