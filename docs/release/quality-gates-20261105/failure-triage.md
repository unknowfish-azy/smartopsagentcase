# HC-05 失败分类与归因规则

| 项 | 值 |
|---|---|
| task_id | HC-05 |
| mode | PLAN |
| 日期 | 2026-11-05 |
| 输入 | `quality-gate.md` 的五态定义、`docs/audit/20261105/test-matrix.md` 历史记录、本轮只读核查 |
| 本轮执行 | **未执行**；本文只给未来 RUN 的归因口径 |

目标：任何一个 `FAIL`/`ERROR`/`SKIP`/`NOT_RUN` 都必须能回答“是谁的问题、怎么复现、证据在哪、下一步做什么”，且不允许通过改测试或放宽阈值来消除。

---

## 1. 分类总表

| 类别 | 一句话定义 | 典型特征 | 对发布的影响 | 默认状态 |
|---|---|---|---|---|
| `REAL_FAIL` | 代码、测试期望或构建产物真实不满足 | 断言失败；构建报错；类型错误；lint error | 阻断 | `FAIL` |
| `ENV_FAIL` | 执行环境不满足，代码本身未被有效验证 | JDK 版本、端口占用、缺 env 键、Python/Node 版本、浏览器缺失、OS 差异 | 阻断对应门禁；整体 `NO_GO` | `NOT_RUN/BLOCKED_ENV` 或 `ERROR` |
| `EXPECTED_REJECT` | 系统按设计拒绝，但测试/探针期望不匹配 | 401/403、租户隔离、readiness false、参数校验拒绝 | 期望未被正确断言时阻断 | `FAIL`；断言正确时属正常用例 |
| `DEP_MISSING` | 生产/测试必需依赖不存在 | pip 包缺失、Playwright/Edge 缺失、Ollama 模型缺失、容器未起 | 阻断对应门禁 | `NOT_RUN/BLOCKED_DEP` |
| `FIXTURE_DIFF` | fixture 与真实链路、或旧期望与当前实现存在差异 | fixture 响应与真实 Provider 不同；历史期望过期；版本升级导致行为变化 | 阻断“真实通过”声明 | `FAIL`，或经批准后 `NOT_RUN` 单列 |
| `FLAKY`（子类） | 同一命令多次结果不稳定 | 偶发超时、随机端口冲突、并发写冲突 | 阻断，等待稳定证据 | `ERROR/FLAKY` |

补充：`NOT_RUN` 不是失败，但在发布算法中与失败一样阻断必需门禁。不能因为“没跑”就降级为“无关”。

---

## 2. 判定流程（按顺序，不得跳步）

1. **看退出码与收集数**：退出码 0 但 `collected=0` → `FAIL/EMPTY_SUITE`，不是通过。
2. **看是收集期还是执行期**：导入错误、语法错误、插件加载失败、解释器崩溃 → `ERROR`；用例已开始后的断言失败 → `FAIL`。
3. **看首个失败文本**：区分“期望值不匹配”“依赖不存在”“连接被拒绝”“版本不支持”。
4. **查环境指纹**：Java/Python/Node/Maven/浏览器/端口/env 是否与报告一致。不一致 → 优先 `ENV_FAIL`。
5. **查依赖**：导入目标包/浏览器/模型/容器是否存在。缺失 → `DEP_MISSING`。
6. **最小复现**：单文件、单用例、单构建命令，`--tb=long -x` 或等价参数；保存完整日志。
7. **与历史/基线比对**：历史绿、本轮红时，先判断源码变化或环境漂移，不得直接改期望。
8. **复跑上限 3 次**：三次同因 → 确定性结论；间歇 → `ERROR/FLAKY`，交模块负责人。
9. **指派负责人并给出出口**：修复、降级为 NOT_RUN 并解除条件、或明确接受缺口（仅限非必需项）。
10. **独立复核**：修复后重跑必须由非修改者复核日志与状态。

---

## 3. 分类细则

### 3.1 `REAL_FAIL`（真实失败）

