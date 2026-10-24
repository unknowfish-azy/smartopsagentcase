# SmartOpsAgent Optimization Changes

## 2026-09-18 / Phase 1

### 修改文件

- `agent/tools/shell.py`：从字符串 Shell 执行改为 tokenizer、argv、allowlist、参数校验和 `shell=False`。
- `agent/inspector/service.py`：增加保留原 `inspect()` 的 `inspect_and_persist()` 兼容入口。
- `ai-service/app/services/model_gateway.py`：停止消费或下发模型明文密钥，直接 Provider 调用在凭据代理完成前显式拒绝。
- Backend Model Connection Controller、Service、SecurityConfig 和配置：Runtime API 最小化响应并增加 Internal Token Filter。
- `backend/src/test/resources/schema.sql`：增加测试专用 Inspector 表。
- `frontend/src/api/http.js`：保留兼容入口，统一复用 `utils/request.js`。
- Frontend Router、Layout、`.env.example`。

### 新增文件

- Shell 安全测试：`tests/agent/test_shell_security.py`。
- Runtime 安全 DTO、Filter、Java 行为测试与 Python 契约测试。
- Inspector Backend Controller、Service、DTO、数据库 migration、Controller 测试和 H2 持久化集成测试。
- Inspector persistence adapter 与专项测试。
- Inspector Center、Detail、Statistics，9 个 Inspector 组件及前端 API。
- Agent Command Center、Execution Trace、Knowledge Evidence、Model Health 基础页面。
- `data/training/` 八类训练目录、Dataset Validator、Evaluation Runner 和测试。
- Windows/Linux 配置检查脚本。
- `docs/MANUAL-CONFIGURATION.md`。

### 修改前

- 遗留 Shell Tool 使用 `subprocess.run(command, shell=True)`，只检查首个字符串 token。
- Runtime Model API 匿名可访问并返回解密后的 Entity 字段。
- `/api/**` 全部统一 `permitAll`，没有 Internal API 专用校验。
- Frontend 依赖未验证，两个 Axios 实例具有不同 timeout 和错误格式。
- Inspector 只有 Python Pipeline，没有数据库、Backend API 或前端页面。
- 没有训练数据质量 dry-run、Evaluation NOT RUN 基础或手动配置总文档。

### 修改后

- Shell 输入先拒绝管道、重定向、`&&`、`||`、`;`、命令替换和换行，再通过 `shlex` 转为 argv；固定 `shell=False`，限制 timeout 与输出长度。
- Runtime URL/Method 保持不变；缺失 Token 返回 401、错误 Token 返回 403、服务端未配置返回 503、正确 Token 只返回非秘密 DTO。
- SecurityConfig 明确 PUBLIC、USER、INTERNAL 分类；USER API 为兼容现有系统暂时保持匿名，Runtime 与 Inspector 写入端点由专用 Filter 校验。
- Frontend `npm install` 完成，0 vulnerabilities；生产构建通过。
- Inspector Result 可经 Agent adapter 写入 Backend，关系表持久化后由 API 供前端 Center/Detail/Statistics 展示。
- 无真实数据时 Agent、Knowledge、Model Health 和 Evaluation 显示 `N/A` 或 `NOT RUN`。

### 修改原因

- 消除任意 Shell 解释器注入面。
- 阻止浏览器或普通请求获取 Model API Key。
- 在不破坏既有用户 API 的前提下建立内部服务安全边界。
- 将现有 Inspector 核心升级为可持久化、可查询、可展示的产品基础。
- 建立不依赖 GPU、不伪造训练结果的数据质量和评测骨架。

### 影响范围

- Backend、AI Service、Agent、Frontend、数据库 migration、配置、测试和文档。
- 未删除或重命名任何现有目录。
- 现有 `date/` 保持不变；新增 `data/training/` 用于后续受质量门禁管理的训练资产。

### API

现有 Server、Metric、Chat、Knowledge 和 Model Connection URL/Method 未变。

新增：

```text
GET  /api/inspector/summary
GET  /api/inspector/events
GET  /api/inspector/events/{id}
POST /api/inspector/check
POST /api/inspector/verify
POST /api/inspector/replan
GET  /api/inspector/statistics
```

安全变更：`GET /api/model-connections/{id}/runtime` 保留 URL/Method，但不再返回秘密字段，且要求 `X-SmartOps-Internal-Token`。

### 数据库

新增 additive migration：`scripts/common/migrations/V002__inspector.sql`。

新增表：

- `inspector_event`
- `inspector_issue`
- `inspection_evidence`
- `inspection_verification`

