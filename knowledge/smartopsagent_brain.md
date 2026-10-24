# SmartOpsAgent 企业级运维智能体知识规范

版本：1.0
状态：知识源，默认只读
适用范围：个人运维学习、故障分析、题库训练、Runbook 查阅

## 1. 产品定位

SmartOpsAgent 不是普通聊天机器人，而是面向运维工程师的智能工作台。它把知识查阅、题目练习、错因分析、Runbook、Incident 和安全操作建议放在同一个闭环中。

目标是让用户在生产问题中知道：先看什么、不要先做什么、需要什么证据、如何缩小范围、如何验证恢复、什么时候回滚或升级。

## 2. 核心闭环

```text
Observe
  -> Detect
  -> Collect Evidence
  -> Analyze
  -> Ask Questions
  -> Search Knowledge
  -> Generate Solution
  -> Human Approval
  -> Execute
  -> Verify
  -> Record Experience
  -> Improve Knowledge
```

默认原则：只观察、只分析、只建议。任何生产变更、重启、删除、扩容、回滚或远程命令都必须先展示目的、风险、预期结果和回滚方式，再等待人工审批。

## 3. 三类角色

### Spider Sentinel

视觉运维哨兵。接收用户主动提供的屏幕、窗口或截图，使用 OCR 和界面识别发现错误提示、异常状态、卡住页面或告警区域。输出 `VisionEvent`，包括时间、来源、识别文本、位置、置信度和分类。禁止后台偷偷截图或访问未授权数据。

### Jellyfish AI Assistant

智能询问与分析助手。先收集环境、影响范围、发生时间、最近变更和已有证据，再给出分层排查路径。不能用猜测代替日志、指标、配置和时间线。

### Knowledge Brain

运维知识大脑。管理知识条目、故障案例、命令说明、Runbook、题目、错题原因和个人经验。每条知识都应能被搜索、查阅、关联和复习。

## 4. 知识条目标准

每条知识建议包含：

- `id`：稳定唯一标识
- `title`：中文标题
- `category`：Linux、MySQL、Nginx、Docker、Kubernetes 等
- `technology`、`platform`、`version`
- `summary`：一段易读摘要
- `symptoms`：现象
- `impact`：影响范围
- `evidence`：需要收集的证据
- `diagnosis`：排查顺序
- `solution`：低风险处理方案
- `rollback`：回滚条件和步骤
- `verification`：恢复验证
- `risk_level`：READ_ONLY、LOW、MEDIUM、HIGH
- `related_questions`、`related_runbooks`、`related_incidents`
- `tags`、`source`、`updated_at`

知识页面优先展示事实、证据和操作边界；原始知识不可被用户笔记覆盖，笔记应作为独立的经验层保存。

## 5. Linux 故障知识

### CPU 高使用率

现象：系统响应慢、请求延迟升高、load 增长。

证据：先看 `top` 或 `htop`，再用 `ps aux --sort=-%cpu` 定位进程；结合 `iostat` 区分 CPU 计算压力与 IO 等待；对比监控时间线、发布记录和流量变化。

常见原因：死循环、流量突增、恶意进程、线程争用、磁盘 IO 等待被误判为 CPU 问题。

风险：没有确认进程归属、影响范围和替代方案前，不要直接 `kill -9` 或重启主机。

验证：CPU 和 load 回落，业务延迟恢复，错误率没有扩大，并记录处置前后的指标。

### 磁盘或 inode 用尽

证据：`df -h` 查看容量，`df -i` 查看 inode，`du -xhd1` 定位目录；检查日志增长、容器层、已删除但仍被进程打开的文件和挂载点。

处理：先归档或轮转可识别日志，确认文件路径和保留策略后再清理；必要时扩容或迁移数据。

风险：禁止对未知路径执行 `rm -rf`，禁止直接删除数据库文件或正在写入的日志。清理后必须验证服务、容量、inode 和告警恢复。

## 6. MySQL 故障知识

### Too Many Connections

现象：应用报连接数耗尽、连接超时或新请求失败。

证据：执行只读查询 `SHOW PROCESSLIST`，查看 `Threads_connected`、`Threads_running`、`max_connections`，同时检查连接池上限、长事务、慢查询、连接泄漏和数据库资源压力。

判断：连接数高不等于数据库 CPU 高。需要区分大量空闲连接、请求堆积、锁等待、慢 SQL 和应用连接池配置。

处理：先限制异常流量或修复连接泄漏，优化慢请求和连接池；只有在确认内存、线程和连接模型后，才评估调整 `max_connections`。

风险：盲目提高连接上限可能放大内存压力并导致数据库整体不可用。调整前必须备份配置、说明回滚值并设置验证窗口。

### 慢 SQL 与死锁

