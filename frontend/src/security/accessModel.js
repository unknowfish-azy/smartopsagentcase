export const ROLES = Object.freeze({
  OPERATOR: 'operator',
  ADMIN: 'admin'
})

export const ROLE_LABELS = Object.freeze({
  operator: '运维用户',
  admin: '系统管理员'
})

export const PLATFORM_ADMIN_LEVELS = Object.freeze({
  root: '最高管理员',
  deputy: '副管理员',
  specialist: '专项管理员'
})

export const PLATFORM_CAPABILITIES = Object.freeze([
  'admin.users', 'admin.config', 'admin.audit', 'admin.security',
  'teams.view', 'teams.manage', 'teams.freeze', 'teams.audit', 'teams.approve'
])

export const ROLE_CAPABILITIES = Object.freeze({
  operator: Object.freeze([
    'operations.read', 'operations.diagnose', 'knowledge.read', 'agent.run',
    'agent.approve', 'models.read', 'connections.read'
  ]),
  admin: Object.freeze([
    'operations.read', 'operations.diagnose', 'knowledge.read', 'agent.run',
    'agent.approve', 'models.read', 'connections.read', 'admin.users',
    'admin.config', 'admin.audit', 'admin.security', 'architecture.read'
  ])
})

export const ARCHITECTURE_LAYERS = Object.freeze([
  { id: 'user', title: '用户层', english: 'USER', owner: '多端接入与交互', technology: 'Web 控制台 / 小程序 / REST API / CLI', wave: '7' },
  { id: 'management', title: '管理层', english: 'MANAGEMENT', owner: '权限、配置、审计、安全', technology: 'RBAC / 配置中心 / 审计报表 / 合规策略', wave: '6' },
  { id: 'application', title: '应用层', english: 'APPLICATION', owner: '智能运维业务流程', technology: '故障诊断 / 自动处置 / 巡检 / 知识问答', wave: '5' },
  { id: 'orchestration', title: 'Agent 智能编排层', english: 'ORCHESTRATION', owner: '任务调度与协作', technology: 'ReAct / 工具调用 / 多 Agent / 人工审批', wave: '4' },
  { id: 'inference', title: '模型推理层', english: 'INFERENCE', owner: '推理与检索增强', technology: 'vLLM / Ollama / Qwen / RAG / GPTQ / AWQ', wave: '3' },
  { id: 'data', title: '数据资源层', english: 'DATA', owner: '业务数据与可观测数据', technology: 'MySQL / Redis / pgvector / Prometheus / Loki', wave: '2' },
  { id: 'infrastructure', title: '基础设施层', english: 'INFRASTRUCTURE', owner: '部署、弹性与交付', technology: 'Docker / Kubernetes / 混合云 / CI/CD', wave: '1' }
])

export const TRAINING_WAVES = Object.freeze([
  { id: 1, layerId: 'infrastructure', title: '底座筑基', focus: '容器化、K8s 编排、交付与最小权限', status: 'ready' },
  { id: 2, layerId: 'data', title: '数据支撑', focus: 'MySQL、Redis、pgvector、指标与日志访问', status: 'ready' },
  { id: 3, layerId: 'inference', title: '智能内核', focus: '多模型推理、量化部署与 RAG 全链路', status: 'ready' },
  { id: 4, layerId: 'orchestration', title: '核心调度', focus: 'ReAct、工具调用、多 Agent 与审批', status: 'ready' },
  { id: 5, layerId: 'application', title: '业务落地', focus: '对话运维、诊断、处置、巡检与问答', status: 'ready' },
  { id: 6, layerId: 'management', title: '管控治理', focus: '身份、配置、审计、安全与合规', status: 'active' },
  { id: 7, layerId: 'user', title: '接入交互', focus: 'Web、小程序、开放 API 与 CLI', status: 'planned' },
  { id: 8, layerId: 'cross-cutting', title: '全链整合', focus: '高可用、可观测、数据安全与合规保障', status: 'planned' }
])

export function getSessionRole(sessionValue) {
  try {
    const session = typeof sessionValue === 'string' ? JSON.parse(sessionValue) : sessionValue
    return session?.role === ROLES.ADMIN ? ROLES.ADMIN : ROLES.OPERATOR
  } catch {
    return ROLES.OPERATOR
  }
}

export function getCurrentRole(storage = globalThis.localStorage) {
  return getSessionRole(storage?.getItem?.('smartops_preview_auth'))
}

export function canAccess(role, capability) {
  return Boolean(ROLE_CAPABILITIES[role]?.includes(capability))
}

export function canAccessPlatformCapability(sessionValue, capability) {
  try {
    const session = typeof sessionValue === 'string' ? JSON.parse(sessionValue) : sessionValue
    return session?.role === ROLES.ADMIN && (session?.platformCapabilities?.includes(capability) || session?.platformLevel === 'root')
  } catch {
    return false
  }
}

export function getVisibleNavigationGroups(groups, role) {
  return groups.filter(group => !group.roles || group.roles.includes(role))
}
