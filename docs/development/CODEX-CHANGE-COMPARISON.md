# Codex 修改前后变化对照

> 项目：智维Agent / SmartOpsAgent  
> 建立日期：2026-09-18  
> 用途：持续记录 Codex 对项目文件的真实修改，便于代码审查、回归验证和比赛材料追踪。

## 记录规则

每次修改按阶段追加，至少记录：

1. 修改文件及修改类型。
2. 修改前的真实状态。
3. 修改后的真实状态。
4. 修改原因和影响范围。
5. API、数据库及配置兼容性。
6. 实际运行的验证命令和结果。
7. 未运行、失败或跳过的项目及原因。

严禁把未执行的测试写成 `PASS`，严禁把 Demo、Mock 或 Synthetic 数据写成真实生产数据。

## 基线限制

> 历史说明：本节及下文 2026-09-18 的“不是 Git 工作树”等表述仅描述当日环境。2026-11-03 已确认本目录为 Git 工作树，HEAD 为 `48b8af4`；本轮整改基线和验证结果见文末新增章节。历史测试数字不代表当前代码全部通过。

当前 `D:\SmartOpsAgent` 不是可识别的 Git 工作树，无法通过 `git diff` 自动恢复完整的历史文件版本。因此：

- 2026-09-18 Phase 0 的“修改前”内容来自 Codex 修改前读取到的原文件。
- 对照记录只描述能够从该次读取、修改操作及测试命令中确认的变化。
- 不推断或伪造更早的代码版本、作者或修改时间。
- 后续若恢复 Git 仓库，应优先使用提交哈希和 `git diff` 作为对照证据。

---

## 2026-09-18 / Phase 0：Current State 更新

### 变更摘要

| 项目 | 内容 |
|---|---|
| 修改文件 | `docs/architecture/current-state.md` |
| 修改类型 | 文档更新 |
| 新增文件 | 无 |
| 删除文件 | 无 |
| API | UNCHANGED |
| 数据库 | UNCHANGED |
| 业务代码 | UNCHANGED |
| 密钥与密码 | 未填写、未修改、未输出 |

### 修改前

原文档主要记录 2026-09-17 的修复结果和简要技术状态：

```text
# SmartOpsAgent 当前项目真实状态

> 生成时间：2026-09-17
> 目的：Phase 0 项目扫描与现状分析，记录真实可验证状态，不包含虚构结果。
```

## 最终建议（基于当前真实状态）

1. **先补齐可运行的评测输入，再训练模型**：当前 7 个训练目录均为 `DRAFT`，样本数为 0；Baseline 报告为 `NOT RUN`。下一步应先导入经过人工审核、来源可追踪的 REAL 或明确标记的 SYNTHETIC 样本。
2. **保持质量门禁顺序**：Schema Validation → Rule/Safety Validation → 去重 → Grouped Split → Leakage Check → Human Review。未通过 `APPROVED` 的样本不得进入正式训练集。
3. **先做 Baseline，再做 SFT/DPO**：在真实模型、评测集和 evaluator 可用前，不应宣称 Accuracy、Precision、Recall、Loss 或模型提升。
4. **安全配置继续手动维护**：密码、API Key、Internal Token、AES-GCM 密钥只写入本地 `.env`，不得写入仓库、Markdown、Dataset、日志或报告。
5. **优先完成 Inspector/Verification 数据闭环**：把 Agent Trace → Inspector → Human Review → Training Candidate 打通，这比直接启动 GPU 训练更能形成可审计的比赛证据链。
6. **处理环境型 skipped**：最新根回归为 `86 passed / 24 skipped`；跳过项涉及服务未启动、`SMARTOPS_AGENT_URL` 未设置及缺少可选依赖，应在目标环境具备后重新运行并保留真实结果。
7. **前端构建已恢复但仍需性能收口**：构建通过，同时保留主 chunk 过大的警告；后续可做路由级懒加载和按需拆包，但不应改变现有 API 契约。

### 当前结论

```text
代码与文档增量变更已记录
API：未破坏，训练能力为新增
训练数据：DRAFT / 0 samples
Dataset Validation：PASS（质量状态 NOT RUN）
Baseline Evaluation：NOT RUN
训练与 GPU：NOT RUN
根回归：86 passed / 24 skipped
```

## 2026-09-18 / Phase 1 最新复核：最终代码与功能对照

> 当前项目没有可用 Git 历史，因此“修改前”依据 Phase 0 扫描记录和修改前读取到的行为；本节不声称存在可恢复的逐行历史 diff。

### 模块对照

