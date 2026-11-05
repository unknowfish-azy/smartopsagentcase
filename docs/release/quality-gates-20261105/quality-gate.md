# HC-05 统一质量门禁（v1）

| 项 | 值 |
|---|---|
| task_id | HC-05 |
| mode | PLAN |
| 日期 | 2026-11-05 |
| 基线 | HEAD `48b8af47603e3d7e2b04b7bae81c667c588328dc`；工作树 359 条他人改动（不改、不还原、不纳入差分） |
| 输入 | `docs/audit/20261105/test-matrix.md`、`status-baseline.md`、`inventory.json`；`pytest.ini`、`frontend/package.json`、两份 vite 配置、`backend/pom.xml`、`.github/workflows/ci.yml`、`scripts/windows/*.ps1`、`deploy/server/*.sh` |
| 本轮状态 | 全部门禁 `NOT_RUN`；未执行测试、构建、启动、git 写操作 |
| 设计状态 | `DONE`（本文档） |
| 实现状态 | `NOT_STARTED`（后续 IMPLEMENT 才改脚本/CI） |
| 验证状态 | `NOT_RUN`（无本轮原始输出） |

本文只定义“怎样才算通过”和“证据长什么样”。任何数字若来自历史日志，必须带 `evidence_class=HISTORICAL`；不得在本轮报告里写成“已通过”。

---

## 1. 五态枚举与判定规则

### 1.1 状态定义

| 状态 | 定义 | 退出码/结果特征 | 计数方式 | 最低证据 |
|---|---|---|---|---|
| `PASS` | 本轮实际执行，且达到该门禁阈值 | 退出码 0，且 collected>0、failed=0、errors=0，所有 skip 有原因 | 计入通过分子/分母 | 命令、工作目录、退出码、原始输出、开始/结束时间、输入 hash、fixture/real 标志 |
| `FAIL` | 本轮实际执行，断言/业务检查/构建结果不满足期望 | 退出码非 0，且失败来自代码、测试期望或构建产物；或报告明确列出失败项 | 计入 failed | 同上 + 首个失败用例与失败摘要 |
| `SKIP` | 运行器实际执行了，但用例被 runner 标记跳过（`skip`/`xfail`/条件跳过） | 退出码可为 0；报告含 skipped 数及原因 | 不计入通过，单列 skipped | 跳过原因、依赖项、替代证据 |
| `ERROR` | 执行中断或无法产生有效断言结果 | 收集失败、导入失败、解释器崩溃、超时、端口冲突、插件异常、构建进程被杀 | 不计入任何通过统计 | 中断点日志、异常栈、复现命令、归因分类 |
| `NOT_RUN` | 本轮根本没有执行 | 无退出码；必须写子原因码 | 不计入分母 | 未执行原因、阻塞证据、解除条件 |

### 1.2 `NOT_RUN` 子原因码

`BLOCKED` 不是第六种状态，而是 `NOT_RUN` 的原因码。

| 原因码 | 含义 | 本项目示例 |
|---|---|---|
| `NOT_AUTHORIZED` | 本轮未获 RUN 授权 | 所有套件本轮默认值 |
| `BLOCKED_ENV` | 工具链/端口/环境变量/数据库不满足 | PATH 上 `java 1.8.0_202`，`pom.xml` 要求 17 |
| `BLOCKED_DEP` | 生产必需依赖缺失（浏览器、模型、系统库） | 浏览器脚本硬编码本机 Edge；真实 Provider 未启动 |
| `BLOCKED_NETWORK` | 外网/审批通道不可达 | 历史 WinError10013、审批 404；GitHub 实时核验 |
| `DESELECTED` | 经明确决策本次不跑 | 性能实验按冻结协议暂缓 |
| `NOT_APPLICABLE` | 本变更不涉及该门禁 | 纯文档变更时的浏览器门禁 |

### 1.3 硬性规则

