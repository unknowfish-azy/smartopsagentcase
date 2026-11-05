# HC-05 启动/构建前 Preflight

| 项 | 值 |
|---|---|
| task_id | HC-05 |
| mode | PLAN |
| 日期 | 2026-11-05 |
| 适用范围 | 任何 `RUN`（测试、构建、启动、回滚）开始前的只读检查 |
| 本轮执行 | **未执行**；下文命令是未来 RUN 的规格，不是本轮结果 |
| 输出根 | `d:\SmartOpsAgent\.runtime\hc-check\<runId>\preflight\` |
| runId 格式 | `YYYYMMDD-HHMMSS-HC05` |

本清单只读：不安装工具、不启动服务、不改环境变量、不输出任何 secret 值。所有命令默认在 `d:\SmartOpsAgent` 执行，除非表中另有工作目录。

---

## 1. 使用方式与判定

```powershell
$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
$run   = "d:\SmartOpsAgent\.runtime\hc-check\$runId-HC05"
New-Item -ItemType Directory -Force -Path "$run\preflight" | Out-Null
$items = New-Object System.Collections.Generic.List[object]
function Add-Item([string]$id, [string]$status, [string]$detail, [string]$evidence) {
    $items.Add([pscustomobject]@{ id=$id; status=$status; detail=$detail; evidence=$evidence })
}
```

判定规则：

| 状态 | 含义 | 对后续动作的影响 |
|---|---|---|
| `PASS` | 本轮只读检查满足判据 | 可继续 |
| `FAIL` | 必需项不满足 | **立即停止**；不得进入测试/构建/启动 |
| `SKIP` | 仅限可选依赖缺失，且已写明原因 | 可继续，但该缺口必须进入报告 |
| `NOT_RUN` | 未检查或无授权 | 必需项按失败处理；可选按缺口登记 |

- 必需项出现 `FAIL` 或 `NOT_RUN` → 整个 RUN 不启动，报告写 `NO_GO`。
- 不允许把 `SKIP` 当成 `PASS`；生产必需依赖缺失（Java 17、浏览器、模型、数据库）一律是 `FAIL`/`NOT_RUN/BLOCKED_*`。
- 检查结果写入 `$run\preflight\preflight.json`：

```json
{
  "run_id": "20261105-XXXXXX-HC05",
  "generated_at": "<iso8601>",
  "mode": "read-only",
  "items": [
    { "id": "A01", "status": "PASS|FAIL|SKIP|NOT_RUN", "detail": "<不含secret>", "evidence": "<path>" }
  ],
  "verdict": "PASS|FAIL",
  "required_failures": ["<id>"],
  "conditional_gaps": ["<id>"]
}
```

单项原始输出保存到 `$run\preflight\<ID>-<name>.txt`，不得把 `.env` 内容重定向到这些文件。

---

## 2. A 组：工具链版本

| ID | 检查项 | 命令（工作目录） | PASS 判据 | 失败/缺口后果 | 输出 |
|---|---|---|---|---|---|
| A01 | Node / npm | `node --version; npm --version`（项目根） | Node ≥ 22；npm ≥ 10；记录精确版本 | 低于 22 判 FAIL；版本漂移（本地 24 vs CI 22）记入报告但不单独阻断 | `A01-node.txt` |
| A02 | Python / pytest | `python --version; python -c "import pytest,sys;print('pytest',pytest.__version__)"`（项目根） | Python ≥ 3.11；pytest 可导入 | 不满足判 FAIL；CI 3.11 与本地 3.14 漂移必须写明 | `A02-python.txt` |
| A03 | PATH JDK | `java -version`（项目根） | 版本号 ≥ 17 | 当前 PATH 为 1.8 时判 FAIL；JAVA-TEST 记 `NOT_RUN/BLOCKED_ENV` | `A03-java.txt` |
| A04 | 受管 JDK17 候选 | `Test-Path "$env:USERPROFILE\scoop\apps\openjdk17\current\bin\java.exe"; & "$env:USERPROFILE\scoop\apps\openjdk17\current\bin\java.exe" -version`（项目根） | 路径存在且输出 17.x | 不存在则仍 BLOCKED；由环境负责人提供 JDK17；本 RUN 不下载安装 | `A04-jdk17.txt` |
| A05 | JAVA_HOME 与 Maven 运行 JDK | `"JAVA_HOME=$env:JAVA_HOME"; mvn -v`（项目根） | `mvn -v` 的 Java version 为 17.x；Maven ≥ 3.9 | Java 非 17 判 FAIL；`.m2` 存在不作为证据 | `A05-maven.txt` |
| A06 | 进程内切换验证 | `$env:JAVA_HOME="$env:USERPROFILE\scoop\apps\openjdk17\current"; $env:Path="$env:JAVA_HOME\bin;$env:Path"; mvn -v`（项目根） | 仅影响当前进程；输出 Java 17 | 切换失败保持 BLOCKED；不得改系统/用户级环境变量 | `A06-maven-jdk17.txt` |
| A07 | Git 与基线 | `git rev-parse HEAD; @(git status --porcelain).Count`（项目根） | HEAD 与报告一致；dirty 条目数与开始记录一致 | 不一致时重新登记基线，不得 revert；只读命令 | `A07-git.txt` |
| A08 | OS / PowerShell / 时区 | `$PSVersionTable.PSVersion; [Environment]::OSVersion.VersionString; Get-TimeZone | Select-Object Id` | 能读出；时区记录为 `Asia/Shanghai` | 无法读取记 `NOT_RUN`，不阻断 | `A08-os.txt` |
| A09 | Docker（可选） | `docker version --format '{{.Server.Version}}'`（项目根） | 命令可用且 Server 版本可读 | 不可用记 `SKIP`；仅影响需要容器的启动验收 | `A09-docker.txt` |
| A10 | 浏览器（条件项） | `Test-Path 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'; Test-Path 'frontend\node_modules\playwright\package.json'`（项目根） | 两者均存在 | 缺失则 FE-VISUAL/FE-A11Y 记 `NOT_RUN/BLOCKED_DEP`；非 Windows 同 | `A10-browser.txt` |

