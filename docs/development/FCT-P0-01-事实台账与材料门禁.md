# FCT-P0-01：事实台账、源码快照与材料门禁

日期：2026-11-06
任务 ID：`FCT-P0-01`（任务书 `docs/development/路演短板优化与多模型实施任务书-20261105.md` §4 FCT-P0-01）

## 0. 状态账

| 维度 | 状态 | 说明 |
|---|---|---|
| plan_status | `DONE` | 口径分账：代码规模 / 路由注解与实际路由 / 迁移定义表与运行库表 / 测试收集与执行；缺失源写 null |
| implementation_status | `DONE` | 只读脚本 `scripts/fact_ledger.py`；七批共改写 208 行（6 + 94 + 24 + 6 + 7 + 7 + 64），保留前像与精确差分，无批量替换 |
| verification_status | `DONE` | v1 快照两次生成字节级一致；改写后 `needs_correction=0`；最终快照 `9f9e7342…` 校验返回 `FROZEN`（只读，退出码 0） |

| 子项 | 状态 | 证据 |
|---|---|---|
| 快照 v1 确定性 | `PASS` | 两次 `metrics.json` sha256 相同（`0C0203EC…A63B52`），`byte_identical=True` |
| 第一批改写后主张扫描 | `PASS` | `needs_correction=0`，`current_claim=1`（该状态在第六批后归 0，见 §4） |
| 第二批 needs_review | `PASS` | 131 → 45；86 条可绑定数值已改写（13 文件、94 行）；`needs_correction` 保持 0 |
| 第三批补采 | `PASS` | 前端 `npm test` 494/494；`tests/agent` 82/82；`ai-service/app/tests` 67/67；原始日志入证据目录并记 sha256 |
| 第三批 needs_review | `PASS` | 45 → 26；10 文件、24 行；`563`/`113`/`22` 旧值已清零，`needs_correction` 保持 0 |
| 第四批 JUnit 类数 | `PASS` | `87 个 JUnit 类` → `122`（`java.test.test_class_n`）；4 文件 6 行 |
| 第五批同源句子 | `PASS` | 其余 7 处「暂无自动化测试套件」+「87 测试类」；5 文件 7 行；全库残留 0 |
| 第六批 Vue 口径 | `PASS` | `146 个页面组件 / 27,983 行` → `175 个 .vue / 21,944 行`；5 文件 7 行；`needs_review` 26 → 20 |
| 第七批对齐快照 | `PASS` | `656 → 671`、`122 → 126`、`15,649 → 16,147`、残留 `87 个测试类` → `126`；12 文件 64 行、76 处替换 |
| 校验模式只读 | `PASS` | `--verify-snapshot` 不再写证据目录；新增 2 例回归，`21 passed` |
| 最终冻结校验 | `FROZEN` | `--verify-snapshot` 对 `9f9e7342…` 返回退出码 0，且证据目录文件哈希前后不变 |
| PDF 重导 | `PASS` | 知识手册 26 页、打印合订本 30 页重新导出并抽检（含 `671`/`126`/`16,147`，无 `656`/`122`/`87`） |
| 运行库表数 | `NOT_RUN` | 无 mysql CLI，记 `null` |

## 1. 交付文件