1. **未运行 ≠ 通过**：`NOT_RUN`、`SKIP`、历史结果都不能计入本轮 pass。
2. **五态互斥**：一个门禁一行一个状态；不得写“基本通过”“部分通过”。部分用例失败时整项为 `FAIL`。
3. **零收集即失败**：退出码 0 但 collected=0，判 `FAIL`（`EMPTY_SUITE`），不算 `PASS`。
4. **生产依赖缺失不得静默 skip**：因真实数据库、真实 Provider、浏览器、模型缺失而跳过的，整项升级为 `NOT_RUN/BLOCKED_DEP`；只有测试内显式标记且不影响发布结论的可选依赖，才允许 `SKIP`。
5. **历史不继承**：必须写 `evidence_class=HISTORICAL`，并注明原始时间；不能替代本轮验收。
6. **fixture 与 real 分账**：`fixture=true` 只证明受控输入下的行为；真实 Provider/真实账号/真实库必须另有 `fixture=false` 证据。
7. **不重试洗绿**：同一命令最多复跑 3 次；只有三次均同因失败才算确定性结论。间歇失败记 `ERROR/FLAKY`，不得只保留绿色那次。
8. **阈值是上限不是目标**：`--max-warnings 31` 是存量债务上限；为了让门禁变绿而抬高阈值，本身判 `FAIL` 流程违规。
9. **静态声明数 ≠ 通过数**：`466` 个前端 `test()/it()`、`441` 个 Java 注解、`59` 个 `test_*.py` 只能作为“声明面”，不得写成 passed。
10. **每项必须有命令、目录、退出码、原始输出**；缺任一项，状态只能是 `NOT_RUN`，不能是 `PASS`。

---

## 2. 证据目录与报告字段

### 2.1 统一运行目录

`runId` 固定格式：`YYYYMMDD-HHMMSS-HC05`。所有输出只写入仓库内已被 `.gitignore` 忽略的 `.runtime`，不污染 `frontend/dist`、`frontend/dist-admin` 或他人文件。

```text
d:\SmartOpsAgent\.runtime\hc-check\<runId>\
  preflight\preflight.json
  logs\<gate-id>.log
  logs\<gate-id>.exit.json
  junit\<gate-id>.xml            # 仅当运行器支持时
  artifacts\user-dist\
  artifacts\admin-dist\
  hashes\inputs.json
  hashes\artifacts.json
  browser\<gate-id>\
  evidence\report.yaml
```

工作目录约定：

| 目录 | 绝对路径 |
|---|---|
| 项目根 | `d:\SmartOpsAgent` |
| 前端 | `d:\SmartOpsAgent\frontend` |
| 后端 | `d:\SmartOpsAgent\backend` |
| 运行证据根 | `d:\SmartOpsAgent\.runtime\hc-check\<runId>` |

### 2.2 每条命令的采集模板（PowerShell，未来 RUN 使用）

```powershell
$runId  = Get-Date -Format 'yyyyMMdd-HHmmss'
$run    = "d:\SmartOpsAgent\.runtime\hc-check\$runId-HC05"
$log    = "$run\logs\PY-AGENT.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
Push-Location 'd:\SmartOpsAgent'
& python -m pytest tests/inspector tests/agent -q *>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
@{ gate='PY-AGENT'; exit_code=$code; started=(Get-Date).ToString('o') } |
  ConvertTo-Json | Set-Content -LiteralPath "$run\logs\PY-AGENT.exit.json" -Encoding UTF8
Pop-Location
```

要点：`$LASTEXITCODE` 必须在被下一条命令覆盖前读取；日志必须保留失败行与 skip 原因，不能只保存最后一行。

### 2.3 输入版本 hash（每次 RUN 必存）

文件清单：

```text
frontend/package.json
frontend/package-lock.json
frontend/vite.config.js
frontend/vite.config.admin.mjs
pytest.ini
ai-service/requirements.txt
knowledge/requirements.txt
backend/pom.xml
.github/workflows/ci.yml
docs/development/GH-P0-01-dependency-lock.json
```

命令与输出：

```powershell
$files = @(
  'frontend\package.json','frontend\package-lock.json','frontend\vite.config.js',
  'frontend\vite.config.admin.mjs','pytest.ini','ai-service\requirements.txt',
  'knowledge\requirements.txt','backend\pom.xml','.github\workflows\ci.yml',
  'docs\development\GH-P0-01-dependency-lock.json'
)
Get-FileHash -Algorithm SHA256 -LiteralPath $files |
  Select-Object Path,Hash | ConvertTo-Json |
  Set-Content -LiteralPath "$run\hashes\inputs.json" -Encoding UTF8
```

同时记录：Node/npm/Python/Java/Maven 版本、`git rev-parse HEAD`、`git status --porcelain` 条目数、OS 版本、时区。禁止写入 `.env`、token、API Key、私有 Prompt 的值。

### 2.4 报告字段（与交接书 7.1 一致）

`evidence/report.yaml` 至少包含：

