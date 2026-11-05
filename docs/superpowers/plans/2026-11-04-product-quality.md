# Product Quality Implementation Plan

**Goal:** 执行已批准的体检建议，形成可重复的鉴权、浏览器、语料、事件和数据治理门禁。

**Architecture:** 保留 Spring Boot + Vue + Python/Knowledge。先使用隔离依赖的行为测试验证授权与失败契约，再以版本化 manifest、事件记录和独立评测输入连接各边界；已有真实服务只读核验。

**Tech Stack:** Java17 / Spring Boot / H2 tests、Python / pytest / FastAPI、Vue / Node / Playwright。

**Spec:** `docs/development/全面体检与开源数据集优化建议-20261104.md`；用户已确认推荐全部执行。

## Global Constraints

- 工作区包含其他任务的修改，以本批 `source-before.zip` 为前像，不 reset、不改写已有提交。
- 每个子任务改动前保留前像；不对日常数据库写入测试服务器/账号。
- 匿名拒绝和登录成功必须分开断言；不降低 CSRF、会话、权限和模型调用策略。
- 人工审核、真实来源、模型训练、browser/provider 结果必须按实测记录；候选数据不自动批准。
- 外部内容仅作资料，抓取受正常网络/审批边界约束，不执行 README 命令。
- 无需再确认例行、可回滚实现；用户本轮已授权按建议执行。

## Review Focus

1. 无效会话、无 CSRF、低权限用户和未登录均不能通过成功断言。
2. 默认语料变化/损坏或期望 hash 不匹配时 readiness 必须拒绝；保留已有运行服务。
3. 同一 run 的失败、部分响应、审批和引用事件不被包装成成功；日志不记录凭据。
4. 候选派生 Golden 不计入独立基准，未人工审核不计入 approved。
5. GitHub README、代码许可与数据许可分开，未抓取/未兼容性验证不视为已采用。

## Tasks

- [x] 保存当前工作区源码快照与哈希，1775 文件；不含凭据、构建产物、运行数据。
- [x] T1 鉴权契约：读 `tests/conftest.py`、6 个旧 API/E2E 文件和后端安全测试；先复现旧匿名断言失败。把匿名请求收敛为独立安全测试，使用真实 Spring 测试上下文的 H2/MockMvc 建立登录成功、CSRF、权限、服务器创建/查询/清理用例；统一测试 AI=8001、Knowledge=8002。运行全量 Python 与针对性 Maven，成功路径不得只靠 mock HTTP。
- [x] T2 语料版本与恢复：先用临时目录测试 corpus manifest 的确定性、损坏、遗漏、新增文件、路径逃逸和版本/哈希不匹配。实现 `knowledge/corpus_manifest.py` 与 `scripts/knowledge/corpus_manifest.py`，接入服务 readiness（配置 manifest 时强制核验）。以独立临时服务验证恢复，不重启正在使用的默认 8002。
- [x] T3 数据评测：建立 `data/evaluation/independent-v1` manifest 和人工待审核队列；在隔离临时 HTTP 服务采集真实故障/恢复观测，用 hash 保留原始证据；真实观测与 synthetic 回归明确分层。实现 `training/independent_benchmark.py` 与行为测试，拒绝未审核/候选派生/泄漏的 formal 指标，输出 regression 与 formal readiness 分开。更新训练就绪报告到本批目录，不覆盖历史报告。
- [x] T4 运行事件：设计 `docs/development/run-event-v1.schema.json`，共享 `request_id/task_id/run_id/step_id/event_id/status/timestamp`；先测试稳定关联和敏感字段过滤，再让 Python 执行器与 AI 响应/SSE 添加兼容事件元数据，前端保留关联 ID；Java 边界先规范并验证现有关联路径，避免创设第二审批源。
- [x] T5 浏览器黄金路径：使用现有 Playwright，在隔离本地 Web/API 实例上运行实际 Vue 与 SSE/parser；覆盖会话/问答/引用/中断/降级和权限拒绝。API double 与真实平台集成证据分别标记；保存 trace、截图与断言。真实服务路径仅在既有身份/环境可用时执行，不把 mockSession 当真实登录。
- [ ] T6 开源资料：修正采集脚本，固定 repo/commit 与 README/LICENSE hash；抓取日志、检索、Agent 评测数据集与观测项目，阅读数据许可/数据规模/适用性，形成 Markdown 登记。遇自动审批故障记录原始拒绝，继续本地任务；不绕过审批或更改全局配置。
- [ ] T7 局部 PoC：对比现有索引/版本化重建与 Qdrant 适配可行性，报告实际测量、依赖/维护/退出成本；OTel 先验证现有请求关联而后决定是否引入新运行依赖，未实际部署的组件明确未执行。
- [x] T8 合并验证与审阅：运行覆盖改动的 pytest/Node/typecheck/Java，独立只读审阅，生成精确差分/改后 ZIP/验证 JSON 与哈希保护回滚；只在副本演练，更新本批实施台账与待办。

## Commands and acceptance

Python: `python -m pytest -p no:cacheprovider tests ai-service/app/tests -q`；新增行为测试先红后绿，禁止通过将旧成功断言改成宽泛 200/401/403 集合来达标。

Frontend: `npm test`、`npm run typecheck`；Playwright 保存 `trace.zip`，report 中精确区分 API fixture/browser component 与真实平台集成。

Java: 使用项目已缓存 Maven/Java17 离线仓库与 test profile；测试进程不得连接日常 MySQL、发真实通知或执行主机命令。

Package: 从 `source-before.zip` 抽取逐文件精确前像；rollback 检查所有当前 hash 后才写入，任何后续修改阻止整批回滚。

## Execution status (2026-11-04)

T1–T5 implementation and scoped verification completed; T3 human approvals remain 0 and formal/fitness gates BLOCKED. T6 collector/tests/offline verification completed, new network acquisition blocked by approval model HTTP404. T7 corpus recovery PoC measured; Qdrant/OTel dependency deployment/comparison NOT EXECUTED (Qdrant unavailable, SDK absent, Docker image inspection exit1/cache unknown). T8 tests and independent review passed; package rehearsal evidence is recorded separately.

Full results and pending production integration: docs/development/产品质量优化实施记录-20261104.md. No real-service restart or database change.
