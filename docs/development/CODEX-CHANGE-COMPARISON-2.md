# SmartOpsAgent 修改前后优化对比与建议（2）

- 项目：智维Agent / SmartOpsAgent
- 项目路径：`D:\SmartOpsAgent`
- 生成日期：2026-09-18
- 说明：当前目录没有可用 Git 历史。本文件依据 Phase 0 扫描记录、修改前读取到的行为和实际测试结果整理，不伪造逐行历史 diff。

## 一、总体变化

| 模块 | 修改前 | 修改后 |
|---|---|---|
| Shell 安全 | `shell=True` 字符串执行，存在注入边界 | argv、allowlist、参数校验、危险元字符拒绝、`shell=False`、timeout、输出限制 |
| Model Runtime | 匿名请求可能接触包含解密 Key 的 Entity | 保留原 Runtime URL/Method；Internal Token；仅返回非秘密 DTO |
| Model 调用 | AI Service 可能需要模型运行时秘密 | Backend 新增受保护 Invoke 代理，Key 只在 Backend 内存中短暂使用 |
| Backend 安全 | `/api/**` 统一匿名放行 | PUBLIC / USER / INTERNAL 分类；Runtime、Invoke、Inspector 写入受内部 Token 保护 |
| Inspector | 主要是 Python Pipeline，缺少产品链路 | Trace → Inspector → Persistence → Backend API → Center/Detail/Statistics UI |
| Frontend | 双 Axios 实例，构建未稳定验证 | `http.js` 兼容导出单一请求层；Inspector、Trace、Knowledge、Model Health 页面可构建 |
| Database | 只有既有业务表 | additive migration 增加 Inspector Event/Issue/Evidence/Verification 表，既有表不变 |
| Training Schema | 仅旧式字段检查 | Schema v1 统一 Task、Environment、Knowledge、Evidence、Policy、Output、Verification、Inspector、Source、Quality、Metadata |
| Training Data | 无角色化数据链与来源门禁 | SFT、Preference、Evidence、Inspector builder；REAL/SYNTHETIC/DEMO 分离；质量状态 PENDING |
| Split/Leakage | 无分组切分和泄漏检查 | 按事件族、根因、环境、版本、场景分组；生成 exact/scenario/evidence 等泄漏报告 |
| Evaluation | 仅有 NOT RUN 骨架 | 只接受 observed evaluator rows；无 evaluator 仍返回 NOT RUN，不产生虚假数字 |
| Model Registry | 无状态保护 | 只有 artifact + COMPLETED evaluation 才能标记 TRAINED |

## 二、关键新增能力

### 1. Inspector 闭环

```text
Agent Trace
→ Rule / Evidence / AI Judge / Verifier
→ Agent Persistence Adapter
→ Inspector DB
→ Backend API
→ Inspector Center / Detail / Statistics
```

### 2. 训练数据闭环基础

```text
Incident Candidate
→ Schema Validation
→ Rule / Safety Validation
→ Deduplication
→ Grouped Split
→ Leakage Check
→ Human Sampling
→ SFT / Preference / Evidence / Inspector Candidate
```

### 3. Synthetic Incident

已实现 10 类候选事件：

```text
Nginx 502 / 504
Redis Memory High
MySQL Slow Query
Docker Container Down
Kubernetes Pod Crash
Disk Full
CPU High
Memory Leak
Network Timeout
```

包含冲突证据、版本差异、证据不足、危险工具和审批要求等难例。所有候选明确为 `SYNTHETIC`，未自动晋升训练集。

## 三、API、数据库和配置结论

- 既有 Server、Metric、Chat、Knowledge、Model Connection URL/Method 未修改。
- 新增 Inspector API 和 Model Invoke 代理 API，均为增量接口。
- 既有 `server`、`server_metric`、`model_connections` 未删除或重命名。
- 未写入任何密码、API Key、Token、密文或 GPU 假配置。
- 不展示隐藏 Chain-of-Thought，只保留可审计 `reasoning_summary`。

## 四、真实验证结果

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/training -q` | PASS：29 passed |
| `python -m pytest -q` | PASS：69 passed，24 skipped |
| `cd backend && mvn -q test` | PASS |
| `cd frontend && npm run build` | PASS：1736 modules transformed；主 chunk > 500 kB 警告 |

24 个根测试跳过项是实际环境条件：Backend/AI Service 未在线、`SMARTOPS_AGENT_URL` 未设置、缺少 `mysql.connector` 或 `redis`。未修改测试以掩盖这些条件。

## 五、明确未完成项

- Knowledge 独立测试仍为 0 tests collected。
- 未执行真实 MySQL/Redis 在线联调和真实 LLM 调用。
- 未发布真实训练数据集。
- 未执行 Baseline、OpsBench、SFT、Preference Optimization、Inspector Evaluation 或 Ablation。
- 未进行 GPU/CUDA 训练，没有 Loss、Accuracy、Precision、Recall、Latency、Token Cost 或训练 Artifact。

## 六、最后建议

### 安全配置

1. MySQL 密码只写入本机 `.env` 或系统环境变量，不写入源码、Markdown、`.env.example` 或 Git。
2. 已在对话中暴露的数据库密码应视为已泄露，生产环境应立即轮换为强密码。
3. 生产环境保持 `SMARTOPS_INTERNAL_BYPASS=false`，并手动设置高强度 `SMARTOPS_INTERNAL_TOKEN`。
4. 完成 MySQL、Redis、LLM、AES-GCM、Internal Token 配置后，再运行 `scripts/windows/check-config.ps1`；脚本只输出状态，不输出秘密。

### 训练实施顺序

1. 先接入经过人工审核的真实 Agent Trace 和日志，保持 `REAL` 与 `SYNTHETIC` 分开。
2. 执行质量门禁、分组切分和 `leakage_report.json`，确认无事件族、根因、环境、版本泄漏。
3. 先运行真实 Baseline，再运行 RAG、Evidence、Inspector、Verification 对照实验。
4. 只有获得真实评测结果和模型 Artifact 后，才允许 Registry 状态变为 `TRAINED`。
5. 训练过程记录 dataset version、hardware、config、start/end time、loss 和 evaluation；缺失字段保持 `NOT RUN` 或 `null`。

### 工程收口

1. 优先拆分 Frontend 主 chunk，解决当前 >500 kB 构建警告。
2. 为 Knowledge 增加可收集的独立测试，覆盖版本匹配、证据支持、冲突和低信任知识。
3. 启动 Backend/AI Service/MySQL/Redis 后，再补跑当前 24 个跳过的集成测试。
4. 将 Dataset Manifest、Quality Report、Leakage Report、Evaluation Report 和 Model Registry 作为比赛演示的可审计证据，而不是展示虚构指标。

## 七、项目内详细记录

- `docs/OPTIMIZATION-CHANGES.md`
- `docs/development/CODEX-CHANGE-COMPARISON.md`
- `docs/experiments/training-plan.md`
- `docs/experiments/evaluation-plan.md`
- `docs/MANUAL-CONFIGURATION.md`
