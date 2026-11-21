# DATA CARD · SmartOps 受控数据集 v1（Controlled/v1）

> 版本：v1 ｜ 冻结日期：2026-11-20 ｜ 维护者：SmartOps Agent 数据治理
> 契约：`schema.json` ｜ 样本：`samples.jsonl` ｜ 切分：`splits/`
> 指纹：`samples.md5 = bd8df5f5cf672ad42894429459ad37f21c38f4988707f842b2772b91c60206d1`

---

## 1. 这个数据集是什么，不是什么

**是**：一个用于验证「运维 Agent 状态断言真伪」的受控样本集。每条受控样本给出
一条 Agent 可能说出的断言（`claim`）、判定标签（`ground_truth.label`）与一组
可判定的状态探针（`state_assertions`），可用于检验假成功（false success）识别、
失败识别与证据不足时的拒判能力。

**不是**：
- 不是真实生产事件集合，**不能**用来声称真实场景准确率；
- 不是训练集。样本为合成 fixture，禁止用于训练或调参后再报同一集合指标；
- 不是红帽教材（RH124/RH134/RH294）内容的衍生——那属「Internal use only」许可违规，本集不含；
- 不是「已复核 Golden」。全部样本 `review_status=unreviewed`、`human_review=PENDING`。

## 2. 规模与构成

| 类别 | 条数 | 说明 |
|---|---|---|
| 受控 verification | **144** | 24 个 `root_cause_group` × 6 变体，全部带 `ground_truth` + 非空 `state_assertions` |
| 领域 DRAFT | **14** | 由 `SmartOps-Dataset/Linux/*.jsonl` 转换，**无状态断言**，`label=UNKNOWN` |
| **合计** | **158** | |

故障族分布（受控部分，每族 24 条）：`F-NET` / `F-HTTP` / `F-L4` / `F-DB` / `F-SSH` / `F-CONF`。

标签分布（受控部分）：

| 标签 | 条数 | 占比 | 语义 |
|---|---|---|---|
| `FALSE_SUCCESS` | 48 | 33.3% | 断言声称成功/恢复，探针显示未恢复 |
| `SUCCESS` | 36 | 25.0% | 断言与探针一致 |
| `FAILED` | 30 | 20.8% | 断言声称故障/异常，探针确认异常存在 |
| `UNKNOWN` | 30 | 20.8% | 证据不足，禁止确定性结论 |

> 标签体系是**四段式**（SUCCESS / FALSE_SUCCESS / FAILED / UNKNOWN），与
> `docs/experiments/dataset-specification.md` 的 State Verifier 角色一致。

## 3. 来源与许可

| 类别 | `source_type` | `data_class` | 许可 | PII |
|---|---|---|---|---|
| 受控 144 条 | `synthetic_dev` | `SYNTHETIC` | `MIT-synthetic` | 无 |
| 领域 14 条 | `user_provided_course_summary` / `ai_authored` | `DEMO` | `CC-BY-4.0-teaching` | 无（占位符 `CLEAN_TRAINING_PLACEHOLDER`） |

- 合成样本由 `scripts/build_controlled_dataset.py` 以固定规则生成，不含任何真实主机名、
  IP 归属或凭据；`10.0.0.0/8`、`172.16.0.0/12` 为 RFC1918 私网示例地址。
- 领域样本来自用户提供的课程总结与 AI 增强，仅作教学演示，**不得**当作真实运维记录。
- 复用红线：引用本集必须同时给出 `n` 与标签分布，禁止只报有利子集（对齐 fact-sheet 红线②）。

## 4. 标注协议

对齐 `docs/development/P0-DATA-01-Golden标注协议-v1.md`：

- **故障族**：6 族，每族 4 个 `root_cause_group`，共 24 组（组名即根因键）。
- **oracle_health**：合成 fixture 一律 `degraded`（协议 §5.1：synthetic 非真实业务观测）；
  领域 DRAFT 为 `insufficient`（无 probe 证据）。
- **proof_sufficient**：受控样本 `partial`（有 probe 但无真实 runbook）；
  UNKNOWN 样本 `no`；领域 DRAFT `no`。
- **双标一致率**：**未执行（NOT_RUN）**。协议要求 ≥2 名独立标注者、核心字段一致率 ≥90% 或
  Cohen's κ ≥0.75。本集为单人生成的合成 fixture，`quality.review_status=unreviewed`，
  因此**不声称**达到该一致率门槛。这是本集最大的未满足项。
- **盲评包已就绪（2026-11-20）**：`review/pack.jsonl`（144 条，**不含 ground_truth**，
  符合协议 §7）、`review/ratings_A.csv` / `ratings_B.csv`（空白评分表），
  pack sha256 = `ae9161dff8cd577c6b35da4d5d1c881ae3371c5fb39078f2c1f0bc1fc091b4ea`。
  执行：`python scripts/dataset_approval_gate.py --score --a <A.csv> --b <B.csv>`。
  脚本在无人工评分时输出 `NOT_RUN`，**不会**用构造标签冒充复核结果。
- **三维隔离**：按 family + environment + version 隔离，由切分协议保证不跨 split。

### 4.1 探针期望的语义位（2026-11-21 增补）

`state_assertions[*].expected` 的取值是**观测快照**，不含判断逻辑；健康与否由归一化层
（`agent/inspector/adapters/controlled_probe.py`）按下列语义位判定。为消除歧义，builder 显式写出以下位：

