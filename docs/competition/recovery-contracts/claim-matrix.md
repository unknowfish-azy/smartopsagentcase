# 恢复契约主张矩阵

原则：每条主张都必须能指到源码位置与可复核实验；没有收益数字就保持 `null`；证据不足写 `UNKNOWN`，不写“已实现”。

| # | 主张 | 判定 | 证据 | 边界 |
|---|---|---|---|---|
| 1 | HTTP 200 / 自检 passed / 有观测都不能证明业务恢复 | 可讲 | N08 `trap-200-passed-business-false`：三条弱基线全部 VERIFIED，实现与 oracle 判 CONTRADICTED | 冻结证据回放 |
| 2 | 恢复判定应按义务拆成 TRUE/FALSE/UNKNOWN，反例优先 | 可讲 | `evaluator.py` 义务求值；`semantics.md` §3 | 仅限已登记谓词模板 |
| 3 | 窗口不满足（偏斜/间隔/组数/同组 target）不得签发 | 可讲 | `semantics.md` §4.2；N08 四个边界案例；HC-11 A 场景首末约 4.9s | 3 组 × A/B 冻结参数 |
| 4 | 非 VERIFIED 一律 `NOT_ISSUED`，回执有效期取 min | 可讲 | `receipts.py`；HC-11 B/C/D | 机制层 |
| 5 | 同证据差分回放能复现历史失败，缺证据诚实报 INCOMPLETE | 可讲 | `replay.py`；HC-11 D；100 次重放一致 | 不补探、不预测修复 |
| 6 | 独立 oracle 能证伪候选实现 | 可讲（有限） | N08 修复后实现假 VERIFIED 0/42，一致 41/42 | oracle 与实现同一协调者编写 |
| 7 | 调度策略比同预算固定顺序更省调用 | **不可讲** | 无对照实验，收益数字 `null` | 需同预算 A/B 实验 |
| 8 | 真实平台闭环 / 真实修复成功 | **不可讲** | N06 BLOCKED；动作轴 `NOT_PERFORMED` | 需平台门禁与真实 E2E |
| 9 | 业界首创 / 第一 | **不可讲** | N00 检索 `NOT_RUN` | 查重前禁止 |
| 10 | 前端三张卡可直接上线 | **不可讲** | 仅 fixture 与组件测试，未接 API/E2E | 依赖 N06 |
