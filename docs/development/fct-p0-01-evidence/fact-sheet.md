# FCT-P0-01 事实表（自动生成）

> 本文件由 `scripts/fact_ledger.py` 生成，请勿手工改数。每个数字的口径见文末“口径定义”。
> `docs/competition/_fix_numbers.py` 是硬编码替换脚本，**不可作为事实来源**。

## 1. 快照

| 项 | 值 |
|---|---|
| git HEAD | `3f41c2c94d15439d019dcb129b685f78c7412cf6` |
| 工作树改动文件数（已排除本次输出目录） | 87 |
| 改动路径摘要 | `sha256:d1d8a5d8996baf8a6c14ec3cb76694e0c0d0f81c101bcbf6de5c88c5414a7d30` |
| 纳入统计源文件数 | 616 |
| 统计源内容摘要 | `sha256:436647f13909dd043c373514d1b2d41826316289e64c65d54c3e8113bc47d7c6` |

冻结校验：`python scripts/fact_ledger.py --verify-snapshot docs/development/fct-p0-01-evidence/sources.json`。来源被改动/增删时退出码 2，不覆盖证据。

## 2. 代码规模（Java / Vue）

| 范围 | 总行 | 空行 | 注释行 | 代码行 |
|---|---:|---:|---:|---:|
| Java main（287 文件） | 28492 | 3444 | 1836 | 23212 |
| Java test（107 文件） | 12589 | 1666 | 375 | 10548 |
| Vue（174 文件） | 21553 | 1919 | 548 | 19086 |

- Java main 中 Controller 文件 54 个、文件名以 Service 结尾 67 个（按文件命名统计，不是接口数）。

## 3. 路由：注解数与实际路由数（口径分开）

| 指标 | 值 | 说明 |
|---|---:|---|
| 路由注解数（含类级） | 423 | 注解出现次数，不等于接口数 |
| 实际路由数（方法+路径去重） | 378 | 类级基路径已拼接 |
| 无法静态解析的路径注解 | 0 | 常量拼接等，未静默丢弃 |

## 4. 数据库表

| 指标 | 值 | 说明 |
|---|---:|---|
| migration 文件数 | 48 | 仅 `src/main/resources/db/migration` |
| migration 中 CREATE TABLE 数 | 111 | 含 IF NOT EXISTS |
| 离线定义表名去重数 | 101 | 仅离线定义口径 |
| 运行库实际表数 | null | 未连接数据库，见“缺失统计源” |

## 5. 测试：收集 / 执行 分开

| 指标 | 值 |
|---|---:|
| pytest 收集数 | 586 |
| 执行数 | 585 |
| 通过 | 562 |
| 失败 | 0 |
| 错误 | 0 |
| 跳过 | 23 |
| Java @Test 注解数 | 559 |

注解数不等于执行数；未提供 junitxml 时执行类指标为 null。

## 6. 缺失统计源（值为 null，不记 0）

| 指标 | 原因 |
|---|---|
| `migrations.runtime_tables_n` | 未找到 mysql CLI，且未提供连接参数；不猜测运行库表数。 |

## 7. 自检

- 恒等式与路由计数自检通过。

## 8. 口径定义

| 指标 | 定义 |
|---|---|
| `java.main.file_n` | backend/src/main/java 下 *.java 文件数（递归，不含 target/） |
| `java.main.loc.total` | 总行数，含空行与注释行 |
| `java.main.loc.blank` | 去掉首尾空白后为空的行数 |
| `java.main.loc.comment` | 整行仅注释（//、/* */），无代码字符的行数 |
| `java.main.loc.code` | 非空且含至少一个代码字符的行数 |
| `java.main => code + comment + blank = total` | 恒等式，用于自检 |
| `java.routes.route_annotation_n` | GetMapping/PostMapping/PutMapping/DeleteMapping/PatchMapping/RequestMapping 注解出现次数（含类级） |
| `java.routes.actual_route_n` | 类级 @RequestMapping 基路径 + 方法级注解路径组合后的 (HTTP方法, 路径) 去重数 |
| `java.routes.unresolved_annotation_n` | 路径不是字符串字面量（常量/变量拼接）而无法静态解析的方法级注解数，不静默丢弃 |
| `java.test.file_n` | backend/src/test/java 下 *.java 文件数 |
| `java.test.test_annotation_n` | @Test 注解出现次数（一个类可有多个；不等于用例执行数） |
| `java.main.controller_file_n` | 文件名含 Controller 的 Java 文件数 |
| `java.main.service_file_n` | 文件名以 Service 结尾的 Java 文件数 |
| `vue.file_n` | frontend/src 下 *.vue 文件数 |
| `vue.loc.*` | 同上 LOC 口径（Vue 单文件按整文件计，识别 <!-- --> 注释） |
| `migrations.file_n` | backend/src/main/resources/db/migration 下 *.sql 文件数（不含 target/ 副本） |
| `migrations.create_table_n` | 上述 migration 文件中 CREATE TABLE 语句数（含 IF NOT EXISTS） |
| `migrations.offline_distinct_table_n` | 上述 CREATE TABLE 的目标表名去重数（离线定义口径，不是运行库事实） |
| `migrations.runtime_tables_n` | 运行库实际表数；未连接数据库时为 null，原因见 unavailable |
| `tests.pytest.collected_n` | pytest --collect-only 收集到的用例数（本快照、本解释器） |
| `tests.pytest.executed_n` | 解析 junitxml 得到的执行数；未提供 junitxml 时为 null |
| `tests.pytest.junitxml_sha256` | junitxml 原始日志的 sha256，用于把执行/通过/跳过数追回到原始日志 |
| `sources.*` | 被统计文件的 sha256 与字节数，用于追溯单个数字 |
| `snapshot.source_digest` | 按路径排序的 "path<TAB>sha256" 拼接后再 sha256，用于“同一快照重复生成一致”的比较 |
| `snapshot.git_dirty_files_n` | git status --porcelain 行数，已排除本次输出目录 |

