// Kubernetes nodes, YAML, workloads, services and resource troubleshooting.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: `kubernetes.resource.${id}`,
  domain: 'linux', platform: 'Linux / Kubernetes', service: 'kubernetes',
  type: 'KUBERNETES RESOURCE OPERATIONS', title, section, summary, content,
  tags: ['Kubernetes', 'kubectl', ...tags], source: 'User-provided Kubernetes Node, YAML, Pod and Service material',
  version: 'Reference pack', risk, executionAllowed: false
})

export const kubernetesResourceEntries = [
  entry('node', 'Node 状态、Label 与 kubeconfig', '11 / Node', 'Node 是运行 Pod 的计算节点，NotReady 排障要从 Conditions/Events 下钻到 kubelet、Runtime 和 Linux。',
    '[SRC] kubectl get nodes、get nodes -o wide、describe node、get node -o yaml 查看状态、IP、运行时、Capacity、Allocatable、Taints、Labels 和 Events。-l 筛选 Label，-L 仅显示 Label 列；label KEY- 删除，--overwrite 覆盖。\n[OPS] kubeadm 节点未必有 $HOME/.kube/config；admin.conf 具有高权限，不能为方便执行 kubectl 就复制到所有主机，应使用最小权限 kubeconfig/RBAC。NotReady 先查 conditions/events、kubelet、containerd、磁盘、内存和网络。\n[VERIFY] 记录 cluster context、节点名、版本、InternalIP、Labels、Taints 和故障时间。',
    ['Node', 'Ready', 'NotReady', 'label', 'selector', 'kubeconfig', 'admin.conf', 'RBAC'], 'HIGH'),
  entry('namespace', 'Namespace、ResourceQuota 与 LimitRange', '12 / Namespace', 'Namespace 用于资源逻辑分组；Quota 和 LimitRange 约束资源使用，但不自动等同于网络隔离。',
    '[SRC] kubectl get/describe ns、kubectl create ns、kubectl get ns -o yaml 管理命名空间；ResourceQuota 可限制 CPU、内存、Pod、Service、PVC 等，LimitRange 可设置默认/最小/最大 requests/limits。\n[OPS] dev/test/prod 等命名空间是组织维度，真正的网络与权限隔离还需 NetworkPolicy、RBAC 和 ServiceAccount。delete ns 会清理其中的 Namespaced 资源，是高风险破坏性操作。\n[VERIFY] 创建或变更前检查命名空间内资源、Quota、LimitRange、RBAC 和网络策略。',
    ['Namespace', 'ResourceQuota', 'LimitRange', 'NetworkPolicy', 'RBAC'], 'HIGH'),
  entry('yaml', 'Kubernetes YAML、Schema 与声明式管理', '13 / YAML', 'YAML 描述资源期望状态，apply 通过协调机制使实际状态趋近声明状态。',
    '[SRC] 基本骨架是 apiVersion、kind、metadata、spec；YAML 区分大小写，使用空格缩进，不使用 Tab；Scalar、Sequence、Mapping 可嵌套，--- 分隔多文档。kubectl explain、api-resources、api-versions 可作为本地 Schema 参考。\n[OPS] create 偏向一次创建，重复执行可能 AlreadyExists；apply 可创建或更新，适合 Git/审计/持续管理。语法正确不代表 Schema、语义、调度、镜像或应用运行正确。修改生产配置优先更新 YAML/Git，不依赖现场 edit。\n[VERIFY] 进行语法、Schema、selector/label、引用、资源关系和运行时验证。',
    ['YAML', 'apiVersion', 'kind', 'metadata', 'spec', 'kubectl explain', 'kubectl apply', 'GitOps']),
  entry('pod', 'Pod 生命周期、命令、镜像策略与 exec', '14 / Pod', 'Pod 是 Kubernetes 最小管理单元，可包含共享网络和存储上下文的一个或多个容器。',
    '[SRC] Pod 状态可能为 Pending、ContainerCreating、Running、Succeeded、Failed；command/args 对应容器入口，imagePullPolicy 有 Always、IfNotPresent、Never，restartPolicy 常见 Always、OnFailure、Never。kubectl exec -it POD -c CONTAINER -- command 在 Pod 容器内执行命令，kubectl cp 做文件交换。\n[OPS] Running 不等于 Ready；多容器 Pod 需明确 -c；容器重启不等于 Pod 重建。Pod 删除前保留 get/describe/logs/yaml 现场，--force 仅在确认 Terminating、finalizers、节点和卷状态后使用。\n[VERIFY] 结合 phase、conditions、containerStatuses、restartCount、ExitCode、Events 和日志判断真实状态。',
    ['Pod', 'command', 'args', 'imagePullPolicy', 'restartPolicy', 'kubectl exec', 'kubectl cp', 'Ready'], 'APPROVAL_REQUIRED'),
  entry('labels-selectors', 'Label、Selector 与资源关系', '15 / Label Selector', 'Label 是 key/value 标识，Selector 将 Deployment、Service、调度和资源查询连接起来。',
    '[SRC] Node、Pod、Deployment、Service 都可有 Labels；kubectl get nodes -l KEY=VALUE 筛选，-l "KEY in (a,b)" 做集合选择。Deployment selector.matchLabels 必须匹配 template.metadata.labels；Service selector 必须匹配 Pod labels。\n[OPS] Label 大小写和命名格式敏感，资源关系错误时会出现 Deployment 不管理 Pod 或 Service 无 Endpoint。修改 Label 前确认控制器选择范围，避免意外接管或脱离资源。\n[VERIFY] 对比 selector、template labels、Pod labels、Service endpoints 和实际控制器关系。',
    ['label', 'selector', 'matchLabels', 'Service selector', 'Endpoint', 'nodeSelector']),
  entry('deployment', 'Deployment、ReplicaSet、DaemonSet 与自愈', '16 / Workload Controller', 'Deployment 管理无状态发布，ReplicaSet 维护副本，DaemonSet 在符合条件的每个 Node 运行一份 Pod。',
    '[SRC] 关系是 Deployment -> ReplicaSet -> Pods -> Containers；kubectl scale 调整期望副本数，控制器会协调实际状态。删除由 Deployment 管理的 Pod 通常会被补回，DaemonSet 常用于 CNI、日志和节点监控。\n[OPS] 排障按 get/describe deployment、get rs、get pods 追踪；不要把直接删除 Pod 当成修复。新 Pod 可能由 Scheduler 放到不同 Node。生产扩缩容和删除控制器需要确认 Namespace、当前副本、业务影响和声明源。\n[VERIFY] 检查 replicas、READY、UP-TO-DATE、AVAILABLE、Conditions、Events、ReplicaSet 和 Pod 分布。',
    ['Deployment', 'ReplicaSet', 'DaemonSet', 'scale', 'reconciliation', 'self-healing'], 'APPROVAL_REQUIRED'),
  entry('service', 'Service、ClusterIP、NodePort 与 Endpoint', '17 / Service', 'Service 为匹配的 Pod 提供稳定入口，selector、Endpoint、port 和 targetPort 必须形成完整链路。',
    '[SRC] ClusterIP 适合集群内访问，NodePort 通过 NodeIP:NodePort 暴露；Service port 是入口端口，targetPort 指向 Pod 应用端口。kubectl get/describe svc、get endpoints、get endpointslices 和 Pod labels 是基本证据。\n[OPS] Service 存在不代表有后端；先对比 selector 与 Pod labels，再检查 Pod Ready、Endpoint、监听端口、网络策略和应用协议。containerPort 只是声明，不会自动创建 Service 或 NodePort。\n[VERIFY] 用集群内/节点侧 curl 或业务探针沿 Client -> Service -> Endpoint -> Pod -> targetPort -> Application 验证。',
    ['Service', 'ClusterIP', 'NodePort', 'port', 'targetPort', 'Endpoint', 'EndpointSlice']),
  entry('resources-probes', 'Pod requests、limits、Probe 与 OOM', '18 / Resource', 'requests 影响调度与保障，limits 约束使用上限，探针决定可用性与重启行为。',
    '[SRC] resources.requests 是调度参考，limits 是资源上限；memory 超限可能 OOMKilled。livenessProbe 判断是否存活并可触发重启，readinessProbe 决定是否接收流量，startupProbe 保护慢启动应用。\n[OPS] CrashLoopBackOff 要查 logs、logs --previous、describe、LastState、ExitCode、Probe、Config、Volume 和资源；不要只增大 limit 或只重启 Pod。Namespace Quota/LimitRange、Node allocatable 和宿主机压力也要纳入。\n[VERIFY] 对比请求、限制、实际使用、Node 余量、Probe 参数、Ready 状态和业务 SLO。',
    ['requests', 'limits', 'OOMKilled', 'livenessProbe', 'readinessProbe', 'startupProbe', 'CrashLoopBackOff']),
  entry('diagnosis', 'Node、Pod、Deployment 与 Service 诊断证据链', '19 / 故障诊断', '按资源关系和层级逐步采集 get、describe、logs、YAML、控制器、节点和运行时证据。',
    '[OPS] Node：get/describe/yaml -> Conditions/Events -> kubelet -> containerd -> Linux；Pod：get -> describe/events -> logs/previous -> yaml -> image/volume/network/resource；Deployment：deploy -> ReplicaSet -> Pod；Service：selector -> labels -> endpoints -> port/targetPort -> application。\n[VERIFY] 先保留现场，再形成可证伪根因；kubectl get -o yaml 用于机器分析 metadata/spec/status，不能只解析表格输出。修复后重新检查同一资源、同一 Namespace 和业务路径。\n[SAFETY] delete ns、delete pod --force、patch、scale、edit 和删除控制器都要判断影响并审批。',
    ['kubectl get', 'kubectl describe', 'kubectl logs', 'events', 'status', 'spec', 'conditions'], 'READ_ONLY'),
  entry('automation', 'Kubernetes 资源自动化闭环', '20 / 自动化', '以 Context、Namespace、声明源、资源关系和验证为核心构建可审计自动化。',
    '[SRC] 标准闭环：确认 context/cluster -> 定位 Namespace -> get/describe -> 读取 YAML -> 校验 schema/selector/引用 -> 修改 Git/YAML -> apply -> 验证 Node/Pod/Controller/Service -> 记录事件。\n[OPS] 参数化集群、命名空间、镜像、版本、副本和端口；删除、强制删除、patch、scale、复制高权限 kubeconfig 前做预览、审批和回滚准备。\n[VERIFY] 依次验证 API 对象、控制器状态、Pod Ready、Endpoint、应用协议和资源指标，不把 apply 成功当作运行健康。',
    ['automation', 'context', 'declarative', 'audit', 'rollback', 'verification'], 'APPROVAL_REQUIRED')
]

export const kubernetesResourceRules = Object.freeze([
  { id: 'K8S-RES-001', trigger: 'Node NotReady', sequence: ['get/describe', 'conditions/events', 'kubelet', 'containerd', 'Linux/network'] },
  { id: 'K8S-RES-002', trigger: 'Service 无法访问', sequence: ['service', 'selector', 'pod labels', 'endpoints', 'ports', 'ready/application'] },
  { id: 'K8S-RES-003', trigger: 'Pod 异常', sequence: ['phase', 'describe/events', 'logs/previous', 'yaml', 'controller', 'runtime/resource'] },
  { id: 'K8S-RES-004', trigger: 'YAML 变更', sequence: ['context/namespace', 'schema', 'semantic relations', 'apply', 'runtime verify', 'audit'] }
])