Java 17 是 `JAVA-TEST` 的硬前置。候选路径存在只代表“可能可切换”，必须 A06 输出 17.x 才能解除 `BLOCKED_ENV`。

---

## 3. B 组：端口与 readiness

| ID | 检查项 | 命令（工作目录） | PASS 判据 | 失败/缺口后果 | 输出 |
|---|---|---|---|---|---|
| B01 | 固定端口占用 | 见下方脚本（项目根） | 构建 preflight：端口空闲；启动 preflight：由**预期服务**占用，且 readiness 通过 | 被未知进程占用判 FAIL；**不得 kill 未知 PID** | `B01-ports.txt` |
| B02 | 浏览器临时端口段 | 见下方脚本（项目根） | 4300–4399、4500–4579 内无监听 | 有监听判 FAIL，换段或先确认归属；不杀进程 | `B02-browser-ports.txt` |
| B03 | HTTP readiness（仅启动阶段） | `. scripts/windows/service-readiness.ps1; Test-ServiceReadiness -Uri 'http://127.0.0.1:8080/actuator/health'`；AI 加 `-ExpectedService 'smartops-ai-service'`；Knowledge 加 `-ExpectedService 'smartops-knowledge-service' -RequireIndex`（项目根） | Backend `status=UP`；AI 服务名匹配；Knowledge `ready=true`、`chunks>0`、`status=READY` | 端口在监听但 readiness 失败 = FAIL；固定 `sleep` 不算证据 | `B03-readiness.txt` |
| B04 | 启动版本指纹 | 启动后请求 `/actuator/health`、`/api/health`、`/api/ready`（项目根） | 返回中的版本/commit/服务名与本次输入 hash 对应 | 缺失版本字段记 `FAIL`（无法解释本次启动的是哪个制品） | `B04-version.txt` |
| B05 | 监听多重绑定 | `Get-NetTCPConnection -LocalPort 8080,5173,5174,8001,8002 -State Listen | Select-Object LocalPort,LocalAddress,OwningProcess`（项目根） | 同一端口只有一个预期进程；无通配地址遮蔽 | 多进程监听判 FAIL（可能命中旧实例） | `B05-multi-bind.txt` |

端口检查脚本（只读）：

```powershell
$ports = 8080,5173,5174,8001,8002,11434,3306,6379
foreach ($port in $ports) {
  $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
  if (!$listeners.Count) { "port $port: FREE"; continue }
  foreach ($l in $listeners) {
    $p = Get-Process -Id $l.OwningProcess -ErrorAction SilentlyContinue
    "port $port: LISTEN $($l.LocalAddress) pid=$($l.OwningProcess) name=$($p.ProcessName)"
  }
}
```

