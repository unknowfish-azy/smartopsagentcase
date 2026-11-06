# FCT-P0-01 过期主张清单（自动生成，只检测不改文）

> 扫描范围：`docs/competition/**`、`docs/audit/**`、`docs/*.md`（对外材料）；`docs/development/**` 是工作报告，不参与核对。
> 只做扫描与分类，**不修改任何文档**。分类规则：能绑定到本快照指标且数值不同 → `needs_correction`；
> 命中历史措辞 → `historical_reference`；命中当前措辞 → `current_claim`；其余 → `needs_review`。
> “N 张表”绑定的是**离线 migration 定义去重数**，不是运行库表数（后者为 null，未核验）；
> “N 个接口”绑定的是静态解析出的 (HTTP方法, 路径) 去重数，常量拼接路径未计入并在 `unresolved_annotation_n` 单列。

| 分类 | 条数 | 含义 |
|---|---:|---|
| needs_correction | 4 | 与本次冻结指标冲突，必须人工改写 |
| needs_review | 133 | 无法自动判定，需按上下文人工确认 |
| historical_reference | 1 | 明确写为历史/旧稿，可保留 |
| current_claim | 0 | 与本次指标一致，视为当前主张 |

## needs_correction（4）

| 文件:行 | 命中数字 | 绑定指标 | 原文（截断） |
|---|---|---|---|
| docs/competition/答辩知识手册-打印版.html:176 | 219, 17,981, 296, 80, 135, 146 | java.main.file_n | <table><thead><tr><th>服务</th><th>技术</th><th>端口</th><th>职责</th><th>真实规模</th></tr></thead><tbody><tr><td><strong>backend</strong></td><td>SpringBoot 3.3.5 + Java 17</td><td>8080</td> |
| docs/competition/答辩知识手册-打印版.html:227 | 219, 17,981, 296, 80 | java.main.file_n | 后端       219 Java 文件 / 17,981 行 / 45 Controller / 55 Service / 296 接口 / 80 张表 |
| docs/competition/项目知识要点手册.md:41 | 219, 17,981, 296, 80 | java.main.file_n | \| **backend** \| SpringBoot 3.3.5 + Java 17 \| 8080 \| 业务主干：权限、服务器、运维会话、哨兵、审计、模型网关、决策闭环 \| 219 个 Java 文件 / 17,981 行 / 45 Controller / 296 接口 / 80 张表 \| |
| docs/competition/项目知识要点手册.md:217 | 219, 17,981, 296, 80 | java.main.file_n | 后端       219 Java 文件 / 17,981 行 / 45 Controller / 55 Service / 296 接口 / 80 张表 |

## needs_review（133）

