// Kubernetes controllers, rollout, jobs and Service discovery reference pack.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: `kubernetes.controller.${id}`,
  domain: 'linux', platform: 'Linux / Kubernetes', service: 'kubernetes',
  type: 'KUBERNETES CONTROLLER SERVICE', title, section, summary, content,
  tags: ['Kubernetes', 'Controller', ...tags], source: 'User-provided Kubernetes controller and Service material',
  version: 'Reference pack', risk, executionAllowed: false
})

export const kubernetesControllerServiceEntries = [
  entry('model', 'Controller、期望状态与资源关系', '30 / Controller', 'Controller 持续比较期望状态与实际状态，通过创建、删除和调整 Pod 实现自愈。',
    '[SRC] Controller 关系包括 Deployment -> ReplicaSet -> Pod -> Container；Controller 通过 Label/Selector 找到管理对象。自主式 Pod 删除后不会由 Deployment 自动恢复，受控 Pod 删除后通常会被补回。\n[OPS] 排障不要只看 Pod，要确认 ownerReferences、控制器、期望副本、实际副本和 Events。删除受控 Pod 不等于解决根因，可能只是触发重新创建。\n[VERIFY] 用 kubectl get deploy/rs/pod、describe 和 ownerReferences 还原资源关系。',
    ['desired state', 'reconciliation', 'ownerReferences', 'Pod', 'Controller']),
  entry('deployment', 'Deployment 与 ReplicaSet 发布管理', '31 / Deployment', 'Deployment 管理无状态应用的副本、滚动升级、版本历史、回滚和扩缩容。',
    '[SRC] Deployment 通过 ReplicaSet 维护 Pod；spec.replicas 表示期望副本，selector.matchLabels 必须匹配 template.metadata.labels。Deployment 适合 Web/API 等无状态应用。\n[OPS] 创建或更新优先使用 YAML + kubectl apply；扩缩容使用 scale；升级前确认容器名和目标镜像，不能把 rollout 成功等同于业务健康。\n[VERIFY] 检查 READY、UP-TO-DATE、AVAILABLE、ReplicaSet、Pod Ready、镜像、Events、Service 和业务请求。',
    ['Deployment', 'ReplicaSet', 'replicas', 'scale', 'rollout', 'selector', 'labels'], 'APPROVAL_REQUIRED'),
  entry('rollout', 'Deployment 滚动升级、历史与回滚', '32 / 发布管理', '通过新 ReplicaSet 逐步替换旧 Pod，并用 rollout status/history/undo 验证与恢复。',
    '[SRC] kubectl set image deployment NAME CONTAINER=IMAGE 修改 Pod Template；rollout status 观察发布，rollout history 查看 revision，rollout undo --to-revision=N 发起回滚。升级会产生新 ReplicaSet，旧 ReplicaSet 通常缩到 0。\n[OPS] 升级或回滚前记录当前镜像、revision、副本、Ready、Service 和业务基线；--record 不应作为唯一历史依据。回滚是高风险变更，需审批、快照和验证。\n[VERIFY] 发布后检查新 Pod 镜像、Ready、日志、探针、Endpoint、Service 访问和应用实际版本。',
    ['RollingUpdate', 'rollout status', 'rollout history', 'rollout undo', 'revision', 'rollback'], 'HIGH'),
  entry('daemonset', 'DaemonSet、节点守护与 Toleration', '33 / DaemonSet', 'DaemonSet 在每个符合条件的 Node 上运行一个 Pod，常用于日志、监控和网络组件。',
    '[SRC] DaemonSet 副本数量由符合条件的 Node 决定，不是固定 replicas；新节点加入后会自动补 Pod。控制平面有 NoSchedule Taint 时，若需运行 DaemonSet，应配置对应 Toleration。\n[OPS] 删除 DaemonSet Pod 通常会被重建；Evicted、DiskPressure、镜像空间和节点状态要与 DaemonSet 配置区分诊断。变更 Toleration 或删除守护 Pod 需评估节点影响。\n[VERIFY] 检查 desired/current/ready、Pod 分布、Node Taints、Events、磁盘和 kubelet/runtime。',
    ['DaemonSet', 'node daemon', 'Toleration', 'control-plane', 'DiskPressure', 'Evicted'], 'APPROVAL_REQUIRED'),
  entry('job-cronjob', 'Job、CronJob、completions 与 parallelism', '34 / 批处理', 'Job 追求一次性成功完成，CronJob 按时间规则周期性创建 Job。',
    '[SRC] Job -> Pod -> Container，成功后 Pod 常为 Completed；completions 是总成功次数，parallelism 是并发运行规模。CronJob -> Job -> Pod，schedule 使用 cron 表达式。\n[OPS] 区分 Deployment 的持续运行目标和 Job 的完成目标；任务失败查 logs、describe、ExitCode、镜像、资源和重启策略。大镜像可在 Containerd 的 Kubernetes namespace 预加载，但要确认实际 runtime/namespace。\n[VERIFY] 检查 Job completions、active/failed/succeeded、CronJob 最近创建时间、Pod 日志和任务结果。',
    ['Job', 'CronJob', 'completions', 'parallelism', 'schedule', 'Completed', 'batch']),
  entry('service', 'Service、Selector、Endpoint 与端口链路', '35 / Service', 'Service 通过 Selector 找到 Pod，提供稳定入口、服务发现和流量转发。',
    '[SRC] Service -> selector -> Endpoint/EndpointSlice -> Pod IP:targetPort。port 是 Service 端口，targetPort 是 Pod 应用端口，两者可以不同。Service 有 ClusterIP 不代表已有后端；ENDPOINTS=<none> 时优先核对 Selector 与 Pod labels。\n[OPS] 访问故障按 Client、Service、Endpoint、Pod Ready、targetPort、实际监听、kube-proxy 和网络逐层排查。不要把 Service 存在或 Endpoint 存在直接解释为业务健康。\n[VERIFY] 使用 get/describe svc、get endpoints/endpointslices、get pods --show-labels、exec ss/curl 和业务请求验证。',
    ['Service', 'selector', 'Endpoint', 'EndpointSlice', 'port', 'targetPort', 'sessionAffinity']),
  entry('service-types', 'ClusterIP、NodePort、LoadBalancer、ExternalName', '36 / Service 类型', '不同 Service 类型对应集群内、节点外部、云负载均衡和 DNS 外部名称映射。',
    '[SRC] ClusterIP 提供集群内虚拟入口；NodePort 使用 NodeIP:NodePort；LoadBalancer 通常对接云平台 LB；ExternalName 通过 DNS CNAME 引用外部域名，不是 Pod 负载均衡。\n[OPS] 外部访问失败先确认访问来源与 Service 类型，再检查 Node IP/端口、云 LB、DNS、权限和网络策略。NodePort 不保证端口从所有网络可达。\n[VERIFY] 检查 Service YAML、端口、Endpoint、kube-proxy、云 LB 状态和 curl/DNS 结果。',
    ['ClusterIP', 'NodePort', 'LoadBalancer', 'ExternalName', 'CNAME', 'external access']),
  entry('headless-dns', 'Headless Service、StatefulSet 与 DNS', '37 / 服务发现', 'clusterIP: None 不提供普通虚拟 IP，DNS 可返回后端 Pod 地址，常与 StatefulSet 配合。',
    '[SRC] Headless Service 使用 clusterIP: None，Service DNS 可解析为多个 Pod IP；StatefulSet 提供稳定 Pod 身份，如 mysql-0，典型 DNS 为 pod.service.namespace.svc.cluster.local。普通 Deployment Pod 名称不保证稳定，不能机械套用 Stateful DNS。\n[OPS] DNS 排障区分 Service 名称解析、Pod IP、CoreDNS/kube-dns、EndpointSlice 和客户端 resolv.conf；ExternalName 是 CNAME 映射，Headless 是后端地址发现。\n[VERIFY] 用 kubectl get svc/endpoints、get pods、dig/nslookup、CoreDNS 日志和集群内 curl 验证。',
    ['Headless Service', 'clusterIP: None', 'StatefulSet', 'CoreDNS', 'kube-dns', 'dig', 'DNS']),
  entry('proxy-network', 'kube-proxy、iptables、IPVS 与 Service 转发', '38 / 网络实现', 'kube-proxy 将 Service 流量编程到 iptables 或 IPVS 等内核转发机制。',
    '[SRC] kube-proxy 可使用 iptables 或 IPVS；IPVS 支持 RR、WRR、LC、WLC、IP Hash 等调度算法。kubectl logs -n kube-system kube-proxy-POD 可确认 proxier，ipvsadm -Ln 可查看虚拟服务与后端。\n[OPS] 修改 kube-proxy ConfigMap、切换模式或删除 kube-proxy Pod 会影响集群服务转发，必须先备份配置、评估窗口并确认 DaemonSet 重建。不要只看到 mode 配置就断言已经生效。\n[VERIFY] 同时检查 kube-proxy Pod 日志、iptables/IPVS 实际规则、Endpoint、节点网络和业务访问。',
    ['kube-proxy', 'iptables', 'IPVS', 'ipvsadm', 'RR', 'WRR', 'LC', 'WLC'], 'HIGH'),
  entry('diagnosis', 'Controller 与 Service 综合故障证据链', '39 / 故障诊断', '沿 Deployment/ReplicaSet/Pod 和 Service/Endpoint/网络两棵关系图定位应用故障。',
    '[OPS] 副本少：get deploy/rs/pod -> describe -> Events -> Node/调度；升级卡住：rollout status -> rs/pod -> image/probe/logs；Service 不通：svc -> selector/labels -> endpoints/endpointslices -> Ready -> port/targetPort -> app -> kube-proxy/IPVS/DNS。\n[VERIFY] 采集 namespace、context、期望/实际副本、owner、镜像、Pod 状态、Endpoint、端口、日志和网络证据。现象不等于根因，apply/rollout 成功不等于业务成功。\n[SAFETY] delete、scale、set image、rollout undo、patch、修改 kube-proxy 和删除 namespace 需影响分析、审批与验证。',
    ['diagnosis', 'Events', 'ownerReferences', 'rollout', 'endpoints', 'network'], 'READ_ONLY'),
  entry('automation', 'Controller 与 Service 自动化运维闭环', '40 / 自动化', '以实际 Cluster Context、Namespace、声明源和上下游验证为核心生成安全运维流程。',
    '[SRC] 自动化顺序：读取 context/namespace -> 获取 Deployment/RS/Pod/Service/Endpoint -> 分析关系与事件 -> 生成变更预览 -> 用户确认 -> apply/scale/rollout -> 验证 Ready、Endpoint、业务和回滚路径。\n[OPS] 动态读取镜像、节点、端口、revision、Service 类型和 registry；不硬编码实验参数，不将 rollout status 或 Endpoint 存在当作业务健康。\n[VERIFY] 记录变更前后对象、Pod 分布、版本、流量、日志、事件和审计结果。',
    ['automation', 'context', 'namespace', 'audit', 'rollback', 'verification'], 'APPROVAL_REQUIRED')
]

export const kubernetesControllerServiceRules = Object.freeze([
  { id: 'K8S-CTRL-001', trigger: '副本不足', sequence: ['deployment', 'replicaset', 'pods', 'events', 'node/scheduling', 'verify'] },
  { id: 'K8S-CTRL-002', trigger: '发布升级', sequence: ['baseline', 'set image', 'rollout status', 'new RS/pods', 'service/endpoint', 'business verify'] },
  { id: 'K8S-SVC-001', trigger: 'Service 访问失败', sequence: ['service type', 'selector/labels', 'endpoints', 'ready/ports', 'kube-proxy', 'iptables/IPVS/DNS'] },
  { id: 'K8S-CTRL-003', trigger: '高风险控制器变更', sequence: ['impact preview', 'approval', 'backup', 'change', 'audit', 'rollback/verify'] }
])
