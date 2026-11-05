export const knowledgeCandidateGuides = Object.freeze([
  Object.freeze({
    id: 'guide-k8s-service-endpoint',
    sourceRunId: 'DEMO-RUN-001',
    traceId: 'demo-trace-k8s-service',
    toolId: 'k8s.service.diagnose',
    title: '【演示】Kubernetes Service 无可用 Endpoint',
    summary: '演示如何依据 Service、Endpoint 与 Pod 标签证据形成可审核的故障知识。',
    status: 'PENDING_REVIEW',
    createdAt: '2026-09-27T00:00:00+08:00',
    isGuide: true,
    contentMarkdown: `# 演示知识候选：Kubernetes Service 无可用 Endpoint

> **演示数据说明：** 本记录仅用于界面引导，不来自真实集群，不写入数据库，不计入审核统计，也不能直接发布。

## 环境

- Kubernetes：演示集群
- Namespace：\`demo\`
- Service：\`web-service\`
- Deployment：\`web\`

## 故障现象

访问 \`web-service\` 超时，Service 已创建，但没有可用后端。

## 已确认事实

1. Service 存在，ClusterIP 已分配。
2. EndpointSlice 中没有可用地址。
3. Deployment 期望副本数为 2。

## 当前推测

Service Selector 与 Pod Label 可能不匹配。该判断仍需读取两侧标签后验证，不能直接当作根因。

## 待验证项

- Service 的 \`spec.selector\`
- Pod 的实际 Labels
- Pod Ready 状态及 Readiness Probe
- Service 的 \`targetPort\` 与容器监听端口

## 操作步骤

1. 查看 Service 配置和 Selector。
2. 查看 Endpoint 与 EndpointSlice。
3. 按 Service Selector 查询 Pod。
4. 对比 Pod Labels，并检查 Ready 状态。
5. 核对 Service Port、TargetPort 和容器监听端口。

## 操作命令

\`\`\`bash
kubectl get svc web-service -n demo -o yaml
kubectl get endpoints web-service -n demo
kubectl get endpointslice -n demo -l kubernetes.io/service-name=web-service
kubectl get pod -n demo --show-labels
kubectl describe pod -n demo -l app=web
\`\`\`

## 示例输出

\`\`\`text
NAME          ENDPOINTS   AGE
web-service   <none>      12m

Service selector: app=web
Pod labels:       app=web-v2
\`\`\`

## 报错原因分析

如果真实输出与示例一致，Service 使用 \`app=web\` 选择后端，而 Pod 标签为 \`app=web-v2\`，控制面无法为 Service 生成可用 Endpoint。只有完成标签比对后，才能把 Selector 不匹配确认为根因。

## 修复方案

根据期望的版本管理方式，选择修正 Service Selector 或 Deployment Pod Template Labels。修改前应确认是否会影响同 Namespace 下的其他工作负载。

## 修复后验证

\`\`\`bash
kubectl get endpoints web-service -n demo
kubectl get pod -n demo -l app=web
curl -v http://web-service.demo.svc.cluster.local/
\`\`\`

验证标准：Endpoint 出现 Ready 地址、目标 Pod 为 Ready、业务请求返回预期 HTTP 状态码。

## 风险与回滚

- 风险：错误修改 Selector 可能把流量转发到非目标 Pod。
- 回滚：恢复修改前的 Service Selector 或 Deployment 模板，并再次检查 Endpoint。
- 生产变更前必须保存原 YAML，并经过人工确认。

## 审核检查清单

- [ ] 事实、推测和待验证项已明确区分
- [ ] 命令中的 Namespace 与资源名已脱敏
- [ ] 组件版本与适用环境已补充
- [ ] 修复命令已在目标环境验证
- [ ] 风险、回滚和验证标准完整
`
  }),
  Object.freeze({
    id: 'guide-docker-container-exit',
    sourceRunId: 'DEMO-RUN-002',
    traceId: 'demo-trace-docker-exit',
    toolId: 'docker.container.diagnose',
    title: '【演示】Docker 容器启动后立即退出',
    summary: '演示如何结合容器状态、退出码和日志判断启动失败原因。',
    status: 'PENDING_REVIEW',
    createdAt: '2026-09-27T00:05:00+08:00',
    isGuide: true,
    contentMarkdown: `# 演示知识候选：Docker 容器启动后立即退出

> **演示数据说明：** 本记录仅用于界面引导，不来自真实主机，不写入数据库，不计入审核统计，也不能直接发布。

## 环境

- Docker：演示环境
- 容器：\`demo-api\`
- 镜像：\`demo/api:1.0\`

## 故障现象

执行 \`docker start demo-api\` 后，容器很快变为 \`Exited\`，应用端口无法访问。

## 已确认事实

1. 容器对象存在。
2. 容器当前状态为 Exited。
3. 示例退出码为 1。

## 当前推测

应用进程可能因配置文件缺失、环境变量错误或依赖服务不可达而退出。退出码 1 只能说明进程失败，不能单独证明具体根因。

## 待验证项

- 容器退出码与 OOMKilled 状态
- 容器 Entrypoint 和 Cmd
- 标准输出与标准错误
- 挂载文件、环境变量和依赖地址
- 宿主机磁盘与内存状态

## 操作步骤

1. 查看全部容器及退出状态。
2. 读取容器 State、配置和挂载信息。
3. 查看最近日志。
4. 检查镜像默认启动命令。
5. 根据日志验证配置、权限或依赖问题。

## 操作命令

\`\`\`bash
docker ps -a --filter name=demo-api
docker inspect demo-api --format '{{json .State}}'
docker inspect demo-api --format '{{json .Config}}'
docker logs --tail 200 demo-api
docker image inspect demo/api:1.0 --format '{{json .Config}}'
\`\`\`

## 示例输出

\`\`\`text
State: Exited (1)
Error: failed to load config /app/config/application.yml: no such file or directory
\`\`\`

## 报错原因分析

若真实日志明确显示配置文件不存在，并且 \`docker inspect\` 证明目标挂载未生效，则可以确认启动失败与配置挂载有关。若日志没有该证据，应继续检查权限、环境变量、端口冲突或依赖服务，不能照搬示例结论。

## 修复方案

检查宿主机源文件是否存在、挂载路径是否正确、容器运行用户是否有读取权限。修正容器编排配置后重新创建容器。

## 修复后验证

\`\`\`bash
docker ps --filter name=demo-api
docker logs --tail 50 demo-api
docker inspect demo-api --format '{{.State.Status}} {{.State.ExitCode}}'
curl -v http://127.0.0.1:8080/health
\`\`\`

验证标准：容器持续处于 running、退出码为 0、日志无重复启动错误、健康检查返回成功。

## 风险与回滚

- 风险：重新创建容器可能造成短暂服务中断。
- 风险：错误挂载可能覆盖镜像内原有目录。
- 回滚：恢复原编排文件和镜像版本，按原参数重新创建容器。
- 删除或替换生产容器前必须人工确认，并保存当前 inspect 信息。

## 审核检查清单

- [ ] 日志与退出码来自同一次运行
- [ ] 配置、路径和凭据已脱敏
- [ ] 原因结论有直接证据支撑
- [ ] 修复后执行了进程与业务双重验证
- [ ] 中断风险与回滚步骤完整
`
  }),
  Object.freeze({
    id: 'guide-nginx-502',
    sourceRunId: 'DEMO-RUN-003',
    traceId: 'demo-trace-nginx-502',
    toolId: 'nginx.upstream.diagnose',
    title: '【演示】Nginx 访问返回 502 Bad Gateway',
    summary: '演示如何从客户端、Nginx 代理层和上游应用三层证据定位 502 故障。',
    status: 'PENDING_REVIEW',
    createdAt: '2026-09-27T00:10:00+08:00',
    isGuide: true,
    contentMarkdown: `# 演示知识候选：Nginx 访问返回 502 Bad Gateway

> **演示数据说明：** 本记录仅用于人工审核操作引导，不来自真实生产环境，不写入数据库、不计入审核统计，也不能直接发布。

## 环境

- 入口：\`https://demo.example.com/api/\`
- Nginx：\`demo-gateway\`
- 上游：\`127.0.0.1:8080\`

## 故障现象

客户端访问接口返回 \`502 Bad Gateway\`。Nginx 进程处于运行状态，但这只能证明代理进程存在，不能证明上游应用可达。

## 已确认事实

1. 客户端已连接到 Nginx，并收到 HTTP 502。
2. Nginx 主进程正在运行。
3. 当前演示配置将请求代理到 \`127.0.0.1:8080\`。

## 当前推测

上游应用可能未监听目标端口，也可能存在代理地址错误、连接超时、协议不一致或上游提前断开连接。以上均为待验证假设。

## 待验证项

- 生效配置中的 \`proxy_pass\` 地址和协议
- 上游端口监听状态及本机连通性
- Nginx error log 的同一请求时间点错误
- 上游应用进程、健康检查和应用日志

## 操作步骤

1. 从客户端复现并记录状态码、响应头和时间。
2. 导出生效配置，确认请求命中了预期 server/location。
3. 查看相同时间点的 Nginx 错误日志。
4. 在代理节点直接访问上游地址并检查端口监听。
5. 根据证据判断是连接拒绝、超时、协议错误还是应用异常。

## 操作命令

\`\`\`bash
curl -vk https://demo.example.com/api/health
nginx -T
tail -n 200 /var/log/nginx/error.log
journalctl -u nginx --since "10 minutes ago"
ss -lntp | grep ':8080'
curl -v --max-time 5 http://127.0.0.1:8080/health
\`\`\`

## 示例输出

\`\`\`text
connect() failed (111: Connection refused) while connecting to upstream
upstream: "http://127.0.0.1:8080/health"
\`\`\`

## 报错原因分析

若错误日志明确显示 \`Connection refused\`，并且 \`ss\` 未发现 8080 监听，可确认 Nginx 已尝试连接上游，但目标端口没有接受连接。若显示 \`upstream timed out\`，应继续检查上游响应耗时、网络策略和超时配置，不能沿用“端口未监听”的结论。

## 修复方案

根据验证结果恢复上游应用，或修正 upstream/proxy_pass 的地址、端口与协议。修改前备份配置，执行 \`nginx -t\` 通过后再平滑 reload。

## 修复后验证

\`\`\`bash
nginx -t
systemctl reload nginx
curl -v http://127.0.0.1:8080/health
curl -vk https://demo.example.com/api/health
tail -n 50 /var/log/nginx/error.log
\`\`\`

验证标准：上游健康检查成功、Nginx 不再产生同类错误、客户端获得预期业务状态码。

## 风险与回滚

- reload 前必须通过语法检查，避免错误配置影响全部域名。
- 保存原配置；验证失败时恢复备份并再次执行 \`nginx -t\` 和 reload。
- 不应为掩盖慢上游而盲目扩大超时时间。

## 审核检查清单

- [ ] 已区分代理层事实与上游故障假设
- [ ] 配置、日志和命令中的域名与地址已脱敏
- [ ] 修复方案由错误日志和连通性证据支持
- [ ] 已完成客户端、代理层、上游三层验证
- [ ] 配置备份与回滚步骤完整
`
  }),
  Object.freeze({
    id: 'guide-mysql-too-many-connections',
    sourceRunId: 'DEMO-RUN-004',
    traceId: 'demo-trace-mysql-connections',
    toolId: 'mysql.connection.diagnose',
    title: '【演示】MySQL 出现 Too many connections',
    summary: '演示如何通过连接指标、会话列表和业务证据分析 MySQL 连接耗尽。',
    status: 'PENDING_REVIEW',
    createdAt: '2026-09-27T00:15:00+08:00',
    isGuide: true,
    contentMarkdown: `# 演示知识候选：MySQL 出现 Too many connections

> **演示数据说明：** 本记录为虚拟审核案例，不包含真实数据库账号、密码或生产连接信息，不进入数据库与正式发布流程。

## 环境

- MySQL：8.0 演示实例
- 业务：\`demo-order-service\`
- 告警：应用新建连接失败

## 故障现象

部分请求报错 \`Too many connections\`，已有连接可能仍能执行查询，新连接间歇性失败。

## 已确认事实

1. 应用日志出现 MySQL 1040 错误。
2. 当前演示实例配置了连接数上限。
3. 故障时需要将连接状态与错误发生时间对齐后才能判断原因。

## 当前推测

连接池泄漏、慢查询积压、突发流量、空闲连接过多或连接上限偏低都可能造成该现象。目前尚未确认其中任何一项为根因。

## 待验证项

- \`Threads_connected\` 与 \`max_connections\` 的实际值
- 活跃、Sleep 和长时间运行会话分布
- 应用连接池最大值、等待时间和释放逻辑
- 同期慢查询、请求量和数据库资源使用率

## 操作步骤

1. 保存故障时间点和应用错误样本。
2. 读取全局连接指标和配置上限。
3. 检查 processlist，识别长事务、慢查询和异常 Sleep 会话。
4. 对照所有应用实例的连接池总容量。
5. 根据证据处理泄漏、慢查询或容量问题，不直接盲目调大参数。

## 操作命令

\`\`\`sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW VARIABLES LIKE 'max_connections';
SHOW FULL PROCESSLIST;
SELECT USER, HOST, COMMAND, COUNT(*) AS sessions
FROM information_schema.PROCESSLIST
GROUP BY USER, HOST, COMMAND
ORDER BY sessions DESC;
\`\`\`

## 示例输出

\`\`\`text
Threads_connected   198
max_connections     200
Max_used_connections 200
\`\`\`

## 报错原因分析

上述指标只能确认连接使用接近上限。若 processlist 显示某应用来源存在大量长期 Sleep 会话，并与连接池配置对应，可进一步验证连接回收问题；若大量会话都在执行慢 SQL，则应优先分析查询与锁等待。不能仅凭 1040 错误认定数据库参数太小。

## 修复方案

优先修复连接泄漏、连接池配置、慢查询或流量异常。只有在数据库内存、线程开销和业务容量评估允许时，才考虑受控调整 \`max_connections\`，并同步限制各应用连接池总量。

## 修复后验证

\`\`\`sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Connection_errors_max_connections';
SHOW FULL PROCESSLIST;
\`\`\`

同时验证应用错误率、新建连接成功率、关键请求和持续观察期内的连接趋势。

## 风险与回滚

- 盲目增大连接上限可能导致内存压力、线程争用和更严重的雪崩。
- 终止会话可能回滚事务或中断业务，必须确认会话归属并获得授权。
- 参数变更前记录原值；异常时恢复原值并回滚应用连接池配置。

## 审核检查清单

- [ ] 未记录账号密码和连接串密钥
- [ ] 连接指标与故障时间一致
- [ ] 推测均有明确待验证证据
- [ ] 参数调整包含容量依据和回滚值
- [ ] 修复后覆盖数据库与业务双重验证
`
  }),
  Object.freeze({
    id: 'guide-linux-root-filesystem-full',
    sourceRunId: 'DEMO-RUN-005',
    traceId: 'demo-trace-linux-storage',
    toolId: 'linux.storage.diagnose',
    title: '【演示】Linux 根分区空间不足',
    summary: '演示如何区分磁盘块、inode 与已删除文件占用，并安全制定清理方案。',
    status: 'PENDING_REVIEW',
    createdAt: '2026-09-27T00:20:00+08:00',
    isGuide: true,
    contentMarkdown: `# 演示知识候选：Linux 根分区空间不足

> **演示数据说明：** 本记录仅展示审核与诊断写法，目录、容量和输出均为虚拟信息，不允许据此直接删除任何真实文件。

## 环境

- Linux：演示服务器
- 文件系统：\`/dev/mapper/demo-root\`
- 挂载点：\`/\`

## 故障现象

应用写日志失败并提示 \`No space left on device\`，根分区使用率告警达到 98%。

## 已确认事实

1. 根分区数据块使用率接近容量上限。
2. 报错发生在向根分区写入文件时。
3. 尚未确认具体目录或文件为根因。

## 当前推测

日志增长、缓存堆积、大文件、inode 耗尽，或文件已删除但仍被进程打开，都可能造成空间异常，需要分别验证。

## 待验证项

- 数据块与 inode 的使用率
- 同一文件系统下各一级目录占用
- 最近增长的大文件和日志轮转状态
- 已删除但仍由进程持有的文件
- 容器运行时、临时目录和日志目录占用

## 操作步骤

1. 确认满载的文件系统、类型和挂载点。
2. 单独检查 inode，避免把 inode 耗尽误判为空间不足。
3. 使用只读命令逐层定位大目录和大文件。
4. 检查已删除文件占用与日志轮转。
5. 与文件所有者确认保留策略、备份和清理范围后再实施变更。

## 操作命令

\`\`\`bash
df -hT /
df -i /
du -xhd1 / 2>/dev/null | sort -h
du -xhd1 /var 2>/dev/null | sort -h
find /var -xdev -type f -size +1G -printf '%s %p\\n' 2>/dev/null | sort -n
lsof +L1 2>/dev/null
journalctl --disk-usage
\`\`\`

## 示例输出

\`\`\`text
/dev/mapper/demo-root  xfs  50G  49G  1G  98% /
/var/log                         21G
\`\`\`

## 报错原因分析

若 \`df -h\` 满而 \`df -i\` 正常，说明主要是数据块容量问题；若 inode 为 100%，即使仍有容量也无法新建文件。若 \`du\` 汇总明显小于 \`df\`，应检查已删除但仍打开的文件、挂载覆盖或文件系统保留空间。示例中的 \`/var/log\` 较大仍需继续定位，不能直接等同于根因。

## 修复方案

依据保留策略轮转、归档或迁移可确认的日志和缓存；修复异常写入源；必要时对文件系统扩容。任何删除动作都必须先确认文件用途、备份要求和业务影响，禁止使用未经审查的 \`rm -rf\` 批量清理。

## 修复后验证

\`\`\`bash
df -hT /
df -i /
du -xhd1 /var 2>/dev/null | sort -h
systemctl --failed
journalctl -p err --since "10 minutes ago"
\`\`\`

验证磁盘空间、inode、受影响服务状态、日志写入和业务请求均恢复正常，并持续观察空间是否再次快速增长。

## 风险与回滚

- 误删日志、数据库文件或应用数据可能不可恢复。
- 清理前建立文件清单并备份；可恢复文件优先移动到隔离目录后观察。
- 服务重启以释放已删除文件句柄会造成中断，必须走变更确认流程。

## 审核检查清单

- [ ] 已区分数据块、inode 和打开文件占用
- [ ] 定位命令保持只读
- [ ] 未提供无范围限制的危险删除命令
- [ ] 清理对象有所有者、保留策略和备份依据
- [ ] 修复后验证覆盖系统、服务与业务
`
  }),
  Object.freeze({
    id: 'guide-k8s-ingress-tls-mismatch',
    sourceRunId: 'DEMO-RUN-006',
    traceId: 'demo-trace-ingress-tls',
    toolId: 'k8s.ingress.tls.diagnose',
    title: '【演示】Kubernetes Ingress HTTPS 证书不匹配',
    summary: '演示如何沿 DNS、入口、Ingress、TLS Secret 与证书 SAN 建立 HTTPS 诊断证据链。',
    status: 'PENDING_REVIEW',
    createdAt: '2026-09-27T00:25:00+08:00',
    isGuide: true,
    contentMarkdown: `# 演示知识候选：Kubernetes Ingress HTTPS 证书不匹配

> **演示数据说明：** 本记录为虚拟审核资料，域名、集群和证书均为演示信息，不读取或保存真实私钥，不进入正式知识发布流程。

## 环境

- 域名：\`app.demo.example.com\`
- Namespace：\`demo\`
- Ingress：\`demo-app\`
- TLS Secret：\`demo-app-tls\`

## 故障现象

浏览器提示证书名称与访问域名不匹配，HTTPS 连接无法通过客户端信任校验。

## 已确认事实

1. DNS 能返回入口地址。
2. 客户端连接到了 443 端口并收到一张证书。
3. 客户端报告该证书不覆盖访问域名。

## 当前推测

Ingress TLS host 配置错误、Secret 位于错误 Namespace、证书 SAN 不包含域名、Controller 未加载 Secret，或请求到达了错误入口，都可能导致该现象。

## 待验证项

- DNS 解析地址与 Ingress Controller 入口地址
- Ingress rule host、tls.hosts 和 secretName
- Secret 是否与 Ingress 同 Namespace，类型是否正确
- 服务端实际返回证书的 Subject、Issuer、SAN 与有效期
- Controller 事件和日志中的证书加载错误

## 操作步骤

1. 核对 DNS 和实际连接入口。
2. 查看 IngressClass、Host、TLS 和后端配置。
3. 检查 Secret 元数据，不在终端输出私钥内容。
4. 使用 SNI 获取服务器实际返回的证书并检查 SAN。
5. 对照 Controller 日志，确认配置是否已加载。

## 操作命令

\`\`\`bash
getent hosts app.demo.example.com
kubectl get ingress demo-app -n demo -o yaml
kubectl describe ingress demo-app -n demo
kubectl get secret demo-app-tls -n demo
kubectl get secret demo-app-tls -n demo -o jsonpath='{.type}{"\\n"}'
openssl s_client -connect app.demo.example.com:443 -servername app.demo.example.com -showcerts </dev/null
curl -vk https://app.demo.example.com/health
\`\`\`

## 示例输出

\`\`\`text
X509v3 Subject Alternative Name:
    DNS:old.demo.example.com
requested host: app.demo.example.com
\`\`\`

## 报错原因分析

如果通过正确入口和 SNI 获取的证书 SAN 只包含旧域名，可确认“实际返回证书不覆盖目标域名”。仍需结合 Ingress 与 Secret 检查，确定是 Secret 本身错误、Ingress 引用了错误 Secret，还是 Controller 返回默认证书。\`curl -k\` 仅跳过客户端验证用于诊断，不能修复证书问题。

## 修复方案

签发或选择覆盖目标域名且证书链完整的证书，在同一 Namespace 创建受控 TLS Secret，并修正 Ingress 的 tls.hosts/secretName。未经确认不得替换生产 Secret，也不得在日志、工单或知识正文中暴露私钥。

## 修复后验证

\`\`\`bash
kubectl describe ingress demo-app -n demo
openssl s_client -connect app.demo.example.com:443 -servername app.demo.example.com -verify_return_error </dev/null
curl -v https://app.demo.example.com/health
\`\`\`

使用可信客户端验证证书链、SAN、有效期、SNI 域名和 HTTPS 业务响应；正式验收不使用 \`-k\`。

## 风险与回滚

- 错误替换 TLS Secret 可能影响同域名或共享证书的全部流量。
- 变更前记录 Ingress 与 Secret 元数据，并安全备份原证书材料。
- 验证失败时恢复原 secretName 或原 Secret 版本，再确认 Controller 已重新加载。

## 审核检查清单

- [ ] DNS、入口 IP、Ingress Host、Secret 与 SAN 证据链完整
- [ ] 未输出或保存 TLS 私钥
- [ ] 已区分证书不匹配与客户端不信任
- [ ] \`curl -k\` 明确限定为诊断用途
- [ ] 生产 Secret 变更包含确认、验证和回滚步骤
`
  }),
  Object.freeze({
    id: 'guide-k8s-image-pull', sourceRunId: 'DEMO-RUN-007', traceId: 'demo-trace-image-pull',
    toolId: 'k8s.image.pull.diagnose', title: '【演示】Kubernetes Pod 镜像拉取失败',
    summary: '依据 Pod 事件、镜像地址和节点运行时证据区分权限、网络、标签与仓库故障。',
    status: 'PENDING_REVIEW', createdAt: '2026-09-27T00:30:00+08:00', isGuide: true,
    contentMarkdown: `# 演示知识候选：Kubernetes Pod 镜像拉取失败

> **演示数据说明：** 本记录仅用于人工审核练习，集群、镜像和输出均为虚构，不写入数据库，不计入待审核统计，不能直接发布。

## 环境

- Namespace：\`demo\`
- Pod：\`api-7c9b\`
- 镜像：\`registry.demo.example.com/team/api:2.1\`

## 故障现象

Pod 状态显示 \`ImagePullBackOff\`，业务副本数不足。

## 已确认事实

1. Pod 已调度到节点，但目标容器尚未启动。
2. 事件显示镜像拉取失败并进入退避重试。
3. 业务访问受影响的范围尚需结合可用副本和 Service Endpoint 确认。

## 当前推测

镜像仓库认证失败、镜像标签不存在、节点到仓库网络异常、证书不受信任或拉取限流都可能导致该状态。\`ImagePullBackOff\` 本身不是根因。

## 待验证项

- Pod 事件中的原始错误码和仓库响应
- Deployment 中的完整镜像地址与标签
- imagePullSecrets 的名称、Namespace 和 ServiceAccount 引用
- 故障节点的 Containerd 网络、DNS、证书和仓库可用性

## 操作步骤

1. 查看 Pod 状态、所在节点及最近事件。
2. 对比工作负载模板中的镜像地址与仓库实际标签。
3. 核查拉取凭据是否被 Pod 引用，只读取 Secret 元数据，不输出凭据内容。
4. 在受影响节点收集 Containerd 错误日志，并和事件时间对齐。
5. 按错误类型选择认证、镜像标签、网络或证书方向继续验证。

## 操作命令

\`\`\`bash
kubectl get pod api-7c9b -n demo -o wide
kubectl describe pod api-7c9b -n demo
kubectl get events -n demo --field-selector involvedObject.name=api-7c9b --sort-by=.lastTimestamp
kubectl get deployment api -n demo -o yaml
kubectl get serviceaccount default -n demo -o yaml
kubectl get secret -n demo
journalctl -u containerd --since "15 minutes ago"
\`\`\`

## 示例输出

\`\`\`text
Failed to pull image "registry.demo.example.com/team/api:2.1": unauthorized: authentication required
Back-off pulling image "registry.demo.example.com/team/api:2.1"
\`\`\`

## 报错原因分析

如果真实事件明确返回 \`unauthorized\`，应检查仓库权限、凭据有效期及 imagePullSecrets 引用；但仍不能仅凭示例断定是 Secret 错误。若返回 \`manifest unknown\`，优先核对仓库路径和标签；若为连接超时或证书错误，则继续检查节点侧网络与信任链。

## 修复方案

基于已确认错误修正镜像标签、仓库授权或节点到仓库的连接。生产凭据轮换及 Deployment 变更必须经过授权，禁止把仓库密码写入命令、日志或知识正文。

## 修复后验证

\`\`\`bash
kubectl get pod -n demo -l app=api -o wide
kubectl describe pod api-7c9b -n demo
kubectl get deployment api -n demo
kubectl get endpoints api -n demo
\`\`\`

确认 Pod Ready、Deployment 可用副本恢复、Service 有可用 Endpoint，并完成业务健康请求。

## 风险与回滚

- 修改镜像标签可能部署错误版本；修改拉取凭据可能影响同 Namespace 其他工作负载。
- 变更前记录 Deployment 模板和 Secret 引用；失败时恢复原镜像与原引用。
- 不直接删除生产 Pod 或覆盖生产 Secret 来试错。

## 审核检查清单

- [ ] 事件错误与结论对应，未把状态名当作根因
- [ ] 镜像地址、凭据和节点信息已脱敏
- [ ] 命令只读，变更操作要求人工确认
- [ ] 验证覆盖 Pod、Deployment、Endpoint 与业务
- [ ] 回滚对象和原值明确
`
  }),
  Object.freeze({
    id: 'guide-mysql-replication-lag', sourceRunId: 'DEMO-RUN-008', traceId: 'demo-trace-mysql-replication',
    toolId: 'mysql.replication.diagnose', title: '【演示】MySQL 从库复制延迟持续升高',
    summary: '演示区分复制线程状态、事务堆积、网络和从库资源瓶颈，避免盲目跳过事务。',
    status: 'PENDING_REVIEW', createdAt: '2026-09-27T00:35:00+08:00', isGuide: true,
    contentMarkdown: `# 演示知识候选：MySQL 从库复制延迟持续升高

> **演示数据说明：** 本记录仅用于人工审核引导，实例、账号和指标均为虚构，不写入数据库、不计入统计，也不能直接发布。

## 环境

- MySQL：8.0 演示主从环境
- 复制方式：异步复制
- 业务：只读查询与报表

## 故障现象

只读实例查询结果晚于主库，监控显示复制延迟从数秒上升到数分钟。

## 已确认事实

1. 监控报告从库追赶落后。
2. 演示时间点的 \`Seconds_Behind_Source\` 高于平时基线。
3. 还没有证据证明 SQL 线程、IO 线程或主库写入是唯一原因。

## 当前推测

大事务、慢 SQL、锁等待、从库磁盘压力、网络延迟、复制线程错误或主库写入突增均可能造成延迟。

## 待验证项

- 复制 IO/SQL 线程状态及 Last_IO_Error、Last_SQL_Error
- Relay log 堆积、GTID 进度与主库写入速率
- 从库 CPU、磁盘吞吐、锁等待及慢查询
- 延迟指标是否为 NULL 或受线程停止影响

## 操作步骤

1. 记录监控时间窗和业务读写不一致样本。
2. 查看复制状态及线程错误，避免只看一个延迟数值。
3. 对比主从 GTID 进度和 relay log 应用速度。
4. 检查从库资源、长事务和锁等待。
5. 将推测与数据库日志、事务及资源指标交叉验证后再决定修复动作。

## 操作命令

\`\`\`sql
SHOW REPLICA STATUS\\G
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW FULL PROCESSLIST;
SELECT * FROM performance_schema.replication_applier_status_by_worker;
SELECT * FROM performance_schema.replication_connection_status;
\`\`\`

\`\`\`bash
df -hT
vmstat 1 5
iostat -xz 1 5
\`\`\`

## 示例输出

\`\`\`text
Replica_IO_Running: Yes
Replica_SQL_Running: Yes
Seconds_Behind_Source: 420
Last_SQL_Error:
\`\`\`

## 报错原因分析

上述输出仅说明复制线程仍运行且当前存在延迟，不足以断言是网络、慢 SQL 或磁盘问题。若 worker 状态显示长时间应用同一事务，并与磁盘繁忙时间对应，可以进一步验证从库应用瓶颈；若 SQL 线程为 No，应优先读取具体错误。\`Seconds_Behind_Source\` 为 NULL 时不能当作零延迟。

## 修复方案

按证据处理慢事务、锁等待、资源瓶颈或网络故障；评估读流量降级、主库回源或暂停强一致场景的从库读取。不得未经确认执行跳过事务、重置复制或重建从库。

## 修复后验证

\`\`\`sql
SHOW REPLICA STATUS\\G
SELECT * FROM performance_schema.replication_applier_status_by_worker;
\`\`\`

持续观察延迟回落到基线、线程无错误、GTID 进度追平，并用可追踪业务数据核对主从读取结果。

## 风险与回滚

- 跳过复制事务可能造成永久数据不一致，禁止将其作为默认修复。
- 调整并行复制、读路由或资源配额前记录原值并评估业务一致性要求。
- 变更失败时恢复原参数与读路由，核对数据一致性和复制状态。

## 审核检查清单

- [ ] 延迟指标、线程状态与日志时间窗一致
- [ ] 已区分事实、推测和待验证证据
- [ ] 命令没有输出密码或敏感业务数据
- [ ] 修复方案不含未经确认的跳事务操作
- [ ] 验证包含复制指标和业务数据一致性
`
  })
])

export function reviewQueueWithGuide(page = {}) {
  const items = Array.isArray(page.items) ? page.items : []

  if (items.length > 0 || Number(page.total) > 0) {
    return { ...page, items, guideMode: false }
  }

  return { ...page, items: knowledgeCandidateGuides, total: 0, guideMode: true }
}