```yaml
run_id: 20261105-XXXXXX-HC05
task_id: HC-05
mode: RUN
input_versions:
  head: <sha>
  dirty_entries: <n>
  node: <version>
  python: <version>
  java: <version>
  maven: <version>
gates:
  - id: PY-AGENT
    state: PASS|FAIL|SKIP|ERROR|NOT_RUN
    reason_code: null|NOT_AUTHORIZED|BLOCKED_ENV|BLOCKED_DEP|BLOCKED_NETWORK|DESELECTED|NOT_APPLICABLE
    command: <exact command>
    cwd: <absolute path>
    exit_code: <int|null>
    collected: <int|null>
    passed: <int|null>
    failed: <int|null>
    errors: <int|null>
    skipped: <int|null>
    fixture: true|false
    real_provider: true|false
    started_at: <iso8601>
    finished_at: <iso8601>
    evidence_paths: []
    unresolved_issues: []
numerator_denominator: "<passed>/<collected>"
release_decision: RELEASE_READY|RELEASE_CONDITIONAL|NO_GO
rollback_location: .runtime/hc-check/<runId>/rollback/
independent_reviewer: <role or PENDING>
```

---

## 3. 套件门禁表

阈值统一前提：命令由本轮执行、原始输出已落盘、工作目录与下表一致。

### 3.1 Python

| Gate ID | 套件 | 工作目录 | 命令 | PASS 阈值 | 必存原始输出 | fixture/real | 级别 |
|---|---|---|---|---|---|---|---|
| PY-AGENT | Inspector + Agent 回归 | `d:\SmartOpsAgent` | `python -m pytest tests/inspector tests/agent -q` | 退出码 0；collected>0；failed=0；errors=0；skip 全部有原因 | stdout/stderr 全量、`-ra` 摘要、退出码 | fixture | 必需 |
| PY-KNOW | Knowledge 服务 | `d:\SmartOpsAgent` | `python -m pytest tests/knowledge -q` | 同上；真实索引依赖缺失时整项 `NOT_RUN/BLOCKED_DEP` | 同上 + 依赖导入信息 | fixture（本地语料） | 必需 |
| PY-AI | AI Service | `d:\SmartOpsAgent` | `python -m pytest ai-service/app/tests -q` | 同上；不得因 `.env` 缺失而静默跳过身份/流式用例 | 同上 + 失败用例的请求/响应摘要（脱敏） | fixture（mock/本地 Ollama 可标 real_provider=false） | 必需 |
| PY-TRAIN | 训练/评测 | `d:\SmartOpsAgent` | `python -m pytest tests/training -q` | 退出码 0；collected>0；failed=0；errors=0 | 同上 + 计分器相关失败上下文 | fixture | 必需 |
| PY-CI-PARITY | CI 口径合并 | `d:\SmartOpsAgent` | `python -m pytest tests/knowledge ai-service/app/tests -q` | 与 PY-KNOW+PY-AI 分项结论一致；不得一项绿一项红时合并成绿 | 合并日志与分项日志同时保存 | fixture | 条件（发布对照） |

说明：历史锚点仅作规模参考——Agent 80 passed、Knowledge 54 passed、AI Service 53 passed（2026-11-05T08:13Z）。它们是 `HISTORICAL`，不是本轮阈值；首次本轮运行后把 collected 写入基线，后续低于基线需解释是删除/跳过还是源码变化。

### 3.2 Java

| Gate ID | 套件 | 工作目录 | 命令 | PASS 阈值 | 必存原始输出 | fixture/real | 级别 |
|---|---|---|---|---|---|---|---|
| JAVA-TEST | Maven 单元/切片测试 | `d:\SmartOpsAgent\backend` | `mvn -B test` | JDK≥17；退出码 0；`Tests run` 总数>0；failures=0；errors=0；skipped 逐条有 `@Disabled` 原因 | 控制台全量日志、`backend/target/surefire-reports/**`、`mvn -v` 输出 | fixture（H2/测试库；须确认未连生产库） | 必需 |

当前阻塞：PATH 上 `java -version` 为 `1.8.0_202`，`backend/pom.xml` 的 `<java.version>17</java.version>` 不满足，故 JAVA-TEST 状态为 `NOT_RUN/BLOCKED_ENV`。Maven 与 `.m2` 的存在不能替代 JDK。

解除步骤（后续 RUN，由环境负责人执行；本任务不下载、不安装）：

1. 只读确认项目启动脚本默认引用的 JDK17 路径：
   `Test-Path "$env:USERPROFILE\scoop\apps\openjdk17\current\bin\java.exe"`