| 探针 | 语义位 | 含义 |
|---|---|---|
| `port` | `occupied: true` | 端口**仍被占用**（假成功证据），与「服务在监听」相反；缺省仍按 `open` 判 |
| `config_value` | `expect: true` + `value` | 「该键应等于 value」，任意配置项均可机检；无此位且无内置规则的键 → `error=fail-closed` |
| `http_status` | `expected_status` | 「此路径应返回该码」，命中即健康；用于「旧接口已下线 → 404 是预期」。未声明时回落默认 2xx/3xx 规则 |

> 变更原因：早期版本只写 `{status: 404}` / `{value: 8}` / `{open: true, owner: ...}`，
> 归一化层无法区分「接口缺失=好」与「服务故障=坏」、「配置符合预期」与「不可机检」，
> 导致翻译忠实性仅 0.8125。补语义位后为 **1.0000（144/144）**。
> 指纹随之更新，见 `samples.md5`。

## 5. 切分协议

- **原子分组键**：`metadata.root_cause_group`。同组样本永不跨 split。
- **双向分层**：按 `metadata.family` × `ground_truth.label` 分层，固定种子
  `20261120`、200,000 次确定性随机搜索求均衡分配。
- **领域 DRAFT** 14 条整体进 `train`，不参与验证性能。

| split | 总条数 | 受控 | 领域 | group 数 | 标签分布 |
|---|---|---|---|---|---|
| train | 62 | 48 | 14 | 9 | SUCCESS 12 / FALSE_SUCCESS 18 / UNKNOWN 12 / FAILED 6 |
| validation | 48 | 48 | 0 | 8 | SUCCESS 12 / FALSE_SUCCESS 18 / UNKNOWN 6 / FAILED 12 |
| test | 48 | 48 | 0 | 8 | SUCCESS 12 / FALSE_SUCCESS 12 / UNKNOWN 12 / FAILED 12 |

**泄漏检查（MEASURED）**：`python scripts/run_leakage_check.py`

- 分组切分正例：`PASS`（exact / scenario / evidence / root_cause / environment / version 六类键命中数全 0）。
- 随机切分负对照：`LEAKAGE_DETECTED`（scenario_duplicate 34、root_cause_leakage 24、
  environment_leakage 35、version_leakage 24）——证明检查器对分组破坏敏感，正例 PASS 不是恒真。
- 报告：`reports/leakage-grouped.json`、`reports/leakage-random-negative-control.json`、`reports/leakage-summary.md`。

## 6. 统计效能与精度（重要）

完整推导见 `reports/power-dataset-sizing.md`（`python scripts/dataset_power_sizing.py`）。

- 现有 n=14 的 M01 Recall@3=0.5000，Wilson 95% CI = **[0.268, 0.732]**（宽度 0.464）——
  不足以支撑任何准确率结论。
- 达到 ±0.10 精度（p=0.5）需 **n=97**（未计聚类）；本集 144 条受控在分组设计
  ICC=0.10（DEFF=1.40）下有效 n≈103，E≈**±0.096**，达到 ±0.10。
- 达到 ±0.05 需 **n=385**（未计聚类；ICC=0.10 时 539 条）——**后续目标，本集未达到**。
- 因此本集的定位是：把「链路打通」升级为「可给出带区间的量化指标」，
  而**不是**「精度已达标」。引用任何比例必须附 Wilson 区间与 n。

## 7. 已知局限（必须随引用一并呈现）

1. **合成分布**：144 条受控样本由模板生成，探针取值是构造的，不代表真实故障分布；
   禁止用本集指标推断生产性能。
2. **无人工复核**：`review_status=unreviewed`，未做双标，未计算 Cohen's κ。
3. **组内相关未测**：同组 6 条变体共享场景模板，存在正相关；ICC 未知，只能给敏感性区间。
4. **近重复未查**：`leakage_checker` 未实现 token 近重复分析，`near_duplicate` 恒为 0；
   本集 PASS 不代表语义近重复已排除。
5. **领域 DRAFT 混入 train**：14 条无 probe 样本在 train 中，会拉低 train 侧任何
   「无证据结论」比例，报指标时应按 `dataset_type` 分层。
6. **UNKNOWN 占比 20.8%**：证据不足样本比例偏高，会压低任何「结论率」型指标。
7. **标签不均衡**：FAILED 组只有 5 个，train 仅 6 条 FAILED；小类指标的区间会更宽。

## 8. 复现

```bash
# 1) 样本量测算
python scripts/dataset_power_sizing.py

# 2) 构建受控集（158 条）
python scripts/build_controlled_dataset.py
python scripts/build_controlled_dataset.py --check          # 校验冻结指纹

# 3) 分组切分（双向分层，种子 20261120）
python scripts/split_controlled.py

# 4) 泄漏检查（正例 PASS + 负对照 LEAKAGE_DETECTED）
python scripts/run_leakage_check.py

# 5) 门禁测试（9 条）
python -m pytest tests/scripts/test_controlled_dataset.py -q
```

任何一步失败即视为本次发布无效，不得以部分产物对外引用。

## 9. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-11-20 | 首版：144 条受控 verification（6 族 × 4 组 × 6 变体）+ 14 条领域 DRAFT；分组切分；leakage_checker 由 NOT_RUN 转 MEASURED。指纹 `bd8df5f5…`（已作废）。 |
| v1.1 | 2026-11-21 | **探针期望补显式语义位**（`port.occupied` / `config_value.expect+value` / `http_status.expected_status`），消除「404 是好是坏」「配置是否符预期」的歧义；同步修正归一化层两处极性错误（systemd `active`、低阈值型 metric）。翻译忠实性 **0.8125 → 1.0000（144/144）**，基线可判子集 FP 由 10 → 0。样本内容与标签分布不变，指纹更新为 `0fce52a1…`。 |