预期归属：Frontend 用户 5173、Frontend 管理 5174、Backend 8080、AI 8001、Knowledge 8002、Ollama 11434、MySQL 3306、Redis 6379。归属不符时只登记、不处理。

---

## 4. C 组：env 存在性（不读 secret）

| ID | 检查项 | 命令（项目根） | PASS 判据 | 失败/缺口后果 | 输出 |
|---|---|---|---|---|---|
| C01 | env 文件存在 | `Test-Path -LiteralPath '.env'; Test-Path -LiteralPath '.runtime\secrets\bootstrap.env'` | `.env` 与 bootstrap 文件存在 | 缺失判 FAIL；`restart-local-backend.ps1` 明确要求 bootstrap 文件 | `C01-env-exists.txt` |
| C02 | 必需键名存在 | 见下方脚本 | 必需键全部为 `True` | 缺任一必需键判 FAIL；只输出布尔值 | `C02-env-keys.txt` |
| C03 | 私密值未落盘 | `Select-String -Path "$run\preflight\*.txt" -Pattern '(?i)(password|token|api_key)=.{8,}'`（项目根） | 无匹配 | 有匹配判 FAIL：删除该文件、重做检查、登记泄露事件 | `C03-secret-scan.txt` |

键名检查脚本（**只输出键名与布尔存在性，绝不输出值**）：

```powershell
$required = @(
  'LLM_PROVIDER','LLM_MODEL','LLM_BASE_URL','LLM_API_KEY',
  'MYSQL_URL','MYSQL_USERNAME','MYSQL_PASSWORD',
  'REDIS_HOST','REDIS_PORT','REDIS_DATABASE',
  'SMARTOPS_INTERNAL_TOKEN','VITE_API_BASE_URL'
)
$present = @{}
Get-Content -LiteralPath '.env' -Encoding UTF8 | ForEach-Object {
  if ($_ -match '^(?<k>[A-Za-z_][A-Za-z0-9_]*)=') { $present[$matches.K] = $true }
}
$required | ForEach-Object { "{0}={1}" -f $_, [bool]$present[$_] }
```

说明：

- 若部署形态不需要某键（例如完全本地 Ollama 不需要云端 `LLM_API_KEY`），在报告中登记“不适用 + 依据”，不能静默缺失。
- 仓库中观察到 `.env` 存在重复的 `MYSQL_USERNAME` 行；本检查只看键存在性，不判断解析优先级。
- 禁止使用 `Get-Content .env` 直接打印、禁止把值写入日志、截图或报告。

---

## 5. D 组：数据库与依赖服务

| ID | 检查项 | 命令（项目根） | PASS 判据 | 失败/缺口后果 | 输出 |
|---|---|---|---|---|---|
| D01 | MySQL 可达 | `Test-NetConnection 127.0.0.1 -Port 3306 -InformationLevel Quiet` | 返回 `True` | 需要真实 DB 的门禁判 `NOT_RUN/BLOCKED_DEP`；不得用 H2 冒充 | `D01-mysql.txt` |
| D02 | Redis 可达 | `Test-NetConnection 127.0.0.1 -Port 6379 -InformationLevel Quiet` | 返回 `True` | 同上；仅影响依赖 Redis 的启动/用例 | `D02-redis.txt` |
| D03 | 容器与隔离库 | `docker ps --format '{{.Names}}  {{.Status}}'`；`docker inspect --format '{{.Name}}' $(docker ps -q)`（项目根） | 容器名能对应 MySQL/Redis；测试库与生产库分离 | 无法证明隔离时判 FAIL；不得在真实库跑测试/迁移 | `D03-containers.txt` |
| D04 | 备份可用（迁移前） | `Test-Path -LiteralPath '.runtime\backups'`；列出最近备份文件名（不读内容） | 目录存在且有一次可读备份 | 无备份时禁止任何迁移演练 | `D04-backups.txt` |
| D05 | Ollama（真实 Provider 条件项） | `Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' | ...` 仅提取模型名 | 目标 model 存在 | 缺失则 REAL-E2E 记 `NOT_RUN/BLOCKED_DEP`；不得用 fixture 冒充 | `D05-ollama.txt` |

D05 只读 `/api/tags`，不发起生成请求。模型名可记录，API Key 不记录。

---