未修改或删除 `server`、`server_metric`、`model_connections`。

### 配置

- 新增实际读取变量 `SMARTOPS_INTERNAL_BYPASS`，默认 `false`。
- `SMARTOPS_INTERNAL_TOKEN` 现在由 Backend Filter 实际校验。
- `.env.example` 仅提供空值/非秘密示例，没有写入密码、Key 或 Token。
- 配置检查只输出 `OK`、`MISSING`、`OPTIONAL`。

### 测试命令与真实结果

| 命令 | 结果 |
|---|---|
| `python -m pytest -q` | PASS：43 passed，24 skipped |
| `cd backend && mvn test` | PASS：25 tests，0 failures，0 errors，0 skipped |
| `cd ai-service && python -m pytest app/tests -q` | PASS：7 passed，2 warnings |
| `cd knowledge && python -m pytest -q` | NOT RUN：0 tests collected，仅 1 个 cache warning |
| `cd frontend && npm install` | PASS：依赖一致，0 vulnerabilities |
| `cd frontend && npm run build` | PASS：1736 modules transformed；存在主 chunk > 500 kB 警告 |
| `python -m pytest tests/inspector -q` | PASS：20 passed，1 cache warning |
| `python -m pytest tests/training -q` | PASS：3 passed（在可用临时目录环境复核） |
| `scripts/windows/check-config.ps1` | 预期 exit 1：当前 MySQL/LLM/Encryption/Internal/Knowledge 为 MISSING，Redis 为 OPTIONAL |

### 失败

- 初次前端构建在受限沙箱中因 esbuild `spawn EPERM` 失败；相同命令在允许子进程的环境中构建通过。
- 初次 Training 测试因 pytest 临时目录权限产生 2 个 setup error；相同测试在允许临时目录的环境中 3/3 通过。
- Runtime Security 测试开发过程中先暴露测试切片未导入真实 SecurityConfig、随后暴露 Mock 参数顺序错误；修复测试配置后最终全套 Backend 23/23 通过。

### 跳过

根测试 24 skipped：Backend/AI Service 未在线运行、`SMARTOPS_AGENT_URL` 未配置、`mysql.connector` 与 `redis` Python 包未安装。未修改测试掩盖这些条件。

### 未运行

- Knowledge 没有独立测试用例可收集。
- 未执行 MySQL 生产 migration、Redis 在线联调、真实 LLM 调用、GPU 训练或模型评测。
- Evaluation 指标保持 `null` 和 `NOT RUN`。

### 最新复核更正（2026-09-18）

后续增加了 Backend 凭据代理 `POST /api/model-connections/{id}/invoke`，并将 Inspector 事件的 `metadata_json`、验证 `details_json` 在 API 边界解析为 JSON 对象。为修复该边界的 Java 泛型断言，测试文件 `backend/src/test/java/com/smartops/integration/InspectorPersistenceIntegrationTest.java` 做了仅测试代码的类型安全调整；没有改变生产 API 或业务逻辑。

本次最终实测：

| 命令 | 真实结果 |
|---|---|
| `python -m pytest -q` | PASS：43 passed，24 skipped；跳过原因为服务未启动、`SMARTOPS_AGENT_URL` 未设置、缺少 `mysql.connector`/`redis` |
| `cd backend && mvn test` | PASS：27 tests，0 failures，0 errors，0 skipped |
| `cd ai-service && python -m pytest app/tests -q` | PASS：8 passed，2 warnings |
| `cd knowledge && python -m pytest -q` | NOT RUN：0 tests collected |
| `cd frontend && npm run build` | PASS：1736 modules transformed；存在主 chunk > 500 kB 警告 |
| `python -m pytest tests/training -q` | PASS：3 passed |
| `python -m pytest tests/inspector -q` | PASS：20 passed，1 warning |

受限沙箱中曾出现 Frontend `esbuild spawn EPERM` 与 Training 临时目录权限错误；在允许子进程和系统临时目录的环境中复核均已通过。未执行真实 LLM、MySQL/Redis 在线联调、GPU 训练或真实模型评测。

## 2026-09-18 / Training Phases 1-17：数据与训练基础设施

### 变更摘要

