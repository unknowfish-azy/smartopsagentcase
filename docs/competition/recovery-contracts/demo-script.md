# 恢复契约答辩演示动线

演示基于已跑通的 HC-11 loopback 证据与 N08 冻结案例；不启动平台服务、不执行任何真实修复或审批。

## 0. 一句话开场

“我们演示的不是‘服务起来了’，而是**在什么条件下才允许说业务已恢复**，以及条件不满足时如何诚实拒发结论。”

## 1. 六步动线

| 步 | 动作 | 展示内容 | 证据 |
|---|---|---|---|
| 1 | 展示“200 + passed=true + 业务 false” | 三条弱基线判 VERIFIED，契约判定 CONTRADICTED | N08 `trap-200-passed-business-false` |
| 2 | 打开缺口卡 | 逐义务 TRUE/FALSE/UNKNOWN、原因码、被拒证据 | `GapCard.vue` + `frontend/test/recovery` |
| 3 | 展示窗口不满足 | 偏斜/间隔/组数边界都返回 INSUFFICIENT/MISSING，不签发 | N08 边界案例；HC-11 C 场景（HTTP 502） |
| 4 | 展示回执 | 仅全 TRUE + 窗口满足才 `ACTIVE`；其余 `NOT_ISSUED` | `receipts.py`；HC-11 A/B/C |
| 5 | 展示同证据回放 | r17→r16 回放复现失败，差异码可见；缺探针报 INCOMPLETE | `replay.py`；HC-11 D；100 次一致 |
| 6 | 展示独立 oracle 对照 | 修复后实现假 VERIFIED 0/42；与 oracle 一致 41/42 | `docs/evaluation/recovery-contracts/n08-report.md` |

## 2. 现场命令

```powershell
python scripts/research/recovery_contract_demo.py
```

预期：退出码 0；A=`VERIFIED`/`ACTIVE`，B=`CONTRADICTED`/`NOT_ISSUED`，C/D=`INSUFFICIENT`/`NOT_ISSUED`；stub 请求增量为 0（回放不补探）。

```powershell
python scripts/research/recovery_contracts/run_experiments.py
```

预期：退出码 0；实现假 VERIFIED 0/42；输出 `.runtime/n08/summary.md`。

## 3. 必须说明的边界

1. HC-11 是 `127.0.0.1` loopback，不是生产平台链路；平台接入（N06）仍 BLOCKED。
2. 动作轴未执行：没有真实修复、没有审批闭环。
3. 调度成本优势未验证：不宣称优于固定顺序。
4. 回放缺录制探针时只报 `REPLAY_INCOMPLETE`，不自动补数据。
5. `passed` 只作为纠察轴原值展示，不能替代恢复轴。

## 4. 收尾

“这套机制的价值不是多一个页面，而是把‘恢复’从一句口头结论变成**可复核、可证伪、可拒绝签发**的证据义务；不满足时就明确说不足。”