## 9. 实际路由明细（节选）

| HTTP | 路径 | 控制器 |
|---|---|---|
| POST | `/api/cloud/accounts` | CloudAssetController |
| GET | `/api/cloud/accounts` | CloudAssetController |
| POST | `/api/cloud/accounts/{id}/sync` | CloudAssetController |
| GET | `/api/cloud/accounts/{id}/sync-runs` | CloudAssetController |
| GET | `/api/cloud/resources` | CloudAssetController |
| GET | `/api/cloud/resources/{uid}` | CloudAssetController |
| POST | `/api/cloud/resources/{uid}/status` | CloudAssetController |
| GET | `/api/cloud/business/{business}/impact` | CloudAssetController |
| POST | `/api/cloud/relations` | CloudAssetController |
| POST | `/api/cloud/resources` | CloudAssetController |
| GET | `/api/cloud/resources/{uid}/history` | CloudAssetController |
| POST | `/api/cloud/resources/{uid}/confirm` | CloudAssetController |
| POST | `/api/cloud/targets/resolve` | CloudAssetController |
| GET | `/api/admin/overview` | AdminAccountsController |
| GET | `/api/admin/registration` | AdminAccountsController |
| PUT | `/api/admin/registration` | AdminAccountsController |
| GET | `/api/admin/users` | AdminAccountsController |
| GET | `/api/admin/users/{id}/context` | AdminAccountsController |
| GET | `/api/admin/governance` | AdminAccountsController |
| POST | `/api/admin/governance/{id}` | AdminAccountsController |
| DELETE | `/api/admin/governance/{id}` | AdminAccountsController |
| POST | `/api/admin/governance/transfer/{id}` | AdminAccountsController |
| POST | `/api/admin/users` | AdminAccountsController |
| PUT | `/api/admin/users/{id}` | AdminAccountsController |
| POST | `/api/admin/users/{id}/reset-password` | AdminAccountsController |
| GET | `/api/admin/sessions` | AdminAccountsController |
| DELETE | `/api/admin/sessions/{id}` | AdminAccountsController |
| GET | `/api/admin/audit` | AdminAccountsController |
| GET | `/api/admin/audit/{id}` | AdminAccountsController |
| GET | `/api/admin/governance/capabilities` | AdminAccountsController |
| GET | `/api/admin/mfa` | AdminMfaController |
| POST | `/api/admin/mfa/setup` | AdminMfaController |
| POST | `/api/admin/mfa/enable` | AdminMfaController |
| POST | `/api/admin/mfa/recovery` | AdminMfaController |
| POST | `/api/admin/mfa/disable` | AdminMfaController |
| GET | `/api/admin/mfa/notices` | AdminMfaController |
| POST | `/api/auth/mfa/notices/{id}/read` | AdminMfaController |
| GET | `/api/admin/model-governance` | AdminModelGovernanceController |
| GET | `/api/admin/readiness` | AdminReadinessController |
| GET | `/api/admin/teams` | AdminTeamsController |
| GET | `/api/admin/teams/{id}/members` | AdminTeamsController |
| PUT | `/api/admin/teams/{id}/status` | AdminTeamsController |
| GET | `/api/admin/workbench` | AdminWorkbenchController |
| GET | `/api/knowledge/artifacts` | ArtifactDraftController |
| POST | `/api/knowledge/artifacts` | ArtifactDraftController |
| POST | `/api/knowledge/artifacts/{id}/submit-review` | ArtifactDraftController |
| GET | `/api/assistant/options` | AssistantController |
| PUT | `/api/assistant/preference` | AssistantController |
| POST | `/api/assistant/chat` | AssistantController |
| GET | `/api/auth/human-verification` | AuthController |
| POST | `/api/auth/human-verification/verify` | AuthController |
| GET | `/api/auth/session` | AuthController |
| POST | `/api/auth/login` | AuthController |
| POST | `/api/auth/mfa/complete` | AuthController |
| POST | `/api/auth/mfa/cancel` | AuthController |
| GET | `/api/auth/registration` | AuthController |
| POST | `/api/auth/register` | AuthController |
| POST | `/api/auth/password` | AuthController |
| GET | `/api/auth/profile` | AuthController |
| PUT | `/api/auth/profile` | AuthController |

> 其余 318 条见 `metrics.json` → `java.main.routes.routes`。
