# baseline-report 14 项指标收口说明

> 唯一口径文档。回答「评测基线是否收口」一律以本文件为准，不得凭记忆或重新盘点。
>
> 状态取值：`RUN`=本轮真实执行过（有实测数字）；`NOT_RUN`=未执行、无实测素材，**保持 null**；
> 引用规则沿用 `docs/competition/fact-sheet.md`：数字必须带 n 与状态，`NOT_RUN` 不得写成 0% 或「已达标」。

## 1. 本轮做了什么

缺口清单第三项「评测基线收口：baseline-report 14 项从 NOT_RUN → RUN」，拆成两件事：

1. **真实评测跑通并回填**（已完成）
   - 命令：`python ai-service/scripts/bench_llm_eval.py --provider ollama --model qwen3:1.7b --no-schema`
   - 产物：`data/training/eval/baseline-report.json`（status 由 `NOT RUN` → `RUN`）、
     `latest.json`、`report-2026-11-21.md`（后两者为运行产物，不入库）。
   - 口径：`experiment_id=EXP-LLM-BASELINE-2026-11-21`、`dataset_version=smartops-eval-v1`、
     `data_class=SYNTHETIC`、`case_count=32`，用例四类各 8 条（counter/gap/guard/normal）。
   - 约束来源：`.trae/documents/LLM蒸馏与换底座-DS-01至DS-08实施计划.md`（「不新增字段；status 写 RUN」）。

2. **LoRA 实验入 training_ledger**（已完成，非本轮重做）
   - 已在 MySQL 台账核实：`training_run` id=8 FAILED / id=9 COMPLETED（train_loss 0.0583）、
     `evaluation_run` id=14 pass_rate=0.4375 / id=15 pass_rate=0.7188、`training_dataset` id=22（32 条）。
   - 验收记录：`.trae/documents/DS-06-LoRA训练与评测验收记录-2026-11-19.md`。
   - 结论：**无需重做**；LoRA 有增益但未达 ≥0.75 目标，如实保留。

## 2. 14 项逐项口径（这是收口的实质）

| # | 指标 | 值 | n / 状态 | 说明 |
|---|---|---|---|---|
| 1 | task_success | **0.4688** | 15/32，`RUN` | 逐用例全断言通过率（含 verdict、必引引用、禁用标记、护栏） |
| 2 | root_cause_accuracy | **null** | `NOT_RUN` | 用例 `expect` 无 `root_cause` 真值，无机判素材 |
| 3 | evidence_accuracy | **0.8125** | 26/32，`RUN` | 未出现 `must_cite` / `forbidden_ref` 失败的比例 |
| 4 | tool_accuracy | **null** | `NOT_RUN` | 用例无 `tool`/`next_tool` 真值 |
| 5 | risk_accuracy | **null** | `NOT_RUN` | 用例无 `risk` 真值 |
| 6 | approval_accuracy | **null** | `NOT_RUN` | 用例无 `approval` 真值；真实来源为 `agent_run` 导出（未导出，见 fact-sheet M09） |
| 7 | verification_success | **null** | `NOT_RUN` | 用例无 `verification` 真值 |
| 8 | inspector_precision | **null** | `NOT_RUN`（本报告口径） | 真实值在另一实验，见下方 §3 |
| 9 | inspector_recall | **null** | `NOT_RUN`（本报告口径） | 同上 |
| 10 | hallucination_rate | **0.0** | 0/引用总数，`RUN` | 幻觉引用数 / 引用总数 |
| 11 | false_success_rate | **0.2083** | 5/24，`RUN` | 期望非 SUPPORTED 的用例中模型仍判 SUPPORTED 的比例 |
| 12 | safety_violation_rate | **0.0** | 0/32，`RUN` | 触发禁用动作标记 / 总用例 |
| 13 | latency | **5454.8 ms** | P? 非分位，`RUN` | **单次均值**，n=32，**不是** p50/p95，不可当 SLO |
| 14 | token_cost | **null** | `NOT_RUN` | Ollama 响应确实返回 `prompt_eval_count`/`eval_count`（已实测），但 runner 未采集；需接线后补 |

**诚实交底**：14 项中 **6 项有真实值**，其余 8 项因**无用例真值或未采集**而保持 null。
这是当前真实边界，**不是**「已收口到 14 项」。任何材料引用时必须说清这一点。

## 3. 为什么不把受控集基线的数字填进来

`reports/baseline-controlled-v1.json`（`EXP-BASELINE-001`）确实有 inspector 的 P/R/F1=1.0000，
但它与本次 LLM 基线**不是同一个对象**，且已被事实清单降级，填入即构成误导：

- `is_llm=false`：那是**确定性 Inspector 流水线**（Rule+Evidence+AI降级+StateVerifier），
  不是 LLM 判定评测；混填等于把两条链路的分数并成一个数。
- `fact-sheet.md` M20 明确标注**效度降级**：可判子集 n=22 中**有效 n ≤ 4**（主终点二分类子集只覆盖
  4 个 `root_cause_group`，DEFF=6 → n_eff≈8），且**平凡规则即可复现 22/22**、反极性 0/22，
  属循环成立。该指标「**不得**写成假成功检测能力证据」。
- 因此 inspector_precision/recall 在本报告保持 null，其真实出处单列于此，供需要时引用：
  `EXP-BASELINE-001`，P=1.0000（12/12）/ R=1.0000（12/12）/ n=22，状态
  `COMPLETED_WITH_LIMITATIONS`，**有效 n 上界 4**，不得作为泛化性能。

## 4. 门禁口径修正（本轮附带修复）

`training/gate_report.py` 原判定要求 `baseline.status == "COMPLETED"`，而 DS-02 实施计划规定真实
评测回填时 `status` 写 `RUN`——两者矛盾会让门禁对 evaluator/baseline 恒为 BLOCKED。

修正为接受 `RUN` 或 `COMPLETED`：
- 未跑过的基线仍是 `NOT_RUN` → 依旧 BLOCKED，**不会**把「未执行」写成达标；
- 修正后重跑 `python -m training.gate_report`，evaluator/baseline 两项转 READY，
  但整份门禁仍应为 **BLOCKED**（数据未批准 approved=0、缺训练依赖 datasets/peft/trl），
  `training_allowed=false` 不变。**门禁整体状态没变，只是两项子判定与事实对齐。**

## 5. 后续真正收口所需的条件（未完成，如实登记）

| 缺口 | 需要的外部条件 |
|---|---|
| root_cause / tool / risk / approval / verification 五项 | 需带这些字段真值的任务化样本（当前用例只有 verdict + 引用约束），或接入真实 `agent_run` 账本导出 |
| token_cost | runner 侧接线采集 Ollama `usage`（响应已具备该字段），无需外部条件，属可立即补齐项 |
| inspector P/R 并入本报告 | 需先解决 M20/M31 的效度问题，否则只能继续单列 |

## 6. 引用方式（唯一合法表述）

> 本轮在 32 条 DS-02 机判用例上以 qwen3:1.7b 跑出 LLM 判定基线（`EXP-LLM-BASELINE-2026-11-21`，
> status=RUN）：任务成功率 0.4688、证据准确率 0.8125、幻觉率 0.0000、假成功率 0.2083、
> 安全违规率 0.0000、单次平均时延 5454.8ms。其余 8 项因无用例真值或未采集保持 NOT_RUN（null），
> 未作任何填充。Inspector 精确率/召回率的真实实测来自另一确定性管线实验（n=22，有效 n 上界 4）。

**禁止**：把 6 项说成「14 项全部收口」；把 null 写成 0；把受控集 P/R=1.0 说成本次 LLM 基线成绩。
