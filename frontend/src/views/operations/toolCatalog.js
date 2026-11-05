const safeName = /^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}$/
const safeNamespace = /^[a-z0-9][a-z0-9.-]{0,62}$/
const safeNumber = /^[0-9]{1,6}$/
const safeHost = /^[a-zA-Z0-9][a-zA-Z0-9.:-]{0,252}$/
const safeUrl = /^https?:\/\/[a-zA-Z0-9][a-zA-Z0-9._~:/?#[\]@!$&'()*+,;=%-]{0,1023}$/

const parameter = (id, label, pattern, defaultValue = '') => ({ id, label, pattern, defaultValue })
const tool = definition => ({ riskLevel: 'LOW', readOnly: true, requireConfirm: false, parameters: [], commands: [], evidence: [], ...definition })

export const operationToolGroups = [
  { id: 'service-diagnostics', label: 'SERVICE DIAGNOSTICS / 服务诊断', shortLabel: 'SERVICE DIAGNOSTICS', items: [
    tool({ id: 'service-http-check', label: 'HTTP / API 检查', title: 'HTTP API AVAILABILITY', subtitle: '仅检查管理员授权目标，支持状态码和受限 JSON 字段断言', capability: 'SERVICE_HTTP_CHECK', executionType: 'service-probe', readOnly: true, evidence: ['目标 ID', '状态码', '总耗时', '受限断言'] }),
    tool({ id: 'service-certificate-check', label: 'HTTPS 证书检查', title: 'HTTPS CERTIFICATE CHECK', subtitle: '检查授权 HTTPS 目标的有效期、主机名和信任链', capability: 'SERVICE_CERTIFICATE_CHECK', executionType: 'service-probe', readOnly: true, evidence: ['颁发者', '有效期', '域名匹配', '信任链'] }),
    tool({ id: 'config-diff', label: '配置差异检查', title: 'CONFIGURATION DIFF', subtitle: '在当前浏览器本地比较配置文本，敏感值默认脱敏', capability: 'CONFIG_DIFF', executionType: 'local-browser', readOnly: true, evidence: ['新增行', '删除行', '敏感值脱敏', '差异摘要'] })
  ] },
  { id: 'cloud-engineering', label: 'CLOUD ENGINEERING / 云运维工程', shortLabel: 'CLOUD ENGINEERING', items: [
    tool({ id: 'docker-compose-status', label: 'Compose 项目巡检', title: 'DOCKER COMPOSE STATUS', subtitle: '读取目标主机的 Compose 项目清单', capability: 'DOCKER_COMPOSE_STATUS', commands: ['docker compose ls --all --format json'], evidence: ['目标主机', '项目名称', '运行状态'], prerequisite: '远程主机安装 Docker Compose 插件；当前账号可访问 Docker。', troubleshooting: '命令不存在：检查 Compose 插件；权限拒绝：检查 Docker 访问授权；空清单不代表其他主机没有容器。' }),
    tool({ id: 'harbor-browser', label: 'Harbor 项目与镜像', title: 'HARBOR REGISTRY BROWSER', subtitle: '浏览已配置 Harbor 的真实项目与镜像仓库', capability: 'HARBOR_READ', evidence: ['项目', '仓库', '镜像数量'], prerequisite: '后端配置 Harbor URL；私有项目需要只读账号。' }),
    tool({ id: 'harbor-endpoint-check', label: 'Harbor 健康检查', title: 'HARBOR ENDPOINT CHECK', subtitle: '读取 Harbor API 健康状态，不登录、不修改仓库', capability: 'HARBOR_ENDPOINT_CHECK', parameters: [parameter('host', 'Harbor 主机', safeHost)], commands: ['curl --fail --silent --show-error --max-time 10 https://{host}/api/v2.0/health'], evidence: ['HTTP 状态', 'Harbor 健康响应', '目标主机'], prerequisite: '远程主机可访问 Harbor；生产环境优先 HTTPS。', troubleshooting: '超时查 DNS/网络；证书错误查 CA；401/403 查访问入口；不要用关闭 TLS 校验掩盖证书问题。' }),
    tool({ id: 'containerd-registry-inspect', label: 'Containerd 仓库检查', title: 'CONTAINERD REGISTRY INSPECTOR', subtitle: '查看 Namespace、镜像和插件状态', capability: 'CONTAINERD_REGISTRY_INSPECT', parameters: [parameter('namespace', 'Containerd Namespace', safeNamespace, 'k8s.io')], commands: ['ctr namespaces list', 'ctr -n {namespace} images list', 'ctr plugins ls'], evidence: ['Namespace', '镜像引用与 Digest', 'Containerd 插件', '目标节点'], prerequisite: '目标 Linux 主机安装 Containerd/ctr；当前用户有只读 socket 权限。', troubleshooting: '看不到镜像先查 Namespace；socket 拒绝查用户组和 rootless 配置；pull/push 失败继续检查 Harbor TLS、hosts.toml、认证和平台。' }),
    tool({ id: 'containerd-config-check', label: 'Containerd 注册配置', title: 'CONTAINERD REGISTRY CONFIG', subtitle: '检查 registry 配置路径与 hosts.toml 文件，不输出凭据内容', capability: 'CONTAINERD_CONFIG_READ', commands: ['containerd config dump', 'find /etc/containerd/certs.d -maxdepth 3 -name hosts.toml -print'], evidence: ['Containerd 配置路径', 'Registry hosts.toml 路径', '目标节点'], prerequisite: '目标 Linux 主机安装 Containerd；当前账号可读取配置目录。', troubleshooting: '找不到 hosts.toml 时检查 config_path；不要把密码写入 hosts.toml，使用受控凭据或 imagePullSecret。' }),
    tool({ id: 'helm-releases', label: 'Helm 发布清单', title: 'HELM RELEASES', subtitle: '读取指定命名空间的发布状态，最多 100 条', capability: 'HELM_RELEASES', parameters: [parameter('namespace', 'Namespace', safeNamespace, 'default')], commands: ['helm list -n {namespace} --max 100 -o json'], evidence: ['集群 Context', 'Release 与 Revision', 'Chart 与状态', '本页最多 100 条，非全量盘点'], prerequisite: '目标主机安装 Helm，并配置已授权的 Kubernetes Context。', troubleshooting: 'Forbidden：检查命名空间授权；列表为空：确认 Context 和命名空间；达到 100 条时需进一步分页核查。' }),
    tool({ id: 'k8s-storage', label: 'K8s 存储巡检', title: 'KUBERNETES STORAGE', subtitle: '读取 PVC 与 StorageClass，辅助定位挂载和供给问题', capability: 'K8S_STORAGE', parameters: [parameter('namespace', 'Namespace', safeNamespace, 'default')], commands: ['kubectl get pvc -n {namespace} -o wide', 'kubectl get storageclass'], evidence: ['PVC 状态', '容量与访问模式', 'StorageClass', '目标命名空间'], prerequisite: '目标主机安装 kubectl；允许读取 PVC 和集群级 StorageClass。', troubleshooting: 'PVC Pending 仅是现象，继续核查事件；StorageClass Forbidden 表示权限不足，不能判断存储不存在。' }),
    tool({ id: 'k8s-rbac-check', label: 'K8s 读取权限检查', title: 'KUBERNETES RBAC CHECK', subtitle: '检查当前身份是否能读取 Pod 和日志', capability: 'K8S_RBAC_CHECK', parameters: [parameter('namespace', 'Namespace', safeNamespace, 'default')], commands: ['kubectl auth can-i get pods -n {namespace}', 'kubectl auth can-i get pods --subresource=log -n {namespace}'], evidence: ['当前 Context 与身份', '目标命名空间', 'Pod 读取授权', '日志读取授权'], prerequisite: '使用目标集群的实际运维身份，不切换为管理员绕过检查。', troubleshooting: '返回 no 是授权结果；工具遇到非零退出码会停止，前一步拒绝时后续权限仍待检查。' }),
    tool({ id: 'mesh-status', label: '服务网格组件巡检', title: 'SERVICE MESH STATUS', subtitle: '检查网格命名空间中的 Pod 与 Service', capability: 'MESH_STATUS', parameters: [parameter('namespace', '网格 Namespace', safeNamespace, 'istio-system')], commands: ['kubectl get pods,services -n {namespace} -o wide'], evidence: ['网格命名空间', 'Pod Ready', '重启次数', 'Service'], prerequisite: '集群已部署网格；按实际部署填写命名空间。', troubleshooting: 'Pod Ready 不能证明业务链路正常；还需结合流量、日志与追踪验证。未部署网格时不要把空结果解释成故障。' }),
    tool({ id: 'terraform-environment', label: 'Terraform 环境检查', title: 'TERRAFORM ENVIRONMENT', subtitle: '确认远程主机 Terraform 版本，不执行资源变更', capability: 'TERRAFORM_ENVIRONMENT', commands: ['terraform version -json'], evidence: ['目标主机', 'Terraform 版本', '平台信息'], prerequisite: '远程主机已安装 Terraform；此工具不代表云账号已连接。', troubleshooting: 'command not found：检查安装和 PATH。资源盘点、plan/apply 与云凭据接入尚需独立配置。' })
  ] },
  { id: 'system', label: 'SYSTEM TOOLS / 系统工具', shortLabel: 'SYSTEM TOOLS', items: [
    tool({ id: 'processes', label: '进程诊断', title: 'PROCESS DIAGNOSTICS', subtitle: '本机与远程进程证据检查', capability: 'PROCESS_LIST' }),
    tool({ id: 'hardware', label: '硬件设备清单', title: 'HARDWARE INVENTORY', subtitle: '主机硬件与系统摘要', capability: 'HARDWARE_INFO', commands: ['uname -a', 'lscpu', 'lsblk'] }),
    tool({ id: 'terminal', label: '受控终端', title: 'CONTROLLED TERMINAL', subtitle: '通过 Operations Bridge 打开受审计会话', capability: 'LOCAL_PTY', riskLevel: 'HIGH', readOnly: false, requireConfirm: true }),
    tool({ id: 'commands', label: '命令模板', title: 'COMMAND TEMPLATES', subtitle: '受控命令定义与参数校验', capability: 'COMMAND_EXEC', riskLevel: 'MEDIUM' }),
    tool({ id: 'packages', label: '软件包查询', title: 'PACKAGE INSPECTOR', subtitle: '远程软件包与版本检查', capability: 'PACKAGE_MANAGER', commands: ['rpm -qa', 'dpkg -l'] })
  ] },
  { id: 'kubernetes', label: 'KUBERNETES / 集群工具', shortLabel: 'KUBERNETES', items: [
    tool({ id: 'k8s-resources', label: 'K8s 资源检查', title: 'KUBERNETES RESOURCE INSPECTOR', subtitle: '查看资源、状态、事件与描述信息', capability: 'K8S_READ', parameters: [parameter('namespace', 'Namespace', safeNamespace, 'default'), parameter('resource', '资源类型', safeName, 'pod'), parameter('name', '资源名称', safeName)], commands: ['kubectl get {resource} {name} -n {namespace} -o wide', 'kubectl describe {resource} {name} -n {namespace}'], evidence: ['目标集群与 Context', 'Namespace 与资源名称', '资源状态和 Conditions', 'Events 与最近变更'] }),
    tool({ id: 'k8s-logs', label: 'K8s Pod 日志', title: 'KUBERNETES LOG VIEWER', subtitle: '读取当前和上一次容器日志', capability: 'K8S_LOGS', parameters: [parameter('namespace', 'Namespace', safeNamespace, 'default'), parameter('pod', 'Pod', safeName), parameter('container', 'Container', safeName), parameter('tail', '日志行数', safeNumber, '200')], commands: ['kubectl logs {pod} -n {namespace} {containerFlag} --tail={tail}', 'kubectl logs {pod} -n {namespace} {containerFlag} --previous --tail={tail}'], evidence: ['Pod/Container 身份', '当前与 previous 日志', '时间范围', '退出码与重启次数'] }),
    tool({ id: 'k8s-events', label: 'K8s 事件时间线', title: 'KUBERNETES EVENT TIMELINE', subtitle: '查看调度、拉取、探针和挂载事件', capability: 'K8S_EVENTS', parameters: [parameter('namespace', 'Namespace', safeNamespace, 'default')], commands: ['kubectl get events -n {namespace} --sort-by=.metadata.creationTimestamp'], evidence: ['Reason', 'Object', 'Message', '发生时间'] })
  ] },
  { id: 'docker', label: 'DOCKER / 容器工具', shortLabel: 'DOCKER', items: [
    tool({ id: 'docker-containers', label: 'Docker 容器检查', title: 'DOCKER CONTAINER INSPECTOR', subtitle: '容器状态、健康检查、端口和挂载', capability: 'DOCKER_READ', parameters: [parameter('container', '容器', safeName)], commands: ['docker ps -a --no-trunc', 'docker inspect {container}'], evidence: ['Container ID 与镜像 Digest', '状态、退出码和健康检查', '端口、网络和挂载'] }),
    tool({ id: 'docker-logs', label: 'Docker 容器日志', title: 'DOCKER LOG VIEWER', subtitle: '读取指定容器的最近日志', capability: 'DOCKER_LOGS', parameters: [parameter('container', '容器', safeName), parameter('tail', '日志行数', safeNumber, '200')], commands: ['docker logs --timestamps --tail {tail} {container}'], evidence: ['Container ID', '日志时间范围', '标准输出与错误输出'] }),
    tool({ id: 'docker-images', label: 'Docker 镜像检查', title: 'DOCKER IMAGE INSPECTOR', subtitle: '镜像层、Digest、标签和构建信息', capability: 'DOCKER_IMAGES', parameters: [parameter('image', '镜像', safeName)], commands: ['docker image ls --digests', 'docker image inspect {image}'], evidence: ['RepoDigest', '创建时间', '镜像层与配置', '架构和入口命令'] })
  ] },
  { id: 'remote-observability', label: 'REMOTE OBSERVABILITY / 远程观测', shortLabel: 'REMOTE OPS', items: [
    tool({ id: 'host-health', label: 'Linux 主机巡检', title: 'REMOTE HOST HEALTH', subtitle: 'CPU、内存、磁盘、负载和监听端口检查', capability: 'HOST_HEALTH', commands: ['uptime', 'free -h', 'df -hT', 'ss -lntup'], evidence: ['主机身份与时间', 'Load/CPU/内存/Swap', '磁盘容量与 inode', '监听端口'] }),
    tool({ id: 'system-logs', label: 'Systemd 日志诊断', title: 'SYSTEMD JOURNAL DIAGNOSTICS', subtitle: '读取服务状态和指定范围日志', capability: 'SYSTEM_LOGS', parameters: [parameter('service', '服务名称', safeName), parameter('lines', '日志行数', safeNumber, '200')], commands: ['systemctl status {service} --no-pager', 'journalctl -u {service} -n {lines} --no-pager'], evidence: ['Unit 状态', '启动时间与 PID', '错误日志与退出原因'] }),
    tool({ id: 'http-probe', label: 'HTTP/TLS 探测', title: 'HTTP AND TLS PROBE', subtitle: '检查 DNS、HTTP 状态、证书和响应链路', capability: 'HTTP_PROBE', parameters: [parameter('url', 'URL', safeUrl, 'https://example.com')], commands: ['curl -vkI --connect-timeout 5 {url}'], evidence: ['解析地址', 'TLS 握手与证书', 'HTTP 状态和响应头', '连接耗时'] }),
    tool({ id: 'dns-probe', label: 'DNS 解析检查', title: 'DNS RESOLUTION PROBE', subtitle: '检查域名记录与解析链路', capability: 'DNS_PROBE', parameters: [parameter('host', '域名', safeHost, 'example.com')], commands: ['dig {host}', 'nslookup {host}'], evidence: ['查询服务器', '记录类型和值', 'TTL 与响应状态'] }),
    tool({ id: 'service-restart', label: '受控服务重启', title: 'CONTROLLED SERVICE RESTART', subtitle: '经过确认、验证和审计的服务重启', capability: 'SERVICE_RESTART', riskLevel: 'HIGH', readOnly: false, requireConfirm: true, parameters: [parameter('service', '服务名称', safeName)], commands: ['systemctl restart {service}'], evidence: ['重启前状态', '审批人与影响范围', '执行退出码', '重启后健康验证'], rollback: '恢复变更前配置；服务未恢复时按 Runbook 切换备用实例或回退版本。' })
  ] },
  { id: 'network', label: 'NETWORK / 网络工具', shortLabel: 'NETWORK', items: [
    tool({ id: 'tunnels', label: 'SSH 隧道', title: 'SSH TUNNEL CONTROL', subtitle: '本地、远程与 SOCKS 转发', capability: 'SSH_TUNNEL', riskLevel: 'MEDIUM', readOnly: false, requireConfirm: true }),
    tool({ id: 'ports', label: '端口占用列表', title: 'OPEN PORTS', subtitle: '监听端口与关联进程', capability: 'PORTS', commands: ['ss -lntup'] }),
    tool({ id: 'network-scan', label: '受控网络扫描', title: 'NETWORK SCANNER', subtitle: '对明确授权网段进行主机发现', capability: 'NETWORK_SCAN', riskLevel: 'MEDIUM', requireConfirm: true }),
    tool({ id: 'capture', label: '数据包捕获', title: 'PACKET CAPTURE', subtitle: '受限时长与过滤条件的流量取证', capability: 'PACKET_CAPTURE', riskLevel: 'HIGH', requireConfirm: true })
  ] },
  { id: 'agent-operations', label: 'AGENT OPERATIONS / 智能体工具', shortLabel: 'AGENT TOOLS', items: [
    tool({ id: 'log-search', label: '日志检索', title: 'LOG SEARCH', subtitle: '按服务、关键词和时间范围检索系统与应用日志', capability: 'LOG_SEARCH', parameters: [parameter('service', '服务名称', safeName), parameter('keyword', '关键词', /^[a-zA-Z0-9][a-zA-Z0-9 ._:/-]{0,127}$/, 'error'), parameter('lines', '行数', safeNumber, '200')], commands: ["journalctl -u {service} -n {lines} --no-pager | grep -i -- '{keyword}'"], evidence: ['时间范围', '匹配行数', '错误频次', '原始日志引用'] }),
    tool({ id: 'network-diagnostics', label: '网络诊断', title: 'NETWORK DIAGNOSTICS', subtitle: 'Ping、端口连通性和 DNS 解析证据采集', capability: 'NETWORK_DIAGNOSTICS', parameters: [parameter('host', '主机或域名', safeHost), parameter('port', '端口', safeNumber, '443')], commands: ['ping -c 3 {host}', 'nc -vz -w 5 {host} {port}', 'dig {host}'], evidence: ['连通性', '端口握手', 'DNS 解析地址', '耗时和丢包'] }),
    tool({ id: 'alerts-query', label: '告警查询', title: 'ALERT QUERY', subtitle: '读取 Prometheus 或告警平台中的当前告警', capability: 'ALERT_QUERY', parameters: [parameter('status', '告警状态', safeName, 'firing')], commands: ['curl --fail --silent --get http://alertmanager:9093/api/v2/alerts?active={status}'], evidence: ['告警规则', '标签', '触发时间', '关联目标'] }),
    tool({ id: 'alerts-suppress', label: '告警抑制申请', title: 'ALERT SUPPRESSION REQUEST', subtitle: '生成需人工审批的告警抑制申请', capability: 'ALERT_SUPPRESS', riskLevel: 'HIGH', readOnly: false, requireConfirm: true, parameters: [parameter('alert', '告警名称', safeName)], commands: ['# 需审批后由告警平台 API 创建 silence: {alert}'], evidence: ['申请人', '抑制范围', '开始与结束时间', '审批记录'], rollback: '在告警平台删除对应 silence，并核对告警恢复。' }),
    tool({ id: 'knowledge-retrieval', label: '知识库检索', title: 'KNOWLEDGE RETRIEVAL / RAG', subtitle: '检索运维手册、故障案例和 Runbook 作为诊断依据', capability: 'KNOWLEDGE_RETRIEVAL', parameters: [parameter('keyword', '检索问题', /^[a-zA-Z0-9][a-zA-Z0-9 ._:/-]{0,127}$/, 'service unavailable'), parameter('topK', '返回数量', safeNumber, '5')], commands: ["smartops knowledge search --query '{keyword}' --top-k {topK}"], evidence: ['知识 ID', '命中片段', '来源与版本', '相关性分数'] }),
    tool({ id: 'database-readonly', label: '数据库只读查询', title: 'DATABASE READ-ONLY QUERY', subtitle: '查看连接数、慢 SQL 和会话状态，禁止写操作', capability: 'DATABASE_READONLY', parameters: [parameter('metric', '指标', safeName, 'connections')], commands: ['smartops db inspect --metric {metric} --read-only'], evidence: ['数据库实例', '查询时间', '只读标记', '脱敏结果'] }),
    tool({ id: 'prometheus-query', label: 'Prometheus 指标查询', title: 'PROMETHEUS QUERY', subtitle: '查询 PromQL 指标并保留时间范围与返回摘要', capability: 'PROMETHEUS_QUERY', parameters: [parameter('query', 'PromQL', /^[a-zA-Z0-9_:.{}=," -]{1,180}$/, 'up'), parameter('range', '时间范围', safeNumber, '15')], commands: ['smartops metrics query --promql "{query}" --minutes {range} --read-only'], evidence: ['PromQL', '时间范围', '样本数量', '聚合结果'] }),
    tool({ id: 'grafana-dashboard', label: 'Grafana 看板查询', title: 'GRAFANA DASHBOARD QUERY', subtitle: '读取看板面板摘要与指标状态，不修改看板', capability: 'GRAFANA_DASHBOARD', parameters: [parameter('dashboard', '看板标识', safeName), parameter('panel', '面板标识', safeName, 'overview')], commands: ['smartops grafana panel --dashboard {dashboard} --panel {panel} --read-only'], evidence: ['看板版本', '面板名称', '查询时间', '指标摘要'] }),
    tool({ id: 'loki-log-query', label: 'Loki 日志查询', title: 'LOKI LOG QUERY', subtitle: '按标签和 LogQL 查询容器日志并统计错误频次', capability: 'LOKI_LOG_QUERY', parameters: [parameter('selector', '标签选择器', /^[a-zA-Z0-9_{}=," .:-]{1,160}$/, '{app="api"}'), parameter('lines', '行数', safeNumber, '200')], commands: ['smartops loki query --selector "{selector}" --limit {lines} --read-only'], evidence: ['LogQL', '时间范围', '错误频次', '日志来源'] }),
    tool({ id: 'mysql-slow-query', label: 'MySQL 慢 SQL', title: 'MYSQL SLOW QUERY', subtitle: '只读查看慢查询摘要、执行次数和平均耗时', capability: 'MYSQL_SLOW_QUERY', parameters: [parameter('database', '数据库', safeName), parameter('limit', '数量', safeNumber, '20')], commands: ['smartops db slow-queries --database {database} --limit {limit} --read-only'], evidence: ['数据库实例', 'SQL 指纹', '执行次数', '平均耗时'] }),
    tool({ id: 'k8s-diagnose', label: 'Kubernetes 资源诊断', title: 'KUBERNETES DIAGNOSTICS', subtitle: '串联工作负载、事件、Service 和 Endpoint 只读证据', capability: 'K8S_DIAGNOSE', parameters: [parameter('namespace', 'Namespace', safeNamespace, 'default'), parameter('name', '资源名称', safeName)], commands: ['kubectl get pod,deploy,svc,endpoints -n {namespace} -l app={name} -o wide', 'kubectl get events -n {namespace} --sort-by=.lastTimestamp'], evidence: ['工作负载状态', '事件时间线', 'Service Endpoint', 'Pod Ready'] })
  ] }
]

export const operationTools = operationToolGroups.flatMap(group => group.items)
export function findOperationTool(id) { return operationTools.find(item => item.id === id) || null }

export function previewOperationToolCommands(toolDefinition, values = {}) {
  if (!toolDefinition) return []
  const normalized = {}
  const allowed = new Set((toolDefinition.parameters || []).map(item => item.id))
  for (const key of Object.keys(values || {})) {
    if (!allowed.has(key)) throw new Error(`参数 ${key} 不属于该工具`)
  }
  for (const item of toolDefinition.parameters || []) {
    const value = String(values[item.id] ?? item.defaultValue ?? '').trim()
    if (value && !item.pattern.test(value)) throw new Error(`参数 ${item.id} 不符合安全规则`)
    normalized[item.id] = value
  }
  normalized.containerFlag = normalized.container ? `-c ${normalized.container}` : ''
  return toolDefinition.commands.map(command => command.replace(/\{([a-zA-Z]+)\}/g, (_, key) => normalized[key] ?? '').replace(/\s+/g, ' ').trim())
}