| 范围 | 修改前 | 修改后 |
|---|---|---|
| Schema | 仅有四类旧式字段元组检查 | Schema v1 registry、统一 sample envelope、Dataset Manifest、任务角色和来源分类 |
| Validator | 必填字段、重复、危险标记和 Evidence label | 保留旧格式兼容；新增 Schema v1 结构/语义校验、证据范围、风险审批、来源真实性约束 |
| Synthetic | 无生成器 | 10 个故障族和标准/难例候选生成器，明确 `SYNTHETIC`，不自动晋升 |
| Dataset | 无角色化转换器 | SFT、Preference、Evidence、Inspector 候选 builder，质量状态保持 `PENDING` |
| Split/Leakage | 无 | 分组切分及 exact/scenario/evidence/root-cause/environment/version 泄漏报告 |
| Evaluation | 仅有 NOT RUN 指标骨架 | observed-result-only Benchmark Runner、Inspector precision/recall 等指标定义 |
| Training/Registry | 无配置门禁和模型状态保护 | CPU/CUDA/GPU dry-run、SFT/QLoRA/Preference 配置校验、PLANNED/TRAINED 防误标 Registry、Ablation 计划 |

### 新增主要文件

- `training/schemas/`、`training/schema_registry.py`
- `training/synthetic_incidents.py`、`training/dataset_builders.py`
- `training/dataset_splitter.py`、`training/leakage_checker.py`
- `training/benchmark_runner.py`、`training/training_pipeline.py`
- `training/model_registry.py`、`training/ablation.py`
- `tests/training/` 对应 Schema、Validator、Synthetic、Builder、Split、Leakage、Benchmark、Registry 测试
- `docs/experiments/training-plan.md`、`docs/experiments/evaluation-plan.md`

### API / 数据库 / 配置

- 未修改既有 API URL、Method、请求字段或响应契约。
- 未修改或删除数据库表；训练候选尚未写入数据库。
- 未增加真实密码、API Key、Token 或 GPU 假配置。

