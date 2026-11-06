# HC-05 CI 缺口清单（对照 `.github/workflows/ci.yml`）

| 项 | 值 |
|---|---|
| task_id | HC-05 |
| mode | PLAN |
| 日期 | 2026-11-05 |
| 被对照文件 | `d:\SmartOpsAgent\.github\workflows\ci.yml`（只读，**未修改**） |
| 本轮执行 | **未执行 CI**；本地未运行测试/构建；不能把“CI 已配置”写成“CI 已通过” |
| 关联 | `quality-gate.md` 门禁表、`failure-triage.md` |

---

## 1. 当前 CI 实际覆盖

| Job | Runner | 步骤/命令 | 覆盖内容 | 未覆盖 |
|---|---|---|---|---|
| `frontend` | ubuntu-latest | `npm ci` → `npm run lint` → `node --test "test/**/*.test.mjs"` → `npm run build` | 前端 lint、Node 单测、用户端默认构建 | typecheck、管理端构建、视觉/a11y、产物 hash、Windows 行为 |
| `lint` | ubuntu-latest | `ruff check .` | Python 静态检查 | 任何 Python 测试 |
| `backend` | ubuntu-latest | `mvn -B test` | Java 测试（Temurin 17） | 打包产物、启动 readiness、测试库隔离声明、报告归档 |
| `python` | ubuntu-latest | 安装 `ai-service/requirements.txt` + `numpy` → `python -m pytest tests/knowledge ai-service/app/tests -q` | Knowledge + AI Service 合并测试 | Agent、Inspector、Training；`knowledge/requirements.txt` 未安装 |

关键事实：

- CI 的 Java job 使用 `java-version: "17"`，说明 Java 门禁在 CI 侧**有**配置；但本地 PATH 是 1.8，因此本地 `JAVA-TEST` 仍为 `NOT_RUN/BLOCKED_ENV`。两者不能互相替代。
- CI 的 Node 为 22、Python 为 3.11；本地观察为 Node `v24.15.0`、Python `3.14.3`。存在版本漂移，CI 绿不等于本机可复现。
- 本轮没有触发或读取任何 CI 运行结果；历史 GitHub 网络核验还出现过 WinError10013/审批 404，相关项只能 `NOT_RUN`。

---

## 2. 缺口清单

优先级定义：`P0` = 不补就无法支撑“可重复发布证据”；`P1` = 覆盖不全或证据不可追溯；`P2` = 工程成熟度。

### P0