慢 SQL 使用慢查询日志、`EXPLAIN` 和执行时间线定位；死锁优先查看 `SHOW ENGINE INNODB STATUS`、事务顺序和锁范围。优化方向包括索引、SQL 重写、缩小事务、统一加锁顺序和降低热点争用。

## 7. Nginx 故障知识

### 502 Bad Gateway

502 表示网关没有得到有效的上游响应，不等于 Nginx 本身损坏。排查顺序：确认影响范围和最近发布；查看 `error.log` 和 `access.log`；检查 upstream 地址和监听端口；用 `curl` 直接访问后端；再检查容器、服务健康、DNS 和网络策略。

如果日志出现 `connect() failed (111: Connection refused)`，优先验证后端进程、监听地址、容器网络和发布变更。不要第一步重启 Nginx，因为这可能丢失现场、造成短暂中断且无法修复根因。

### 504 Gateway Timeout

504 通常说明上游响应超时。需要比较 Nginx timeout、后端处理时间、数据库耗时、线程池和网络延迟。提高 timeout 只能缓解症状，不能替代性能定位。

## 8. Docker 与 Kubernetes

### 容器退出

先执行 `docker ps -a`、`docker logs`、`docker inspect`，确认退出码、启动参数、环境变量、挂载、依赖和资源限制。容器处于 Up 不代表业务 Ready，必须结合健康检查和真实请求验证。

### CrashLoopBackOff

先用 `kubectl describe pod` 查看事件、探针和调度信息，再用 `kubectl logs --previous` 查看上一次容器日志；检查配置、Secret、依赖服务、端口、启动命令和最近发布。不要只重复删除 Pod，应确认 Deployment 的期望状态、变更版本和恢复验证。

### OOMKilled 与 Pending

OOMKilled 要对比容器限制、工作集、节点压力和应用内存增长；Pending 要查看调度事件、资源请求、节点污点、亲和性、PVC 和镜像拉取条件。每次调整资源都要记录变更、风险和回滚。

## 9. 监控、日志与 Incident

指标、日志、链路、变更记录和用户报告应放在同一时间线上。告警流程：确认告警 -> 判断影响 -> 收集证据 -> 建立假设 -> 选择低风险验证 -> 修复或回滚 -> 验证恢复 -> 复盘。

Incident 至少记录：`incident_id`、严重度、影响、开始时间、时间线、证据、假设、根因、处置、恢复验证、预防措施和关联 Runbook。P1/P2 事件应明确升级对象和沟通节奏。

## 10. Runbook 标准

每个 Runbook 包含：目的、适用环境、前置检查、症状、证据、只读检查命令、决策分支、修复步骤、风险、审批点、回滚、验证、升级条件和复盘链接。

命令必须标注版本依赖、是否只读以及潜在影响。Runbook 是指导文档，不代表系统会自动执行其中命令。

## 11. 题库与错题学习

题库训练的不只是记忆，还包括命令理解、日志分析、诊断顺序、风险判断和生产事故决策。题目可关联知识点、Runbook、Incident 和命令。

错题记录至少保存：用户答案、正确答案、错误原因、知识薄弱点、置信度、用时、复习次数、下次复习时间和掌握度。错误原因可分为概念误解、命令混淆、配置误解、诊断路径错误、风险判断错误、记忆错误、粗心、猜测和未知。

复习采用间隔重复：首次答错尽快复习，重复错误缩短间隔，连续正确逐渐拉长间隔。答对但低置信度或耗时异常的题目也应进入复习队列。

## 12. AI 检索与回答规则

搜索支持关键词、标签、分类、服务、平台、版本和语义检索。回答顺序：

1. 已知事实与影响范围
2. 需要补充的证据
3. 可能原因及置信度
4. 低风险排查路径
5. 处理方案、风险和回滚
6. 验证标准与升级条件

引用知识时保留来源和版本。知识不足时要明确说明未知，不编造日志、指标、命令结果或生产状态。

## 13. 安全与远程操作

默认不执行生产操作，不自动修改数据库、不删除日志、不关闭防火墙、不使用 `chmod 777`、不盲目重启服务。远程操作必须经过命令预览、目的说明、风险分级、用户审批、执行记录和结果验证；删除、停机、回滚、扩容等高风险动作需要二次确认。

## 14. 本地运行库

本地数据可保存到用户配置的目录，默认包含 `logs/`、`screenshots/`、`reports/`、`knowledge/`、`history/`、`database/` 和 `backup/`。真实日志生成知识前必须脱敏 IP、主机名、账号、密码、Token、域名、内部 URL、数据库名和个人数据，除非用户明确允许。

## 15. 知识增长闭环

```text
Knowledge -> Question -> Answer -> Wrong Analysis -> Runbook -> Incident
          -> Practice -> Mastery -> Production Readiness -> Knowledge Update
```

所有 AI 生成内容默认是 `DRAFT` 或 `REVIEW_REQUIRED`，只有人工审核后才能进入正式题库或正式 Runbook。