2. 若存在，执行 `& "$env:USERPROFILE\scoop\apps\openjdk17\current\bin\java.exe" -version`，输出必须为 `17.x`。
3. 仅在当前进程设置 `JAVA_HOME` 与 `Path`，再执行 `mvn -v` 确认 “Java version: 17”。
4. 若候选路径不存在或版本不为 17，保持 `BLOCKED_ENV`，由环境负责人提供受管 JDK17；不得把 Java 门禁降级为可选，也不得改 `pom.xml` 的 17 要求。
5. 解除后重跑 `mvn -B test` 并保存上述原始输出；失败按 `failure-triage.md` 分类。

### 3.3 前端静态与构建

| Gate ID | 套件 | 工作目录 | 命令 | PASS 阈值 | 必存原始输出 | fixture/real | 级别 |
|---|---|---|---|---|---|---|---|
| FE-UNIT | Node 单元测试 | `d:\SmartOpsAgent\frontend` | `npm test` | 退出码 0；tests>0；fail=0；cancelled=0；skip 有原因 | stdout/stderr、退出码、Node 版本 | fixture | 必需 |
| FE-TC | TypeScript 检查 | `d:\SmartOpsAgent\frontend` | `npm run typecheck` | 退出码 0；错误数=0 | `tsc --noEmit` 全量输出 | fixture | 必需 |
| FE-LINT | ESLint | `d:\SmartOpsAgent\frontend` | `npm run lint` | 退出码 0；warnings ≤ 31；记录实际 warning/error 数 | 全量输出 + 统计行 | fixture | 必需 |
| FE-BUILD | 用户端生产构建 | `d:\SmartOpsAgent\frontend` | `npm run build -- --outDir ../.runtime/hc-check/<runId>/artifacts/user-dist` | 退出码 0；`user-dist/index.html` 存在；`prebuild` 的 `knowledge:check` 通过；产物 hash 已记录；`frontend/dist` 前后 hash 不变 | 构建全量日志、产物文件清单、`hashes/artifacts.json`、`frontend/dist` 前后 hash | fixture（静态构建） | 必需 |
| FE-ADMIN | 管理端构建 | `d:\SmartOpsAgent\frontend` | `npm run build:admin -- --outDir ../.runtime/hc-check/<runId>/artifacts/admin-dist` | 退出码 0；`admin-dist/admin.html` 存在；产物 hash 已记录；`frontend/dist-admin` 前后 hash 不变 | 同上，管理端独立日志 | fixture | 必需 |

约束：

- `<runId>` 必须替换为本次真实目录名；输出目录必须**唯一且预先不存在**。已存在时先归档，不覆盖。
- `--outDir` 相对 `frontend` 解析，因此落到 `d:\SmartOpsAgent\.runtime\hc-check\<runId>\artifacts\...`。
- `build:admin` 的 vite 配置本身写 `dist-admin`；CLI `--outDir` 覆盖后，验收以 admin 产物目录为准。
- 构建前后对 `frontend\dist\index.html`、`frontend\dist-admin\admin.html` 做 SHA256；任一变化判 `FAIL`（违反“构建不删除/替换正在使用的制品”）。
- `prebuild` 的 `npm run knowledge:check` 失败属于构建门禁 `FAIL`，不是“附带警告”。

### 3.4 浏览器与真实链路

| Gate ID | 套件 | 工作目录 | 命令 | PASS 阈值 | 必存原始输出 | fixture/real | 级别 |
|---|---|---|---|---|---|---|---|
| FE-VISUAL | 视觉/交互回归 | `d:\SmartOpsAgent\frontend` | `npm run test:visual` | 退出码 0；套件内 7 个脚本全部退出 0；Vite 自启成功；浏览器可用 | 每个子脚本日志、失败截图/页面错误、临时端口与启动日志 | fixture=true；real_provider=false | 条件（UI 变更时必需） |
| FE-A11Y | 无障碍/响应式 | `d:\SmartOpsAgent\frontend` | `npm run test:a11y` | 退出码 0；axe `serious/critical` = 0；375/768/1440、浅/深色、键盘与 reduced-motion 项目均有结果 | 每页面/视口报告、截图、违规清单 | fixture=true；real_provider=false | 条件（UI 变更时必需） |
| REAL-E2E | 真实 UI→服务→Provider 链路 | 项目根/前端 | 另行授权后按冻结协议执行 | 真实账号、真实服务、`fixture=false`、浏览器 trace、持久结果可回查 | trace、pageerror、服务日志、run_id 贯穿证据 | real=true；real_provider=true | 发布前条件，默认 `NOT_RUN` |

