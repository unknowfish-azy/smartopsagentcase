# HC-05 副本回滚演练设计

| 项 | 值 |
|---|---|
| task_id | HC-05 |
| mode | PLAN |
| 日期 | 2026-11-05 |
| 演练位置 | `d:\SmartOpsAgent\.runtime\hc-check\<runId>\`（仓库内、已被 `.gitignore` 忽略） |
| 本轮执行 | **未执行**；未构建、未切换、未启动、未连库、未做任何 git 写操作 |
| 关联 | `quality-gate.md` AUX-ROLLBACK、`preflight.md` E 组、`failure-triage.md` |

目标：先在副本上证明“构建产物可原子切换、旧制品保留、数据库迁移可逆、失败可退回”，再谈发布。回滚方案不得依赖 `git reset --hard`/`git clean`，也不得触碰工作树中 359 条他人改动。

---

## 1. 原则

1. **副本优先**：所有演练只在 `.runtime/hc-check/<runId>/` 内发生；`frontend/dist`、`frontend/dist-admin`、真实数据库、真实服务一律不写。
2. **旧制品保留**：切换前把当前版本完整复制到 `backups/A-<stamp>/`，并生成 hash manifest；切换后 A 仍原样保留。
3. **唯一构建目录**：新版本只构建到 `builds/B-<stamp>/user-dist`、`builds/B-<stamp>/admin-dist`，不复用、不覆盖。
4. **原子切换**：只替换指针文件 `current.json`（同盘临时文件 + `Move-Item -Force`），不做“先删旧目录再拷新目录”的空窗操作。
5. **迁移逆向在隔离库**：数据库演练使用独立库名 `smartops_drill_<runId>`；真实库只允许只读导出备份，不允许执行迁移/逆向。
6. **失败可解释**：每次切换/回滚都有命令、退出码、hash、耗时、冒烟结果和独立复核人。
7. **不破坏他人改动**：演练前后对目标文件与 `git status --porcelain` 条目数做只读比对；只删除本次 `created-files.json` 中登记的文件。

---

## 2. 演练拓扑

```text
d:\SmartOpsAgent\.runtime\hc-check\<runId>\
  rollback\
    live-sim\
      current.json              # 指针：记录 current / previous / release_id
      artifacts\
        A-<stamp>\user-dist\    # 旧制品（只读保留）
        A-<stamp>\admin-dist\
        B-<stamp>\user-dist\    # 新制品（构建产出）
        B-<stamp>\admin-dist\
      releases\
        A-<stamp>.manifest.json
        B-<stamp>.manifest.json
    backups\
      A-<stamp>\                # 切换前完整副本（含 manifest）
    db-drill\
      source-<stamp>.sql        # 真实库只读导出（权限受限，不提交）
      restored-<stamp>.sql      # 逆向恢复用的同一 dump
      counts-before.json
      counts-after.json
    logs\
    evidence\
      created-files.json
      rollback-report.yaml
```

命名：`<stamp>` 用 `yyyyMMdd-HHmmss`；`release_id` 用 `A-<stamp>`/`B-<stamp>`，不得复用。

---

## 3. 前置（只读）

| 项 | 命令（项目根） | 要求 |
|---|---|---|
| 运行目录唯一 | `Test-Path -LiteralPath $run` | 不存在，新建 |
| 旧制品前像 | `Get-FileHash frontend\dist\index.html,frontend\dist-admin\admin.html,backend\target\smartops-backend-0.0.1-SNAPSHOT.jar -Algorithm SHA256` | 存在项全部记录到 `inputs.json`；缺失项标 `ABSENT` |
| 工作树前像 | `git rev-parse HEAD; @(git status --porcelain).Count` | 只读；HEAD 与 dirty 数写入报告 |
| 环境 | `quality-gate.md` 3.2 的 JDK17 检查、`preflight.md` A/B/E/F 必需项 | 未满足则不开始切换演练 |
| 数据库 | `preflight.md` D01–D04 | 迁移演练需要可连接 MySQL、备份目录可用、隔离库可建 |

前置失败：`AUX-ROLLBACK=NOT_RUN/BLOCKED_*`，不得用“模拟通过”替代。

---

## 4. 制品回滚演练（未来 RUN 步骤）

### Step 1 冻结旧制品 A

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$live  = "$run\rollback\live-sim"
$A     = "$live\artifacts\A-$stamp"
New-Item -ItemType Directory -Force -Path "$A\user-dist","$A\admin-dist" | Out-Null
Copy-Item -Recurse -Force 'd:\SmartOpsAgent\frontend\dist\*'        "$A\user-dist\"
Copy-Item -Recurse -Force 'd:\SmartOpsAgent\frontend\dist-admin\*'  "$A\admin-dist\"
# 生成 A manifest：逐文件相对路径 + SHA256
```