## 6. E 组：制品输出目录唯一性

| ID | 检查项 | 命令（项目根） | PASS 判据 | 失败/缺口后果 | 输出 |
|---|---|---|---|---|---|
| E01 | run 目录唯一 | `Test-Path -LiteralPath $run` | 不存在（由本次创建） | 已存在时换新 runId，禁止复用/覆盖旧证据 | `E01-run-dir.txt` |
| E02 | live 制品前像 | `Get-FileHash frontend\dist\index.html,frontend\dist-admin\admin.html -Algorithm SHA256` | 两文件存在，hash 已保存 | 缺失记 `NOT_RUN`（尚未构建）；存在则必须前后一致 | `E02-live-dist.txt` |
| E03 | 构建输出路径 | `Test-Path -LiteralPath 'frontend'`；`Resolve-Path '.runtime\hc-check' -ErrorAction SilentlyContinue` | 构建目录落在 `.runtime\hc-check\<runId>\artifacts`，不在 `frontend\dist*` | 路径不符判 FAIL；`.runtime` 已被 `.gitignore` 忽略 | `E03-outdir.txt` |
| E04 | 磁盘写入归属 | `Get-ChildItem -Force '.runtime\hc-check' -ErrorAction SilentlyContinue` | 只包含本次与历史 runId 目录 | 发现他人目录时只读，不删除、不移动 | `E04-ownership.txt` |
| E05 | 构建不触碰live | 构建前后各执行一次 E02，比较 hash | hash 完全一致 | 任一变化判 `FAIL`，并按回滚流程恢复副本 | `E02` 前后两份 |

目录约定：

```text
d:\SmartOpsAgent\.runtime\hc-check\<runId>\
  artifacts\user-dist\
  artifacts\admin-dist\
```

`npm run build -- --outDir ../.runtime/hc-check/<runId>/artifacts/user-dist` 与 `build:admin` 的同名参数都以 `frontend` 为基准解析。

---

## 7. F 组：磁盘、内存与缓存

| ID | 检查项 | 命令（项目根） | PASS 判据 | 失败/缺口后果 | 输出 |
|---|---|---|---|---|---|
| F01 | 磁盘余量 | `Get-PSDrive -PSProvider FileSystem | Select-Object Name,@{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}}` | 项目所在盘 ≥ 5 GB 可用 | 低于阈值判 FAIL；不得自动清理他人目录 | `F01-disk.txt` |
| F02 | 内存余量 | `Get-CimInstance Win32_OperatingSystem | Select-Object @{n='FreeMB';e={[int]($_.FreePhysicalMemory/1024)}}` | ≥ 2048 MB 可用 | 低于阈值记 `FAIL`（启动多服务易 OOM） | `F02-memory.txt` |
| F03 | 前端依赖已安装 | `Test-Path 'frontend\node_modules\vite\package.json'; Test-Path 'frontend\node_modules\playwright\package.json'` | 存在 | 缺失判 FAIL；是否 `npm ci` 由 RUN 所有者决定并记录网络条件 | `F03-node-modules.txt` |
| F04 | Python 依赖 | `python -m pip list --format=json > $run\preflight\F04-piplist.json` | 含 `pytest`、`fastapi`、`numpy`；Knowledge 用例所需依赖按 requirements 检查 | 缺失时对应门禁 `NOT_RUN/BLOCKED_DEP`，不得静默 skip | `F04-piplist.json` |
| F05 | 构建缓存与权限 | `Test-Path 'frontend\.vite-once-cache'; (Get-Item 'frontend').Attributes` | 可写；缓存不指向他人目录 | 不可写判 FAIL | `F05-cache.txt` |

`pip list` 属于只读输出，不安装任何包；若当前 Python 是全局环境，报告中注明（未使用隔离环境本身就是可复现性风险）。

---

## 8. G 组：依赖 lock hash