| 文件 | 职责 |
|---|---|
| `scripts/fact_ledger.py` | 只读统计与材料核对；`--verify-snapshot` 只做校验（不写证据），漂移时退出码 2 |
| `tests/scripts/test_fact_ledger.py` | 21 例：行分类、路由解析、数值绑定与上下文分类、null 语义、确定性、冻结校验、校验模式只读 |
| `docs/development/fct-p0-01-evidence/metrics.json` | 全部指标（不含时间戳），当前快照 `9f9e7342…` |
| `docs/development/fct-p0-01-evidence/sources.json` | 675 个统计源文件的 sha256，用于追回每个数字并校验快照 |
| `docs/development/fct-p0-01-evidence/fact-sheet.md` | 人读事实表（自动生成，禁止手改数字） |
| `docs/development/fct-p0-01-evidence/stale-claims.md` | 旧数值扫描清单（4 类，仅检测不改文） |
| `docs/development/fct-p0-01-evidence/pytest.xml` | 测试执行原始日志（junitxml） |
| `docs/development/fct-p0-01-evidence/run-meta.json` | 生成时间、命令、工作树改动清单、metrics 摘要（易变信息只放这里） |
| `docs/development/fct-p0-01-evidence/non-ledger-tests.json` | 台账口径外的三套测试（前端 / `tests/agent` / ai-service）命令、退出码、计数、日志 sha256；失败的两套单列 not_a_source |
| `docs/development/fct-p0-01-evidence/frontend-tests.log` 等 | 前端、Agent、ai-service 测试原始日志；`frontend-visual-failed.log` / `frontend-a11y-failed.log` 为失败记录 |
| `docs/development/fct-p0-01-evidence/stale-claims-after-batch7.json` | 第七批改写后的主张扫描全量（needs_correction 0 / needs_review 20 / historical 3 / current 0） |
| `docs/development/fct-p0-01-evidence/final-verify.json` | 快照切换记录：`9228…` → `9f9e7342…` 的漂移清单与逐项差额 |
| `docs/development/fct-p0-01-prior/` | 第一批前像（3 份）+ `diffs/`；`batch2/`（16 份）、`batch3/`（10 份）、`batch4/`（4 份）、`batch5/`（5 份）、`batch6/`（5 份）、`batch7/`（12 份），均含差分与 sha256；`snapshot-v1/` 归档 |

## 2. 口径定义（摘录，完整版见 fact-sheet §8）

| 指标 | 定义 | 零/缺失时 |
|---|---|---|
| Java/Vue 文件数 | 对应目录下 `*.java` / `*.vue` 递归计数，排除 `target/` | 目录缺失 → null + 原因 |
| 总行/空行/注释/代码 | 按字符状态机逐行分类，识别字符串与 `//`、`/* */`、`<!-- -->`，字符串里的 `//` 不计为注释 | — |
| 路由注解数 | 6 类 `*Mapping` 注解出现次数（含类级） | — |
| 实际路由数 | 类级 `@RequestMapping` 基路径 + 方法级路径组合后的 `(HTTP 方法, 路径)` 去重数 | — |
| 无法解析注解 | 路径为常量/变量而非字面量的方法级注解数，单列不丢弃 | — |
| migration 表 | `CREATE TABLE` 语句数、目标表名去重数（离线定义口径） | 目录缺失 → null |
| 运行库表数 | 需连库查询；未授权/无 CLI → null | 恒 null + 原因 |
| 测试收集数 | `pytest --collect-only` 计数 | 失败 → null |
| 测试执行/通过/失败/跳过 | 解析 junitxml | 无日志 → null |

`docs/competition/_fix_numbers.py` 是硬编码旧口径的替换脚本，**不作为事实来源**；第七批已给它加运行保护（默认 `sys.exit`，需 `ALLOW_LEGACY_FIX=1` 才执行）。

## 3. 当前冻结快照的数值

快照标识：git HEAD `9893705`（改写期间未产生新提交），统计源 675 个，
`source_digest = sha256:9f9e734241590138a16a1cd479a146208131f2457d38c3e380b0ecf8c1c3ea06`。

历史快照：v1 `sha256:5ed4b277…c09765`（316 文件 / 34,154 行，归档于 `fct-p0-01-prior/snapshot-v1/`）；v2 `sha256:92288325…e213d`（首轮材料口径，见 §7 第 2 条）。

| 范围 | 数值 |
|---|---|
| Java main | 321 文件；34,777 行（空 4,107 / 注释 2,234 / 代码 28,436） |
| Java test | 126 文件；16,147 行；`@Test` 671 处 |
| Vue | 175 文件；21,944 行（代码 19,453） |
| 路由 | 注解 476；实际路由 422；无法解析 0 |
| 迁移 | 57 文件；`CREATE TABLE` 129；离线定义表名去重 119；运行库表数 `null` |
| pytest | 收集 610 = 执行 610；通过 600；失败 0；错误 0；跳过 10 |