### 真实测试结果

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/training -q` | PASS：29 passed |
| Schema 专项验证 | PASS：5 passed |

### 明确未运行

- 没有生成并提交可训练数据集；Synthetic 仅为内存候选。
- 没有执行真实 Baseline、OpsBench、SFT、Preference Optimization、Inspector Evaluation 或 Ablation。
- 没有真实模型、Loss、Accuracy、Precision、Recall、Latency、Token Cost、GPU 时间或 Artifact。

## 2026-09-18 / Training Engineering：Manifest、Dataset Validation 与 Baseline 边界

### 修改前

- 训练目录有 Schema、Validator 和候选生成器，但没有每个 Dataset 的 `manifest.json`。
- `quality_report.json` 仍是早期空目录摘要，Baseline 只有计划描述。
- 本轮要求的 dataset specification、data quality、leakage、baseline、ablation、model training、model registry 文档尚未齐全。

### 修改后

- 新增 `training/manifest.py` 和 `training/scripts/validate_datasets.py`。
- 为 `sft`、`preference`、`inspector`、`evidence`、`tool_call`、`safety`、`verification` 生成 manifest；当前均为 `DRAFT`、0 samples。
- 真实运行 Dataset Validation，更新 `data/training/quality_report.json`；生成 `data/training/eval/baseline-report.json`，状态 `NOT RUN`。
- 新增 `training/baseline_runner.py`，缺少 REAL 模型、批准数据集或 evaluator 时不会生成指标。
- 新增 7 份实验文档并更新 `MANUAL-CONFIGURATION.md` 的训练变量实际支持状态。

### API / 数据库

- 现有 API 和数据库未修改；仅新增训练控制文件和文档。

### 真实结果

| 命令 | 结果 |
|---|---|
| `python -m training.scripts.validate_datasets` | PASS：7 个 manifest 生成；总体 `NOT RUN`，无 promoted samples |
| `python -m pytest tests/training -q` | PASS：31 passed |
| `python -m pytest -q` | 历史阶段完整回归 71 passed / 24 skipped；Phase 4 最新根回归为 86 passed / 24 skipped |

### NOT RUN

## 2026-09-18 / 对照报告（3）

### 新增

- `docs/development/优化前后项目文件变动信息（3）.md`
- 桌面交付文件：`SmartOpsAgent-优化前后项目文件变动信息（3）.md`

### 内容

- 汇总文件级修改前后对照、API/数据库兼容性、训练目录和真实测试结果。
- 增加下一阶段 P0/P1/P2 优化建议。
- 明确 `DRAFT`、`NOT RUN`、`REAL`、`SYNTHETIC` 等状态边界。
- 未写入任何密码、API Key、Token 或密文。

## 2026-09-18 / Phase 3：Training Readiness 与 Baseline 门禁

### 修改前

- 训练目录只有空 Manifest，无法统一回答依赖、模型、数据集和硬件是否满足训练前置条件。
- Manifest 没有显式记录 `dataset_type`、`approved_count`、`leakage_count`。
- Baseline 保持 `NOT RUN`，没有新的真实模型或批准数据集。

### 修改后

- 新增 `training/readiness/` 模块：依赖、模型配置、Dataset、硬件/磁盘和报告分别检查。
- 新增 `training/readiness-report.json` 与 `training/readiness-report.md`。
- Manifest 增加 `dataset_type`、`approved_count`、`leakage_count`，仅人工审批状态为 `APPROVED` 的样本可计入批准数。
- 新增 readiness 测试，验证空数据集会阻断 SFT。

### API / 数据库 / 配置

```text
API：UNCHANGED
数据库：UNCHANGED
敏感配置：未读取、未写入、未打印值
训练是否启动：NO
```

### 真实 Readiness 结果

```text
Overall: BLOCKED
Requirements: PARTIAL（torch 可用；transformers/datasets/peft/trl 缺失）
Model: PARTIAL（`.env` 配置为 Mock；不是 REAL 模型 Baseline）
Dataset: BLOCKED（7 个目录均 DRAFT，0 approved，leakage NOT_RUN）
Hardware: READY（磁盘可写；CUDA/GPU 不可用）
Evaluation: READY（评测边界存在，但没有真实输入）
SFT: BLOCKED
Preference Optimization: NOT_READY
Baseline: NOT RUN
```

### 测试

| 命令 | 结果 |
|---|---|
| `python -m training.readiness` | PASS：生成 BLOCKED readiness 报告，未启动训练 |
| `python -m training.scripts.validate_datasets` | PASS：7 个 Manifest，0 promoted samples，质量/Baseline 为 NOT RUN |
| `python -m pytest tests/training -q` | 环境阻断：Windows `tmp_path` 创建目录返回 `WinError 5`；已执行的非临时目录测试通过，未将阻断计为 PASS |

### 剩余门禁

必须先提供人工审核的 REAL/明确标记 SYNTHETIC 样本、可用 evaluator 和真实模型 Provider，才可执行 Baseline；Baseline 完成前不得启动 RAG 消融、SFT 或 Preference Optimization。

### 对照报告（4）

新增文件：`docs/development/优化前后项目文件变动信息（4）.md`。该报告同步至桌面 `SmartOpsAgent-优化前后项目文件变动信息（4）.md`，包含本 Phase 的文件级前后对照、真实 Readiness、测试结果和后续建议。

## 2026-09-18 / Phase 4：Knowledge Tests 与 Windows Test Infrastructure

### 修改前

- `tests/knowledge/` 不存在，运行 `python -m pytest tests/knowledge -q` 为 0 tests collected/目录不存在。
- 训练测试的 `tmp_path` 依赖受限系统临时目录，部分用例返回 Windows `WinError 5`。

### 修改后

- 新增 Knowledge 纯单元测试 11 个文件，覆盖 ingestion、chunking、embedding、vector、BM25、hybrid、reranker、version、evidence、trust。
- `tests/conftest.py` 新增项目内隔离 `tmp_path` fixture：每个用例生成独立目录并清理，不依赖受限系统临时目录。
- 未修改 API、数据库表或业务契约。

### 真实测试结果

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/knowledge -q` | PASS：13 passed，1 个 pytest cache warning |
| `python -m pytest tests/training -q` | PASS：33 passed，1 个 pytest cache warning；WinError 5 已消除 |
| `python -m pytest tests/knowledge tests/training -q` | PASS：46 passed，1 个 pytest cache warning |
| `python -m training.readiness` | BLOCKED：Mock Provider、0 approved samples、训练依赖不完整、无 CUDA/GPU |
| `python -m training.scripts.validate_datasets` | PASS：7 个 Manifest，0 promoted samples，Baseline NOT RUN |

### 尚未执行

REAL Dataset 导入、Human Review、Approved Dataset、Baseline、RAG/Inspector/Verification Ablation、SFT、Preference Optimization、GPU Training 均保持 `NOT RUN/BLOCKED/NOT_READY`，没有伪造任何指标。

## 2026-09-18 / Phase 5：Training Gate 与 Candidate Review Lifecycle

### 修改前

- Readiness 已能发现 7 个 Dataset 均为空，但没有独立的 Candidate → Human Review → Approved 状态机。
- 没有针对“未明确人工批准不得晋级”的单元测试。

### 修改后

- 新增 `training/candidate_lifecycle.py`，实现 `CANDIDATE`、`VALIDATED`、`QUALITY_CHECKED`、`SAFE`、`REVIEW_PENDING`、`APPROVED` 及失败状态。
- 新增 `HumanReview` 数据模型，包含 review id、sample id、reviewer、status、reason、created/updated 时间。
- `promote()` 只有在候选状态、Review 状态和样本 `quality.human_review` 同时为 `APPROVED` 时才允许返回样本。
- 新增 `tests/training/test_candidate_lifecycle.py`，验证顺序转换和禁止自动批准。

