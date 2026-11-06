const routeMetadata = Object.freeze({
  Dashboard: Object.freeze({ personalGroup: 'home', pageFlow: null }),
  Chat: Object.freeze({ personalGroup: 'ai-chat', pageFlow: null }),
  Knowledge: Object.freeze({ personalGroup: 'knowledge', pageFlow: null }),
  PluginCenter: Object.freeze({ personalGroup: 'plugins', pageFlow: null }),
  SkillCenter: Object.freeze({ personalGroup: 'skills', pageFlow: null }),
  Connections: Object.freeze({ personalGroup: 'connections', pageFlow: null }),
  HarborWorkbench: Object.freeze({ personalGroup: 'harbor', pageFlow: 'operations' }),
  CloudNativeWorkbench: Object.freeze({ personalGroup: 'cloud-native', pageFlow: 'operations' }),
  ModelSettings: Object.freeze({ personalGroup: 'models', pageFlow: null }),
  ModelStrength: Object.freeze({ personalGroup: 'models', pageFlow: null }),
  TokenUsage: Object.freeze({ personalGroup: 'models', pageFlow: null }),
  ServerList: Object.freeze({ personalGroup: 'operations', pageFlow: null }),
  ServerDetail: Object.freeze({ personalGroup: 'operations', pageFlow: null }),
  HealthCenter: Object.freeze({ personalGroup: 'operations', pageFlow: null }),
  MilestoneHall: Object.freeze({ personalGroup: 'milestones', pageFlow: null }),
  AgentCommandCenter: Object.freeze({ personalGroup: 'agent', pageFlow: 'agent' }),
  ExecutionTrace: Object.freeze({ personalGroup: 'agent', pageFlow: 'agent' }),
  InspectorCenter: Object.freeze({ personalGroup: 'memory', pageFlow: 'memory' }),
  InspectorStatistics: Object.freeze({ personalGroup: 'memory', pageFlow: 'memory' }),
  OperationRunHistory: Object.freeze({ personalGroup: 'memory', pageFlow: null }),
  RecoveryContracts: Object.freeze({ personalGroup: 'memory', pageFlow: null }),
  KnowledgeCandidateReview: Object.freeze({ personalGroup: 'memory', pageFlow: null }),
  InspectorDetail: Object.freeze({ personalGroup: 'memory', pageFlow: null }),
  AdminControlCenter: Object.freeze({ personalGroup: 'admin', pageFlow: null, roles: ['admin'] }),
  ArchitectureMap: Object.freeze({ personalGroup: 'architecture', pageFlow: null, roles: ['admin'] })
})

export function routeMetaFor(routeName) {
  return routeMetadata[routeName] || { personalGroup: null, pageFlow: null }
}