Java main 内 Controller 文件 63 个、文件名以 `Service` 结尾 75 个——这是按文件命名统计，**不是接口数**。

这些数字是“该 `source_digest` 的瞬时事实”。统计期间其他进程把 Java main 从 316 推到 321、路由从 421 推到 422、`@Test` 从 649 推到 671，因此引用时必须同时给出 digest。

## 4. 旧材料差异与逐条改写（七批）

分类变化：`needs_correction` 6 → 0；`needs_review` 131 → 45 → 26 → 20；`historical_reference` 1 → 3；`current_claim` 1 → 0。

- 第一批：6 条硬冲突（219 / 17,981 / 296 / 80 / 135 / 428），3 文件 6 行。
- 第二批：131 条 `needs_review` 中 86 条可按快照绑定，13 文件 94 行；另修 4 处清单外同类“75 表”与 2 处注释措辞。
- 第三批：先补采台账外三套测试，再改写 45 条中的 19 条（10 文件 24 行），把 `563` / `113` / `22` 三个无统计源的数字换成实测值。
- 第四批：`87 个 JUnit 类` → `122`（4 文件 6 行）。
- 第五批：其余同源句子的「暂无自动化测试套件」→ 实测 494 项，`87 测试类` → `122`（5 文件 7 行）。
- 第六批：`146 个页面组件 / 27,983 行` → `175 个 .vue / 21,944 行`，并删掉「尚未建自动化测试套件」（5 文件 7 行）。
- 第七批：把材料整体对齐到当前冻结快照 `9f9e7342…`（`656→671`、`122→126`、`15,649→16,147`、残留 `87 个测试类 / 87 后端类→126`），12 文件 64 行。

各批明细表中的数值是**该批当时的快照口径**；最终口径以 §3 与 §4.9 为准。

### 4.1 前像与差分

| 项 | 位置 |
|---|---|
| 前像（原文完整副本 + sha256） | `fct-p0-01-prior/`（第一批 3 份）、`batch2/`（16 份）、`batch3/`（10 份）、`batch4/`（4 份）、`batch5/`（5 份）、`batch6/`（5 份）、`batch7/`（12 份） |
| 精确差分 | 各批 `diffs/*.diff`（`git diff --no-index` 生成） |
| 改动规模 | 第一批 3 文件 6 行；第二批 94 行；第三批 24 行；第四批 6 行；第五批 7 行；第六批 7 行；第七批 64 行（63 删 / 63 增 + 1 行 `project-plan.md`）；均为行内替换，涉及 17 个文档、共 208 行 |

### 4.2 6 条改写明细

| 文件:行（Markdown / 打印版 HTML 同源） | 旧主张 | 改写后（当时快照 `9228…`） |
|---|---|---|
| `项目知识要点手册.md:41` / `答辩知识手册-打印版.html:176` | 219 个 Java 文件 / 17,981 行 / 45 Controller / 296 接口 / 80 张表 | 321 个 Java 文件 / 34,777 行 / 63 Controller / 422 接口 / 119 张表（迁移脚本定义，运行库未核验） |
| `项目知识要点手册.md:217` / `答辩知识手册-打印版.html:227` | 219 Java 文件 / 17,981 行 / 45 Controller / 55 Service / 296 接口 / 80 张表 | 321 Java 文件 / 34,777 行 / 63 Controller / 75 Service / 422 接口 / 119 张表（迁移脚本定义） |
| `答辩实战问答手册.md:181` / `答辩知识手册-打印版.html:322` | Python 135 个用例 111 通过 24 跳过 0 失败，后端 428 个 @Test | Python 610 个用例 600 通过 10 跳过 0 失败（后端服务运行时），后端 656 个 @Test |

改写原则：

