import { immutableSnapshot } from './eventBus.ts'

const LIST_FIELDS = ['observations', 'evidence', 'questions', 'answers', 'hypotheses', 'recommendations', 'knowledgeReferences', 'incidents', 'infrastructureSignals', 'remoteSessionReferences', 'capabilityStatuses']

function arrayValue(value: unknown): unknown[] { return Array.isArray(value) ? [...value] : [] }

export function createCompanionContext(input: Record<string, any> = {}) {
  const now = new Date().toISOString()
  return {
    id: input.id || `companion-${Date.now()}`,
    sessionId: input.sessionId || '',
    activePage: input.activePage || input.page || '',
    activeWindow: input.activeWindow || '',
    environment: input.environment || '',
    observations: arrayValue(input.observations),
    evidence: arrayValue(input.evidence),
    questions: arrayValue(input.questions),
    answers: arrayValue(input.answers),
    hypotheses: arrayValue(input.hypotheses),
    recommendations: arrayValue(input.recommendations),
    knowledgeReferences: arrayValue(input.knowledgeReferences),
    incidents: arrayValue(input.incidents),
    infrastructureSignals: arrayValue(input.infrastructureSignals),
    remoteSessionReferences: arrayValue(input.remoteSessionReferences),
    capabilityStatuses: arrayValue(input.capabilityStatuses),
    mode: input.mode || 'NORMAL',
    attentionPolicy: input.attentionPolicy || 'silent',
    riskContext: { autonomyLevel: 1, executionAllowed: false },
    faultEvent: input.faultEvent || null,
    investigationState: input.investigationState || 'IDLE',
    executionAllowed: false,
    createdAt: input.createdAt || now,
    updatedAt: input.updatedAt || now
  }
}

export function mergeCompanionContext(context: Record<string, any>, patch: Record<string, any> = {}) {
  const next = createCompanionContext({ ...context, ...patch, updatedAt: new Date().toISOString() })
  for (const field of LIST_FIELDS) if (field in patch) next[field] = arrayValue(patch[field])
  return next
}

export function snapshotCompanionContext(context) {
  return immutableSnapshot(context)
}
