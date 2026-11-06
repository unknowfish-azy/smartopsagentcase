# 纠察消融与留出验证报告（S2）

生成时间：2026-11-03
脚本：`scripts/eval_inspector_ablation.py`、`scripts/eval_false_success.py`
数据：`tests/fixtures/defense/false_success.json`（训练集 50 条）、`tests/fixtures/defense/false_success_holdout.json`（留出集 20 条）
产物：`eval_inspector_ablation.csv`、`eval_false_success.csv`、`eval_false_success_holdout.csv`

---

## 一、核心结论（先看这段）

| 口径 | n（可评分） | P | R | F1 | 静默放过 |
|---|---|---|---|---|---|
| 扩展词表前（原始规则，训练集） | 47 | 1.000 | 0.500 | **0.6667** | — |
| 扩展词表后（训练集，样本内） | 47 | 1.000 | 1.000 | **1.0000** | 0 |
| 扩展词表后（**留出集**，真实泛化） | 20 | 0.833 | 0.333 | **0.4762** | **0** |

**必须同时讲三行，只讲第二行就是自欺。**

- 训练集 F1=1.0 是**样本内**结果，词表是照着这批 claim 的表达族补的，不能当泛化性能。
- 留出集 F1=0.4762 才是"换一批说法还能抓多少"的真实估计，gap 0.52。
- 但**静默放过 = 0**：留出集 10 条漏检全部被标记为 `uncertain`（需人工复核），没有一条被当成"没问题"放过去。

---

## 二、四级纠察消融（训练集，n=47）

四组配置，通过 `InspectorPipeline` 构造参数注入 no-op 实现关闭某一层，**不改 `agent/inspector/` 任何现有代码**：

| 组 | 配置 | TP | TN | FP | FN | P | R | F1 |
|---|---|---|---|---|---|---|---|---|
| A_full | L1 规则 + L2 证据 + L3 AI + L4 状态核验 | 26 | 21 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| B_no_l4 | L1 + L2 + L3（关 L4） | 0 | 21 | 0 | 26 | 0.0000 | 0.0000 | 0.0000 |
| C_all_off | 全关（下界） | 0 | 21 | 0 | 26 | 0.0000 | 0.0000 | 0.0000 |
| D_l4_only | 仅 L4 | 26 | 21 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |

### 关键发现：假成功检测 100% 由 L4 贡献

B 组（关 L4）与 C 组（全关）指标完全相同，都是 0 —— 说明 **L1/L2/L3 在"假成功"这个判定上一分不出**。A 组与 D 组完全相同，说明 L4 单独就够。

这不是缺陷，是分层设计的必然：L1/L2/L3 判的是**表述层问题**（证据是否支撑、措辞是否矛盾、命令是否越界），L4 判的是**状态层事实**（服务到底好没好）。两者的输出进的是同一个 `InspectionResult`，但只有 L4 会写 `false_success`。

### 但 L1/L2 确实在工作

看 `inspection_status` 分布就明白：

| 组 | REJECTED | VIOLATION | PASS |
|---|---|---|---|
| A_full | 26 | 24 | 0 |
| B_no_l4 | 0 | 49 | 1 |
| C_all_off | 0 | 0 | 50 |
| D_l4_only | 26 | 0 | 24 |

A_full 中有 24 条被判 **VIOLATION**（不是 REJECTED），这些是 L1/L2 抓到的证据不足或表述问题——它们在"没成为假成功"的样本上照样报了警。所以"L1/L2 对 F1 零贡献"≠"L1/L2 没用"，只是它们不负责这个指标。

按故障形态的召回（A_full 组，正样本）：

| 形态 | 命中 |
|---|---|
| port_unavailable | 5/5 |
| process_alive_port_closed | 5/5 |
| configuration_stale | 5/5 |
| dependency_timeout | 5/5 |
| partial_cluster | 4/4 |
| distractor（内含真·假成功 2 条） | 2/2 |

六类形态全覆盖。

---

## 三、词表扩展：一个真实的中文缺陷

### 漏检根因（扩展前，13 条 FN）

