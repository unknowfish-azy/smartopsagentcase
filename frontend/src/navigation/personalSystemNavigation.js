const directGroup = ({ id, label, cn, icon, routeName, to, roles }) => Object.freeze({
  id,
  label,
  cn,
  icon,
  routeName,
  to,
  roles,
  children: Object.freeze([])
})

const expandableGroup = ({ id, label, cn, icon, routeName, to, children, roles }) => Object.freeze({
  id,
  label,
  cn,
  icon,
  routeName,
  to,
  roles,
  children: Object.freeze(children.map(child => Object.freeze(child)))
})

export const personalSystemGroups = Object.freeze([
  directGroup({ id: 'home', label: 'HOME', cn: '首页', icon: 'HomeFilled', routeName: 'Dashboard', to: '/' }),
  directGroup({ id: 'ai-chat', label: 'AI CHAT', cn: 'AI 对话', icon: 'ChatDotRound', routeName: 'Chat', to: '/chat' }),
  directGroup({ id: 'insights', label: 'INSIGHTS', cn: '自然语言洞察', icon: 'DataAnalysis', routeName: 'Insights', to: '/insights' }),
  directGroup({ id: 'team-space', label: 'TEAM SPACE', cn: '团队协作', icon: 'Grid', routeName: 'TeamSpaces', to: '/teams' }),
  directGroup({ id: 'knowledge', label: '知识库', cn: '知识库', icon: 'Collection', routeName: 'Knowledge', to: '/knowledge' }),
  directGroup({ id: 'cloud-native', label: 'CLOUD NATIVE', cn: '云原生工程', icon: 'Monitor', routeName: 'CloudNativeWorkbench', to: '/cloud-native' }),
  /* Cloud-native resources live in the workbench instead of expanding the sidebar. */
  /*
    expandableGroup({
    id: 'cloud-native', label: 'CLOUD NATIVE', cn: '云原生工程', icon: 'Monitor', routeName: 'Knowledge', to: '/knowledge?domain=cloud-operations',
    children: [
      { label: 'COMPOSE STATUS', cn: 'Compose 巡检', routeName: 'Tools', to: '/tools/docker-compose-status' },
      { label: 'HARBOR BROWSER', cn: 'Harbor 项目与镜像', routeName: 'Tools', to: '/tools/harbor-browser' },
      { label: 'HARBOR CHECK', cn: 'Harbor 健康检查', routeName: 'Tools', to: '/tools/harbor-endpoint-check' },
      { label: 'CONTAINERD REGISTRY', cn: 'Containerd 仓库检查', routeName: 'Tools', to: '/tools/containerd-registry-inspect' },
      { label: 'CONTAINERD CONFIG', cn: 'Containerd 注册配置', routeName: 'Tools', to: '/tools/containerd-config-check' },
      { label: 'PROMETHEUS QUERY', cn: '指标实时查询', routeName: 'Tools', to: '/tools/prometheus-query' },
      { label: 'LOKI QUERY', cn: '日志实时查询', routeName: 'Tools', to: '/tools/loki-log-query' },
      { label: 'HELM RELEASES', cn: 'Helm 发布清单', routeName: 'Tools', to: '/tools/helm-releases' },
      { label: 'STORAGE CHECK', cn: 'K8s 存储巡检', routeName: 'Tools', to: '/tools/k8s-storage' },
      { label: 'RBAC CHECK', cn: 'K8s 权限检查', routeName: 'Tools', to: '/tools/k8s-rbac-check' },
      { label: 'MESH STATUS', cn: '服务网格巡检', routeName: 'Tools', to: '/tools/mesh-status' },
      { label: 'TERRAFORM', cn: 'IaC 环境检查', routeName: 'Tools', to: '/tools/terraform-environment' },
      { label: 'TOOL ROADMAP', cn: '工具路线', routeName: 'Knowledge', to: '/knowledge?query=Cloud+Native+Tool+Roadmap' },
      { label: 'HELM', cn: '应用发布', routeName: 'Knowledge', to: '/knowledge?query=Helm' },
      { label: 'KUSTOMIZE', cn: '多环境配置', routeName: 'Knowledge', to: '/knowledge?query=Kustomize' },
      { label: 'ARGO CD', cn: 'GitOps 交付', routeName: 'Knowledge', to: '/knowledge?query=Argo+CD' },
      { label: 'OBSERVABILITY', cn: 'Prometheus / Grafana', routeName: 'Knowledge', to: '/knowledge?query=Prometheus' }
      ,{ label: 'OCR KNOWLEDGE', cn: '图片识别与资料校正', routeName: 'Knowledge', to: '/knowledge?query=OCR+图片运维笔记' }
      ,{ label: 'KUBERNETES LAB', cn: '实验室与故障注入', routeName: 'Knowledge', to: '/knowledge?query=Kubernetes+Lab' }
      ,{ label: 'OBSERVABILITY CENTER', cn: '指标日志链路告警', routeName: 'Knowledge', to: '/knowledge?query=Observability' }
      ,{ label: 'GITOPS DELIVERY', cn: '发布同步与回滚', routeName: 'Knowledge', to: '/knowledge?query=GitOps' }
      ,{ label: 'SUPPLY CHAIN SECURITY', cn: '镜像、签名与证书安全', routeName: 'Knowledge', to: '/knowledge?query=Supply+Chain+Security' }
    ]
  }),*/
  directGroup({ id: 'plugins', label: 'PLUGINS', cn: '插件中心', icon: 'Grid', routeName: 'PluginCenter', to: '/plugins' }),
  directGroup({ id: 'skills', label: 'SKILLS', cn: '技能中心', icon: 'Collection', routeName: 'SkillCenter', to: '/skills' }),
  directGroup({ id: 'connections', label: '连接中心', cn: '远程运维', icon: 'Link', routeName: 'Connections', to: '/connections' }),
  directGroup({ id: 'harbor', label: 'HARBOR WORKBENCH', cn: 'Harbor 工作台', icon: 'Monitor', routeName: 'HarborWorkbench', to: '/harbor' }),
  directGroup({ id: 'operations', label: 'OPERATIONS', cn: '运维系统', icon: 'Monitor', routeName: 'ServerList', to: '/servers' }),
  directGroup({ id: 'health', label: 'HEALTH CENTER', cn: '健康诊断', icon: 'CircleCheck', routeName: 'HealthCenter', to: '/health' }),
  directGroup({ id: 'milestones', label: 'MILESTONES', cn: '里程碑战报', icon: 'Trophy', routeName: 'MilestoneHall', to: '/milestones' }),
  expandableGroup({
    id: 'models', label: 'MODELS', cn: '模型中心', icon: 'Cpu', routeName: 'ModelSettings', to: '/model-settings',
    children: [
      { label: 'CONNECTIONS', cn: '模型接入', routeName: 'ModelSettings', to: '/model-settings' },
      { label: 'GATEWAY', cn: '统一模型网关', routeName: 'ModelGateway', to: '/model-gateway' },
      { label: 'STRENGTH', cn: '模型强度', routeName: 'ModelStrength', to: '/model-strength' },
      { label: 'TOKEN USAGE', cn: '用量与额度', routeName: 'TokenUsage', to: '/token-usage' }
    ]
  }),
  expandableGroup({
    id: 'agent',
    label: 'AGENT',
    cn: '智能体',
    icon: 'Cpu',
    routeName: 'AgentCommandCenter',
    to: '/agent',
    children: [
      { label: 'COMMAND CENTER', cn: '控制中心', routeName: 'AgentCommandCenter', to: '/agent' },
      { label: 'EXECUTION TRACE', cn: '执行轨迹', routeName: 'ExecutionTrace', to: '/agent/trace' },
      { label: 'AGENT MODULE', cn: '智能体模块', routeName: 'AgentModule', to: '/agent/module' }
    ]
  }),
  expandableGroup({
    id: 'memory',
    label: 'MEMORY',
    cn: '运维记忆',
    icon: 'Memo',
    routeName: 'InspectorCenter',
    to: '/inspector',
    children: [
      { label: 'INSPECTOR CENTER', cn: '纠察中心', routeName: 'InspectorCenter', to: '/inspector' },
      { label: 'STATISTICS', cn: '统计', routeName: 'InspectorStatistics', to: '/inspector/statistics' },
      { label: 'RUN HISTORY', cn: '运行记录', routeName: 'OperationRunHistory', to: '/operations/runs' }
      ,{ label: 'RECOVERY', cn: '恢复契约', routeName: 'RecoveryContracts', to: '/operations/recovery' }
      ,{ label: 'KNOWLEDGE REVIEW', cn: '知识审核', routeName: 'KnowledgeCandidateReview', to: '/knowledge/review' }
    ]
  })
  ,expandableGroup({
    id: 'sentinel',
    label: 'SENTINEL',
    cn: '哨兵与自动化',
    icon: 'Monitor',
    routeName: 'SentinelDashboard',
    to: '/sentinel',
    children: [
      { label: 'DASHBOARD', cn: '哨兵监控台', routeName: 'SentinelDashboard', to: '/sentinel' },
      { label: 'SCRIPT LIBRARY', cn: '脚本库', routeName: 'ScriptLibrary', to: '/sentinel/scripts' },
      { label: 'ALERT CENTER', cn: '告警中心', routeName: 'AlertCenter', to: '/sentinel/alerts' },
      { label: 'INCIDENT CENTER', cn: '工单中心', routeName: 'IncidentCenter', to: '/incidents' },
      { label: 'GUARDIAN', cn: '守护 Agent', routeName: 'SentinelGuardian', to: '/sentinel/guardian' }
    ]
  })
  ,directGroup({ id: 'admin', label: 'ADMIN', cn: '管理控制台', icon: 'Setting', routeName: 'AdminControlCenter', to: '/admin', roles: ['admin'] })
  ,directGroup({ id: 'architecture', label: 'ARCHITECTURE', cn: '架构总览', icon: 'DataAnalysis', routeName: 'ArchitectureMap', to: '/architecture', roles: ['admin'] })
])

export function visiblePersonalSystemGroups(groups = personalSystemGroups, role = 'operator') {
  return groups.filter(group => typeof group.to === 'string' && group.to.startsWith('/') && (!group.roles || group.roles.includes(role)))
}

export function findPersonalSystemGroup(routeName, groups = personalSystemGroups) {
  return groups.find(group =>
    group.routeName === routeName || group.children.some(child => child.routeName === routeName)
  ) || null
}

export function isRouteInPersonalSystem(routeName, groups = personalSystemGroups) {
  return findPersonalSystemGroup(routeName, groups) !== null
}

export function navigationGroupView(group, expandedGroupIds = []) {
  const expandable = group.children.length > 0
  return {
    expandable,
    expanded: expandable && expandedGroupIds.includes(group.id)
  }
}

export { routeMetaFor } from './routeMetadata.js'
