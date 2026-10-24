// Kubernetes Ingress, controller, TLS and edge-routing reference pack.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: `kubernetes.ingress.${id}`,
  domain: 'linux', platform: 'Linux / Kubernetes', service: 'kubernetes',
  type: 'KUBERNETES INGRESS AND EDGE ROUTING', title, section, summary, content,
  tags: ['Kubernetes', 'Ingress', ...tags], source: 'User-provided Kubernetes Ingress, TLS and Traefik material',
  version: 'Reference pack', risk, executionAllowed: false
})

export const kubernetesIngressEntries = [
  entry('model', 'Ingress 与 Ingress Controller 职责', '41 / Ingress 基础', 'Ingress 描述 HTTP/HTTPS 路由规则，Ingress Controller 读取并实际执行这些规则。',
    '[SRC] Ingress 表达 Host、Path、Backend Service、Port 和 TLS；Controller 才负责监听入口、同步规则并转发请求。\n[OPS] 诊断域名访问时沿 DNS/hosts -> Controller -> Ingress -> Service -> Endpoint/EndpointSlice -> Pod -> Application 检查，不要把 Ingress 对象存在等同于流量可用。\n[VERIFY] 检查 kubectl get/describe ingress、IngressClass、Controller Pod/Service、日志和后端 Service。',
    ['Ingress', 'Ingress Controller', 'IngressClass', 'HTTP', 'HTTPS']),
  entry('routing', 'Host 与 Path 七层路由', '42 / 域名路由', 'Ingress 可以按域名 Host 和请求路径 Path 将流量路由到不同 Service。',
    '[SRC] rules.host 与 http.paths 定义域名和路径匹配，pathType 常见 Prefix；请求 Host/Path 必须与规则匹配。直接访问入口 IP 可能因 Host 不一致而无法命中。\n[OPS] 对比实际请求 Host、Path、Ingress host/path/pathType、Backend Service 名称和端口；多文档 YAML 的 --- 需要逐文档解析。\n[VERIFY] 使用 kubectl describe ingress 和 curl -v -H/目标 URL 验证实际匹配结果。',
    ['host', 'path', 'pathType', 'Prefix', 'domain', 'routing']),
  entry('service-chain', 'Ingress 到 Service 的后端链路', '43 / 后端链路', 'Ingress 通常连接 ClusterIP Service，再由 Selector 和 EndpointSlice 找到 Ready Pod。',
    '[SRC] 推荐链路为 Client -> Ingress Controller -> Ingress Rule -> ClusterIP Service -> Endpoint/EndpointSlice -> Pod；Ingress backend port 必须存在于 Service，Service targetPort 还要对应应用实际监听端口。\n[OPS] Ingress 后端不存在、Service 端口错误、Selector 无匹配或 Endpoint 为空时分别定位，不要只看 Controller Pod。\n[VERIFY] 检查 get/describe svc、get endpoints/endpointslices、Pod labels/Ready、实际监听端口和业务请求。',
    ['Service', 'ClusterIP', 'Endpoint', 'EndpointSlice', 'targetPort', 'Pod']),
  entry('controllers', 'ingress-nginx、NGINX、Traefik 与其他 Controller', '44 / Controller 选型', 'ingress-nginx、NGINX Ingress Controller、Traefik、HAProxy、Istio、Kong 属于不同 Controller 体系，不能仅凭名称混同。',
    '[SRC] Controller 选择应结合 L4/L7 协议、动态配置、TLS、认证、WAF、监控、Canary 和团队技术栈；同一入口环境无规划部署多个 Controller 可能产生冲突。\n[OPS] 记录 Controller 类型、版本、Namespace、IngressClass、Service、Deployment/DaemonSet 和镜像来源；版本兼容必须结合 Kubernetes API 版本验证。\n[VERIFY] 检查 Controller 文档、实际 Pod 参数、IngressClass、日志和支持的 networking.k8s.io/v1 API。',
    ['ingress-nginx', 'NGINX-Ingress', 'Traefik', 'HAProxy', 'Istio', 'Kong', 'L7']),
  entry('tls', 'HTTPS 与 TLS Secret', '45 / HTTPS', 'HTTPS 通常监听 443，Ingress 使用 kubernetes.io/tls Secret 保存证书和私钥。',
    '[SRC] Ingress.spec.tls.hosts 必须与 rules.host 一致，secretName 指向包含 tls.crt/tls.key 的 Secret；自签证书在实验环境可能触发浏览器不信任提示。\n[OPS] HTTP 正常而 HTTPS 失败时优先检查 443、TLS Secret Namespace、Host、证书域名、Controller 监听和证书链；curl -k 仅用于测试诊断。\n[VERIFY] 使用 kubectl get/describe secret、describe ingress、Controller 日志和 curl -vk 验证，不把跳过证书校验当生产方案。',
    ['HTTPS', 'TLS', 'Secret', 'certificate', 'private-key', '443'], 'HIGH'),
  entry('traefik-rbac', 'Traefik 身份、RBAC 与配置', '46 / Traefik', 'Traefik 需要 ServiceAccount、ClusterRole、ClusterRoleBinding 以及配置入口来读取 Kubernetes 资源并执行路由。',
    '[SRC] Traefik 读取 Service、Endpoint、Ingress、IngressClass、Secret 等对象，RBAC 形成 ServiceAccount -> ClusterRoleBinding -> ClusterRole；ConfigMap 可定义 entryPoints、指标、ping 和 Dashboard。\n[OPS] 日志出现 forbidden/cannot list/watch/get 时，核对 Controller Pod 的 serviceAccountName、RBAC subject、资源 apiGroups、verbs 和绑定范围。api.insecure=true、公开 Dashboard、修改 RBAC 都是高风险配置。\n[VERIFY] 检查 get serviceaccount/clusterrole/clusterrolebinding、Pod spec、日志和实际权限，先生成变更预览再审批。',
    ['Traefik', 'RBAC', 'ServiceAccount', 'ClusterRole', 'ClusterRoleBinding', 'ConfigMap'], 'APPROVAL_REQUIRED'),
  entry('deployment', 'Ingress Controller 部署与镜像运行时', '47 / 部署排障', 'Ingress Controller 是由 Namespace、RBAC、ConfigMap、Service、Deployment/DaemonSet、Webhook 等组成的资源集合。',
    '[SRC] Controller 不只是一个 Pod；镜像必须能被实际调度 Node 上的 Containerd 获取，DaemonSet 副本数取决于符合条件的 Node。hostNetwork/hostPort 会改变网络隔离或产生端口冲突。\n[OPS] ContainerCreating、ImagePullBackOff、Pending、CrashLoopBackOff 分别沿 Events -> Node 调度/hostPort -> Containerd 镜像 -> 日志排查；不要硬编码实验仓库、IP 或版本。\n[VERIFY] 检查 get all、describe Pod/Node、ctr namespace/image、端口占用、Controller Ready 和日志。',
    ['DaemonSet', 'Deployment', 'Containerd', 'k8s.io', 'hostNetwork', 'hostPort', 'ImagePull'], 'HIGH'),
  entry('dns', 'DNS、hosts 与入口地址', '48 / DNS', '域名必须解析到可达的 Ingress 入口地址，实验环境可用 hosts 模拟 DNS。',
    '[SRC] 访问链路从域名解析开始；Could not resolve host 属于 DNS/hosts 层问题，不能先假设 Pod 或 Service 故障。\n[OPS] 检查 nslookup/dig、客户端 resolv.conf 或 Windows hosts、入口 IP 可达性，再继续 Controller 和 Ingress 规则；记录真实环境 DNS，不复制课程 IP。\n[VERIFY] 验证解析结果、TCP 80/443 连通性、Host 头和 curl -v 请求。',
    ['DNS', 'hosts', 'CoreDNS', 'nslookup', 'dig', 'HTTP']),
  entry('diagnosis', 'Ingress 访问失败证据链', '49 / 故障诊断', 'Ingress 故障必须从 DNS 到应用逐层收集证据并区分 HTTP、HTTPS、RBAC、调度和后端问题。',
    '[OPS] 标准顺序：DNS/hosts -> 入口 IP -> Controller Pod/Service -> IngressClass -> Ingress Host/Path/TLS -> Backend Service -> Endpoint/EndpointSlice -> Pod Ready/端口 -> Application -> Controller 日志/RBAC。HTTP 正常 HTTPS 失败优先看 TLS；两者都失败再扩大到 DNS 和入口。\n[VERIFY] 命令包括 kubectl get/describe ingress、ingressclass、svc、endpoints、pods，Controller logs，以及 curl -v/-vk；每一步记录现象、证据、结论和修复后验证。\n[SAFETY] 删除 Controller、切换 Controller、修改 hostNetwork/hostPort、删除 TLS Secret、批量删除 Namespace 或开放 Dashboard 必须影响评估、审批、备份和回滚。',
    ['diagnosis', 'Events', 'TLS', 'RBAC', 'endpoint', 'curl', 'verification']),
  entry('canary', 'Ingress 流量治理与金丝雀', '50 / 流量治理', '金丝雀发布通过逐步调整旧新版本流量比例观察错误率、延迟和业务指标。',
    '[SRC] Canary 的核心是从小比例流量开始，逐步扩大到新版本，而不是一次切换 100%；Traefik、Istio 等组件可提供不同的流量治理能力。\n[OPS] 变更前记录版本、Service、入口规则和业务基线，阶段性验证错误率、延迟、日志和业务交易；具体权重语法取决于 Controller 实现。\n[VERIFY] 每次比例变化后检查 Controller 配置、Endpoint/Pod、指标和真实请求，异常时按已审批的回滚路径恢复。',
    ['Canary', 'TrafficRouting', 'Traefik', 'Istio', 'metrics', 'rollback'], 'APPROVAL_REQUIRED')
]

export const kubernetesIngressRules = Object.freeze([
  { id: 'K8S-ING-001', trigger: 'Ingress 访问失败', sequence: ['dns/hosts', 'entrypoint', 'controller', 'ingressclass', 'host/path/tls', 'service', 'endpoint', 'pod/application', 'verify'] },
  { id: 'K8S-ING-002', trigger: 'HTTP 正常 HTTPS 失败', sequence: ['port 443', 'tls secret', 'secret namespace', 'host/certificate', 'controller logs', 'curl verify'] },
  { id: 'K8S-ING-003', trigger: 'Controller forbidden 或无法同步', sequence: ['serviceaccount', 'clusterrole', 'binding', 'pod serviceAccountName', 'logs', 'permission verify'] },
  { id: 'K8S-ING-004', trigger: 'Ingress Controller 变更', sequence: ['impact preview', 'version/API compatibility', 'backup', 'approval', 'change', 'traffic/rollback verify'] }
])
