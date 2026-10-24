# Phase 7.2 实验链路状态

本文件记录 Phase 7.2 的真实前置状态，不代表已经完成模型训练或真实实验。

当前门禁顺序为：Candidate -> Validation -> Quality -> Safety -> Leakage -> Human Review -> Split -> Evaluator -> REAL Model -> Baseline -> Ablation。

截至本阶段检查：

| 项目 | 状态 | 说明 |
|---|---|---|
| 本地代码测试 | PASS | Training、Knowledge、Inspector 测试已通过 |
| Candidate Dataset | BLOCKED | 尚无候选文件进入 `data/training/candidates/` |
| Human Review | NOT_RUN | 审核 CLI 仅提供显式单条操作，不自动审核 |
| Approved Dataset | BLOCKED | 0；禁止训练 |
| Train/Validation/Test | NOT_READY | 0/0/0 |
| Safety | NOT_RUN | 没有可审核样本 |
| Leakage | NOT_RUN | 没有可切分数据 |
| Evaluator | NOT_READY | 已提供结构化 Ground Truth 评估原语，尚无 Golden Set 执行结果 |
| REAL Model | BLOCKED | 当前为 Mock 或缺少人工配置/连通性 |
| Prompt/Real Baseline | NOT_RUN | 不得使用 Mock 生成真实基线 |
| RAG/Inspector/Verification | NOT_RUN | 必须在 Real Baseline 后执行 |
| SFT/DPO | BLOCKED/NOT_READY | 未满足数据、模型、评估和硬件门禁 |

新增工具：

- `python -m training.scripts.review_dataset --list`
- `python -m training.scripts.review_dataset --sample <id>`
- `python -m training.scripts.review_dataset --approve <id> --reviewer <id> --reason <text>`
- `python -m training.scripts.check_model`
- `python -m training.scripts.phase_status`

所有审核动作都要求明确的 reviewer 和 reason；所有未执行实验保持 `NOT_RUN`，不会用 0 代替。