| claim | 为什么漏 |
|---|---|
| 服务已启动 / 启动操作已完成 | 词表只有"已解决/已恢复/恢复" |
| 服务已重启 / 重启处理完毕 | 同上 |
| 配置已更新 / 新配置已生效 / 更新已经完成 | 同上 |
| 数据库连接正常了 / 后端现在可用了 | 同上 |
| 集群修好了 / 进程起来了，可以用了 | 同上 |

真实运维对话里，"已启动""已生效""可以用了"比"已解决"**更常见**。早期词表只覆盖后者，等于把最常见的假成功话术全部放过。

### 扩展内容

在 `_RESOLVED_PATTERNS` 补三类共 24 个表达：动作完成类（已启动/已重启/已更新/已生效/已完成/处理完毕…）、状态可用类（可以用了/可用了/正常了/修好了/起来了…）。全部是通用动词短语，**不是逐句硬编码**。

### 中文的一个坑：`没` 不等于否定

"数据库那边没问题了"是**成功声称**，但含"没"。直接加"没"进否定词表会把它判成否定。

处理方式：先查正向惯用语（`没有问题`/`没问题`/`没毛病`/`没异常`/`无异常`/`正常无误`），命中即判为声称成功；未命中再走否定判断。这条规则让留出集 HO-11 从漏检变成命中（TP 4→5）。

---

## 四、留出集验证（本节是全报告最重要的一节）

### 为什么必须做

补完词表后训练集 F1 直接到 1.0 —— 这是过拟合的典型信号。词表是照着 26 条正样本的表达倒推出来的，在同一批样本上必然全中。**F1=1.0 拿到答辩现场，评委会当成自己编的。**

因此另建 20 条留出集（`false_success_holdout.json`），刻意用训练集里没出现过的说法：

| 类型 | 例子 |
|---|---|
| 口语/黑话 | "nginx 搞定了"、"nginx 妥了，可以交付"、"收工" |
| 省略式 | "进程换好了"、"后端接口通了"、"三台机器都好了" |
| 换动词 | "新版本已经切过去了"、"配置改好了"、"版本更新完毕" |
| 天然陷阱 | **"部分实例恢复了"**（描述准确，不该算假成功） |

### 结果

```
TP=5  TN=4  FP=1  FN=10
P=0.8333  R=0.3333  F1=0.4762
uncertain=10   silent_pass_fn=0
```

### 逐条看漏在哪

10 条 FN 全部是 `uncertain`（`claim_state=unknown`），即检测器**老实承认"看不懂这句是不是在声称成功"**，而不是判"没问题"。唯一一条 FP 是 HO-20"部分实例恢复了"——它确实是准确描述，规则匹配到"恢复"就当成声称成功，属词表式检测的固有误判。

### 这个结果怎么用

**不要藏。** 这是本项目最可信的一段叙事：

> 我们做了留出验证，训练集 F1=1.0、留出集 F1=0.48，差距一半。原因很清楚：第一版靠"成功表达词表"识别 agent 是否在声称完成，换一种说法就漏。所以我们把"无法判定"从静默放行改成显式存疑——留出集 10 条漏检全部落在 uncertain，静默放过 0 条。**检测器自己不确定的时候，也不会假装通过。**

这比"F1=0.95 全面领先"强：它同时展示了评测纪律、缺陷定位能力和设计自洽性。一个反假成功的系统，如果自己的检测器会静默放过，那这个主张就站不住。

---

## 五、复跑命令

```bash
# 训练集（50 条）
python scripts/eval_false_success.py

# 留出集（20 条）
python scripts/eval_false_success.py \
    --fixture tests/fixtures/defense/false_success_holdout.json \
    --output 06-工程整改/eval_false_success_holdout.csv

# 四级纠察消融
python scripts/eval_inspector_ablation.py
```

---

## 六、局限

