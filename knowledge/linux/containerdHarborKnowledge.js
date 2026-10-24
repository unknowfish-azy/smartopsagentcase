// Containerd, OCI runtime and Harbor operations reference pack.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: `containerd.${id}`,
  domain: 'linux', platform: 'Linux / Containerd', service: 'containerd',
  type: 'CONTAINER RUNTIME OPERATIONS', title, section, summary, content,
  tags: ['Containerd', 'ctr', 'OCI', ...tags], source: 'User-provided Containerd, Harbor and OCI material',
  version: 'Reference pack', risk, executionAllowed: false
})

export const containerdHarborEntries = [
  entry('architecture', 'Containerd、OCI、runC 与 Kubernetes 分层', '01 / 基础架构', 'Containerd 管理容器生命周期，runC 按 OCI 规范创建 Linux 隔离进程，Kubernetes 通过 CRI 接入。',
    '[SRC] 常见链路：Kubelet -> CRI -> Containerd -> OCI runtime/runC -> Linux Namespace、Cgroup、RootFS -> 进程。Docker Engine、Containerd 和 Kubernetes 属于不同层级。\n[OPS] 排障时不要把 Containerd 当作 Docker 的完全替代；先确认调用层、运行时、socket 和版本兼容性。OCI 是标准生态，runC 是常见实现。\n[VERIFY] 分别核对 kubectl/kubelet、containerd、ctr 和 runc 的版本与服务状态。',
    ['OCI', 'runC', 'runc', 'CRI', 'Kubernetes', 'Docker', 'runtime']),
  entry('install-service', 'Containerd 安装、配置与 systemd 验证', '02 / 安装', 'DNF 或二进制安装后生成 config.toml，启动 systemd 服务并用 ctr version 验证。',
    '[SRC] 常用证据：dnf list installed | grep containerd、containerd config default、systemctl status containerd、journalctl -u containerd、ctr version、runc -V。默认配置通常为 /etc/containerd/config.toml。\n[OPS] 指定版本前确认发行版、架构、CRI/CNI 需求和兼容矩阵；不要无条件覆盖现有配置。二进制安装还要核对 PATH、containerd.service、runC、CNI 和权限。enabled 是当前开机状态，preset 是策略预设。\n[VERIFY] 安装后验证服务、socket、配置加载、客户端/服务端版本和最小镜像操作。',
    ['dnf', 'binary install', 'systemd', 'systemctl', 'journalctl', 'config.toml', 'version'], 'APPROVAL_REQUIRED'),
  entry('image-lifecycle', 'Containerd 镜像管理与平台选择', '03 / Image', '使用 ctr 管理镜像的 pull、list、tag、mount、export、import、push 和 remove。',
    '[SRC] ctr i/ images ls 查看，pull 拉取，tag 增加引用，export/import 迁移，mount/unmount 查看文件系统，rm 删除。多平台操作需要明确 --platform linux/amd64、linux/arm64 或 --all-platforms，并保持 pull/export/push 的平台意图一致。\n[OPS] 删除、推送、挂载和导出前确认完整镜像引用、目标 namespace、磁盘空间和敏感层；镜像 tag 只是引用变化，不会重新下载。\n[VERIFY] 每个动作后用 ctr -n <namespace> images ls、digest、平台信息和目标文件校验。',
    ['image', 'pull', 'push', 'tag', 'mount', 'unmount', 'export', 'import', 'platform'], 'APPROVAL_REQUIRED'),
  entry('container-task', 'Image、Container、Task 三层对象', '04 / Container 与 Task', 'Image 是只读模板，Container 是静态定义，Task 是实际运行的进程实例。',
    '[SRC] ctr c create IMAGE ID 只创建 Container；ctr t start -d ID 启动 Task；ctr t ps ID 查看进程；ctr t kill、pause、resume、rm 管理任务；ctr t exec --exec-id ID -t ID /bin/sh 进入运行中的容器。ctr run 可将创建和运行合并。\n[OPS] Container 存在而 Task 不存在可能是正常的静态状态；Task STOPPED 仍可能保留对象。exec 前确认 Task 运行、exec-id 唯一以及镜像存在 /bin/sh 或 /bin/bash。\n[VERIFY] 按 Image -> Container -> Task -> Linux PID 逐层检查，结合 ps、pstree、/proc 和运行时日志。',
    ['image', 'container', 'task', 'ctr c create', 'ctr t start', 'ctr t exec', 'PID', 'PPID']),
  entry('namespace', 'Containerd Namespace 隔离与排障', '05 / Namespace', 'Namespace 对镜像、Container 和 Task 做逻辑隔离，是 ctr 看不到对象时的一级排查变量。',
    '[SRC] ctr ns ls 查看，ctr ns create NAME 创建，ctr ns rm NAME 删除；ctr -n NAME i ls、ctr -n NAME t ls 在指定空间操作。不指定 -n 时通常使用 default。Kubernetes 常见专用 namespace 需要结合实际配置确认。\n[OPS] 不要因 default 看不到镜像就重复 pull；先列出 namespace 并在目标空间查询。删除 namespace 会影响其中对象，属于高风险动作。\n[VERIFY] 记录命令中的 namespace、镜像 digest、Container ID 和 Task 状态，确保前后操作处于同一空间。',
    ['namespace', 'default', 'k8s.io', 'ctr -n', 'isolation'], 'APPROVAL_REQUIRED'),
  entry('registry-config', 'Containerd Registry、certs.d 与 hosts.toml', '06 / Registry 配置', '通过 config.toml 的 registry.config_path 和 certs.d/hosts.toml 连接 Harbor 或其他 OCI Registry。',
    '[SRC] 常见链路：/etc/containerd/config.toml -> [plugins.cri.registry].config_path -> /etc/containerd/certs.d/registry/hosts.toml。hosts.toml 可声明 server、host URL 和 capabilities。修改后通常需要重启或按版本支持的方式重新加载。\n[OPS] 先确认 registry 主机名解析、HTTP/HTTPS、证书、capabilities、代理和 Containerd 版本；--plain-http 只能用于明确的 HTTP Registry，不能机械添加。生产环境优先 TLS，避免将认证信息写入命令历史。\n[VERIFY] 用 getent hosts、curl、配置检查、journalctl 和最小 pull 验证解析、协议、认证和镜像路径。',
    ['registry', 'Harbor', 'config_path', 'certs.d', 'hosts.toml', 'HTTP', 'HTTPS', '--plain-http'], 'HIGH'),
  entry('harbor', 'Harbor 安装、项目与镜像生命周期', '07 / Harbor', 'Harbor 提供企业私有 OCI Registry，项目权限决定 pull/push 能力。',
    '[SRC] Harbor 部署通常需要 hostname、HTTP/HTTPS、管理员配置、足够磁盘和 Docker/Compose 依赖；项目可公开或私有。Containerd 侧先 tag 为 harbor.example/project/image:tag，再 push；pull 时使用同一完整引用。\n[OPS] Harbor 安装、LVM 扩容、项目权限、管理员密码和 push 都可能改变系统或暴露凭据，需审批。课程中的明文密码和 HTTP 仅适合隔离实验；生产应使用 TLS、最小权限和安全凭据。\n[VERIFY] 检查 Harbor 服务、项目、权限、磁盘、DNS、curl 响应、镜像 digest 和 pull/push 审计记录。',
    ['Harbor', 'registry', 'project', 'library', 'push', 'pull', 'LVM', 'XFS'], 'HIGH'),
  entry('troubleshooting', 'Containerd 端到端故障树', '08 / 故障诊断', '按服务、配置、Namespace、Image、Container、Task、Runtime、进程、网络和 Registry 逐层定位。',
    '[OPS] ctr version 失败先查 systemctl status、journalctl 和 /run/containerd；镜像看不到先查 ctr ns ls 和 ctr -n；pull/push 失败依次查主机名解析、网络、协议、证书、hosts.toml、认证、项目、tag 和平台；Container 创建成功但 Task 启动失败要区分 rootfs、runtime、ENTRYPOINT/CMD 和进程立即退出。\n[VERIFY] 采集原始报错、版本、namespace、完整镜像引用、config.toml 片段、hosts.toml、journalctl、curl/getent 和 Task/PID 状态。不要证据不足就重装或删除对象。',
    ['troubleshooting', 'journalctl', 'DNS', 'rootfs', 'ENTRYPOINT', 'socket', 'process']),
  entry('automation', 'Containerd 自动化运维工作流', '09 / 自动化', '将安装、镜像、容器、任务和 Harbor 操作组织为可验证的分层流程。',
    '[SRC] 标准链路：确认环境与版本 -> 服务与配置 -> Namespace -> Image -> Container -> Task -> Runtime/Process -> Network/Registry -> 日志与验证。\n[OPS] 脚本应显式接收 namespace、镜像引用、平台和 registry 协议；每一步检查退出码并记录证据。删除镜像、Container、Task 或 Namespace、重启服务、修改仓库和扩容磁盘必须有审批、目标预览和回滚/恢复方案。\n[VERIFY] 在单机或隔离 namespace 先执行，完成最小 pull/create/start/exec/stop 流程后再扩展到 Kubernetes 或多节点。',
    ['automation', 'runbook', 'verification', 'rollback', 'Kubernetes'], 'APPROVAL_REQUIRED')
]

export const containerdHarborRules = Object.freeze([
  { id: 'CONTAINERD-001', trigger: 'ctr 看不到镜像', sequence: ['list namespaces', 'select namespace', 'list images', 'verify digest/platform'] },
  { id: 'CONTAINERD-002', trigger: '容器起不来', sequence: ['service', 'config', 'namespace', 'image', 'container', 'task', 'runtime', 'process'] },
  { id: 'CONTAINERD-003', trigger: 'Harbor pull/push 失败', sequence: ['DNS', 'network', 'protocol/TLS', 'config_path', 'hosts.toml', 'project/auth', 'tag/platform'] },
  { id: 'CONTAINERD-004', trigger: '生产变更', sequence: ['preview', 'approval', 'least privilege', 'execute', 'audit', 'verify/rollback'] }
])