| 文件:行 | 命中数字 | 绑定指标 | 原文（截断） |
|---|---|---|---|
| docs/audit/20261105/status-baseline.md:9 | 81 | - | \| HEAD \| `48b8af47603e3d7e2b04b7bae81c667c588328dc` \| `git rev-parse HEAD` \| |
| docs/audit/20261105/status-baseline.md:20 | 83 | - | \| SCORE-01 尚未修复 \| CONFIRMED \| `training/evaluator.py` hash = `83a0d44c…`、`benchmark_runner.py` hash = `f1a9b97b…`，与交接书第 6.1 节记录的"当时源码 hash"完全一致 \| |
| docs/audit/20261105/test-matrix.md:19 | 80 | - | \| Agent pytest \| `pytest tests/agent -v --tb=no` \| — \| 80 passed \| NOT_RUN \| 覆盖 Inspector/Executor 定向回归 \| |
| docs/competition/adjustment-plan.md:44 | 80 | migrations.offline_distinct_table_n | - [x] **D1 数据库 schema 自愈**：新增 `AssistantWorkspaceConfig`，启动时幂等补齐 `chat_conversation` / `chat_message` / `chat_attachment` / `vision_event` / `operator_memory` / `personal_knowledge |
| docs/competition/adjustment-plan.md:55 | 563 | - | npm test            # node --test（563 项） |
| docs/competition/defense-advanced.md:25 | 80 | migrations.offline_distinct_table_n | \| 11 \| 80 张表**偏重** \| "完整域模型 + 幂等迁移；可模块化裁剪核心子集。" \| |
| docs/competition/defense-advanced.md:178 | 563, 135, 428 | - | **E1 563 项测试（Python 135 + 后端 428）是不是凑数？** |
| docs/competition/defense-advanced.md:184 | 80 | migrations.offline_distinct_table_n | **E3 80 张表会不会太重？** |
| docs/competition/defense-advanced.md:404 | 80 | - | 证据=词重叠 / 版本精确匹配 / 无benchmark / 图像仅文件名 / 80表偏重 / 未压测 |
| docs/competition/defense-master.md:25 | 563, 135, 428 | - | > 智维Agent 是一个可信 AI 智能运维平台。它用"版本感知混合检索 + 证据可信度评分 + 四级纠察 + 风险策略 + 人工审批 + 全程审计"，把大模型从"会回答问题"变成"可信地完成运维任务"。四端全栈、563 项测试（Python 135 + 后端 428）、零密钥可复现。一句话：AI 负责思考，人负责授权，系统负责留痕。 |
| docs/competition/defense-master.md:136 | 80 | migrations.offline_distinct_table_n | 四端全栈可运行；前端双入口构建（暂无自动化测试套件）、后端 87 测试类、80 张表；mock 零密钥跑通。模型基准评测尚未接入（见 E 类）。 |
| docs/competition/defense-master.md:208 | 80 | migrations.offline_distinct_table_n | **C7 🔥 80 张表是不是过度设计？** |
| docs/competition/defense-master.md:275 | 563 | - | 前端 563 项全过 + `tsc --noEmit` + 双构建；后端 87 个 JUnit 类（H2 MySQL 兼容跑真实迁移）；75 表迁移幂等。 |
| docs/competition/defense-master.md:280 | 563, 135, 428 | - | **F3 🔥 563 项测试（Python 135 + 后端 428）是不是凑数？** |
| docs/competition/defense-master.md:344 | 563, 135, 428 | - | 按模块切 + 门禁保交接 + 文档脚本保可复现；563 项测试（Python 135 + 后端 428）就是"某人请假也不崩"的保证。 |
| docs/competition/defense-master.md:361 | 563, 135, 428 | - | 套壳是"换个皮调 API"。我们有自研 Agent 内核、检索/证据/纠察/风险四套算法、75 表域模型、563 项测试（Python 135 + 后端 428）。**壳下面是自己的骨架。** |
| docs/competition/defense-master.md:423 | 563, 80 | - | 数字：563测试 · 87后端类 · 80表 · 5模块 · 6思考阶段 · 零密钥可复现 |
| docs/competition/defense-qa.md:94 | 80 | migrations.offline_distinct_table_n | A：前端双入口构建通过（暂无自动化测试套件）、`tsc --noEmit` 通过、双入口构建通过；后端 87 个 JUnit 测试类（H2 MySQL 兼容模式跑真实迁移）；MySQL 8 / 80 张表、迁移幂等、启动自动补齐。质量门禁命令全在 `project-plan.md`。 |
| docs/competition/defense-qa.md:99 | 80 | migrations.offline_distinct_table_n | **Q25：80 张表是不是过度设计？** |
| docs/competition/defense-qa.md:158 | 563, 135, 428 | - | A：按模块切分（前端交互 / 后端数据 / AI 算法），用测试与构建门禁防单人阻塞，文档与脚本保证可交接。563 项测试（Python 135 + 后端 428）就是"不会因为某个人请假而崩"的保证。 |
| docs/competition/defense-qa.md:170 | 563, 135, 428 | - | - 数字武器：563 项测试（Python 135 + 后端 428） / 87 后端类 / 75 表 / 5 模块 / 6 思考阶段 / 零密钥可复现。 |
| docs/competition/defense.md:53 | 113 | - | - **Python Agent 框架（可插拔算法内核）**，五个核心模块：planner（规划）/ executor（执行）/ inspector（核查）/ memory（记忆）/ policies（策略），经 **113 个单测**验证；产品级运行闭环由后端 `DecisionLoopService` 承载。 |
| docs/competition/defense.md:120 | 146 | - | - **前端**：146 个页面组件，用户层 / 管理员层**双入口构建通过**（注：前端尚未建自动化测试套件，已通过构建与类型检查验证）； |
| docs/competition/defense.md:121 | 428 | - | - **后端**：**428 个 @Test（87 个测试类）**，基于 H2（MySQL 兼容模式）跑真实迁移脚本； |
| docs/competition/defense.md:122 | 80 | migrations.offline_distinct_table_n | - **数据库**：MySQL 8，**80 张表**，迁移脚本幂等，启动自动补齐； |
| docs/competition/defense.md:162 | 563, 135, 428 | - | \| 前端工程质量 \| 10% \| 第 6 节 \| 563 项测试（Python 135 + 后端 428）、双入口同源、分包优化 \| |
| docs/competition/defense.md:171 | 563, 135, 428 | - | > 智维Agent 是一个可信 AI 智能运维平台。它用"版本感知混合检索 + 证据可信度评分 + 四级证据核查（规则→证据→AI→状态核验） + 风险策略 + 人工审批 + 全程审计"，把大模型从"会回答问题"变成"可信地完成运维任务"。四端全栈、563 项测试（Python 135 + 后端 428）、零密钥可复现。一句话：AI 负责思考，人负责授权，系 |
| docs/competition/demo-script.md:105 | 563, 135, 428 | - | \| 操作 \| 终端三条命令滚动，展示 563 项测试（Python 135 + 后端 428）通过；管理端快速展示审计页与模型网关页 \| |
| docs/competition/demo-script.md:107 | 563, 135, 428 | - | \| 字幕 \| 563 项测试（Python 135 + 后端 428） · tsc --noEmit · 双入口构建 · 模型网关 \| |
| docs/competition/innovation.md:106 | 563 | - | - 563 项前端测试覆盖契约、安全不变量与领域逻辑。 |
| docs/competition/innovation.md:120 | 563 | - | \| 前端工程化 \| `frontend/vite.shared.mjs`、`test/*.test.mjs` \| `npm test` 563 项通过 \| |
| docs/competition/innovation.md:128 | 563, 135, 428 | - | \| 前端工程质量 \| 10% \| 共享逻辑层 TS、双入口同源不变量、分包优化、563 项测试（Python 135 + 后端 428） \| |
| docs/competition/project-plan.md:66 | 563 | - | \| 前端工程质量 \| Vue 3 + Vite 7；共享逻辑层 TypeScript；构建分包；563 项前端测试 + 类型检查 + 双入口构建门禁 \| |
| docs/competition/project-plan.md:132 | 80 | migrations.offline_distinct_table_n | MySQL 8（80 张表） + Redis（会话/限流） |
| docs/competition/project-plan.md:201 | 563 | - | \| 前端测试 \| Node test runner，**563 项**断言全部通过（96 个测试文件） \| |
| docs/competition/project-plan.md:205 | 80 | migrations.offline_distinct_table_n | \| 数据库 \| MySQL 8，80 张表；迁移脚本幂等，启动自动补齐 schema \| |
| docs/competition/project-plan.md:212 | 563 | - | npm test            # 563 项 |
| docs/competition/recovery-contracts/evidence-index.md:35 | 219 | - | \| 后端测试 \| `tests/recovery_contracts/` \| 219 passed / 1 skipped \| |
| docs/competition/technical-document.html:92 | 80 | migrations.offline_distinct_table_n | <tr><td>后端</td><td>Spring Boot 3.3.5 / Java 17，MyBatis，MySQL 8（80 张表），Redis 7；账户/权限/审计</td></tr> |
| docs/competition/technical-document.html:141 | 563 | - | <tr><td>前端工程质量</td><td>Vue 3 + Vite 7；共享逻辑层 TS；构建分包；563 项前端测试 + 类型检查 + 双入口构建门禁</td></tr> |
| docs/competition/technical-document.html:170 | 80 | migrations.offline_distinct_table_n | MySQL 8（80 张表） + Redis（会话/限流）</pre> |
| docs/competition/technical-document.html:312 | 563 | - | <li><b>前端质量门禁</b>：563 项前端测试覆盖契约、安全不变量与领域逻辑；<code>tsc --noEmit</code> 类型检查纳入门禁；双入口（用户层/管理层）构建门禁保证同源。</li> |
| docs/competition/technical-document.html:321 | 80 | migrations.offline_distinct_table_n | <li><b>存储</b>：MySQL 8（业务与审计，80 张表）+ Redis 7（会话/限流）。</li> |
| docs/competition/technical-document.html:376 | 563 | - | <p>用户层/管理层共用代理工厂 <code>vite.shared.mjs</code>，避免两端口各写代理导致会话与 CSRF 分裂；共享逻辑层 TS（48 模块）承载 api/domain/utils/types，<code>tsc --noEmit</code> 纳入门禁；563 项前端测试守护契约与安全不变量。</p> |
| docs/competition/technical-document.html:394 | 563 | - | <div class="note avoid-break"><b>可验证证据对照</b>：可信闭环 → 管理端审批与审计页面；版本感知检索 → 同一主题多版本检索对比；透明推理 → 对话面板思考阶段逐条点亮；多模态边界 → 语音输入 + 图像证据 + 附件隔离；插件生态 → 插件列表与工具调用；模型网关 → mock/Ollama 切换；前端工程化 → <c |
| docs/competition/四件套万全之策-打印版.html:74 | 79 | - | .callout { background:#fffdf4; border:0.8pt solid #eadfc0; border-left:3pt solid #c79a2e; |
| docs/competition/答辩实战问答手册.md:22 | 80, 296, 563 | migrations.offline_distinct_table_n | > 这不是 PPT：后端 SpringBoot **80 张表 296 个接口**，前端 Vue3 **26 个以上页面**，AI 侧自研 Python 内核，**563 个测试用例**，而且**零 API Key 就能跑通全链路**。 |
| docs/competition/答辩实战问答手册.md:135 | 80 | migrations.offline_distinct_table_n | ### Q20 数据库 80 张表，会不会过度设计？ |
| docs/competition/答辩实战问答手册.md:136 | 81 | - | - **说**：81 张是按领域拆分的：账号权限、运维连接、哨兵告警、知识协同、模型网关、AI 决策闭环、团队协作七大域。拆得细是因为**审计和权限要求**——比如运行记录就拆成 `operation_run_record` / `_output` / `_evidence` 三张，用 `trace_id` 串起来，为的是**证据可独立追溯**。这不算过度设 |
| docs/competition/答辩实战问答手册.md:181 | 135, 111, 428 | tests.pytest.collected_n | - **说**：**没有跑过真实评测，我不会编数字。**实验文档有 17 个，其中 9 个明确标了 NOT RUN，原因写在里面：仓库没有配置真实模型、没有审核通过的数据集、没有评测器。**我能给出的真实数字是工程回归：Python 135 个用例 111 通过 24 跳过 0 失败，后端 428 个 @Test。**我们文档里自己注明这是"工程回归结果，不 |
| docs/competition/答辩实战问答手册.md:196 | 563 | - | - **说**：我们用了 AI 辅助，但**每一行都过过手**，并且有证据：全项目 grep `TODO\|FIXME\|HACK` **命中 0 处**；563 个测试用例覆盖核心逻辑；审计、MFA、SSH 终端、哨兵这些都是真依赖真实现（比如 SSH 用的是 `sshd-core 2.12.1`）。如果要验证，我可以当场讲任何一个模块的调用链。 |
| docs/competition/答辩实战问答手册.md:273 | 563 | - | - **说**：**给分必给理由。**"工程完整度我给 8 分——全栈真实现、563 个测试、零密钥可复现；算法深度我给 6 分——机制设计是我最满意的部分，但多个组件还是确定性基线；评测严谨度我给 4 分——这是我承认的最大短板。**综合我给 6.5 分，扣分主要扣在没有真实指标上。**" |
| docs/competition/答辩材料-合订本.md:58 | 113 | - | - **Python Agent 框架（可插拔算法内核）**，五个核心模块：planner（规划）/ executor（执行）/ inspector（核查）/ memory（记忆）/ policies（策略），经 **113 个单测**验证；产品级运行闭环由后端 `DecisionLoopService` 承载。 |
| docs/competition/答辩材料-合订本.md:125 | 146 | - | - **前端**：146 个页面组件，用户层 / 管理员层**双入口构建通过**（注：前端尚未建自动化测试套件，已通过构建与类型检查验证）； |
| docs/competition/答辩材料-合订本.md:126 | 428 | - | - **后端**：**428 个 @Test（87 个测试类）**，基于 H2（MySQL 兼容模式）跑真实迁移脚本； |
| docs/competition/答辩材料-合订本.md:127 | 80 | migrations.offline_distinct_table_n | - **数据库**：MySQL 8，**80 张表**，迁移脚本幂等，启动自动补齐； |
| docs/competition/答辩材料-合订本.md:167 | 563, 135, 428 | - | \| 前端工程质量 \| 10% \| 第 6 节 \| 563 项测试（Python 135 + 后端 428）、双入口同源、分包优化 \| |
| docs/competition/答辩材料-合订本.md:176 | 563, 135, 428 | - | > 智维Agent 是一个可信 AI 智能运维平台。它用"版本感知混合检索 + 证据可信度评分 + 四级证据核查（规则→证据→AI→状态核验） + 风险策略 + 人工审批 + 全程审计"，把大模型从"会回答问题"变成"可信地完成运维任务"。四端全栈、563 项测试（Python 135 + 后端 428）、零密钥可复现。一句话：AI 负责思考，人负责授权，系 |
| docs/competition/答辩材料-合订本.md:231 | 563, 135, 428 | - | > 智维Agent 是一个可信 AI 智能运维平台。它用"版本感知混合检索 + 证据可信度评分 + 四级纠察 + 风险策略 + 人工审批 + 全程审计"，把大模型从"会回答问题"变成"可信地完成运维任务"。四端全栈、563 项测试（Python 135 + 后端 428）、零密钥可复现。一句话：AI 负责思考，人负责授权，系统负责留痕。 |
| docs/competition/答辩材料-合订本.md:342 | 80 | migrations.offline_distinct_table_n | 四端全栈可运行；前端双入口构建（暂无自动化测试套件）、后端 87 测试类、80 张表；mock 零密钥跑通。模型基准评测尚未接入（见 E 类）。 |
| docs/competition/答辩材料-合订本.md:414 | 80 | migrations.offline_distinct_table_n | **C7 🔥 80 张表是不是过度设计？** |
| docs/competition/答辩材料-合订本.md:481 | 563 | - | 前端 563 项全过 + `tsc --noEmit` + 双构建；后端 87 个 JUnit 类（H2 MySQL 兼容跑真实迁移）；75 表迁移幂等。 |
| docs/competition/答辩材料-合订本.md:486 | 563, 135, 428 | - | **F3 🔥 563 项测试（Python 135 + 后端 428）是不是凑数？** |
| docs/competition/答辩材料-合订本.md:550 | 563, 135, 428 | - | 按模块切 + 门禁保交接 + 文档脚本保可复现；563 项测试（Python 135 + 后端 428）就是"某人请假也不崩"的保证。 |
| docs/competition/答辩材料-合订本.md:567 | 563, 135, 428 | - | 套壳是"换个皮调 API"。我们有自研 Agent 内核、检索/证据/纠察/风险四套算法、75 表域模型、563 项测试（Python 135 + 后端 428）。**壳下面是自己的骨架。** |
| docs/competition/答辩材料-合订本.md:629 | 563, 80 | - | 数字：563测试 · 87后端类 · 80表 · 5模块 · 6思考阶段 · 零密钥可复现 |
| docs/competition/答辩材料-合订本.md:756 | 80 | migrations.offline_distinct_table_n | A：前端双入口构建通过（暂无自动化测试套件）、`tsc --noEmit` 通过、双入口构建通过；后端 87 个 JUnit 测试类（H2 MySQL 兼容模式跑真实迁移）；MySQL 8 / 80 张表、迁移幂等、启动自动补齐。质量门禁命令全在 `project-plan.md`。 |
| docs/competition/答辩材料-合订本.md:761 | 80 | migrations.offline_distinct_table_n | **Q25：80 张表是不是过度设计？** |
| docs/competition/答辩材料-合订本.md:820 | 563, 135, 428 | - | A：按模块切分（前端交互 / 后端数据 / AI 算法），用测试与构建门禁防单人阻塞，文档与脚本保证可交接。563 项测试（Python 135 + 后端 428）就是"不会因为某个人请假而崩"的保证。 |
| docs/competition/答辩材料-合订本.md:832 | 563, 135, 428 | - | - 数字武器：563 项测试（Python 135 + 后端 428） / 87 后端类 / 75 表 / 5 模块 / 6 思考阶段 / 零密钥可复现。 |
| docs/competition/答辩材料-合订本.md:863 | 80 | migrations.offline_distinct_table_n | \| 11 \| 80 张表**偏重** \| "完整域模型 + 幂等迁移；可模块化裁剪核心子集。" \| |
| docs/competition/答辩材料-合订本.md:1016 | 563, 135, 428 | - | **E1 563 项测试（Python 135 + 后端 428）是不是凑数？** |
| docs/competition/答辩材料-合订本.md:1022 | 80 | migrations.offline_distinct_table_n | **E3 80 张表会不会太重？** |
| docs/competition/答辩材料-合订本.md:1242 | 80 | - | 证据=词重叠 / 版本精确匹配 / 无benchmark / 图像仅文件名 / 80表偏重 / 未压测 |
| docs/competition/答辩材料-打印合订本.html:59 | 135 | - | margin:6mm 0 10mm; background:linear-gradient(135deg,#0f2b46,#1f6feb); color:#fff; } |
| docs/competition/答辩材料-打印合订本.html:132 | 113 | - | <ul><li><strong>前端</strong> Vue 3 + Vite，用户层 / 管理员层双入口；</li><li><strong>后端</strong> Spring Boot，管账户、权限、审计、附件会话；</li><li><strong>AI 服务</strong> FastAPI，管模型网关、对话编排、RAG；</li><li><stro |
| docs/competition/答辩材料-打印合订本.html:159 | 146, 428, 80 | migrations.offline_distinct_table_n | <ul><li><strong>前端</strong>：146 个页面组件，用户层 / 管理员层<strong>双入口构建通过</strong>（注：前端尚未建自动化测试套件，已通过构建与类型检查验证）；</li><li><strong>后端</strong>：<strong>428 个 @Test（87 个测试类）</strong>，基于 H2（MySQL |
| docs/competition/答辩材料-打印合订本.html:175 | 563, 135, 428 | - | <table><thead><tr><th>评分维度</th><th>权重（参考）</th><th>本稿对应段落</th><th>你要在台上"亮"的点</th></tr></thead><tbody><tr><td>AI 技术深度 / 算法</td><td>35%</td><td>第 4 节</td><td>版本感知混合检索、trust_score、四级证据 |
| docs/competition/答辩材料-打印合订本.html:178 | 563, 135, 428 | - | <blockquote>智维Agent 是一个可信 AI 智能运维平台。它用"版本感知混合检索 + 证据可信度评分 + 四级证据核查（规则→证据→AI→状态核验） + 风险策略 + 人工审批 + 全程审计"，把大模型从"会回答问题"变成"可信地完成运维任务"。四端全栈、563 项测试（Python 135 + 后端 428）、零密钥可复现。一句话：AI 负责 |
| docs/competition/答辩材料-打印合订本.html:202 | 563, 135, 428 | - | <blockquote>智维Agent 是一个可信 AI 智能运维平台。它用"版本感知混合检索 + 证据可信度评分 + 四级纠察 + 风险策略 + 人工审批 + 全程审计"，把大模型从"会回答问题"变成"可信地完成运维任务"。四端全栈、563 项测试（Python 135 + 后端 428）、零密钥可复现。一句话：AI 负责思考，人负责授权，系统负责留痕。< |

> 其余 53 条省略，完整列表可用 `--claims-json` 另存。

## historical_reference（1）

| 文件:行 | 命中数字 | 绑定指标 | 原文（截断） |
|---|---|---|---|
| docs/OPTIMIZATION-CHANGES.md:397 | 89 | - | \| `python -m pytest -q` \| 上一轮真实结果：89 passed / 24 skipped \| |

## current_claim（0）

无。

