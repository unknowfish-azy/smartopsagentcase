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
