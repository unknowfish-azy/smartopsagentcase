// Kubernetes scheduling, lifecycle, probes and failure diagnosis.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: `kubernetes.scheduling.${id}`,
  domain: 'linux', platform: 'Linux / Kubernetes', service: 'kubernetes',
  type: 'KUBERNETES SCHEDULING LIFECYCLE', title, section, summary, content,
  tags: ['Kubernetes', 'Scheduling', ...tags], source: 'User-provided Kubernetes scheduling, lifecycle and probe material',
  version: 'Reference pack', risk, executionAllowed: false
})

export const kubernetesSchedulingLifecycleEntries = [
  entry('flow', 'Pod 创建与调度流程', '21 / 调度基础', 'Pod 对象创建不等于容器运行，Scheduler、kubelet 和 Container Runtime 分层完成落地。',
    '[SRC] kubectl create/apply -> API Server -> etcd 状态 -> Scheduler 观察待调度 Pod 并写入 Node 结果 -> 目标 Node kubelet -> CRI/Containerd -> runc/Linux process。spec.nodeName 非空时属于定向绑定。\n[OPS] 区分 Resource Created、Scheduled、ContainerCreated、Running、Ready；故障先判断停在哪一层，不要用“API 对象存在”推断业务已启动。\n[VERIFY] 使用 kubectl get/describe、Events、Node 状态、kubelet/containerd 日志逐层核对。',
    ['API Server', 'etcd', 'Scheduler', 'kubelet', 'CRI', 'containerd', 'nodeName']),
  entry('constraints', 'NodeName、NodeSelector 与 NodeAffinity', '22 / 节点约束', 'NodeName 指定具体节点，NodeSelector 匹配标签，NodeAffinity 支持硬约束和软倾向。',
    '[SRC] nodeName: node1 直接绑定；nodeSelector: business=game 选择标签节点；requiredDuringSchedulingIgnoredDuringExecution 必须满足，preferredDuringSchedulingIgnoredDuringExecution 是带 weight 的倾向。Affinity 运算符包括 Exists、DoesNotExist、In、NotIn、Gt、Lt。\n[OPS] 硬约束无匹配节点会 Pending；Gt/Lt 需确认标签值和 API 规则。调度诊断先读取实际 Node labels、Pod spec 和 FailedScheduling Events，不要硬编码实验节点。\n[VERIFY] 用 kubectl get nodes --show-labels、describe pod、describe node 验证候选节点、标签和条件。',
    ['nodeName', 'nodeSelector', 'nodeAffinity', 'required', 'preferred', 'weight', 'FailedScheduling']),
  entry('pod-affinity', 'PodAffinity、PodAntiAffinity 与 topologyKey', '23 / Pod 亲和', 'PodAffinity 让 Pod 靠近匹配 Pod，PodAntiAffinity 让副本分散到拓扑域。',
    '[SRC] podAffinity/podAntiAffinity 通过 labelSelector 匹配 Pod，topologyKey（常见 kubernetes.io/hostname）定义拓扑域；required 是硬约束，preferred 是软倾向。\n[OPS] 先区分匹配的是 Node Label 还是 Pod Label；反亲和可降低单节点故障造成的副本同时丢失风险，但可能因节点数量不足造成 Pending。\n[VERIFY] 对比 Pod labels、拓扑标签、现有 Pod 分布和 Scheduler Events，确认规则实际生效。',
    ['podAffinity', 'podAntiAffinity', 'topologyKey', 'labelSelector', 'high availability']),
  entry('taints', 'Taints、Tolerations 与 NoExecute 风险', '24 / 污点容忍', 'Taint 是 Node 侧排斥规则，Toleration 是 Pod 侧允许匹配的能力。',
    '[SRC] Taint 格式为 key=value:effect；PreferNoSchedule 是软排斥，NoSchedule 阻止不容忍的新 Pod，NoExecute 还可驱逐已有不容忍 Pod。Toleration 可用 Equal/Exists、key/value/effect/tolerationSeconds 匹配。\n[OPS] master 常有 control-plane:NoSchedule；NoExecute 变更前必须统计节点上所有 Pod、Toleration、控制器和业务影响。删除 Taint 需确认 key/effect，避免误改其他规则。\n[VERIFY] 先 describe node 查看现有 Taints，再 describe pod 查看 FailedScheduling/驱逐 Events，修改后验证 Pod Node、Ready 和业务。',
    ['Taint', 'Toleration', 'PreferNoSchedule', 'NoSchedule', 'NoExecute', 'tolerationSeconds', 'eviction'], 'HIGH'),
  entry('pending', 'Pending 与 FailedScheduling 故障诊断', '25 / 调度故障', 'Pending 是状态信号，根因通常来自节点、资源、标签、亲和、污点或 PVC 等约束。',
    '[SRC] kubectl get pod -> kubectl describe pod -> Events/FailedScheduling 是首要证据。常见原因：nodeName 不存在、Node NotReady、NodeSelector/Affinity 不匹配、PodAffinity/AntiAffinity 冲突、untolerated taint、CPU/内存不足、Quota/PVC。\n[OPS] 不要看到 Pending 就 delete 或重建；先读取 Pod YAML、候选节点 labels/taints、requests、Namespace quota 和调度器事件。\n[VERIFY] 修复约束或资源后观察 Pod 是否绑定正确 Node、进入 Running/Ready，并记录调度前后差异。',
    ['Pending', 'FailedScheduling', 'resource', 'Quota', 'PVC', 'taint', 'affinity']),
  entry('lifecycle', 'Pod 生命周期、Init、Hook 与重启策略', '26 / 生命周期', 'Pod 经历调度、Init Container、主容器、Hook、探针和终止；Container 重启不等于 Pod 重建。',
    '[SRC] initContainers 完成后才启动主容器；postStart 在容器启动后执行，preStop 在终止前执行；restartPolicy 有 Always、OnFailure、Never。terminationGracePeriodSeconds 控制优雅终止等待。\n[OPS] 控制器删除 Pod 后可能重新创建新 Pod，Scheduler 可能选择不同 Node；CrashLoopBackOff 是反复失败的退避状态，不是根因。Hook 失败、慢启动、命令/参数和依赖都要结合 Events/日志判断。\n[VERIFY] 检查 phase、containerStatuses、LastState、RestartCount、ExitCode、Hook、控制器关系和终止时间线。',
    ['Pod lifecycle', 'initContainer', 'postStart', 'preStop', 'restartPolicy', 'terminationGracePeriod', 'CrashLoopBackOff']),
  entry('probes', 'Startup、Liveness、Readiness 探针', '27 / 健康检查', 'Startup 保护慢启动，Liveness 决定是否重启，Readiness 决定是否接收 Service 流量。',
    '[SRC] Probe 支持 exec、httpGet、tcpSocket；initialDelaySeconds、periodSeconds、timeoutSeconds、successThreshold、failureThreshold 控制探测节奏。Startup 成功后才进入后续健康判断；Liveness 失败可重启容器；Readiness 失败通常使 Pod NotReady 并从 Service 后端移除。\n[OPS] Running 不等于 Ready；一次失败不一定立即重启；慢启动应用若 liveness 过早会造成假故障。Probe path、port、命令和成功标准必须与真实应用一致。\n[VERIFY] 用 describe 查看 Probe Failed Events，结合 logs、exec/curl、端口监听、Ready 状态和 RestartCount 验证。',
    ['startupProbe', 'livenessProbe', 'readinessProbe', 'exec', 'httpGet', 'tcpSocket', 'NotReady']),
  entry('diagnosis', 'Pod 重启、Probe 与 OOM 证据链', '28 / 运行故障', '对 CrashLoopBackOff、Probe Failed、OOMKilled 和 Readiness 失败按不同路径采集证据。',
    '[OPS] 重启先执行 kubectl describe pod、kubectl logs、kubectl logs --previous、kubectl get pod -o yaml；检查 ExitCode、LastState、OOMKilled、command/args、env、volume、resources 和 probe。Readiness 失败重点看 Service/Endpoint，Liveness/Startup 失败重点看重启和配置。\n[VERIFY] Node 层再查 kubelet、containerd、free、dmesg/journalctl -k。区分 Container Restart、Pod Recreate、Pod NotReady 和业务协议失败，不要把 CrashLoopBackOff 当作最终根因。',
    ['CrashLoopBackOff', 'OOMKilled', 'logs --previous', 'ExitCode', 'LastState', 'Probe Failed', 'Endpoint']),
  entry('automation', '调度与生命周期自动诊断工作流', '29 / 自动化', '把 context、Namespace、约束、事件、探针、节点和运行时验证组织成可审计流程。',
    '[SRC] 调度流程：确认 cluster/context/namespace -> get pod -> describe/events -> 读取 nodeName/selector/affinity/tolerations/resources -> 对比 Node labels/taints/allocatable -> 修复声明源 -> apply -> 验证 Node/Ready。生命周期流程：phase -> container state -> logs/previous -> probes -> runtime/Linux -> Service。\n[OPS] 修改 label、taint、toleration、affinity、scale、delete 或 force delete 前预览影响范围并审批；不要使用实验 IP、节点名、镜像地址硬编码生产自动化。\n[VERIFY] 记录资源、Namespace、候选节点、事件、变更前后 YAML、Pod 所在 Node、Ready、Endpoint 和业务结果。',
    ['automation', 'context', 'namespace', 'scheduler diagnostic', 'probe diagnostic', 'audit'], 'APPROVAL_REQUIRED')
]

export const kubernetesSchedulingLifecycleRules = Object.freeze([
  { id: 'K8S-SCH-001', trigger: 'Pod Pending', sequence: ['describe/events', 'nodeName', 'selector/affinity', 'taints/tolerations', 'resources/quota', 'verify'] },
  { id: 'K8S-SCH-002', trigger: 'Node scheduling change', sequence: ['inspect labels/taints', 'impact analysis', 'approval', 'change', 'verify pods/ready'] },
  { id: 'K8S-LIFE-001', trigger: 'Container restart', sequence: ['describe', 'logs', 'logs --previous', 'exit/OOM/probe/command', 'runtime'] },
  { id: 'K8S-PROBE-001', trigger: 'Probe failed', sequence: ['identify startup/liveness/readiness', 'inspect config', 'reproduce exec/http/tcp', 'check app', 'verify ready/restarts'] }
])