| 项 | 内容 |
|---|---|
| 识别特征 | 断言失败、期望值不符、构建/类型/lint 报错；依赖齐全、环境版本符合；同一环境可稳定复现 |
| 复现（项目根） | `python -m pytest <failing nodeid> -q --tb=long`；日志写入 `$run\triage\REAL_FAIL\<gate>.log` |
| 复现（前端） | `cd d:\SmartOpsAgent\frontend; node --test test\<file>.test.mjs`；或 `node --test --test-name-pattern "<name>" test\<file>.test.mjs` |
| 复现（Java） | `cd d:\SmartOpsAgent\backend; mvn -B test -Dtest=<Class>#<method>` |
| 复现（构建） | `cd d:\SmartOpsAgent\frontend; npm run build -- --outDir ../.runtime/hc-check/<runId>/triage/REAL_FAIL/user-dist` |
| 日志采集点 | pytest 全量输出与 `-ra`；Node test TAP 输出；`backend/target/surefire-reports/` 下的 `*.txt`、`*.xml`；vite 构建全量日志；首个失败堆栈与输入数据 |
| 判定负责人 | 模块 owner 定位；HC-05 owner 记录；独立复核人确认复现 |
| 不得做 | 批量改测试期望、删除用例、把断言改宽、加无条件 skip、用 `-k` 排除、只保留绿色重跑结果 |
| 出口 | 修复源码/测试期望并附变更理由 → 重跑同命令 → `PASS`；否则保持 `FAIL`，发布 `NO_GO` |

### 3.2 `ENV_FAIL`（环境失败）

| 项 | 内容 |
|---|---|
| 识别特征 | JDK/Python/Node/Maven 版本不符；端口被未知进程占用；`.env` 缺键；数据库/Redis 不可达；浏览器不存在；OS 路径差异 |
| 典型本项目案例 | PATH `java 1.8.0_202` vs `pom.xml` 17 → `NOT_RUN/BLOCKED_ENV`；`start-all.ps1` 端口被未知进程占用；`.env` 缺 `SMARTOPS_INTERNAL_TOKEN`；非 Windows 缺 Edge |
| 复现（项目根） | `java -version; mvn -v; node --version; python --version`；`Get-NetTCPConnection -LocalPort 8080 -State Listen`；键名存在性脚本见 `preflight.md` C02 |
| 日志采集点 | `preflight\<ID>-*.txt`、服务启动日志 `.runtime\launcher-logs\*`、`.runtime\logs\*`；只记录布尔/版本，不记录 secret |
| 判定负责人 | 环境 owner 修复工具链/端口/env；HC-05 owner 记录阻塞；不得由模块 owner “改代码绕过” |
| 不得做 | 改 `pom.xml` 的 Java 17 要求、降级依赖、kill 未知 PID、改全局环境变量、把 `BLOCKED_ENV` 写成 `SKIP` |
| 出口 | 环境修复并留下版本/端口/env 键证据 → 重跑；否则 `NOT_RUN/BLOCKED_ENV`，发布 `NO_GO` |

Java 17 解除步骤见 `quality-gate.md` 3.2；只切当前进程，不安装、不改系统配置。

### 3.3 `EXPECTED_REJECT`（预期拒绝）

| 项 | 内容 |
|---|---|
| 识别特征 | 系统按设计返回 401/403、租户隔离空结果、readiness 503/false、参数校验 400、审批拒绝；测试却期望 200/成功 |
| 关键原则 | “预期拒绝”不是“任何报错都算通过”。必须断言**具体状态码/错误码/消息/副作用**；`HTTP 200 + success=false` 不得被 UI 测试当作成功 |
| 复现（项目根） | 定向用例：`python -m pytest <nodeid> -q --tb=short`；接口用已脱敏的 curl/httpx 请求，保存状态码与响应体（去除 token） |
| 复现（知识/健康） | `Invoke-WebRequest http://127.0.0.1:8002/api/ready -SkipHttpErrorCheck`，断言 `status=READY` 且 `chunks>0`；空索引时必须断言非 READY |
| 日志采集点 | 请求方法/路径/状态码/错误码；服务端审计日志；测试断言原文；不得保存 Authorization/Cookie |
| 判定负责人 | 模块 owner 确认安全/业务语义；安全相关由独立审阅人复核 |
| 不得做 | 把 401/403 改成“跳过”；用宽泛 `pytest.raises(Exception)`；把业务失败当 HTTP 成功；删除负向用例 |
| 出口 | 断言修正到具体拒绝语义并通过 → `PASS`；若拒绝行为本身错误 → 转 `REAL_FAIL` |