要求：A 目录写入完成后设为只读（`attrib +R` 或 ACL），后续步骤不得修改。若 `frontend/dist*` 不存在，A 标 `ABSENT`，此演练只能验证“从无到有”的切换，不能声称“旧制品保留”。

### Step 2 构建新制品 B（唯一目录）

```powershell
cd d:\SmartOpsAgent\frontend
npm run build -- --outDir "../.runtime/hc-check/$runId/rollback/live-sim/artifacts/B-$stamp/user-dist"
npm run build:admin -- --outDir "../.runtime/hc-check/$runId/rollback/live-sim/artifacts/B-$stamp/admin-dist"
```

要求：退出码 0；`user-dist/index.html`、`admin-dist/admin.html` 存在；`frontend/dist`、`frontend/dist-admin` 前后 hash 不变；失败则整项 `FAIL`，不进入切换。

### Step 3 生成 manifest 与指针

`B-<stamp>.manifest.json` 至少包含：

```json
{
  "release_id": "B-20261105-XXXXXX",
  "created_at": "<iso8601>",
  "source": { "head": "<sha>", "package_lock_sha256": "<hash>", "vite_config_sha256": "<hash>" },
  "artifacts": {
    "user-dist": { "files": 123, "tree_sha256": "<hash>", "index_html_sha256": "<hash>" },
    "admin-dist": { "files": 45, "tree_sha256": "<hash>", "admin_html_sha256": "<hash>" }
  }
}
```

指针 `current.json`：

```json
{
  "current": "B-20261105-XXXXXX",
  "previous": "A-20261105-XXXXXX",
  "switched_at": "<iso8601>",
  "switched_by": "<role>"
}
```

切换命令（只替换指针）：

```powershell
$tmp = "$live\current.json.tmp"
@{ current=$B; previous=$A; switched_at=(Get-Date).ToString('o'); switched_by=$env:USERNAME } |
  ConvertTo-Json | Set-Content -LiteralPath $tmp -Encoding UTF8
Move-Item -LiteralPath $tmp -Destination "$live\current.json" -Force
```

说明：不使用“删除 live 目录再复制”的方式；`deploy/server/rollback.sh` 采用 `mv` + `cp -a`，存在空窗且无 DB 逆向，只可作参考，不得直接作为演练证据（`SOURCE_OBSERVED`）。

### Step 4 切换后验证

| 检查 | 命令 | 通过判据 |
|---|---|---|
| 指针一致 | `Get-Content "$live\current.json"` | `current=B`，`previous=A` |
| 产物完整 | 重算 B 目录逐文件 hash，对比 manifest | 0 缺失、0 多余、hash 全等 |
| 旧制品仍在 | 重算 A 目录 hash | 与 A manifest 全等，未被修改 |
| 静态冒烟 | 用只读静态服务器或 `vite preview` 指向当前指针目录，GET `/`、`/admin.html` | HTTP 200；标题/关键资源与 manifest 对应；保存响应摘要与截图 |
| live 未变 | 重算 `frontend/dist`、`frontend/dist-admin` hash | 与 Step 1 前像全等 |
| 他人改动 | `@(git status --porcelain).Count` | 与前置计数一致（只读） |