| 模块 | 修改前 | 修改后 | 兼容性/证据 |
|---|---|---|---|
| Shell Tool | `subprocess.run(..., shell=True)`，仅检查首 token | 拒绝管道、重定向、命令替换、`;`、`&&`、`||` 和换行；`shlex` 转 argv；allowlist、超时、输出截断、`shell=False` | 既有只读定位保留；安全测试覆盖注入场景 |
| Model Runtime | 匿名请求可能返回包含解密密钥的 Entity | 保留原 Runtime URL/Method；Internal Token；仅返回非秘密 DTO | 明文、密文和解密字段不出 DTO |
| Model 调用 | AI Service 需要获取运行时秘密 | 新增受保护 `POST /api/model-connections/{id}/invoke`；Backend 内存中解密并代理 Provider | AI Service 不接收 API Key |
| Backend Security | `/api/**` 统一匿名放行 | PUBLIC/USER/INTERNAL 分类；Runtime、Invoke、Inspector 写入由 Internal Token 过滤 | USER 端点为兼容现状暂保留匿名 |
| Inspector | Python Pipeline，无 DB/API/UI 持久化链路 | Trace → Inspector → Agent adapter → DB → API → Vue Center/Detail/Statistics | 新增 7 个 Inspector API |
| Frontend 请求层 | 两套 Axios 实例 | `http.js` 兼容导出 canonical `utils/request.js` | 生产构建实测通过 |
| Frontend 产品页面 | Inspector、Trace、Knowledge Evidence、Model Health 不完整 | 新增懒加载路由、Inspector 9 组件、Agent Command Center、Execution Trace、Knowledge、Model Health | 无数据显示空态/N/A/NOT RUN |
| Database | `server`、`server_metric`、`model_connections` | additive migration 新增 4 张 Inspector 表 | 既有表未删除或重命名 |
| Training/Evaluation | 无统一训练质量门禁 | 保留 `date/`；新增 `data/training/`、Validator、dry-run、NOT RUN Evaluation | 不伪造指标 |
| Configuration | 缺少统一手动配置手册和检查 | 新增手册及 Windows/Linux check-config | 不写入或打印敏感值 |

### 关键行为对照

`agent/tools/shell.py`：由字符串 Shell 执行改为危险元字符拒绝、allowlist/参数校验、argv 和 `shell=False`，保留 timeout、输出上限及结构化结果。

Model Runtime：缺失 Token 返回 401、错误 Token 返回 403、服务端未配置返回 503；响应不含 `apiKeyCiphertext`、`apiKeyPlaintext` 或解密 Key。Invoke 由 Backend 代理 Provider，AI Service 只接收模型结果。

Inspector：事件的 `metadata_json` 与验证 `details_json` 在 API 边界解析为对象；事件、Issue、Evidence、Verification 分表持久化，前端展示时间线、证据、风险、决策和验证。

### API 与数据库结论

- 既有 Server、Metric、Chat、Knowledge、Model Connection URL/Method 未修改。
- 新增 Inspector API 及 Model Invoke 代理 API，均为增量接口。
- 既有业务表未删除；Inspector 使用 additive migration。

### 最终真实验证

| 命令 | 结果 |
|---|---|
| `python -m pytest -q` | PASS：43 passed，24 skipped |
| `cd backend && mvn test` | PASS：27 tests，0 failures，0 errors，0 skipped |
| `cd ai-service && python -m pytest app/tests -q` | PASS：8 passed，2 warnings |
| `cd knowledge && python -m pytest -q` | NOT RUN：0 tests collected |
| `cd frontend && npm run build` | PASS：1736 modules transformed；主 chunk > 500 kB 警告 |
| `python -m pytest tests/training -q` | PASS：3 passed |
| `python -m pytest tests/inspector -q` | PASS：20 passed，1 warning |

24 个根测试跳过项是实际环境条件：服务未在线、`SMARTOPS_AGENT_URL` 未设置、缺少 `mysql.connector` 或 `redis`。未执行真实 LLM、MySQL/Redis 在线联调、GPU 训练和真实模型评测。

## 2026-09-18 / Training Infrastructure：训练数据与评测基础

### 修改前

- 仅有 `training/dataset_validator.py` 的四类旧式字段检查。
- 没有统一 Schema envelope、来源分类、Dataset Manifest、分组切分或泄漏报告。
- Evaluation 只有 `NOT RUN` 指标骨架，没有 observed-result-only Benchmark 边界。
- 没有 SFT/Preference/Evidence/Inspector 候选转换器、dry-run 训练配置或模型状态保护。

### 修改后

- 新增 `training/schemas/` 与 `schema_registry.py`，Schema v1 固定 Task、Environment、Knowledge、Evidence、Policy、Output、Verification、Inspector、Source、Quality、Metadata。
- Validator 保留旧格式兼容，并增加 Schema v1 语义门禁：证据范围、版本/来源、REAL/SYNTHETIC/DEMO、HIGH/CRITICAL 审批一致性。
- 新增 10 类 Synthetic Incident 候选生成器，明确 `SYNTHETIC`，不自动晋升训练集。
- 新增 SFT、Preference、Evidence、Inspector builders；新增分组 split、泄漏检查、Benchmark Runner、训练 dry-run、Model Registry lifecycle guard 和 Ablation matrix。
- 新增 `docs/experiments/training-plan.md` 与 `evaluation-plan.md`，所有未执行实验明确标记 `NOT RUN`。

