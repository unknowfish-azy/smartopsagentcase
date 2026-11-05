# Synthetic Cases 冻结令（DATA-P0-01）

日期：2026-11-05  
冻结者：DATA-P0-01（协议负责人，非人工批准人）  
状态：**FROZEN**（冻结不代表批准使用；ART-007/008 已登记 APPROVED 作受控 prototype，但 formal 人工 Golden 仍 BLOCKED）

## 1. 冻结范围

| 资产 | 路径 | SHA-256 | 条目数 | Oracle |
|---|---|---|---:|---|
| 合成主集（ART-007） | `tests/fixtures/defense/false_success.json` | `28c757cdabcfd24d69e27cb4bc3abdbd185d793ea3d5dbe4340093cacf86d45a` | 50 | degraded（synthetic） |
| 留出集（ART-008） | `tests/fixtures/defense/false_success_holdout.json` | `424a636a2c6d0d02e329247138953478aa4e467d6505de1ce87e9ffa1094a304` | 20 | degraded（synthetic） |

冻结依据：两个 fixture 文件的 SHA-256 在 FCT-P0-01 审计时已记录，SCORE-P0-01 已用它们生成 v2 metrics（schema_version=2）。**任何修改这些文件的行为都违反冻结令**。

## 2. Case 分布

从 SCORE-P0-01 基线（fixture_sha256=28c757cd…）：

| 分布 | 主集 50 条 | 留出集 20 条 |
|---|---:|---:|
| expected_false_success=True（正例） | 36 | 15 |
| expected_false_success=False（负例） | 14 | 5 |
| unscored（expected=null） | 3 | 0 |
| 类别覆盖（6 类 + distractors） | 全部 | 全部 |

## 3. SCORE-P0-01 基线结果（冻结快照）

**主集 50 条**：TP=26, TN=21, FP=0, FN=0, F1=1.0, uncertain=0, silent_pass_fn=0
**留出集 20 条**：TP=5, TN=4, FP=1, FN=10, F1≈0.4762, uncertain=10, silent_pass_fn=0

留出集 10 条 uncertain 正例已计入 FN，不在 F1 分母外排（DATA-P0-01 §5 Oracle 冻结口径）。

完整证据：`.runtime/score-p0-01/holdout-metrics.json`、`.runtime/score-p0-01/train-metrics.json`

## 4. 冻结边界

| 允许 | 禁止 |
|---|---|
| 受控机制验证（Inspector 版本比较、StateVerifier 版本比较、恢复契约消融、目标/时效/版本/窗口/调度消融） | 宣称等效人工 Golden |
| 比较完整 Inspector + StateVerifier 与增加恢复契约的版本 | 把 synthetic 结果外推到真实业务效果 |
| 同预算固定顺序的独立 Oracle 验证 | 用 synthetic case 作正式评测分母 |
| RAG 评估辅助线索（不影响真实召回率评估） | 据此宣称调度优于同样 6 次调用的专家 SOP |

## 5. 验证脚本

```powershell
# 验证 fixture hash 未变
python -c "
import hashlib, pathlib
for p in ['tests/fixtures/defense/false_success.json',
         'tests/fixtures/defense/false_success_holdout.json']:
    h = hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
    print(f'{p}: {h}')
"
# 输出必须与本节 SHA-256 完全一致
```

## 6. 后续

- DATA-P0-01 继续负责：**人工 Golden 采集**（需 2+ 独立标注者 + 30+ case 的 oracle_health=complete）
- P0-DATA-02 负责：**RH 许可违规处置**（移除 RH124/RH134/RH294 + 重建 manifest）
- SCORE-P0-01 已完成 v2 协议，后续评测消费它

冻结令签署人：DATA-P0-01 协议负责人（非人工批准人）。正式 Golden 冻结需人工负责人签字——当前 synthetic 冻结是受控 prototype，不替代人工批准。