冒烟不得用 dev server 替代构建产物；若 `vite preview` 不支持任意 `--outDir`，改用一次性 Node 静态服务器，并在报告中记录所用命令。端口从预检空闲段选择（避开 5173/5174/8080/8001/8002）。

### Step 5 回滚到 A

```powershell
$tmp = "$live\current.json.tmp"
@{ current=$A; previous=$B; switched_at=(Get-Date).ToString('o'); switched_by=$env:USERNAME } |
  ConvertTo-Json | Set-Content -LiteralPath $tmp -Encoding UTF8
Move-Item -LiteralPath $tmp -Destination "$live\current.json" -Force
```

回滚后重复 Step 4 的指针、A 产物、B 保留、live hash、冒烟检查。记录从发出回滚命令到冒烟通过的耗时（RTO），不得填写估计值。

### Step 6 故障注入（至少一项）

| 注入 | 做法（只在副本） | 期望 |
|---|---|---|
| 产物缺失 | 从 B 的副本中删除 `assets/` 下一个文件 | 切换前 hash 校验应失败，流程停在 Step 3，不更新指针 |
| manifest 不匹配 | 修改 B manifest 中一个 hash | 校验失败，`FAIL`，不切换 |
| 冒烟失败 | 临时把 B 的 `index.html` 替换为空文件（副本） | Step 4 冒烟失败 → 立即回滚 A，报告 `FAIL` 并保留现场 |
| 切换中断 | 只写 `current.json.tmp`，不执行 `Move-Item` | 指针仍为 A，服务不受影响；清理 tmp 后重来 |

故障注入后必须能从 A 恢复并给出证据；不能恢复则 `AUX-ROLLBACK=FAIL`。

---

## 5. 数据库迁移逆向演练（隔离库）

### 5.1 边界

- 只对 `smartops_drill_<runId>` 操作；真实库 `smartops` 只做只读导出。
- Flyway 迁移目录 `backend/src/main/resources/db/migration/`（当前 38 个）没有 down 脚本，因此“逆向”定义为**dump 恢复**，不是 `flyway undo`，更不是 `flyway clean`。
- 任何凭据从 `.env` 读入进程环境变量，不打印、不写日志；使用 `MYSQL_PWD` 临时变量并在 `finally` 还原。

### 5.2 步骤

1. **只读导出真实库**（不迁移）：
   `mysqldump --single-transaction --routines --triggers --events --no-tablespaces` 导出到 `db-drill\source-<stamp>.sql`；校验文件非空、退出码 0。
2. **建隔离库**：`CREATE DATABASE smartops_drill_<runId>`（仅演练库）；导入 dump；记录表数量与关键表行数到 `counts-before.json`。
3. **选一个迁移前向执行**：记录迁移文件 SHA256；在隔离库执行该 SQL（或用后端指向隔离库启动让 Flyway 执行）；确认 `flyway_schema_history` 记录与 checksum。
4. **检测**：重新统计表数量、关键表行数、索引/约束数量，写入 `counts-after.json`；与 before 比对，差异必须能由该迁移解释。
5. **逆向恢复**：删除并重建演练库（`DROP DATABASE smartops_drill_<runId>` 仅在演练库），重新导入同一 dump；再次统计到 `counts-restored.json`。
6. **比对**：`counts-restored.json` 与 `counts-before.json` 的 schema/行数/关键 checksum 一致；`flyway_schema_history` 回到导入时状态。
7. **清理**：只删除本次创建的 `smartops_drill_<runId>` 与 `.runtime/hc-check/<runId>/` 内登记文件；真实库与真实备份保留。

### 5.3 数据库回滚判据

| 判据 | 通过条件 |
|---|---|
| 隔离性 | 全程未连接/写入真实库（连接串指向 drill 库，报告留证） |
| 前向可执行 | 迁移在 drill 库成功，退出码 0，schema history 有记录 |
| 逆向可执行 | dump 恢复成功，退出码 0，耗时已记录 |
| 一致性 | 恢复后表数量、关键行数、关键 checksum 与迁移前一致；差异为 0 |
| 无残留 | 演练库已删除或明确保留待查；真实库未变 |
| 可解释 | 每条 SQL/命令、退出码、日志路径、执行人齐全 |