### API / 数据库 / 数据

```text
API: UNCHANGED
Database: UNCHANGED
New training samples: NONE
Approved samples: 0
Secrets: not read, written or logged
```

### 真实结果

| 命令 | 结果 |
|---|---|
| `python -m training.readiness` | BLOCKED：Mock Provider、0 approved samples、训练依赖 PARTIAL、CUDA/GPU 不可用 |
| `python -m training.scripts.validate_datasets` | PASS：7 个 Manifest，质量 NOT RUN，Baseline NOT RUN |
| `python -m pytest tests/training -q` | PASS：36 passed，1 个 pytest cache warning |
| `python -m pytest -q` | PASS：89 passed，24 skipped，1 个 pytest cache warning |

### 明确未运行

没有真实数据导入、Human Review、Dataset Promotion、Baseline、Prompt Baseline、RAG/Inspector/Verification Ablation、SFT、Preference Optimization 或 GPU Training。不得由本阶段结果推导任何模型指标。

### 对照报告（6）

新增并同步桌面文件：`docs/development/优化前后项目文件变动信息（6）.md` / `SmartOpsAgent-优化前后项目文件变动信息（6）.md`，记录 Candidate 门禁、真实测试结果、当前阻塞状态和后续建议。

### 实验对照报告（7）

新增并同步桌面文件：`docs/experiments/前后实验对照数据（7）.md` / `SmartOpsAgent-前后实验对照数据（7）.md`，汇总 Baseline、Prompt Baseline、RAG、Inspector、Verification、SFT 和 Preference 的实验前后边界及后续建议。所有未执行实验保持 `NOT RUN/BLOCKED/NOT_READY`。

## 2026-09-18 / Phase 6：Training Gate Report

### 修改前

- Readiness、Quality、Manifest 和 Baseline 状态分散在多个报告中。
- 没有统一输出 Dataset、Approved Samples、Split、Leakage、Safety、Model、Evaluator、Baseline、Dependencies、Hardware 门禁的报告。

### 修改后

- 新增 `training/gate_report.py`。
- 生成 `training/training-gate-report.json` 与 `training/training-gate-report.md`。
- 报告只读取现有报告，不创建样本、不提升 Dataset、不调用模型、不修改 Registry。

### 真实 Gate 结果

```text
Overall: BLOCKED
Dataset: BLOCKED
Approved Samples: 0 / BLOCKED
Split: BLOCKED
Leakage: BLOCKED
Safety: BLOCKED
Model: BLOCKED（当前为 Mock）
Evaluator: BLOCKED
Baseline: BLOCKED / NOT RUN
Dependencies: BLOCKED
Hardware: READY（CUDA/GPU 不可用）
Training Allowed: NO
```

### 真实测试

| 命令 | 结果 |
|---|---|
| `python -m training.readiness` | BLOCKED，未启动训练 |
| `python -m training.scripts.validate_datasets` | PASS：7 个 Manifest，0 approved，Baseline NOT RUN |
| `python -m training.gate_report` | PASS：生成统一 BLOCKED Gate Report，不调用模型 |
| `python -m pytest tests/training -q` | PASS：36 passed，1 个 cache warning |
| `python -m pytest tests/knowledge -q` | PASS：13 passed，1 个 cache warning |
| `python -m pytest -q` | 上一轮真实结果：89 passed / 24 skipped |

### 明确未运行

Dataset 导入、Human Review、Grouped Split、Leakage、Safety、REAL Model、Evaluator、Prompt Baseline、Real Baseline、RAG/Inspector/Verification Ablation、SFT、Preference 和 GPU Training 均未运行或被门禁阻断。

### 对照报告（8）

新增并同步桌面文件：`docs/development/优化后项目变动数据前后对照（8）.md` / `SmartOpsAgent-优化后项目变动数据前后对照（8）.md`，记录统一 Training Gate、真实状态、测试结果和后续修改建议。

### 对照报告（5）

新增并同步桌面文件：`docs/development/优化前后项目文件变动信息（5）.md` / `SmartOpsAgent-优化前后项目文件变动信息（5）.md`，记录 Phase 4 的测试恢复、真实结果与下一步建议。

Baseline、真实数据集发布、SFT、DPO/Preference Optimization、GPU 训练、RAG/Inspector Ablation、OpsBench、模型 Artifact 和 TRAINED Registry 状态均未执行。