浏览器阻塞说明：`test:visual` 与 `test:a11y` 会自启 Vite（随机端口 4300–4399 / 4500–4579），但多个脚本硬编码 `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` 或 `channel: 'msedge'`。非 Windows 或本机无 Edge 时，整项状态为 `NOT_RUN/BLOCKED_DEP`，不是 `SKIP`，更不是 `PASS`。人工读屏复核不属于自动化门禁，单独登记为 `NOT_RUN`。

### 3.5 辅助门禁

| Gate ID | 目的 | 工作目录 | 命令 | PASS 阈值 | 必存输出 | fixture/real | 级别 |
|---|---|---|---|---|---|---|---|
| AUX-LOCK | 依赖锁合规 | `d:\SmartOpsAgent` | `python scripts/check_dependency_lock.py` | 退出码 0；HIGH=0；输出版本清单 | 全量输出 + `hashes/inputs.json` | fixture | 条件（依赖变更时必需） |
| AUX-START | 启动 readiness 与版本 | `d:\SmartOpsAgent` | `powershell -ExecutionPolicy Bypass -File scripts/windows/preflight-readiness.ps1 -Real`；随后才允许 `scripts/windows/start-all.ps1` | 所有必需项 PASS；Backend `/actuator/health`=UP；AI `/api/health` 服务名匹配；Knowledge `/api/ready` 为 READY 且 chunks>0 | preflight 日志、各服务启动日志、端点响应（脱敏）、版本/commit | real=true（启动真实服务） | 条件（发布启动验收时必需） |
| AUX-ROLLBACK | 副本回滚演练 | `d:\SmartOpsAgent` | 见 `rollback-drill.md` | 切换/回滚后 hash 与预期一致；冒烟通过；他人改动数不变 | 命令日志、hash manifest、耗时、前后状态 | 副本/隔离库 | 条件（发布前必需） |

启动门禁只认 HTTP readiness，不认“端口在监听”。`scripts/windows/service-readiness.ps1` 已实现该判据；端口存活单独出现时不能判 PASS。

---

## 4. 汇总与放行判定

### 4.1 级别

- **必需（required）**：PY-AGENT、PY-KNOW、PY-AI、PY-TRAIN、JAVA-TEST、FE-UNIT、FE-TC、FE-LINT、FE-BUILD、FE-ADMIN。
- **条件（conditional）**：FE-VISUAL、FE-A11Y（涉及前端 UI 时转必需）；AUX-LOCK（依赖文件变更时）；AUX-START / AUX-ROLLBACK（发布启动与回滚时）。
- **单独分账**：REAL-E2E、真实 Provider 效果、人工读屏、性能实验；不得用 fixture 结果替代。

### 4.2 放行算法

| 组合 | 结论 |
|---|---|
| 所有必需项 `PASS`，条件项 `PASS` 或经批准 `SKIP` | `RELEASE_READY` |
| 所有必需项 `PASS`，但存在条件项 `NOT_RUN/BLOCKED_DEP`（如浏览器）且发布不涉及该范围 | `RELEASE_CONDITIONAL`，必须在报告中单列缺口与影响 |
| 任一必需项为 `FAIL` 或 `ERROR` | `NO_GO` |
| 任一必需项为 `NOT_RUN`（含 `BLOCKED_ENV`、`NOT_AUTHORIZED`） | `NO_GO`（含 Java 17 未解除） |
| 必需项出现未批准的 `SKIP` | `NO_GO`；先把 skip 升级为 `NOT_RUN/BLOCKED_DEP` 并给出解除条件 |
| 仅历史结果、无本轮输出 | `NO_GO`，对外只能描述为“上一轮记录为绿，本轮未复跑” |

补充：

- `fixture=true` 的 PASS 不能支持“真实平台 E2E 完成”的结论；三类声明（代码通过 / 平台 E2E / 效果提升）互不替代。
- 单个门禁内部有部分失败时，整项 `FAIL`；禁止用通过率百分比掩盖。
- 静态扫描数量、历史放行、README 自报结果均不进入放行算法。

---

## 5. 本轮状态（不得改写为通过）