失败处理：恢复失败即停止，保留 drill 库与日志供诊断；不得改去真实库“试一下”。真实库若被误写，立即升级为事件，按备份恢复并由独立复核人确认。

---

## 6. 成功/失败判据（整体）

| 维度 | 成功 | 失败 |
|---|---|---|
| 制品切换 | 指针更新、hash 全等、冒烟 200、A 保留 | hash 不符、指针未更新、冒烟失败、A 被改 |
| 回滚 | A 恢复后 hash 全等、冒烟通过、RTO 有实测值 | 回滚后仍失败或需要重建 |
| 数据库 | drill 前向/逆向均成功、一致性差异 0、真实库未动 | 恢复失败、真实库被写、无法比对 |
| 他人改动 | 演练前后 dirty 条目数一致、仅删除登记文件 | 出现未登记改动/删除他人文件 |
| 证据 | 命令、退出码、日志、hash manifest、耗时、复核人齐全 | 缺任一项视为未完成 |
| 结论 | `AUX-ROLLBACK=PASS` | `FAIL` 或 `NOT_RUN/BLOCKED_*` |

时间目标只记录实测，不在本文预设“已达标”。本地演练记录 RTO 与 RPO（数据库）实际值；RPO 由 dump 时间点决定。

---

## 7. 不破坏他人改动的校验

1. 演练前记录 `git status --porcelain` 条目数与关键文件 hash（只读）。
2. 建立 `evidence\created-files.json`，逐条登记本次新建文件的绝对路径与 hash。
3. 演练中只写 `created-files.json` 内的路径；不得写 `docs/`、`frontend/src/`、`backend/src/`、`tests/`。
4. 演练后再次记录 dirty 条目数；若增加且不是本次登记文件，停止并报告，不执行 `git checkout`/`clean` 来“恢复”。
5. 清理时只删除登记文件；删除前逐个核对 hash，发现内容已被他人修改则整体拒绝删除。
6. 禁止使用 `git reset --hard`、`git clean -fdx`、`git checkout -- .`、`git restore .`、`git stash drop`。

---

## 8. 禁止事项

- 在 `frontend/dist`、`frontend/dist-admin`、`backend/target` 上做切换/回滚演练。
- 直接运行 `deploy/server/rollback.sh` 指向真实 `APP_DIR`；它没有演练保护、没有数据库逆向、且 `mv`+`cp` 非原子。
- 对真实库执行迁移、逆向、`DROP DATABASE`、`flyway clean`。
- 用 `git reset --hard`/`clean` 恢复演练现场。
- 只保留成功日志、删除失败日志；或把“未演练”写成“回滚已就绪”。
- 把 A 目录设为可写后又声称“旧制品未被修改”。
- 在报告中写入 `.env` 值、数据库密码、token。

---

## 9. 本轮状态

| 项 | 状态 | 原因 |
|---|---|---|
| 制品切换演练 | `NOT_RUN` | PLAN，无 RUN 授权；未构建 |
| 故障注入 | `NOT_RUN` | 同上 |
| 数据库逆向演练 | `NOT_RUN` | 未连库、未导出、未建 drill 库 |
| `AUX-ROLLBACK` 门禁 | `NOT_RUN` | 无本轮证据 |
| 已核实事实 | `SOURCE_OBSERVED` | `deploy/server/rollback.sh` 存在 `mv`+`cp` 空窗且无 DB 逆向；`restart-local-backend.ps1` 会保留旧 jar 到 `.runtime\backend`；`.runtime` 已被 `.gitignore` 忽略 |

后续 RUN 完成后，把 `AUX-ROLLBACK` 状态、RTO/RPO 实测、manifest 路径、复核人写入 `quality-gate.md` 的 `report.yaml`；未完成前不得给 `RELEASE_READY`。