### 真实验证

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/training -q` | PASS：29 passed |
| `python -m pytest -q` | PASS：71 passed，24 skipped |
| `cd backend && mvn -q test` | PASS |
| `cd frontend && npm run build` | PASS：1736 modules transformed；主 chunk > 500 kB 警告 |

### 未运行

真实数据集发布、Baseline、OpsBench、SFT、Preference Optimization、Inspector Evaluation、Ablation、GPU 训练、模型注册为 `TRAINED` 均未执行。

## 2026-09-18 / Training Engineering：Manifest 与 Baseline 边界

### 修改前

训练 Schema、Validator、Synthetic、Builder、Split、Leakage、Benchmark 和 Registry 基础已经存在，但没有 per-dataset manifest、真实质量运行入口、Baseline `NOT RUN` 报告，以及本轮要求的 7 份实验规范文档。

### 修改后

- 新增 `training/manifest.py`，为 7 个训练目录生成版本、来源、样本数、split、重复/无效/不安全数和 hash 字段。
- 新增 `training/baseline_runner.py`，没有 REAL 模型、批准数据集和 evaluator 时只返回 `EXP-BASELINE-001 / NOT RUN`。
- 新增 `training/scripts/validate_datasets.py`，真实写入 manifest、质量报告和 baseline 报告。
- 新增 `dataset-specification.md`、`data-quality.md`、`data-leakage.md`、`baseline.md`、`ablation-study.md`、`model-training.md`、`model-registry.md`。

### 实测

| 命令 | 结果 |
|---|---|
| `python -m training.scripts.validate_datasets` | PASS：7 个 manifest，0 promoted samples，质量 `NOT RUN`，Baseline `NOT RUN` |
| `python -m pytest tests/training -q` | PASS：31 passed |

没有把空数据集、Synthetic 候选或 Mock 配置冒充 REAL Baseline；没有启动 SFT、DPO 或 GPU 训练。

原有主要内容：

- Backend、Frontend、AI Service、Knowledge、Agent 和 Inspector 的技术栈概览。
- Backend 16 passed、AI Service 7 passed、根测试 18 passed / 24 skipped 的历史结果。
- 已修复问题摘要。
- 环境限制与 Phases 6-16 待办事项。

原文档尚未完整列出：

- 当前目录和文件扫描边界。
- 逐项 API 契约冻结清单。
- 当前数据库表、索引和待新增表状态。
- 前端已注册路由、未注册页面和双请求层现状。
- Plugin、Skill、Tool Registry 现状。
- Model Connection 的加密、掩码和 Runtime API 风险。
- Inspector 的 Target、Severity、Category、Evidence Label 能力。
- 2026-09-18 重新执行的测试结果。

### 修改后

文档更新为 12 个可审查章节：

```text
1. 扫描边界与目录现状
2. 技术栈与可运行状态
3. 已冻结的现有 API 契约
4. 当前数据库
5. 当前 Frontend
6. 当前 Agent Runtime、Registry 与安全链路
7. 当前 Model Provider 与 API Key 处理
8. 当前 Inspector
9. 配置与环境变量现状
10. 本次真实测试结果
11. Phase 0 结论与后续优先级
12. 本轮未做事项
```

新增或补充的事实包括：

- 扫描约 955 个文件，并注明缓存和构建产物包含在内。
- 明确当前目录不是 Git 工作树，无法生成可靠 Git diff 基线。
- 明确现有目录是 `date/`，目标中的 `data/` 尚不存在，未擅自重命名。
- 冻结 Backend、AI Service、Knowledge 现有 API URL、Method、输入和输出。
- 记录 `server`、`server_metric`、`model_connections` 三张现有表。
- 记录当前前端路由及 Marketplace 页面尚未注册的事实。
- 记录 `frontend/src/api/http.js` 与 `frontend/src/utils/request.js` 两套请求实例并存。
- 记录 6 个 Plugin Manifest 和现有 Skill、Tool 基础。
- 记录 Model Connection 使用 AES-256-GCM、Ciphertext、Last4 和掩码响应。
- 记录 Inspector 四级流水线、枚举、已有测试场景和前端/API/持久化缺口。
- 区分历史测试结果与 2026-09-18 本次实测结果。

### 安全发现

| 位置 | 修改前事实 | 本次处理 | 后续要求 |
|---|---|---|---|
| `agent/tools/shell.py` | 存在 `subprocess.run(..., shell=True)` | 仅记录，未修改业务代码 | 在兼容性评估和测试后迁移或隔离 |
| `/api/model-connections/{id}/runtime` | 返回包含解密 API Key 的实体 | 仅记录，未修改 API | 保持内部调用兼容的前提下增加鉴权和最小化响应 |
| `SecurityConfig` | `/api/**` 当前匿名放行 | 仅记录 | 设计内部 Token 或等效服务鉴权 |
| `SMARTOPS_INTERNAL_TOKEN` | 示例配置已声明，但未发现实际校验 | 仅记录 | Phase 2/安全阶段实现并验证 |

### API 对照

```text
修改前：现有 Controller、FastAPI Route 和前端 API 调用正常存在。
修改后：上述 API 源码没有修改，仅在 Current State 文档中建立冻结快照。
```

结论：`UNCHANGED`。

### 数据库对照

```text
修改前：server、server_metric、model_connections。
修改后：表结构、初始化 SQL 和 Mapper 均未修改。
```

结论：`UNCHANGED`。

### 配置对照

```text
修改前：.env.example 中敏感值为空，.gitignore 忽略 .env 并保留 .env.example。
修改后：配置文件、密码、Token、API Key 均未修改。
```

结论：`UNCHANGED`。

### 真实验证结果

| 范围 | 命令 | 真实结果 |
|---|---|---|
| Backend | `cd backend && mvn test` | PASS：16 tests，0 failures，0 errors，0 skipped |
| AI Service | `cd ai-service && python -m pytest app/tests -q` | PASS：7 passed，2 warnings |
| Root / Agent / Inspector | `python -m pytest -q` | PASS：21 passed，24 skipped，1 warning |
| Frontend | `cd frontend && npm run build` | NOT RUN：找不到 `vite` 命令，依赖未就绪 |

根测试的 24 个跳过项没有计为通过。原因包括服务未启动、未设置 `SMARTOPS_AGENT_URL`，以及缺少 `mysql.connector` 和 `redis` Python 包。

### 本阶段最终差异

```diff
- 旧 Current State：以历史修复摘要和历史测试结果为主。
+ 新 Current State：建立完整架构、API、数据库、前端、Agent、Inspector、配置和测试基线。
+ 新增 API 冻结清单，但没有修改 API。
+ 新增安全风险记录，但没有在 Phase 0 擅自修改业务实现。
+ 新增本次真实测试结果，并明确 Frontend 未构建。
```

---

## 后续阶段追加模板

## 2026-09-18 / Phase 1：安全、构建与 Inspector 产品化基础

完整逐文件记录见 `docs/OPTIMIZATION-CHANGES.md`。

| 领域 | 修改前 | 修改后 |
|---|---|---|
| Shell | 字符串命令通过 `shell=True` 执行 | argv + allowlist + 参数校验 + `shell=False` + timeout + 截断 |
| Model Runtime | 匿名请求可能获得解密 Entity | Internal Token 校验；只返回非秘密 DTO |
| Security | `/api/**` 无分类统一放行 | PUBLIC / USER / INTERNAL 分类；Internal 专用 Filter |
| Frontend | 两个 Axios 实例；构建未验证 | 单一 Axios 实例兼容导出；生产构建通过 |
| Inspector | Python 内部 Pipeline | Agent adapter → Backend DB → API → Inspector UI |
| Database | 3 张现有表 | additive migration 新增 4 张 Inspector 表，原表不变 |
| Training | 无统一训练目录和 Validator | 新增兼容 `data/training/`、dry-run Validator、NOT RUN Evaluation |
| Configuration | 无总配置手册和双平台检查 | 新增手动配置文档及 Windows/Linux 检查脚本 |

初次 Phase 1 记录结果：Root 43 passed / 24 skipped；Backend 25/25；AI Service 7/7；Inspector 最终由 Root 全套覆盖 20 项；Training 3/3；Frontend build PASS；Knowledge 0 tests collected，记为 NOT RUN。后续加入 Model Invoke 代理及 JSON 边界测试后，最终复核结果以本文“Phase 1 最新复核”章节为准：Backend 27/27、AI Service 8/8。

---

复制以下结构到文档末尾，并替换为真实内容：

````markdown
## YYYY-MM-DD / Phase N：阶段名称

### 变更摘要

| 项目 | 内容 |
|---|---|
| 修改文件 | ... |
| 新增文件 | ... |
| 删除文件 | 无 / ... |
| API | UNCHANGED / ADDED |
| 数据库 | UNCHANGED / MIGRATION ADDED |

### 文件：path/to/file

修改前：

```text
真实旧行为或关键代码
```

修改后：

```text
真实新行为或关键代码
```

修改原因：...

兼容性影响：...

### 真实验证结果

| 命令 | 结果 |
|---|---|
| `...` | PASS / FAILED / NOT RUN：原因 |

### 未完成与风险

- ...
````

## 2026-09-18 / Phase 3 Readiness 增量

| 项目 | 修改前 | 修改后 |
|---|---|---|
| Training Readiness | 无统一门禁报告 | `training/readiness/` 分模块检查依赖、模型、数据集、硬件并生成 JSON/Markdown |
| Dataset Manifest | 无显式批准数和数据类型 | 增加 `dataset_type`、`approved_count`、`leakage_count`；只统计人工 `APPROVED` |
| SFT Gate | 容易把有效样本误认为可训练 | Dataset/Model/Leakage/Safety/Split 不全通过时为 `BLOCKED` |
| Baseline | `NOT RUN` 原因较粗 | readiness 关联明确：无真实模型、无 approved 数据、无 evaluator 时保持 `NOT RUN` |

真实执行结果：`python -m training.readiness` 返回 `BLOCKED`；7 个 Dataset 均 `DRAFT/0 approved`，当前 `.env` 为 Mock Provider（不是 REAL 模型），CUDA/GPU 不可用，未启动 Baseline、SFT 或 Preference Optimization。训练测试另外受到 Windows `tmp_path` 临时目录 `WinError 5` 环境权限阻断，未伪造为通过。

## 2026-09-18 / Phase 4 Knowledge Tests 与 Windows Test Infrastructure

| 项目 | 修改前 | 修改后 |
|---|---|---|
| Knowledge Tests | `tests/knowledge` 不存在，无法收集测试 | 新增 11 个测试文件，覆盖 ingestion、chunking、embedding、vector、BM25、hybrid、reranker、version、evidence、trust |
| Training tmp_path | 受限系统临时目录导致 `WinError 5` | `tests/conftest.py` 使用项目内隔离目录，每个用例独立创建并清理 |
| API/Database | 既有契约 | UNCHANGED |

真实结果：Knowledge `13 passed`；Training `33 passed`；合计 `46 passed`。仅剩 pytest cache warning，未影响断言。Readiness 仍为 `BLOCKED`，Dataset 为 0 approved，Baseline/SFT/Preference/Ablation 均未运行。

## 2026-09-18 / Phase 5 Training Gate 与 Candidate Review Lifecycle

| 项目 | 修改前 | 修改后 |
|---|---|---|
| Candidate 生命周期 | 只有 Builder/Manifest，缺少独立晋级状态机 | 新增 `training/candidate_lifecycle.py`，强制 Candidate → Validation → Quality → Safety → Review → Approval |
| Human Review | 没有独立 review 对象和晋级断言 | 新增 `HumanReview`，要求 review 与样本 `quality.human_review` 同时 APPROVED |
| 自动批准 | 容易被误用为训练入口 | `promote()` 未获明确人工批准直接拒绝 |
| 真实数据 | 不存在 | 本阶段仍未创建，Approved Samples=0 |

真实结果：Readiness `BLOCKED`；Provider 为 Mock；7 个 Dataset 均 `DRAFT/0 approved`；Training `36 passed`；Root `89 passed / 24 skipped`；Baseline、Ablation、SFT 和 Preference 均 `NOT RUN/BLOCKED/NOT_READY`。

## 2026-09-18 / Phase 7 Gate Recheck

真实执行确认：Gate `BLOCKED`、Approved Samples `0`、Split `0/0/0`、Leakage/Safety `NOT RUN`、Model 为 Mock、Evaluator `NOT READY`、Baseline `NOT RUN`；Training `36 passed`、Knowledge `13 passed`。未创建或批准任何训练样本，未启动 Baseline、Ablation、SFT 或 Preference。

---

## 2026-11-03 / 答辩工程整改 v1—v2：原始观测、真实模型与可复核评测

### 记录边界与基线

本节根据本会话实际改动、评测 CSV、原始验证日志和 Work Buddy 备份记录追加。此次文档更新只核对既有证据，未重新运行完整业务测试；下表保留 2026-11-03 已执行批次的结果。

- 当前 `D:/SmartOpsAgent` 已是 Git 工作树，HEAD 为 `48b8af4`。9 月 18 日无 Git 基线的历史描述继续保留，不作为当前状态。
- 整改前已核实 `backup/pre-defense-20261103`、源码和素材归档及未提交补丁，位置为 `E:/Projects/SmartOpsAgent-Defense/07-交付与备份`。
- 精确任务差分使用 Work Buddy 的 `SmartOpsAgent-src-20261103.tar.gz` 中原文件作为基线；该备份包含原有工作区状态，并非干净 HEAD。未重置、提交或覆盖其他已有修改及删除项。
- [交付清单](../../06-工程整改/delivery-manifest.json)列出打包时的 29 个任务变更文件及前后哈希；[精确差分](../../06-工程整改/整改对照.patch)和[改后文件包](../../06-工程整改/changed-files.zip)供逐文件核对。本次追加本文的改动另以 `git diff` 及文档专项备份记录，不冒称已进入此前生成的交付包。

### 修改文件与行为对照

| 文件 / 类型 | 修改前 | 修改后与原因 | 影响与限制 |
|---|---|---|---|
| `agent/inspector/verifiers/state_verifier.py` / 修改 | 接收 `actual_state.resolved` 结论，缺少真实探针采集 | 从 `probes` 原始观测推导；加入 HTTP GET、端口连接、进程采集及配置版本等判定；忽略输入 `resolved`；缺失或非法观测标记未核验，排除否定成功表达 | 旧 `resolved` 单字段不再构成通过证据；未覆盖的成功同义表达仍会漏检 |
| `agent/inspector/collectors/trace_collector.py` / 修改 | 观测数据未完整进入核验上下文 | 传递 `probes` 和 `observed_at` | 保留原始观测供流水线核验 |
| `agent/inspector/pipeline.py` / 修改 | `evidence_label` 字符串与枚举序列化不一致 | 规范为 `EvidenceLabel`，修复 `to_dict()` 异常 | L3 仍默认 passthrough，不宣称四层均执行真实模型判定 |
| `ai-service/app/services/llm.py` / 修改 | Ollama 分支模拟输出或受环境代理影响降级 | 请求真实 `/api/generate`，解析 JSON / NDJSON；两个 httpx 客户端使用 `trust_env=False`；异常回落 mock 并标记原因与 provider | 直连模型不继承环境代理；降级可见，不等于所有现场路径已验收 |
| `ai-service/app/services/chat.py` / 修改 | 缺少降级信息与 Inspector 返回 | 响应 metadata 暴露 `degraded`、`effective_provider`、原因；可选请求元数据触发核验；SSE 增加 `inspection` 事件 | 原路由保留；没有自动探测任意目标或自动执行 Re-plan 的完整闭环 |
| `frontend/src/components/ai/AiChatPanel.vue` / 修改 | 缺少相应状态展示，重规划文字会被误读为已经执行 | 展示降级和拒绝结果，文案为“需要重新规划” | 不把核验结果冒称已完成后续操作 |
| `.env.example` / 修改 | 缺少本地代理绕过示例 | 增加 `NO_PROXY=127.0.0.1,localhost` | 仅示例配置，不填写真实凭据 |
| `scripts/eval_false_success.py`、`tests/fixtures/defense/false_success.json` / 新增 | 早期评测模板同源、直接输入结论；中间结果存在追分问题 | 冻结 50 条 AI 合成样本；预测仅接收 id/claim/probes，预期标签仅计分；保留真实漏检及未知项 | 不以目标 F1 筛选样本；不是生产数据或独立人工标注集 |
| `scripts/eval_retrieval.py` / 新增 | 早期 n=70 由模板加壳，后续曾错误标记 `human:` | 默认仅评测 14 原始问法；70 问为显式可选补充，56 条 AI 改写全部标记 `generated:` | 未满足独立人工改写验收；有效独立样本≈14 |
| `scripts/collect_probes.py`、`scripts/check_llm_live.py` / 新增 | 缺少可复跑真实观测和五问验收入口 | 输出 HTTP/端口/进程观测；五问检查拒绝空回答、mock 或降级 | 五问检查直接调用 LLMService，未覆盖浏览器整链路 |
| `scripts/scan_anonymity.py`、`scripts/check_numeric_consistency.py` / 新增 | 缺少可复跑扫描，曾误报匿名清零及表数 | 重扫文本/Office XML；SQL 去注释后统计唯一 CREATE TABLE；扫描保留待复核项 | 不识别 PDF 页面或视频画面中的身份；数词 OK 不证明测试通过 |
| `scripts/windows/start-all.ps1` / 新增；相关 README / 修改 | 应用逐项启动，无 Ollama 启动保障 | 已加入 Ollama 检测/拉起及端口轮询、启动说明 | 后续隐藏进程、HTTP 就绪、模型环境和 Java 选择加固未应用；整套启动未验收 |
| AI Service、Inspector、脚本及前端相关测试 / 修改或新增 | 缺少探针、标签隔离、来源和降级回归；单测可误读本机模型配置 | 增加真实临时 HTTP 502→REJECTED、未知观测、来源标记、标签隔离等验证；autouse mock 配置隔离，降级测试显式模拟连接失败 | 实跑结果见下表；与独立真实五问分开记账 |
| `scripts/rollback_defense.py`、`06-工程整改/rollback-defense-changes.ps1` / 新增 | 分支切换或直接应用 dirty patch 不足以恢复混合工作区 | 按任务文件清单校验全部哈希，当前文件先移入隔离目录，再恢复备份原文 | 默认只读预检；后续文件修改会阻止整批覆盖；不是全仓库重置 |

工程评测、扫描、台账及验证输出位于 `06-工程整改/`。新增测试夹具和脚本均属于链路验证基础设施；本轮未启动 SFT、DPO 或 GPU 训练，没有把合成评测转为真实模型训练基准。

### API、数据库与配置兼容性

- 原有 Chat URL / Method 保留；响应 metadata 字段及 SSE `inspection` 事件为增量。现有 SSE 消费者需容忍新增事件。
- Inspector 的状态证据契约收紧为原始 `probes`；调用方只传 `resolved` 将得到未核验结果，需接入真实观测。
- 本轮工程整改未新增数据库迁移、删除表或重命名表。已有其他任务的 Java / migration 变更未归入本轮成果。
- 静态复核为 **35 个 migration 文件、79 个唯一 CREATE TABLE 表名**。方案中的 80 把 SQL 注释示例中的 `if` 误计；这不是运行数据库或 Java 启动补表后的总表数。
- `.env.example` 仅增加示例值；未将密码、Token 或 API Key 写入本记录。后述 Codex 审批配置修复尚未应用。

### 已执行验证与原始证据

| 命令 / 实验 | 2026-11-03 实际结果 | 证据与边界 |
|---|---|---|
| `python -m pytest -p no:cacheprovider tests/scripts tests/inspector ai-service/app/tests -q` | **55 passed in 3.71s** | `.runtime/defense-v2/python-final.log`；相关回归，不是全仓库 Python 测试总量 |
| `python scripts/eval_false_success.py` | n=50，47 可评分、3 未知；TP=13/TN=21/FP=0/FN=13；Precision=1.0、Recall=.5、F1=.6667 | [逐项 CSV](../../06-工程整改/eval_false_success.csv)；40 主样本涵盖六类、10 干扰；AI 合成，仅验证链路，不代表线上性能，低于方案建议区间 |
| `python scripts/eval_retrieval.py` | n=14 原始问法；Recall@3=.6429、MRR=.4167 | [主评测 CSV](../../06-工程整改/eval_retrieval.csv)；7 个 Linux JSONL、14 种子，HashEmbedding+BM25、每条响应首切片索引，仅验证链路 |
| `python scripts/eval_retrieval.py --include-variants --output 06-工程整改/eval_retrieval_ai_variants.csv` | 补充 n=70 query；Recall@3=.6000、MRR=.4262 | 14 原句+56 AI 改写，独立样本≈14；无 `human:` 来源 |
| `python scripts/check_llm_live.py`，环境 provider=ollama/model=qwen3:1.7b/timeout=120 | 五问 **5/5** `effective_provider=ollama`、`degraded=False`；总耗时 32.3867s | `.runtime/defense-v2/llm-live.log`；直接 LLMService 流式路径；首字延迟 2305.0—5220.7ms |
| 临时真实本地 HTTP 502 + 探针采集 + InspectorPipeline | **HTTP 502 → REJECTED** | [完整输入和输出](../../06-工程整改/real_502_pipeline.json)；随机空闲端口，不冒称 8080/8001 或生产现场验收 |
| `npm test`，frontend | **458 项，456 通过、2 失败** | `.runtime/defense-v2/frontend-tests.log`；缺失 `heartbeat.js` 与导航 3/4 子项预期差异，保留现有用户改动 |
| `node --test test/ai-chat.test.mjs test/assistant-mini.test.mjs`，frontend | **20 passed、0 fail** | `.runtime/defense-v2/frontend-targeted.log`；定向验证 |
| `npm run typecheck`，frontend | **通过** | `.runtime/defense-v2/typecheck.log`；不代表完整前端测试通过或完成双构建 |
| Java17/Maven3.9.15：`mvn -o -s D:/SmartOpsAgent/.runtime/defense-v2/maven-settings.xml -Dmaven.repo.local=D:/SmartOpsAgent/.m2/repository test`，backend | **BUILD SUCCESS；448 执行、0 失败、0 错误、1 跳过** | `.runtime/defense-v2/backend-tests-combined-repos.log`；跳过 `MiniAssistantEngineTest.ignoresOutsideSymlinks`，符号链接能力假设未满足；项目内配置兼容 central/alimaven 缓存来源 |
| `python scripts/scan_anonymity.py` | **35 条命中，均待人工处理** | [复核清单](../../06-工程整改/anonymity_review.csv)中 35 条均 PENDING；机器建议不等于人工批准 |
| `python scripts/check_numeric_consistency.py` | 279 条上下文命中、108 条 REVIEW；迁移定义 79 表 | [数字 CSV](../../06-工程整改/numeric_consistency.csv)、[表清单](../../06-工程整改/table_inventory.json)；不将数词匹配视作测试或业务验收 |
| `python scripts/rollback_defense.py --bundle 06-工程整改/rollback-bundle.zip` | **28 个任务文件只读预检通过** | 全批哈希核验；未对实际工作区执行回滚 |

假成功冻结夹具 SHA256：`28c757cdabcfd24d69e27cb4bc3abdbd185d793ea3d5dbe4340093cacf86d45a`。历史 F1=1.0000 / 中间 .8571、`human:56`、匿名 0 命中及 Ollama 始终阻塞的记录已由本轮证据替代，不用于新材料。

### 失败尝试、未完成项与审批故障诊断

1. 后端早期离线构建因缓存仓库标识及插件来源不匹配失败，后用项目内 Maven 设置同时声明 central/alimaven 后完成测试。未修改全局缓存标识或认证。
2. Python 最终回归首次出现 `test_mock_llm` 误调用本机真实模型的失败；配置隔离和显式降级故障注入后得到上表 55 通过。后续新增的启动健康回归只在待修复状态运行失败，已移出默认测试目录保存为 `.runtime/defense-v2/startup-health-test.pending.py`，不计入 55 项通过。
3. 启动脚本后续加固和完整一键启动均 **未完成**。源文件仍为现有实现，部分待审补丁不等于已应用。现有脚本仍有可见命令窗口、TCP 代替 HTTP 就绪、模型环境和 Java 选择不足等限制。
4. E 盘工程整改交付包复制 **未执行**；本地包仍为 `.runtime/defense-v2/defense-v2-20261103-1248.zip`，不能宣称已归档或完成单一交付目录归位。
5. 阻塞发生在工具执行前：自动审批请求 `gpt-5.6-luna`，Tool2AI 入口返回当前账号组不支持该模型的 404。用户授权已记录，但重试仍失败。审批失败并非代码测试失败，也未判定动作不安全。
6. 诊断后已准备 `model_catalog_json` 修复：主模型的 `auto_review_model_override` 指向 `gpt-6.1-sol`，保留审批和沙箱控制。本机 CLI 严格配置加载通过，`debug models` 读回正确覆盖值；但应用配置的命令同样被审批 404 阻断，**全局配置尚未更改，也未证明运行中的审批已修复**。详见 [审批故障诊断与修复](../../.runtime/defense-v2/审批故障诊断与修复.md)。
7. 独立人工检索改写、35 条匿名命中逐项审核、PDF/视频视觉匿名，以及完整前端 2 项失败仍待处理。F1=.6667 为真实当前结果，不通过修改样本追求方案目标分数。
8. 讲稿/PPT/海报/录屏按整改方案由材料负责人处理；本轮未替其宣称完成。真实五问不等于浏览器演示，探针拒绝也不等于自动重规划闭环。

### 本节文档更新的验证

本次只为本文追加可溯源记录，并给原有 Git 基线说明添加日期限定。已核对上述日志和 CSV，检查文档差分及本地链接；未因文档变更重复运行全套业务测试。修改前文档另有专项备份、差分、验证记录和带哈希保护的回滚脚本，保存在 `.runtime/defense-v2/comparison-doc-*` 对应目录；此前 28 文件代码回滚包不包含本次文档追加。

## 2026-11-03 晚间补充：全面体检与首批稳定性修复

本节对应 `.runtime/health-audit-20261103-223606`，是晚于上述整改验证的工作区快照。完整报告见 [全面体检与优化方案](全面体检与优化方案-20261103.md)，开源参考见 [GitHub 开源候选](GitHub开源参考与选型-20261103.md)。前文保留为历史，不把前文指标直接视为当前结果。

本轮先保存 1,750 文件源码快照，再保存涉及文件的精确前像；保留已有脏文件与其他任务修改。首批修复为：RAG 禁用环境代理并区分空命中/连接故障/坏响应；每次模型调用重置降级标记；真实模型部分输出后中断不再混入 mock；空流与缺失结束标志不报告成功；SSE 客户端识别 error、坏 JSON、提前 EOF 与 CRLF；消息保留真实部分与错误说明；对话进度只展示实际步骤。新增 26 项 Python 行为回归与 7 项前端行为回归。

| 本轮核验 | 实际结果 |
|---|---|
| 后端 Maven test | 450 项，0 失败、0 错误、1 跳过 |
| AI 服务完整测试 | 39 通过 |
| Inspector/脚本回归 | 42 通过 |
| 前端定向回归 | 23 通过 |
| 前端完整测试 | 修复前 464 项/462 通过/2 失败；修复后 471 项/469 通过/2 失败；已有缺失 heartbeat.js 与导航预期失配仍在 |
| 前端类型检查 | 通过 |
| 用户端/管理端独立目录构建 | 均通过；默认用户端 dist 清理曾报 ENOTEMPTY，未强删旧制品 |
| 当前冻结假成功夹具 | 50 样本、47 可评分、3 未评分；TP26/TN21/FP0/FN0；F1=1.0；合成回归，不是独立泛化证明 |
| 当前检索评测 | n14，Recall@3=.5000、MRR=.4286；与早期数值版本不同，后续需固定语料/实现再对照 |
| Knowledge 实例对照 | 在线 chunks=0；61 个参考 Markdown 在新实例摄入得 2,465 chunks；运行进程归因和就绪切换待做 |

修复前完整 Python 测试为 16 失败、125 通过、7 跳过；修复后为 16 失败、151 通过、7 跳过。失败集中于旧匿名 API 契约与现有鉴权不一致；本轮不通过取消权限来达标。原始记录见完整报告链接的最终日志。

还复现了“无观测/未知结论+异常探针仍可能汇总 PASS”和“重启 mysql 规划为 nginx”两项问题，已列为下一批 P0。没有修改这些已有 Agent/纠察逻辑，也未将全部项目宣称为稳定验收完成。

GitHub 公共源码资料抓取被普通网络限制及自动审批模型 404 阻断，命令未执行；没有核验当前许可证/活跃度。已交付固定候选表与只读采集脚本，未修改全局审批控制。在线 AI/Knowledge 进程没有重启，本轮不宣称已加载首批修复。

四件交付及哈希保护回滚入口见完整报告第 7 节。本轮差分以逐文件备份为前像，不以 Git HEAD 覆盖其他人的修改。

## 2026-11-03 深夜补充：第二批 P0 门禁与 Knowledge 就绪

对应 `.runtime/p0-stability-20261103-231528`；完整记录见 [P0 稳定性整改](P0稳定性整改-20261103.md)。修改前源码快照 1756 文件，保留上轮与其他任务改动。

本批：执行验证必需但缺观测/结论未知时 WARN + 人工复核，增加验证状态字段；风险大小写归一；AI Chat 显式验证标志透传；诊断“解决方案/如何解决”不冒称执行完成；Planner 绑定明确 nginx/mysql/redis 目标并拒绝歧义写操作；Knowledge 新增 `/api/ready`、语料摘要与实例标识；Windows 启动复用已有监听、增加 HTTP 就绪、隐藏窗口与落盘日志，状态脚本展示多监听。

相关回归 **162 通过**；全量 Python **201 通过、16 失败、7 跳过**，原有鉴权契约失败未隐藏。冻结假成功 47 可评分样本全对，仍为合成回归。独立审阅指出的门禁/边界问题已修复并复核。

定位运行环境根因：PID21396 的 127.0.0.1:8002 旧实例空索引遮蔽 PID43128 的通配监听；通过 127.0.0.2 实测后者有 2465 chunks。本轮临时 18002 新实例的 readiness、3 条搜索命中和真实 RAG HTTP 成功，随后已清理该临时进程。停止已确认旧实例先被 OS 拒绝，提升申请又因审批模型 gpt-5.6-luna 不可用返回404，命令未执行；默认8002运行切换仍待完成。

PowerShell 5.1 三个脚本零语法错误；其本机执行策略禁止脚本文件加载，未修改策略，HTTP/超时/复用函数测试在 PowerShell7 运行。完整 start-all 未执行，未重启其他服务。审批执行授权、探针目标/时效、前端两项失败与登录测试改造留在下一批，不把源码门禁修复说成所有链路验收完成。

## 2026-11-04 补充：执行审批与验收整改

对应 `.runtime/execution-gate-20261104-084309`，完整记录见 [执行审批与验收整改](执行审批与验收整改-20261104.md)。保留前文历史；本节更新审批环境、默认 Knowledge 与前端遗留失败的最新状态。先保存涉及生产代码的精确前像及 1765 文件源码快照，再实施；后续文档另在编辑前扩展前像。未重置或覆盖其他任务改动。

Python ApprovalManager 采用可信宿主内存状态，批准绑定请求、用户、环境、步骤、工具、动作与 JSON 参数，默认 300 秒、锁内单次消费。PolicyEngine 明确区分“需要批准”与“已批准”，未配置管理器时拒绝需批准动作，保留 CRITICAL 拒绝，分类器与声明取较高风险。Executor 深复制执行快照并在调用前消费批准；工具显式失败、非布尔 success 和异常均按失败审计。未新增公开审批接口或 Java 审批桥接；批准不跨进程/重启持久化。

新增审批回归最终 **36 通过**；相关 Python **198 通过**；全量 Python **237 通过、16 失败、7 跳过**。16 项旧匿名/CSRF 契约失败保留，下一批建立隔离登录 fixture，不降低权限。只读独立审阅发现循环参数导致拒绝审计缺失的 P2，先复现失败再修复，复核通过。前端已删除退役心跳模块的孤立测试，同步 Guardian 四子项及别名分组断言，完整 Node 测试 **470 通过/0 失败**，typecheck 通过；未重跑本轮未改动的 Java 和双端构建，未宣称浏览器 E2E 全过。

本轮自动审批提升已成功：核对归属后停止空索引旧 PID21396 与旧项目实例 PID43128，将当前 Knowledge 隐藏启动至 127.0.0.1:8002（PID26072）。默认 readiness HTTP200 READY，61 篇语料、2465 chunks、错误0，搜索与真实 RAG HTTP 均3条命中，仅一个本机监听。8001 AI 进程未重启，完整 start-all 未执行；本轮未修改全局审批配置/执行策略，不能将操作成功归因为已应用旧配置补丁。

GitHub 10/10 官方仓库 metadata/README 已实际抓取，另保存并校验 LICENSE 固定 blob 原文。Phoenix 根许可为 **Elastic License 2.0**，含第三方托管服务限制；不按 MIT/Apache 处理。LlamaIndex README 当前偏向文档处理，整体迁入暂缓。根许可审阅不代表全依赖合规批准，未安装候选项目。详见 [GitHub 调研与后续路线](GitHub开源调研与后续路线-20261104.md)：先补鉴权测试与真实浏览器验收，再逐步观测、持久化、网络采集边界和长期任务。

四件交付为本批改后 ZIP、精确前像差分、验证记录与哈希保护回滚工具。文件回滚不撤销 Knowledge 进程切换，真实工作区未执行回滚；包校验及副本演练以本批 `bundle-validation.json` 为准。