| ID | 缺口 | 影响/证据 | 补法（不实际改 CI） | 对应门禁 |
|---|---|---|---|---|
| CI-01 | Agent/Inspector 测试未进 CI | `ci.yml` 的 python job 只跑 `tests/knowledge ai-service/app/tests`；交接书要求 `tests/inspector tests/agent` | 新增独立 step/job：`python -m pytest tests/inspector tests/agent -q`；保存 JUnit/日志；失败不得 `continue-on-error` | PY-AGENT |
| CI-02 | 前端 typecheck 未进 CI | `frontend` job 无 `npm run typecheck` | 在 lint 后加 `npm run typecheck`，使用同一 `npm ci` 缓存 | FE-TC |
| CI-03 | 管理端构建未进 CI | 只跑 `npm run build`；`build:admin` 与 admin.html 入口未验证 | 加 `npm run build:admin -- --outDir <唯一目录>`；校验 `admin.html` 存在并记录 hash | FE-ADMIN |
| CI-04 | Training 测试未进 CI | 无 `tests/training` step | 加 `python -m pytest tests/training -q`；与 SCORE-01 修复联动，禁止批量改期望 | PY-TRAIN |
| CI-05 | Knowledge 可选依赖未安装，相关路径无 CI 覆盖 | `ci.yml` 注释明确“只装测试必需项，BGE/OCR/PDF 可选依赖不装”；实际只安装 `ai-service/requirements.txt` 与 `numpy`。因此 PDF 解析、OCR、BGE 嵌入路径在 CI 中没有执行证据；若导入失败则 job 直接红 | 在报告中明确标注“未覆盖的可选路径”；需要正式覆盖时安装 `knowledge/requirements.txt` 或补显式 skip 标记 + 替代证据；不得让导入失败表现为“绿”，也不得把未覆盖说成已通过 | PY-KNOW |
| CI-06 | 本地与 CI 前端单测命令不一致 | 本地 `npm test` 为 `node --test test/**/*.test.mjs`（未加引号），CI 为加引号形式；Linux shell 与 Node glob 行为可能不同，收集数可能不同 | 统一为带引号的脚本（修改 `package.json` 属 IMPLEMENT，本轮不改）；CI 与本地都记录 collected 数并比对 | FE-UNIT |
| CI-07 | 视觉/a11y 未进 CI，且现有脚本无法在 ubuntu 跑 | `visual-suite.mjs`、`accessibility.browser.mjs` 等硬编码 `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` 或 `channel: 'msedge'`；CI 为 ubuntu | 新增 Windows runner 的 nightly job，或改为 Playwright 自带 Chromium 并参数化 base URL；在补齐前 FE-VISUAL/FE-A11Y 只能 `NOT_RUN/BLOCKED_DEP` | FE-VISUAL、FE-A11Y |
| CI-08 | 无制品 hash/保留证据 | `npm run build` 输出默认 `dist`；未上传产物，未计算 hash；无法证明“构建不删除正在使用制品” | 构建到唯一目录，生成文件清单+SHA256，上传为 artifact；保留至少一个版本用于回滚演练 | FE-BUILD、AUX-ROLLBACK |
| CI-09 | 无 preflight/启动 readiness | CI 不检查端口、env 键、Java/Maven 实际运行 JDK、服务 readiness | 增加只读 preflight job（版本、lock hash、端口、env 键存在性）；启动验收另设受控 job，使用 `/actuator/health`、`/api/health`、`/api/ready` 判据 | AUX-START |
| CI-10 | 无失败归因/NOT_RUN 产出 | CI 只有成功/失败，未区分 SKIP/ERROR/NOT_RUN，也没有失败分类字段 | 要求 job 输出结构化摘要（exit code、collected、failed、skipped、fixture/real）；失败按 `failure-triage.md` 记录，不允许用 `continue-on-error` 洗绿 | 全门禁 |

### P1

| ID | 缺口 | 影响/证据 | 补法 | 对应门禁 |
|---|---|---|---|---|
| CI-11 | 依赖锁检查未进 CI | 存在 `scripts/check_dependency_lock.py`，但 `ci.yml` 未调用 | 新增 step：`python scripts/check_dependency_lock.py`；HIGH=0 才通过；lock 文件变更时必跑 | AUX-LOCK |
| CI-12 | 无 JUnit/日志归档 | 失败后难以复核 surefire / TAP / pytest 原始输出 | 上传 `backend/target/surefire-reports`、pytest JUnit、Node TAP、构建日志为 artifacts，保留期限明确 | 全门禁 |
| CI-13 | 无超时设置 | 任一挂起 job 会长时间占用 runner，且无法区分“超时/失败” | 给各 job 设 `timeout-minutes`；超时按 `ERROR` 归因，不重试到绿 | 全门禁 |
| CI-14 | 无 Windows runner，与主开发环境不一致 | 启动脚本、浏览器脚本、路径分隔符均为 Windows 语义；ubuntu 无法验证本机发布流程 | 增 nightly Windows job 或声明“CI 只覆盖 Linux 子集”，并在报告中登记平台差异 | AUX-START、FE-VISUAL/A11Y |
| CI-15 | Java 无打包/启动验收 | `mvn -B test` 不产出 jar，不验证 `/actuator/health` | 加 `mvn -B -DskipTests package`，记录 jar hash；启动验收在隔离 profile/测试库执行健康检查 | JAVA-TEST、AUX-START |
| CI-16 | 无测试库隔离声明 | `mvn test` 依赖 H2（pom 有 h2 test scope），但 CI 未显式声明使用测试 profile/库 | 在 job 中显式设置测试 profile/数据源，确保不连外部库；报告写明 fixture | JAVA-TEST |
| CI-17 | Node/Python 版本矩阵缺失 | 仅 Node 22、Python 3.11；本地 24/3.14 漂移无覆盖 | 增加版本矩阵或在报告中固定“发布验证版本”；漂移必须有对照结果 | FE-UNIT、PY-* |
| CI-18 | 无 SBOM/依赖清单产出 | 交接书要求依赖锁定/SBOM 输出 | 生成 Python (`pip freeze`/`pip inspect`) 与 npm (`package-lock` 摘要) 清单，附 hash；不引入新工具为默认前提 | AUX-LOCK |