1. 数值全部取自同一 `source_digest`，不跨快照拼数。
2. `119 张表` 是 migration 离线定义去重数，运行库未核验，因此同一句加限定。
3. 测试数标注“后端服务运行时”，因为后端运行与否决定集成测试是执行还是跳过（跳过 10 vs 23）。
4. 只改点名的行，**没有**用 `_fix_numbers.py` 做全局替换。

### 4.3 第二批：可绑定数值的统一口径（当时）

| 旧表述 | 新表述 | 依据 |
|---|---|---|
| 80 / 81 / 75 张表 | 119 张表 | `migrations.offline_distinct_table_n`（离线定义，运行库 `null`） |
| 296 个接口 | 422 个接口 | `java.main.routes.actual_route_n` |
| 428 个 @Test | 656 个 @Test | `java.test.test_annotation_n`（第七批已改 671） |
| 89 个测试文件 / 8,761 行 | 122 个测试文件 / 15,649 行 | `java.test.file_n` / `java.test.loc.total`（第七批已改 126 / 16,147） |
| 135 用例 = 111 通过 / 24 跳过 | 610 用例 = 600 通过 / 10 跳过 | 收集 610、junitxml 执行 610 |
| 563 项测试（Python 135 + 后端 428） | 610 个 Python 用例 + 656 个后端 @Test | 按决策不给合计（第七批 @Test 改 671） |

同步范围：Markdown 与打印版 HTML 的同源句子一起改。第二批按“仅可绑定数值”保留了 `87 个测试类` 与 `146 个页面组件`，第四批改为 `122`、第六批改为 `175 个 .vue`、第七批随快照改为 `126`；前端 `563`、Agent `113`、ai-service `22` 在第三批补采后改写（见 4.5）。

### 4.4 第三批补采：台账口径外的三套测试

| 套件 | 命令 | 结果 | 是否并入台账 |
|---|---|---|---|
| 前端 | `cd frontend && npm test`（`node --test test/**/*.test.mjs`） | `tests 494 / pass 494 / fail 0 / skipped 0`，99 个测试文件 | 否（不入 `metrics.json`） |
| Agent | `python -m pytest tests/agent -q` | 82 passed | 否（`tests/agent` 是 `tests/` 子集，已包含在 610 内） |
| ai-service | `python -m pytest ai-service/app/tests -q` | 67 passed | 否（独立目录，不属 `tests/`） |

