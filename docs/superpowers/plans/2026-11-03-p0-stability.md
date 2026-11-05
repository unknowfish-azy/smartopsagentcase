# P0 稳定性第二批实施计划

**目标：** 阻断未核验执行被汇总 PASS，明确规则规划的服务目标，识别知识索引未就绪与重复监听。

**范围与授权：** 按既有体检报告第二批顺序执行；用户已要求继续并授权先备份后整改。保持当前工作区的其他修改。每批以逐文件快照为比较基线，不重置 Git。

**约束：** 保留现有 PASS/WARN/VIOLATION/REJECTED 枚举；本轮未核验用 WARN + requires_human。诊断性描述没有执行验证请求时仍可正常 PASS。规划仅支持现有 nginx/mysql/redis，歧义、否定和未知目标走知识查询。知识接口区分 liveness 与 readiness；不改变数据库。运行中的旧实例切换先核对 PID、模块、绑定与空索引状态。

## Task 1：执行验证汇总

Files：`agent/inspector/pipeline.py`、`tests/inspector/test_verification_gate.py`。

- [x] 新增无状态、空/无效探针、未知结论+异常探针、已验证健康、原有策略违规优先级的行为测试。
- [x] 首次运行新增测试，保存失败输出。
- [x] 明确 verification_result.required/status；执行验证待定时添加 VERIFICATION/WARNING，并要求复核；不覆盖更高严重度违规。
- [x] 运行完整 inspector 与 AI 回归，冻结评测样本不变。

## Task 2：规划服务目标

Files：`agent/planner/planner.py`、`tests/agent/test_planner_targets.py`。

- [x] 表驱动测试 nginx/mysql/redis，中英文、大小写、明确 service 后缀；未知/多目标/否定/额外命令不得生成写操作。
- [x] 首次运行复现 mysql 被绑定 nginx。
- [x] 只识别完整且单一的受支持操作，action 与 arguments.service 一致；模糊请求回到知识检索。
- [x] 验证状态查询不产生重启计划，重启计划仍标记 requires_approval。

## Task 3：Knowledge readiness 与启动边界

Files：`knowledge/server.py`、`tests/knowledge/test_server_readiness.py`、`scripts/windows/service-readiness.ps1`、`scripts/windows/start-all.ps1`、`scripts/windows/status-local.ps1`、`tests/scripts/test_startup_readiness.py`、Windows README。

- [x] 测试空索引 HTTP 503、有效索引 200、手动摄入后动态 ready、种子目录缺失/禁用/空目录/有效语料摘要。
- [x] 增加 /api/ready，health 继续提供进程存活；暴露语料摘要和实例标识，不暴露本机绝对目录。
- [x] 新增纯函数 PowerShell 就绪库，对真实本地临时 HTTP 服务测试 legacy/空索引/错误服务/有效索引；不直接执行完整启动脚本作为测试。
- [x] start-all 避免重复占用，后台隐藏窗口、日志落盘，Knowledge 按 ready+chunks 判断；状态脚本展示所有监听地址及 Knowledge readiness。
- [x] 先记录现有双监听与两个实例的索引差异，再验证目标端口刷新；若系统权限阻断，只报告已执行部分，保留可运行的启动/诊断工具，不强杀未知进程。

## Task 4：审阅、验证与交付

- [x] 运行 `python -m pytest -p no:cacheprovider tests/inspector tests/agent tests/knowledge tests/scripts ai-service/app/tests -q`。
- [x] 运行冻结假成功评测并保存本批输出；检查 PowerShell 5.1 语法及受控 HTTP 行为。
- [x] 独立只读审阅本批快照增量，处理实质问题。
- [x] 更新 `docs/development/P0稳定性整改-20261103.md` 与 CODEX 比较记录，附未解决事项与证据。
- [x] 生成改后包、差分、验证记录、哈希保护回滚脚本；在临时副本演练恢复与冲突保护。

备份目录由 `.runtime/p0-stability-current.txt` 指向。数据库、依赖框架、前端页面布局和线上权限模型不在本批变更范围。现有 PolicyEngine 将 requires_approval 标记当作批准的风险会单独记录；本批不宣称已经完成真实审批执行闭环。

## 执行结果与范围补充

相关测试162通过，全量Python201通过/16项既有失败/7跳过。审阅后扩展修改StateVerifier分类、AI Chat标志透传及其行为回归，前像从本批原始源码快照取回。PowerShell5.1仅解析语法，运行测试在PS7；没有修改执行策略。Knowledge临时18002 readiness和真实RAG成功且已停止；默认8002旧实例的停止被OS与审批服务模型404阻断，运行切换未完成。详情见P0稳定性整改记录及verification.json。
