// Kubernetes architecture, kubeadm deployment and troubleshooting reference pack.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: `kubernetes.${id}`,
  domain: 'linux', platform: 'Linux / Kubernetes', service: 'kubernetes',
  type: 'KUBERNETES OPERATIONS', title, section, summary, content,
  tags: ['Kubernetes', 'K8s', ...tags], source: 'User-provided Kubernetes architecture, kubeadm and troubleshooting material',
  version: 'Reference pack', risk, executionAllowed: false
})

export const kubernetesFoundationEntries = [
  entry('architecture', 'Kubernetes 集群架构与控制面', '01 / 架构', 'Control Plane 负责决策和状态，Worker Node 运行工作负载，二者通过 API Server 协作。',
    '[SRC] Control Plane（课程中的 Master）包含 API Server、Scheduler、Controller Manager、etcd；Worker 包含 kubelet、kube-proxy 和 Container Runtime。API Server 是统一 API 入口，Scheduler 决定 Pod 放置节点，Controller 维护期望状态，etcd 保存关键集群状态。\n[OPS] 排障先判断控制面、节点还是工作负载层。Docker、Containerd、Kubernetes 不在同一层；Kubelet 通过 CRI 调用 Containerd，再由 OCI runtime/runC 创建 Linux 进程。\n[VERIFY] 用 kubectl、systemctl、journalctl 和运行时工具分别验证各组件，而不是仅凭单个状态判断集群健康。',
    ['Control Plane', 'Master', 'Worker', 'API Server', 'Scheduler', 'Controller Manager', 'etcd', 'kubelet', 'kube-proxy', 'CRI']),
  entry('workloads-network', 'Pod、Service、CNI 与常见 Add-ons', '02 / 工作负载与网络', 'Pod 是 Kubernetes 基本运行单元，Service 提供稳定访问入口，CNI/Flannel 提供 Pod 网络。',
    '[SRC] Pod 包含一个或多个容器；Service 将请求转发到匹配的 Pod；Flannel 是常见 CNI，CoreDNS 提供集群 DNS，Ingress Controller 提供外部入口，Metrics Server/Prometheus/Grafana用于指标和告警。\n[OPS] kubeadm 的 --pod-network-cidr 必须与 CNI 配置一致，例如实验中的 10.244.0.0/16；网络插件、Service、Endpoint、kube-proxy 和 Pod 状态要联合检查。\n[VERIFY] 使用 kubectl get pod -A、get svc、get endpoints、describe 和 DNS/网络测试确认链路。',
    ['Pod', 'Service', 'CNI', 'Flannel', 'CoreDNS', 'Ingress', 'Endpoint', 'Metrics Server']),
  entry('deployment-choice', 'Minikube、kubeadm、Kubeasz 与二进制部署', '03 / 部署方式', '根据学习、快速集群、自动化生产或底层控制需求选择部署方式。',
    '[SRC] Minikube 适合单机学习测试；kubeadm 是官方快速部署工具；Kubeasz 基于 Ansible 适合多节点自动化；二进制部署细节透明但维护复杂。\n[OPS] 选型前明确节点数、网络、版本、镜像源、可维护性和回滚能力，不要把课程实验参数直接复制到生产。\n[VERIFY] 无论方式都应记录 Kubernetes、Containerd、CNI、runC 版本和最终组件状态。',
    ['Minikube', 'kubeadm', 'Kubeasz', 'binary deployment', 'version compatibility']),
  entry('preflight', 'kubeadm 部署前置检查', '04 / 环境准备', '主机名、解析、时间、Swap、内核模块、sysctl、Containerd 和版本是初始化集群的基础。',
    '[SRC] 检查 hostname/hostnamectl、/etc/hosts、时间同步、swapon --show、SELinux/firewalld、iptables、br_netfilter、overlay、net.ipv4.ip_forward、Containerd SystemdCgroup、kubeadm/kubelet/kubectl 和仓库可达性。\n[OPS] 修改 fstab、iptables、内核参数、防火墙和 sysctl 会影响主机，必须先输出当前值并获得审批；不要把“关闭所有安全控制”当作通用生产方案。\n[VERIFY] 形成前置检查报告，确认每个节点的 IP、主机名、解析、运行时、版本和资源满足目标集群要求。',
    ['hostname', 'hosts', 'Swap', 'SELinux', 'firewalld', 'iptables', 'br_netfilter', 'overlay', 'sysctl', 'SystemdCgroup'], 'APPROVAL_REQUIRED'),
  entry('kubeadm-init-join', 'kubeadm init、join 与 kubeconfig', '05 / 集群初始化', 'Master 使用 kubeadm init，Worker 使用当前集群生成的 join 命令，kubectl 依赖 admin.conf。',
    '[SRC] init 常见参数包括 --apiserver-advertise-address、--control-plane-endpoint、--pod-network-cidr、--image-repository；成功后输出动态 token 和 CA hash。忘记时可用 kubeadm token create --print-join-command 重新生成。\n[OPS] Token、CA hash、IP、CIDR 和镜像仓库必须按当前环境确认，不能硬编码课程值。初始化后将 /etc/kubernetes/admin.conf 安全复制到 $HOME/.kube/config，并确认权限。\n[VERIFY] 用 kubectl get node、kubectl get pod -A、端口 6443 连通性和节点状态验证；失败先保留 init/join 原始输出。',
    ['kubeadm init', 'kubeadm join', 'kubeadm token', 'admin.conf', '.kube/config', '6443'], 'APPROVAL_REQUIRED'),
  entry('cni-join', 'Flannel 安装与 Node Ready 验证', '06 / CNI', '没有可用 CNI 时节点可能 NotReady；Flannel 配置需与 Pod CIDR 对齐。',
    '[SRC] kubectl apply -f kube-flannel.yml 将资源提交给 API Server；kubectl get pod -A 查看 CNI Pod，kubectl describe pod -n kube-flannel 查看 Events。\n[OPS] ErrImagePull 时先查镜像源、DNS、网络和容器运行时；不要首先强制删除 Pod。删除/重装 Flannel 前保存 YAML、Events 和配置，强制删除仅在证据充分时使用。\n[VERIFY] 确认每个目标节点的 Flannel Pod、Node Ready、Pod-to-Pod 连通性和 DNS。',
    ['Flannel', 'CNI', 'kubectl apply', 'NotReady', 'ErrImagePull', 'Events'], 'APPROVAL_REQUIRED'),
  entry('states', 'Kubernetes 状态关键词与故障路由', '07 / 状态诊断', '根据 NotReady、Pending、CrashLoopBackOff、ErrImagePull 等状态选择不同证据路径。',
    '[SRC] Ready 表示节点可用；NotReady 优先查 kubelet、Containerd、CNI 和系统条件；Pending 查 Scheduler、资源、Taint 和 Volume；CrashLoopBackOff 查应用命令、配置、探针和日志；ErrImagePull/ImagePullBackOff 查镜像、tag、Registry、认证、DNS、网络和架构。\n[OPS] 状态是线索不是根因。先 kubectl get，再 describe/events、logs，必要时下沉到 journalctl -u kubelet、journalctl -u containerd、ctr 和 Linux 工具。\n[VERIFY] 修复后重新观察状态、事件、日志、Node Conditions 和业务访问，不以 delete Pod 作为默认修复。',
    ['Ready', 'NotReady', 'Pending', 'Running', 'CrashLoopBackOff', 'ErrImagePull', 'ImagePullBackOff', 'Init:ErrImagePull']),
  entry('evidence-chain', 'Kubernetes 三层故障排查证据链', '08 / 故障排查', '从 Kubernetes API 层下沉到 Container Runtime 和 Linux 层，逐层保留证据。',
    '[SRC] 标准命令链：kubectl get -> kubectl describe -> kubectl logs -> kubectl get events -> journalctl -u kubelet -> journalctl -u containerd -> ctr -> ps/ss/ip/df/free。kubectl 无法连接时还要查 kubeconfig、API Server、6443 和网络。\n[OPS] Pod、Node、Service 和控制面问题需要分别定位；kubelet 错误不等于应用错误，Containerd 错误也不一定是 Kubernetes 配置错误。保留时间、namespace、资源名、Events、日志和版本。\n[VERIFY] 每层提出可证伪假设，修复后验证同一资源、同一节点和同一业务路径。',
    ['kubectl get', 'kubectl describe', 'kubectl logs', 'events', 'journalctl', 'ctr', 'ps', 'ss']),
  entry('common-failures', 'kubeadm 与集群常见故障模型', '09 / 常见故障', '覆盖 localhost:8080、Swap、6443、重复 join、镜像失败和 CrashLoopBackOff。',
    '[SRC] localhost:8080 常见于 kubectl 未加载 $HOME/.kube/config；init/join 卡住查 hosts、6443、网络、Token、CA hash、Swap、kubelet 和 Containerd；重复初始化或加入可在确认后使用 kubeadm reset；CrashLoopBackOff 必须结合 describe、logs 和容器命令。\n[OPS] kubeadm reset、kubectl delete、强制删除 Pod、修改防火墙或重装集群都是有影响的动作，不能作为无证据的通用修复。\n[VERIFY] 记录 reset 前状态，修复后检查节点、系统 Pod、事件、运行时和业务访问。',
    ['localhost:8080', 'kubeadm reset', '6443', 'CrashLoopBackOff', 'kubelet'], 'HIGH'),
  entry('automation', 'Kubernetes 部署与运维自动化工作流', '10 / 自动化', '将环境检查、运行时、控制面、CNI、节点加入和验证组织成可复用流程。',
    '[SRC] 工作流：环境检查 -> 主机配置 -> Containerd -> kubeadm/kubelet/kubectl -> init -> kubeconfig -> CNI -> join -> get node/pod -> 业务验证。\n[OPS] 脚本应参数化版本、IP、endpoint、CIDR、镜像仓库和 join 命令；每一步记录退出码和证据，动态 token 不写死。生产执行需要快照/备份、审批、分批和回滚。\n[VERIFY] 先在隔离集群完成最小 Nginx 或测试工作负载，再扩大到多节点和业务资源。',
    ['automation', 'runbook', 'Nginx', 'verification', 'rollback'], 'APPROVAL_REQUIRED')
]

export const kubernetesFoundationRules = Object.freeze([
  { id: 'K8S-001', trigger: 'kubectl 无法连接', sequence: ['kubeconfig', 'API Server', '6443', 'network', 'kubelet/control plane logs'] },
  { id: 'K8S-002', trigger: 'Node NotReady', sequence: ['describe node', 'conditions/events', 'kubelet', 'containerd', 'CNI', 'Linux network'] },
  { id: 'K8S-003', trigger: 'Pod 异常', sequence: ['get', 'describe/events', 'logs', 'image/scheduler/network/storage', 'runtime/Linux'] },
  { id: 'K8S-004', trigger: '集群部署', sequence: ['preflight', 'runtime/version', 'init', 'kubeconfig', 'CNI', 'join', 'verify'] }
])