三套互不可相加，也不与 610 相加；`metrics.json` 的 `tests.pytest` 仍只描述仓库根 `tests/`。原始日志与 sha256 见 [non-ledger-tests.json](file:///d:/SmartOpsAgent/docs/development/fct-p0-01-evidence/non-ledger-tests.json)。

`npm run test:visual`（4 个浏览器用例等待 `.ai-run-diagnostics` 超时）与 `npm run test:a11y`（1 个 pageError）失败，**不作为统计来源**，仅作失败记录留档。

### 4.5 第三批：19 条 `needs_review` 的改写口径

| 旧表述 | 新表述 | 依据（实测） |
|---|---|---|
| 前端 `563` 项 | 前端 `494` 项 | `npm test`：494 pass / 0 fail |
| `96 个测试文件` | `99 个测试文件` | `frontend/test/**/*.test.mjs` 计数 |
| Agent `113` 单测 | Agent `82` 单测 | `pytest tests/agent`：82 passed |
| agent-service `135 用例` | agent-service `82 用例` | 同上（该行原指 Agent 侧用例） |
| ai-service `约 22 个` | ai-service `67 个` | `pytest ai-service/app/tests`：67 passed |

同步改动 10 文件 24 行：`项目知识要点手册.md`、`defense.md`、`答辩材料-合订本.md`、`defense-master.md`、`adjustment-plan.md`、`project-plan.md`、`innovation.md`、`technical-document.html`、`答辩知识手册-打印版.html`、`答辩材料-打印合订本.html`。其中 2 行为口径注释。

### 4.6 剩余 20 条 `needs_review` 的构成

- **误报**：git hash 片段（`81` / `83`）、CSS（`135deg` / `79`）、源码行号（`89` / `219` / `#L29-L79`）、HTTP `428`、端口 `80`、`00111` 二进制串、文件链接行号。
- **历史 / 命令级日志**：`80 passed`、`89 passed` 等当时真实的执行记录。
- **本轮新增注释**：`135 用例口径` 说明 2 处，已归 `historical_reference`。

明细见 [stale-claims-after-batch7.json](file:///d:/SmartOpsAgent/docs/development/fct-p0-01-evidence/stale-claims-after-batch7.json)。

### 4.7 第四 / 五批：JUnit 类数与「暂无自动化测试套件」

| 旧表述 | 新表述 | 依据 |
|---|---|---|
| 后端 `87 个 JUnit 类` / `87 测试类` | 后端 `122 个 JUnit 类` / `122 测试类`（第七批改为 `126`） | `java.test.test_class_n` |
| 「前端双入口构建通过（暂无自动化测试套件）」 | 「前端 `npm test` 494 项全过（99 个测试文件）」 | 第三批实测；原文与 494 项直接冲突 |

覆盖位置：

- 第四批（4 文件 6 行）：`defense-master.md:275`、`defense-qa.md:94`、`答辩材料-合订本.md:481/756`、`答辩材料-打印合订本.html:294/402`。
- 第五批（5 文件 7 行）：`defense-master.md:136`、`defense-qa.md:24`、`demo-script.md:106`、`答辩材料-合订本.md:342/686`、`答辩材料-打印合订本.html:246/376`。
- 全库复查：`87 个 JUnit` / `87 测试类` / `暂无自动化测试套件` 命中 0。

### 4.8 第六批：页面组件口径

| 旧表述 | 新表述 | 依据 |
|---|---|---|
| `146 个页面组件` / `146 个 .vue` / `146 .vue` | `175 个 .vue 文件` / `175 个 .vue` / `175 .vue` | `metrics.json → vue.file_n = 175` |
| `27,983 行` | `21,944 行` | `metrics.json → vue.loc.total = 21,944` |
| 「前端尚未建自动化测试套件」 | 「`npm test` 494 项全过」 | 第三批实测 |

口径说明：`175` 是 `frontend/src` 下全部 `*.vue`（views 67 / components 105 / layouts 2 / App.vue 1）；“页面组件”不再作为独立口径，统一按 `.vue` 文件数表述，避免 67 / 105 / 175 三种读法混用。

覆盖位置（5 文件 7 行）：`defense.md:120`、`答辩材料-合订本.md:125`、`答辩材料-打印合订本.html:159`、`项目知识要点手册.md:45/221`、`答辩知识手册-打印版.html:176/230`。全库复查：`146 个` / `27,983` / `尚未建` 命中 0。

### 4.9 第七批：材料对齐到当前快照 `9f9e7342…`

| 旧表述 | 新表述 | 依据 |
|---|---|---|
| `656 个后端 @Test` / `656 个 @Test` / `656 @Test` / `656 后端 @Test` | `671` 同型表述 | `java.test.test_annotation_n = 671` |
| `122 个测试文件` | `126 个测试文件` | `java.test.file_n = 126` |
| `15,649 行` | `16,147 行` | `java.test.loc.total = 16,147` |
| `122 个 JUnit` / `122 测试类` | `126 个 JUnit` / `126 测试类` | `java.test.test_class_n = 126`（第四批曾按旧快照写 122） |
| 残留 `87 个测试类` / `87 后端类` / `87 后端类` | `126 个测试类` / `126 后端类` | 同上；此前批次只覆盖了「87 测试类 / 87 个 JUnit 类」两种写法 |
| 生成脚本 `_gen_print.py` 尾卡 | `610 个 Python 用例 + 671 个后端 @Test · 119 张表` | 与 HTML 尾卡同口径 |

覆盖 12 文件 64 行、76 处替换：`demo-script.md`、`innovation.md`、`defense.md`、`defense-advanced.md`、`defense-master.md`、`defense-qa.md`、`答辩实战问答手册.md`、`答辩材料-合订本.md`、`答辩材料-打印合订本.html`、`答辩知识手册-打印版.html`、`项目知识要点手册.md`、`project-plan.md`（1 行 `87 个测试类`，人工补入）。

全库复查：`656` / `15,649` / `122 个测试文件` / `122 测试类` / `87 个测试类` / `87后端类` 命中 0。

## 5. 快照可追溯与确定性

| 校验 | 结果 |
|---|---|
| 每个数字 → 源码 | `sources.json` 记录 675 个文件的 sha256/字节数；`metrics.json` 的 `snapshot` 给出 `source_digest` |
| 测试数字 → 原始日志 | `tests.pytest.junitxml_sha256 = sha256:505113a5…b3729`，路径记入 `run-meta.json` |
| 同一快照重复生成 | v1 快照连续两次生成 `metrics.json` sha256 均为 `0C0203EC…A63B52`，**byte-identical = True** |
| 当前快照 | `source_digest = sha256:9f9e7342…3ea06`；`--verify-snapshot` 返回 `FROZEN`、退出码 0，证据目录哈希前后不变 |
| 快照是否漂移 | `--verify-snapshot` 返回 `FROZEN` 时退出码 0；有新增/改动/删除时退出码 2 并列出文件，且**不写任何文件** |
| 生成时间是否污染比较 | 时间、命令、工作树改动清单只写入 `run-meta.json`；`metrics.json` 内无时间戳、无 `git_dirty*` 字段 |
| 快照切换记录 | [final-verify.json](file:///d:/SmartOpsAgent/docs/development/fct-p0-01-evidence/final-verify.json)：`9228…` → `9f9e7342…`（5 改 / 4 增 / 0 删）及逐项差额 |

## 6. 命令级证据

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/scripts/test_fact_ledger.py -q` | `PASS`：21 passed（含 2 例校验模式只读回归） |
| `python -m pytest tests -q --junitxml=docs/development/fct-p0-01-evidence/pytest.xml` | `PASS`：600 passed, 10 skipped |
| `python scripts/fact_ledger.py --collect-pytest --junitxml …` | `PASS`：`self_check=PASS`，`snapshot=NOT_VERIFIED` |
| `python scripts/fact_ledger.py --verify-snapshot docs/development/fct-p0-01-evidence/sources.json` | `PASS`：`snapshot=FROZEN`，退出码 0，未写证据 |
| 同命令在修复前 | `DRIFT`/`FROZEN` 分支曾写回证据目录（§7 第 2 条），已修复 |
| 前像与差分 | `PASS`：七批累计 17 文件 208 行；各批 `diffs/` 逐行可逆 |
| `cd frontend && npm test` | `PASS`：`tests 494 / pass 494 / fail 0 / skipped 0`；日志 `frontend-tests.log` |
| `python -m pytest tests/agent -q` | `PASS`：82 passed；日志 `agent-tests.log` |
| `python -m pytest ai-service/app/tests -q` | `PASS`：67 passed；日志 `ai-service-tests.log` |
| `cd frontend && npm run test:visual` | `FAIL`：4 个浏览器用例等待 `.ai-run-diagnostics` 超时；**不作为统计源** |
| `cd frontend && npm run test:a11y` | `FAIL`：1 个 pageError；**不作为统计源** |
| `python -c "…scan_claims(…)"`（只读复算，输出 `stale-claims-after-batch7.json`） | `PASS`：`needs_correction=0` / `needs_review=20` / `historical_reference=3` / `current_claim=0` |
| `node docs/competition/_knowledge2pdf.mjs` | `PASS`：26 页（1,066,910 字节）；含 `671`/`16,147`/`126 个测试文件`/`175 个 .vue`，无 `656`/`15,649`/`87` |
| `node docs/competition/_html2pdf.mjs` | `PASS`：30 页（1,273,683 字节）；含 `671`/`126 个 JUnit 类`/`126 测试类`/`494 项全过`，无 `656`/`122 测试类`/`87` |
| `node scripts/export-technical-pdf.mjs` | 未重导：`technical-document.html` 本批未改，PDF（14 页 / 523,078 字节）仍有效 |
| `docs/competition/_fix_numbers.py` | `NOT_RUN`：已加保护，默认拒绝执行（`sys.exit`），需 `ALLOW_LEGACY_FIX=1` |
| 运行库表数 | `NOT_RUN`：无 mysql CLI / 未授权连库 → `null`，不记 0 |
| MySQL、Redis、Ollama 相关外部依赖 | `SKIP`：本轮不属于 FCT 统计口径，未启动额外组件 |

## 7. 环境偏差（必须如实记录）

1. **仓库在统计与改写期间被其他进程持续写入**：Java main 287 → 316 → 321，路由 421 → 422，`@Test` 649 → 671，`CREATE TABLE` 111 → 129。因此 §3 的数值是**该 `source_digest` 的瞬时事实**；任何后续复核先跑 `--verify-snapshot`。
2. **校验命令曾覆盖已钉住的证据（已修复）**：修复前 `--verify-snapshot` 在 `FROZEN` 分支仍会写证据目录，一次收尾校验把 `9228…` 快照覆盖为 `9f9e7342…`（旧的 `sources.json` 不可还原）。现已改为纯只读，并加 2 例回归（`21 passed`）；当前唯一 pin 为 `9f9e7342…`，材料已按第七批统一。
3. **快照口径随并发写入推进**：`9228…`（122 / 656 / 15,649）已被 `9f9e7342…`（126 / 671 / 16,147）取代；主数值（Java main / 路由 / Vue / 迁移）两者一致，只有 Java 测试侧变化。
4. **Spring Boot 服务处于运行状态**：集成测试由 `SKIP` 变为实际执行，跳过数从 23 降到 10、执行数增至 610；对外引用必须同时给出“是否启动后端”。
5. **MySQL CLI 缺失**：运行库表数无法核对，只能给离线定义数（119），二者不可混用。
6. **扫描器盲区**：`stale-claims` 的数值绑定依赖旧主张清单；把旧数改成新数后，新数不再被绑定（`needs_correction=0` 对“行数/接口数”不再敏感）。复核以 `fact-sheet.md` 与 `metrics.json` 为准。
7. **台账外三套测试不计入 `metrics.json`**：前端 494、`tests/agent` 82、ai-service 67 与仓库根 `tests/` 的 610 不是同一集合，**不可相加**；`tests/agent` 是 610 的子集。
8. `git status` 已加 `core.quotepath=false`，中文路径不再输出为八进制转义。

## 8. 未做 / 边界

- 七批共改 17 个文档、208 行；剩余 20 条 `needs_review` 按 §4.6 分类保留，不做无依据替换（改动只会制造新错误）。
- 未做数据库连接、未采集运行库 schema。
- `四件套万全之策-打印版` 未重导：该文件不含任何受影响的数值（`656`/`122`/`146`/`563` 命中 0），PDF 保持 2026-11-05 版本。
- `technical-document.html` 本批未改，PDF 未重导。
- 未修复扫描器对新数值不绑定的盲区（§7 第 6 条），只在报告里披露。
- 未提交 git：本轮改动未做提交，按需再执行。

## 9. 回滚

- 脚本改动可回滚：`scripts/fact_ledger.py` 的校验只读分支与 `tests/scripts/test_fact_ledger.py` 的 2 例回归可单独撤销；删除 `scripts/fact_ledger.py`、`tests/scripts/`、`docs/development/fct-p0-01-evidence/` 即可完全回滚，无代码副作用、无数据写入。
- 文档改写可回滚：按 `batch7 → batch6 → batch5 → batch4 → batch3 → batch2 → 第一批` 逆序用 `fct-p0-01-prior/<批>/` 覆盖回原文件；sha256 见各 `manifest.json`，`diffs/` 可反向应用。
- 注意：`9228…` 的逐文件哈希证据已被覆盖，无法回到该 pin；若要复原首轮材料口径，只能用 `batch7` 及更早前像反向覆盖，并重新生成台账。
