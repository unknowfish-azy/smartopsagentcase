# SmartOpsAgent 架构调整决策与执行顺序

日期：2026-10-17。依据当前源码静态核对；不把架构图中的「成熟」「已接通」当作运行验收证据。

## 决策

保留 Java 业务核心、Vue 双入口及现有 Python 研究/工具模块。当前不以语言替换作为性能优化方案，也不为了候选用途预先新增 C# 服务。优先让交付依赖、产品描述、运行链路和验收范围一致，再以测量决定并发、SQL、缓存或局部实现调整。

默认交付以 Java 受控运维和知识协同链路为中心；模型能力根据所选路径配置 Mini/Ollama 或外部模型。Python AI/知识服务单独标为可选能力，Python Agent 的产品接入状态单独验收。保留源码与测试，归档/移除需先核对部署、脚本、文档和测试引用，不凭主流程未发现引用直接删除。

## 已核对的证据

|观察|代码位置|结论边界|
|Spring Boot 3.3.5、Java 17|backend/pom.xml|确认构建配置，不代表已做 Java 21 兼容性验证|
|前端走 /api/assistant/*|frontend/src/api/assistant.js|聊天主入口指向 Java|
|Java 控制器调用 AssistantService|backend/src/main/java/com/smartops/controller/AssistantController.java|主链路不是直接调用 Python 8001|
|AssistantService 使用 MiniAssistantEngine 与模型连接服务|backend/src/main/java/com/smartops/service/AssistantService.java|Python mock 不控制这条模型链路|
|团队运行具有 approve/preview/execute 端点|backend/src/main/java/com/smartops/controller/TeamAgentRunController.java|受控审批执行已存在；不等于自主规划/重规划已闭环|
|会话注册表为 ConcurrentHashMap|backend/src/main/java/com/smartops/security/AccountSessionRegistry.java|不能据 Redis 配置宣称分布式会话已完成|
|SentenceTransformerEmbedding 调用 HashEmbedding|knowledge/embedding/sentence_transformer.py|当前该实现没有加载真实语义模型|
|HashEmbedding 逐 token SHA256、向量归一化|knowledge/embedding/hash_embedding.py|有 CPU 成本，需随输入规模测量；不是「没有计算量」|

本轮在 backend/src/main/java 与 frontend/src/api 的检索中未发现 8001/8002 或 AI_SERVICE_URL 直接调用证据。这支持把 Python 服务从默认前端聊天依赖中拆开，但不构成全仓废弃证明。源码文件检索未发现 C# 工程资产；不据此推断团队技能水平。

## 修正性能判断

- 「99% 等网络」「换语言收益近零」「C# 快 10–50 倍」「.NET 100MB/JVM 400MB」均不是本项目测量结论，不作为决策依据。
- Java 21 与虚拟线程作为独立实验：JDK、CI、启动脚本、依赖兼容、ThreadLocal、安全上下文、线程固定、SSH/WebSocket、调度器和回滚均需验证。Spring Boot 版本支持相关配置不等于全应用线程池自动切换。
- 虚拟线程不增加 MySQL 连接池容量，也不解决慢 SQL、LLM 延迟或 CPU 饱和；需有超时、并发上限与背压。
- ZGC 适合与暂停目标和内存预算一起评估，不默认优于当前 GC；缓存先明确一致性、失效策略和租户隔离。
- CPU 占用超过任意固定比例不是换语言门槛。门槛应是已测的 SLO 不达标、具体热点及同负载实验收益。
- C# 若用于新 worker/网关，选择届时仍受支持的 .NET LTS，并核实生命周期；不沿用材料中的 8/9 版本推荐作为长期决策。

## 执行批次与验收

### P0：交付边界与能力真实性

1. 默认安装链路：MySQL + Java + 双前端；Redis 按已启用功能与健康检查配置验收；Mini 及外部模型分别验收。
2. Python AI/知识/Agent、真实 SSH、Harbor、Prometheus/Loki 分别列配置条件、调用入口和验收结果。没有运行证据时标为「已实现，待集成验收」。
3. 功能名称和说明采用「受控运维平台、知识协同、本地/外部模型问答」。只有任务创建→规划→审批→执行→验证→持久化→前端展示全过程验证后，才宣称自主闭环。
4. 校验器区分 PASS / FAIL / SKIPPED / ERROR；未配置模型不应被统计成 AI 验证通过。具体修改前先找到实际运行判定入口及消费方，避免只改实验模块造成产品假象。

### P1：观测基线

对登录、列表分页/详情、聊天、SSH 工具执行分别记录负载、并发、p50/p95/p99、吞吐、错误率、CPU、RSS、GC、连接池等待、SQL 与模型耗时。真实 SSH 测试在约定测试主机进行。基线与候选变更使用同数据、同硬件、同热身条件。

先定位慢 SQL/外部请求/锁竞争，再选择索引、查询收敛、超时与限流。缓存、Java 21、虚拟线程、GC 各自单独实验，避免多变量同时变动。

### P2：Agent 接入

先选一个只读诊断闭环，约定任务 ID、traceId、状态机、幂等、取消、超时、证据与故障恢复。复用 Java 权限、审批和审计边界；变更操作保留人工审批。评估是在 Java 内实现编排，还是给 Python Agent 建受限 worker 接口；在决定前不新增部署进程。

验收至少覆盖拒绝审批、重复请求、超时、断线、重启恢复、跨用户访问和证据持久化；工具可调用不等于任务已验证成功。

### P3：可选 C# 局部试点

只有当明确热点、Windows 专有需求或团队维护能力使收益成立时再立项。采用独立服务，Java 保持用户认证与授权入口；内部身份、超时、重试幂等和审计另作契约，不简单复制 cookie/CSRF 或仅凭一个共享 Token 代替用户授权。通过相同负载对比和运维成本审查后才接入正式链路。

## 本轮交付范围

已调整架构决策与交接指南。未升级 JDK、切换 GC、添加 C#、归档 Python、修改执行权限、运行压测或声明真实外部系统验收通过。上述批次为后续实施顺序，不是已完成清单。
