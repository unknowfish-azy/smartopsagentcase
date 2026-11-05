# 许可、血缘与撤回登记（模板骨架）

对应任务：P0-DATA-02（建立许可、血缘和撤回登记）
状态：`NOT_STARTED` —— 本文件仅为登记表结构。**当前没有任何已批准 artifact**；所有来源默认 `pending`。

## 1. 目的

让每一条进入知识库 / 评测集 / 训练候选的资料都能回答三个问题：许不允许用、从哪里来、撤回时影响谁。缺少任一答案即保持 `pending`，不下载、不入库。

## 2. Artifact Registry 表结构

| 字段 | 说明 |
|---|---|
| artifact_id | 稳定唯一 ID |
| name / version | 名称与版本（或 commit） |
| origin_url | 来源地址（离线来源写采集记录号） |
| license_text_ref | LICENSE / 数据条款原文保存位置与 hash |
| license_summary | 条款摘要（允许/禁止事项，逐条列出） |
| internal_grant | 内部授权证明（自研/内部资料必填） |
| pii_status | clean / redacted / pending / rejected |
| content_hash | 内容 SHA-256 |
| introduced_at | 引入位置（索引/数据集/配置路径） |
| status | pending / approved / rejected / withdrawn |

## 3. 登记规则（默认拒绝）

- 缺 LICENSE 或数据条款原文 → `pending`；
- SPDX `NOASSERTION` 或条款无法归类 → `pending`；
- 内部资料缺授权证明 → `pending`；
- 任何 `pending` artifact 的派生 case 同步 `pending`，不得进入正式评测或训练；
- 审批服务不可用（如采集网关返回 404/5xx）时保存原始错误，不绕过、不改全局配置，恢复后重新采集并 hash 固定。

## 4. 血缘记录

每个 artifact 维护血缘链：

```text
origin_url / 采集记录
  → 加工步骤（脱敏、切分、转换，各步工具与版本）
  → 入库位置（索引名 / 数据集路径）
  → 每步输出 hash
```

血缘链任一环缺失，artifact 不得置为 `approved`。

## 5. 撤回 / 删除影响图

登记撤回时需输出影响图：按 content_hash 定位受影响样本、chunk、索引快照与派生评测结论，逐项标记 delete / rebuild / invalidate，并保留执行记录。

## 6. 验收与证据

（骨架）登记表文件、NOTICE/LICENSE 原文目录、hash 校验命令与原始输出，随首个登记批次补录。

## 7. 回滚方式

登记表按版本管理；误登记撤回时整行标记 `withdrawn`（不删除历史行），派生物按第 5 节影响图执行回滚。