| ID | 检查项 | 命令（项目根） | PASS 判据 | 失败/缺口后果 | 输出 |
|---|---|---|---|---|---|
| G01 | lock/config hash | `Get-FileHash -Algorithm SHA256 frontend\package-lock.json,backend\pom.xml,ai-service\requirements.txt,knowledge\requirements.txt,frontend\vite.config.js,frontend\vite.config.admin.mjs,pytest.ini,docs\development\GH-P0-01-dependency-lock.json` | 全部可读且 hash 已记录 | 缺文件判 FAIL；hash 与基线不同需登记原因 | `G01-locks.json` |
| G02 | 与基线比对 | 读取上一次 `hashes/inputs.json`，逐项比较 | 一致，或差异有明确变更说明 | 未说明差异判 FAIL（无法解释制品来源） | `G02-lock-diff.txt` |
| G03 | 依赖锁合规（门禁） | `python scripts/check_dependency_lock.py`（项目根） | 退出码 0、HIGH=0 | 非 0 判 `AUX-LOCK=FAIL`；不得改脚本放宽 | `G03-dependency-lock.txt` |
| G04 | 前端 lock 与 package.json 一致 | `npm ls --depth=0 --json`（`frontend`，仅只读；失败不修改） | 无 `missing`/`invalid` | 有不一致判 FAIL，通过 `npm ci` 修复需另行授权 | `G04-npm-ls.json` |

G03 会执行一个 Python 脚本并读取 `pip list`，但不安装包、不联网。若当前解释器缺失依赖，输出会体现，按 `NOT_RUN/BLOCKED_DEP` 处理。

---

## 9. H 组：网络与环境限制

| ID | 检查项 | 命令（项目根） | PASS 判据 | 失败/缺口后果 | 输出 |
|---|---|---|---|---|---|
| H01 | 外网/GitHub | `Test-NetConnection github.com -Port 443 -InformationLevel Quiet` | `True` | `False` 时 GitHub 实时核验记 `NOT_RUN/BLOCKED_NETWORK`；不得重试到成功为止 | `H01-network.txt` |
| H02 | 本地 provider 地址 | `Test-NetConnection 127.0.0.1 -Port 11434 -InformationLevel Quiet` | 需要真实 Provider 时为 `True` | 否则 REAL-E2E `NOT_RUN/BLOCKED_DEP` | `H02-ollama.txt` |
| H03 | 代理/审批通道 | 仅记录 `HTTP_PROXY`/`HTTPS_PROXY` 是否存在（不打印值） | 存在性与预期一致 | 历史 WinError10013/审批 404 记 `BLOCKED_NETWORK`；不改全局审批配置 | `H03-proxy.txt` |

---

## 10. 本轮已知观察（不是 preflight PASS）

以下来自本轮只读核对或历史台账，仅用于与未来结果比对，`evidence_class=SOURCE_OBSERVED`/`HISTORICAL`：

| 项 | 观察值 | 说明 |
|---|---|---|
| Node | `v24.15.0` | `inventory.json`，本轮未重跑版本命令 |
| npm | `11.12.1` | 同上 |
| Python | `3.14.3` | 与 CI 的 3.11 存在漂移，需在 RUN 中记录 |
| java（PATH） | `1.8.0_202` | 不满足 `pom.xml` 的 17 → JAVA-TEST `BLOCKED_ENV` |
| mvn | `3.9.15`（`D:\RuanJianKaiFa\RuanJianKaiFa Package\apache-maven-3.9.15\bin\mvn.cmd`） | Maven 存在不代表 JDK 满足 |
| JDK17 候选 | `C:\Users\33908\scoop\apps\openjdk17\current\bin\java.exe` 存在 | 仅路径存在；本轮未执行 `-version`，未解除阻塞 |
| `.env` | 存在 | 仅观察到键名；未读取值 |
| `frontend/package-lock.json` | 存在 | 未计算 hash |
| `frontend/dist`、`frontend/dist-admin` | 存在 | 构建前必须做前像 hash |
| `.runtime/hc-check` | 不存在 | 本轮到目前未创建运行目录 |
| 端口 8080/5173/5174/8001/8002/11434/3306/6379 | 未检查 | 本轮未启动/探测服务 |
| HEAD / 工作树 | `48b8af4` / 359 条 | 来自 `status-baseline.md` |
| Edge / Playwright | 未检查 | FE-VISUAL/FE-A11Y 仍为 `NOT_RUN` |

---

## 11. Preflight 之后

- `verdict=PASS` 只表示“允许开始”，不表示任何测试/构建已通过。
- 进入 `quality-gate.md` 第 6 节顺序；每个门禁单独记录五态。
- 任一必需项在运行中变为 `FAIL`/`ERROR`，停止后续阶段并按 `failure-triage.md` 处理。
- 启动验收通过后，必须再做 `rollback-drill.md`；未做回滚演练不得给 `RELEASE_READY`。