| Gate ID | 本轮状态 | 原因码 | 历史锚点（HISTORICAL，不可替代本轮） |
|---|---|---|---|
| PY-AGENT | `NOT_RUN` | `NOT_AUTHORIZED` | 2026-11-05T08:13Z：Agent 80 passed |
| PY-KNOW | `NOT_RUN` | `NOT_AUTHORIZED` | 2026-11-05T08:13Z：54 passed |
| PY-AI | `NOT_RUN` | `NOT_AUTHORIZED` | 2026-11-05T08:13Z：53 passed |
| PY-TRAIN | `NOT_RUN` | `NOT_AUTHORIZED` | 无 |
| JAVA-TEST | `NOT_RUN` | `BLOCKED_ENV` | 无；JDK 版本不满足 |
| FE-UNIT | `NOT_RUN` | `NOT_AUTHORIZED` | 2026-11-05T08:13Z：479 collected / 478 pass |
| FE-TC | `NOT_RUN` | `NOT_AUTHORIZED` | 无 |
| FE-LINT | `NOT_RUN` | `NOT_AUTHORIZED` | 无 |
| FE-BUILD | `NOT_RUN` | `NOT_AUTHORIZED` | 无 |
| FE-ADMIN | `NOT_RUN` | `NOT_AUTHORIZED` | 无 |
| FE-VISUAL | `NOT_RUN` | `NOT_AUTHORIZED` | 既有 fixture 级记录，未复跑 |
| FE-A11Y | `NOT_RUN` | `NOT_AUTHORIZED` | 既有 fixture 级记录，未复跑 |
| AUX-LOCK | `NOT_RUN` | `NOT_AUTHORIZED` | GH-P0-01 历史 46 项依赖锁 |
| AUX-START | `NOT_RUN` | `NOT_AUTHORIZED` | 历史 P0-RUN-01 仅覆盖 AI↔Knowledge |
| AUX-ROLLBACK | `NOT_RUN` | `NOT_AUTHORIZED` | 无 |
| REAL-E2E | `NOT_RUN` | `BLOCKED_DEP` | 真实 Provider 未启动 |

静态声明面（仅供规模参考，不是通过数）：Java `@Test/@ParameterizedTest` 441；前端 `test()/it()` 466；`tests/` 下 `test_*.py` 59。

---

## 6. 未来 RUN 的执行顺序

1. `preflight.md` 全量检查；必需项 FAIL 则停止，不进入构建/启动。
2. 采集输入 hash 与工具链版本，建立 `<runId>` 目录。
3. Python 四项（PY-AGENT、PY-KNOW、PY-AI、PY-TRAIN）。
4. 前端 FE-UNIT、FE-TC、FE-LINT。
5. 前端 FE-BUILD、FE-ADMIN（唯一输出目录；确认 live 制品未变）。
6. 切换 JDK17 后 JAVA-TEST。
7. 条件项 FE-VISUAL、FE-A11Y；浏览器缺失则 `NOT_RUN/BLOCKED_DEP`。
8. AUX-LOCK；需要启动验收时执行 AUX-START。
9. 发布前执行 `rollback-drill.md`。
10. 汇总 `report.yaml`，按第 4 节算法给 `release_decision`。

---

## 7. 禁止事项

- 禁止为刷绿批量改测试期望、删除用例、加无条件 skip、放宽 `--max-warnings`、缩小测试路径。
- 禁止 `git reset --hard`、`git clean -fdx`、`git checkout -- .`、`git restore .` 或覆盖 359 条他人改动。
- 禁止构建直接写入 `frontend/dist` / `frontend/dist-admin`，或在构建后替换正在使用的制品。
- 禁止把 `NOT_RUN`、`SKIP`、历史日志、静态计数写成 `PASS`。
- 禁止在日志/报告中输出 `.env` 值、token、API Key、私有 Prompt、真实账号密码。
- 禁止用 fixture 响应延迟证明真实 Provider 首 token 性能；禁止用固定 `sleep` 冒充 readiness。
- 禁止在真实库上直接做迁移逆向、`flyway clean` 或删库重放。

---

## 8. 与交接书验收的映射

| 交接书验收（HC-05） | 本文落点 |
|---|---|
| PASS/FAIL/SKIP/ERROR/NOT_RUN 分开 | 第 1 节；`NOT_RUN` 子原因码 |
| 真实依赖缺失不静默 skip | 1.3 规则 4；3.4 浏览器说明 |
| 前端构建不删除正在使用制品 | 3.3 约束；`rollback-drill.md` |
| 启动检查 readiness 和版本 | 3.5 AUX-START；`preflight.md` |
| 副本上先执行 rollback | `rollback-drill.md` |
| 现有工作区变更不纳入差分 | 头部基线；`rollback-drill.md` 第 7 节 |
