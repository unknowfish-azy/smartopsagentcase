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
  /* 战报并入「用量与额度」?view=milestones；单子项不再单列菜单（D1/D4） */
  /* 自然语言洞察并入「智能仓库」3D 空间（2026-11-16），侧栏不再单列 */
  directGroup({ id: 'repository', label: 'SMART REPO', cn: '智能仓库', icon: 'Box', routeName: 'SmartRepository', to: '/repository' }),
  /* 团队协作入口收敛至顶部空间切换器（SpaceSwitcher「团队空间」），侧栏不再单列（2026-11-16） */
  expandableGroup({
    id: 'knowledge', label: 'KNOWLEDGE', cn: '知识中心', icon: 'Collection', routeName: 'KnowledgeSpace', to: '/knowledge/space',
    children: [
      { label: 'KNOWLEDGE SPACE', cn: '知识空间', routeName: 'KnowledgeSpace', to: '/knowledge/space' },
      { label: 'SCIVERSE INGEST', cn: '科学文献蒸馏', routeName: 'KnowledgeSciverse', to: '/knowledge/sciverse' },
      { label: 'KNOWLEDGE ATLAS', cn: '知识蒸馏图谱', routeName: 'KnowledgeAtlas', to: '/atlas' },
      { label: 'TRACEABLE QA', cn: '引用溯源问答', routeName: 'ScholarQa', to: '/scholar/qa' },
      { label: 'STUDY CARDS', cn: '研究资料卡', routeName: 'ScholarCards', to: '/scholar/cards' },
      { label: 'REVIEW BUILDER', cn: '综述生成器', routeName: 'ScholarReview', to: '/scholar/review' },
      { label: 'RETRIEVAL PIPELINE', cn: '检索编排', routeName: 'ScholarPipeline', to: '/scholar/pipeline' },
      { label: 'SHARED KNOWLEDGE', cn: '共享知识', routeName: 'SharedKnowledge', to: '/knowledge/shared' }
    ]
  }),
  expandableGroup({
    id: 'research', label: 'NEURAL RESEARCH', cn: '联网研究', icon: 'Connection', routeName: 'WebResearch', to: '/web-research',
    children: [
      { label: 'WEB RESEARCH', cn: '联网检索', routeName: 'WebResearch', to: '/web-research' },
      { label: 'FRESHNESS RADAR', cn: '时效雷达', routeName: 'Radar', to: '/radar' },
      { label: 'RE WORKBENCH', cn: '逆向研究工作台', routeName: 'ReWorkbench', to: '/re-workbench' }
    ]
  }),
  expandableGroup({
    id: 'extensions', label: 'EXTENSIONS', cn: '扩展能力', icon: 'Grid', routeName: 'PluginCenter', to: '/plugins',
    children: [
      { label: 'PLUGINS', cn: '插件中心', routeName: 'PluginCenter', to: '/plugins' },
      { label: 'SKILLS', cn: '技能中心', routeName: 'SkillCenter', to: '/skills' }
    ]
  }),
  expandableGroup({
    id: 'operations', label: 'OPERATIONS', cn: '运维系统', icon: 'Monitor', routeName: 'ServerList', to: '/servers',
    children: [
      { label: 'SERVER LIST', cn: '服务器列表', routeName: 'ServerList', to: '/servers' },
      /* 云原生工程 / Harbor 工作台并入「智能仓库」3D 空间（2026-11-16），侧栏不再单列 */
      { label: 'CONNECTIONS', cn: '连接中心', routeName: 'Connections', to: '/connections' },
      { label: 'HEALTH CENTER', cn: '健康诊断', routeName: 'HealthCenter', to: '/health' },
      { label: 'LOG DIAGNOSIS', cn: '日志诊断', routeName: 'LogDiagnosis', to: '/log-diagnosis' },
      { label: 'DEVICE REGISTRY', cn: '设备接入台账', routeName: 'DeviceRegistry', to: '/devices' },
      { label: 'ROBOT CONSOLE', cn: '机器人控制台', routeName: 'RobotConsole', to: '/robot' },
      { label: 'PATROL PLAN', cn: '巡检计划', routeName: 'PatrolPlan', to: '/patrol' }
    ]
  }),
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
      { label: 'INSPECTOR DESK', cn: '洞察台', routeName: 'InspectorDesk', to: '/inspector/desk' },
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
      { label: 'GUARDIAN', cn: '守护 Agent', routeName: 'SentinelGuardian', to: '/sentinel/guardian' },
      { label: 'FORECAST', cn: '预测面', routeName: 'ForecastPlane', to: '/sentinel/forecast' },
      { label: 'SECTION ANALYSIS', cn: '断面对比', routeName: 'SectionAnalysis', to: '/sentinel/sections' },
      { label: 'OBSERVABILITY', cn: '引擎可观测', routeName: 'EngineObservability', to: '/sentinel/observability' }
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