### P2

| ID | 缺口 | 影响 | 补法 |
|---|---|---|---|
| CI-19 | 无覆盖率门槛 | 无法量化回归保护；但覆盖率不能替代验收 | 先采集不上门槛；有基线后再评审阈值 |
| CI-20 | 无 release/tag 工作流与制品晋级 | push/PR 之外没有发布证据链 | 增加 tag 触发的 release job，绑定本文件门禁与 rollback 证据 |
| CI-21 | 无安全/许可扫描 | 依赖来源与许可证未自动核对 | 先接 `scripts/check_corpus_licensing.py` 与依赖许可清单，避免误引入 CANDIDATE_ONLY |
| CI-22 | 无 required checks/环境保护 | 失败可被合并/绕过 | 在仓库设置 required status checks；本轮只记录，不改设置 |

---

## 3. 覆盖矩阵（现有 CI vs 统一门禁）

| 门禁 | CI 现状 | 结论 |
|---|---|---|
| PY-AGENT | 无 | 缺口 CI-01（P0） |
| PY-KNOW | 有，但与 AI 合并；依赖安装不完整 | 部分覆盖，缺口 CI-05 |
| PY-AI | 有，合并执行 | 覆盖，但缺独立失败可见性 |
| PY-TRAIN | 无 | 缺口 CI-04（P0） |
| JAVA-TEST | 有（ubuntu + Temurin 17） | 覆盖测试；缺打包/启动/报告（CI-15/16） |
| FE-UNIT | 有，但命令与本地不一致 | 部分覆盖，缺口 CI-06 |
| FE-TC | 无 | 缺口 CI-02（P0） |
| FE-LINT | 有 | 覆盖 |
| FE-BUILD | 有默认 `dist` | 部分覆盖，缺唯一目录/hash（CI-08） |
| FE-ADMIN | 无 | 缺口 CI-03（P0） |
| FE-VISUAL | 无，且 ubuntu 不可运行 | 缺口 CI-07（P0） |
| FE-A11Y | 无，且 ubuntu 不可运行 | 缺口 CI-07（P0） |
| AUX-LOCK | 无 | 缺口 CI-11 |
| AUX-START | 无 | 缺口 CI-09/15 |
| AUX-ROLLBACK | 无 | 缺口 CI-08/20 |
| REAL-E2E | 无 | 不要求 CI 默认跑；另行 RUN，fixture/real 分账 |

---

## 4. 补法原则（不实际改 CI）

1. **只加不删**：不得删除现有 job、不得把失败 job 设为 `continue-on-error`、不得缩小 `ruff check .` 或测试路径。
2. **失败必须可见**：新 job 默认阻断；确实需要非阻断的（如 nightly 浏览器），单独标记 `NIGHTLY_ONLY`，并在发布结论中单列缺口。
3. **证据可追溯**：每个 job 上传原始日志/JUnit/产物 hash；报告字段与 `quality-gate.md` 2.4 对齐。
4. **版本固定**：Node/Python/Java 版本写死并记录；依赖变更同时更新 lock hash 与 AUX-LOCK。
5. **不在 CI 里做真实生产副作用**：不连生产库、不调用真实 Provider、不部署；真实 E2E 单独受控执行。
6. **先补 P0 再谈矩阵**：CI-01～CI-10 未补齐前，不得用“CI 绿”替代发布证据。

---

## 5. 本轮状态

| 项 | 状态 |
|---|---|
| 读取 `ci.yml` 并对照 | `DONE`（SOURCE_OBSERVED） |
| 实际触发 CI / 查看运行结果 | `NOT_RUN` |
| 修改 CI | `NOT_STARTED`（本任务禁止） |
| 缺口优先级与补法 | `DONE`（本文档） |
| 依赖 GitHub 实时数据的项 | `NOT_RUN/BLOCKED_NETWORK`（历史 WinError10013/审批 404，本轮未重试） |