### 3.4 `DEP_MISSING`（依赖缺失）

| 项 | 内容 |
|---|---|
| 识别特征 | `ModuleNotFoundError`、`Cannot find module`、Playwright/Edge 缺失、Ollama 模型不存在、Docker 容器未启动、`knowledge:check` 找不到 manifest |
| 复现（项目根） | `python -c "import fastapi, pytest, numpy"`；`Test-Path frontend\node_modules\playwright\package.json`；`Test-Path 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'`；`Invoke-RestMethod http://127.0.0.1:11434/api/tags`（仅列模型名） |
| 日志采集点 | `pip list --format=json`、`npm ls --depth=0 --json`、依赖导入错误原文、容器 `docker ps -a`、模型 tags |
| 判定负责人 | 环境/依赖 owner 安装或提供；HC-05 owner 记录 `BLOCKED_DEP` |
| 不得做 | 在未授权时 `pip install`/`npm install`；把缺失依赖的 skip 计入通过；用 mock 替代真实 Provider 后宣称 real |
| 出口 | 依赖就绪并记录版本 → 重跑；否则 `NOT_RUN/BLOCKED_DEP`，必需项 `NO_GO` |

注意：`pip install`、`npm ci` 可能访问网络，属于 RUN 动作，必须先获授权并记录 lock hash；本 PLAN 不执行。

### 3.5 `FIXTURE_DIFF`（fixture/真实差异）

| 项 | 内容 |
|---|---|
| 识别特征 | fixture 下通过、真实链路失败；历史期望与当前实现不一致；相同输入在 fixture 与真实 Provider 返回结构/字段不同；fixture 数据版本落后 |
| 复现 | 同一用例分别以 `fixture=true` 与 `fixture=false` 运行；记录输入、fixture 文件版本/hash、真实请求摘要（脱敏）；输出到 `$run\triage\FIXTURE_DIFF\` |
| 日志采集点 | fixture 文件路径与 hash、真实响应关键字段、模型/服务版本、run_id；禁止保存私有 Prompt 与完整模型输出中的敏感内容 |
| 判定负责人 | 模块 owner 判断代码还是 fixture 过期；HC-05 owner 决定是否允许 `RELEASE_CONDITIONAL`；独立审阅人复核 |
| 不得做 | 把 fixture 结果写成真实通过；为了让真实失败变绿而改 fixture 期望；把真实 Provider 缺失降级为 `SKIP` |
| 出口 | 修正 fixture 并说明依据 → 重跑；真实不可用 → `NOT_RUN/BLOCKED_DEP`；差异属实现缺陷 → `REAL_FAIL` |

真实 Provider、真实账号、真实库缺失时，`REAL-E2E` 只能 `NOT_RUN/BLOCKED_DEP`；`fixture` 通过只支持“受控输入下行为”。

---

## 4. FLAKY / 超时

| 项 | 内容 |
|---|---|
| 识别特征 | 同命令同环境三次中部分通过；随机端口冲突；并发写同一目录；网络抖动 |
| 处理 | 连续 3 次同环境复跑，记录每次 exit code 与日志；全部同因才算确定性；否则 `ERROR/FLAKY` |
| 复现 | 同门禁命令重复 3 次，输出 `$run\triage\FLAKY\<gate>-run1..3.log` |
| 负责人 | 模块 owner 定位竞态；环境 owner 定位端口/网络 |
| 不得做 | “重试直到绿”；只保留成功那次；把 flaky 写成 PASS；通过加大超时掩盖问题（超时调整需单独评审） |
| 出口 | 修复竞态或隔离端口 → 3 次稳定 PASS；否则保持 `ERROR`，发布 `NO_GO` |

超时类（pytest/vite/playwright 超时）先归 `ERROR`，再按栈判断是 `ENV_FAIL`（机器慢/端口）还是 `REAL_FAIL`（死锁/无限等待）。固定 `sleep` 不能作为 readiness 证据。

---

## 5. 单条归因记录模板

每次失败在 `$run\evidence\incidents.yaml` 追加：

```yaml
- incident_id: <gate>-<seq>
  gate_id: PY-AGENT
  run_id: 20261105-XXXXXX-HC05
  command: python -m pytest tests/inspector tests/agent -q
  cwd: d:\SmartOpsAgent
  exit_code: 1
  collected: 80
  failed: 1
  first_failure: "<文件:行号 断言摘要，脱敏>"
  classification: REAL_FAIL|ENV_FAIL|EXPECTED_REJECT|DEP_MISSING|FIXTURE_DIFF|FLAKY
  severity: BLOCKER|MAJOR|MINOR
  fixture: true
  real_provider: false
  evidence_paths:
    - .runtime/hc-check/<runId>/logs/PY-AGENT.log
  owner: <role>
  decision: FIX_CODE|FIX_ENV|FIX_FIXTURE|BLOCKED|ACCEPTED_GAP
  retest_command: <same>
  retest_result: PASS|FAIL|NOT_RUN
  reviewer: <role>
