const toolDefinitions = [
  ['helm', 'Helm', 'Kubernetes 应用包管理与发布', 'FOUNDATION', 'P0', ['Kubernetes', 'Deployment', 'Service'], ['Chart', 'Values', '升级', '回滚']],
  ['kustomize', 'Kustomize', '多环境 Kubernetes 配置组合', 'FOUNDATION', 'P0', ['Kubernetes', 'YAML'], ['Base', 'Overlay', 'Patch']],
  ['kind', 'kind', '本地 Kubernetes 实验集群', 'FOUNDATION', 'P0', ['Kubernetes', 'Containerd'], ['集群创建', '节点模拟', '故障实验']],
  ['prometheus', 'Prometheus', '指标采集与 PromQL 查询', 'OBSERVABILITY', 'P0', ['Kubernetes', '监控'], ['Metrics', 'PromQL', '告警规则']],
  ['grafana', 'Grafana', '监控看板与运维可视化', 'OBSERVABILITY', 'P0', ['Prometheus', 'Loki'], ['Dashboard', '变量', '告警面板']],
  ['loki', 'Loki', '云原生日志聚合与 LogQL 查询', 'OBSERVABILITY', 'P1', ['Kubernetes', 'Grafana'], ['日志标签', 'LogQL', '日志关联']],
  ['opentelemetry', 'OpenTelemetry', '指标、日志、链路统一采集标准', 'OBSERVABILITY', 'P1', ['Prometheus', 'Tempo', 'Jaeger'], ['Trace', 'Span', '采集器']],
  ['argocd', 'Argo CD', 'GitOps 持续交付与集群同步', 'DELIVERY', 'P0', ['Git', 'Helm', 'Kustomize'], ['同步', '漂移', '回滚']],
  ['argo-rollouts', 'Argo Rollouts', '蓝绿和金丝雀发布', 'DELIVERY', 'P1', ['Argo CD', 'Service'], ['灰度', '分析指标', '自动回滚']],
  ['harbor', 'Harbor', '企业镜像仓库与制品管理', 'SUPPLY_CHAIN', 'P0', ['Containerd', 'Docker'], ['项目', '镜像策略', '复制']],
  ['trivy', 'Trivy', '镜像、文件系统和 IaC 漏洞扫描', 'SECURITY', 'P0', ['Harbor', 'Kubernetes'], ['CVE', 'SBOM', '配置扫描']],
  ['velero', 'Velero', 'Kubernetes 资源和卷备份恢复', 'RELIABILITY', 'P1', ['Kubernetes', 'PV', 'PVC'], ['备份', '恢复', '灾难演练']],
  ['cilium', 'Cilium', '基于 eBPF 的 CNI 与网络策略', 'NETWORKING', 'P1', ['CNI', 'NetworkPolicy'], ['eBPF', '网络策略', '服务可视化']],
  ['cert-manager', 'cert-manager', 'Kubernetes TLS 证书自动签发和续期', 'SECURITY', 'P1', ['Ingress', 'Gateway API', 'TLS'], ['Issuer', 'Certificate', '续期']],
  ['terraform', 'Terraform / OpenTofu', '基础设施即代码和资源编排', 'PLATFORM', 'P1', ['Cloud', 'Kubernetes'], ['Module', 'State', 'Plan / Apply']]
]

export const cloudNativeToolCatalog = toolDefinitions.map(([id, name, purpose, phase, priority, related, capabilities]) => ({
  id,
  name,
  purpose,
  phase,
  priority,
  related,
  capabilities
}))

export const cloudNativeToolEntries = cloudNativeToolCatalog.map(tool => ({
  id: `cloud-native.tool.${tool.id}`,
  domain: 'cloud-operations',
  platform: 'Cloud Native',
  service: 'cloud-native-tools',
  type: 'CLOUD NATIVE TOOL ROADMAP',
  title: `${tool.name} 云原生工具路线`,
  summary: tool.purpose,
  source: 'SmartOpsAgent Cloud Native Tool Roadmap',
  section: tool.phase,
  version: '1.0',
  risk: 'REFERENCE',
  tags: ['云原生', tool.phase, tool.priority, ...tool.related, ...tool.capabilities],
  content: [
    `工具：${tool.name}`,
    `定位：${tool.purpose}`,
    `学习阶段：${tool.phase}`,
    `推荐优先级：${tool.priority}`,
    `关联知识：${tool.related.join('、')}`,
    `核心能力：${tool.capabilities.join('、')}`,
    '后续建设：补充安装、配置、常用命令、报错原因、排查 Runbook、版本兼容矩阵和生产风险。'
  ].join('\n')
}))