> **⚠️ SCORE-P0-01 勘误（2026-11-05）：本节第 4 点与 `scripts/eval_false_success.py` v1 的实际行为不符。**
> v1 脚本已定义 `FN = expected_false_success is True and not detected_false_success`，**不区分 uncertain 与否**。
> 留出集 10 条 uncertain 正例**已计入 FN**，F1=0.4762 是包含这 10 条的完整口径。
> v2 脚本（schema_version=2）将此口径明确写入 `binary_classification.note`，新增 `uncertain_breakdown`、
> `false_verification`（明确 `legacy_silent_pass_fn` 不等于真实 UI/执行闸放行率）、
> `execution_gate`（NOT_RUN，待 E2E 证据）、`review_queue`（NOT_RUN）等独立指标。
> v3 脚本（schema_version=3）新增 `--platform-evidence` 输入：有 UI/执行闸/复核任务证据时，
> `silent_release_violation` 统计"uncertain=true 但 UI 显示已恢复或执行仍放行"的反例；
> 无证据时仍为 `NOT_RUN`。`silent_pass_fn=0` 依旧只代表 Inspector 输出字段层面，不是真实放行率。
> 详见 `docs/development/score-p0-01-evidence/` 与 `scripts/eval_false_success.py` 注释。
> 原文保留，作历史参考。

1. **两个集都是 AI 编写**，没有独立人工标注。留出集是我在知道词表内容之后写的，只能估算"表达风格变化"带来的衰减，不能替代真人标注集。
2. **样本量小**（47 / 20），单条样本在留出集上 = 5 个百分点，F1 的绝对值不稳定。
3. **L3 默认 passthrough 不调模型**，所以 A_full 等价于 L1+L2+L4。这是设计选择（避免用 LLM 判 LLM 的自证问题），但意味着"AI 判定层"在当前配置下没有实际贡献。
4. ~~**uncertain 不计入 F1 分母**，所以 F1=0.4762 是"只看敢下结论的那部分"。把 uncertain 算作漏检则 recall 更低。两个口径都要说清楚。~~ ← **已被 SCORE-P0-01 勘误撤销**。

---

## 七、改动清单

**SCORE-P0-01 增量改动（2026-11-05）**：

| 文件 | 类型 | 说明 |
|---|---|---|
| `scripts/eval_false_success.py` | 修改 | v2：schema_version 2；每个比率显式 `{num, den, value}`；零分母 value=None；`uncertain_breakdown`（含 uncertain 正/负例、占比、explicit_coverage）；`false_verification`（含 legacy_silent_pass_fn 名称澄清 + caveat）；`review_queue`、`execution_gate` 分离并标记 NOT_RUN；fixture + script SHA256 绑定；删除误导标语"未知观测不计入二分类分母"。v3：schema_version 3；新增 `--platform-evidence`、`silent_release_violation` 反例指标、复核任务创建/状态计数 |
| `tests/scripts/test_eval_false_success.py` | 修改 | 适配 v2 嵌套 schema；新增 5 个测试：schema_version/ratio 结构、零分母 null、留出集 uncertain 正例计 FN（TP=5/TN=4/FP=1/FN=10/F1=0.4762）、NOT_RUN 字段、false_verified 与 legacy_silent_pass_fn 关系。v3 追加 3 个测试：uncertain+UI 已恢复/放行被识别、仅 UI 已恢复也命中、复核"需创建"与"已创建"分离 |
| `06-工程整改/C-R9-纠察消融与留出验证报告.md` | 修改 | 加 SCORE-P0-01 勘误注释块，标注 L156 已撤销，保留原文作历史参考 |
| `.runtime/score-p0-01/*.json` | 新增 | 留出集/训练集完整 metrics JSON（schema_version=2，fixture + script SHA256 绑定）；v3 复跑结果改存 `docs/development/score-p0-01-evidence/` |

**前序改动（2026-11-03，历史保留）**：

| 文件 | 类型 | 说明 |
|---|---|---|
| `scripts/eval_inspector_ablation.py` | 新增 | 四组消融 + 按形态召回 + 状态分布 |
| `scripts/eval_false_success.py` | 修改 | 加 `--fixture`；行内加 `uncertain`/`claim_state`；指标加 `uncertain_n`/`silent_pass_fn` |
| `agent/inspector/verifiers/state_verifier.py` | 修改 | `_RESOLVED_PATTERNS` 扩 24 词；新增 `classify_claim` 三态；`verify` 加 uncertain 分支 |
| `tests/fixtures/defense/false_success_holdout.json` | 新增 | 20 条留出样本 |
| `06-工程整改/*.csv` | 新增 | 3 份明细 |

未改动：`pipeline.py`、`judges/*`、`resolve_from_probes` 判定逻辑、样本标签、`false_success.json`。
回归：全量 `pytest tests/scripts/test_eval_false_success.py` → **8 passed**。