```

没有 `classification`、`owner`、`evidence_paths`、`retest_command` 的记录，视为未归因，发布结论只能是 `NO_GO`。

---

## 6. 绝对禁止的处理方式

1. 批量修改测试期望、删除/重命名失败用例、把断言改成 `assert True`。
2. 用 `-k`、`--ignore`、`testpaths` 缩小范围来绕开失败。
3. 抬高 `--max-warnings`、关闭 ESLint 规则、`continue-on-error: true` 掩盖 CI 失败。
4. `git reset --hard`、`git clean -fdx`、`git checkout -- .`、`git restore .`、删除他人未提交改动。
5. 在真实库执行迁移逆向、`flyway clean`、`DROP DATABASE`。
6. 修改 `pom.xml` 的 Java 版本要求、`requirements.txt` 去掉失败依赖、`package.json` 去掉测试脚本。
7. 把 `SKIP`/`NOT_RUN`/历史结果/静态计数写成 `PASS`；把 fixture 结果写成真实 Provider 通过。
8. 在日志、截图、报告中输出 `.env` 值、token、API Key、真实账号密码、私有 Prompt。
9. 用固定 `sleep` 或“端口在监听”冒充 readiness。
10. 无授权安装依赖、启动服务、访问外网。

---

## 7. 与门禁的联动

| 分类 | 门禁状态更新 | 发布结论 |
|---|---|---|
| `REAL_FAIL` | 对应门禁 `FAIL` | `NO_GO` |
| `ENV_FAIL` | 对应门禁 `NOT_RUN/BLOCKED_ENV`；若已执行中断则 `ERROR` | `NO_GO` |
| `EXPECTED_REJECT` 未正确断言 | 对应门禁 `FAIL` | `NO_GO` |
| `DEP_MISSING` | 对应门禁 `NOT_RUN/BLOCKED_DEP` | 必需项 `NO_GO`；条件项 `RELEASE_CONDITIONAL` 并登记缺口 |
| `FIXTURE_DIFF` | 与真实相关的声明 `NOT_RUN`；实现缺陷则 `FAIL` | 不得声称真实通过 |
| `FLAKY` | `ERROR` | `NO_GO`，直到 3 次稳定 |

最终状态必须回写到 `quality-gate.md` 的 `report.yaml`，并保留原始日志与复现命令；不得只在聊天里口头描述。
