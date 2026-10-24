const SEVERITIES = new Set(['INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])
const SOURCES = new Set(['VISION', 'DOM', 'OCR', 'API', 'USER', 'MONITORING'])

function clean(value, fallback = '') { return typeof value === 'string' ? value.trim() : fallback }

export function createFaultEvent(input: Record<string, any> = {}) {
  const now = new Date().toISOString()
  const evidence = Array.isArray(input.evidence) ? input.evidence.filter(Boolean).map((item: any) => ({
    id: clean(item.id) || `evidence-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    source: SOURCES.has(item.source) ? item.source : 'USER',
    content: clean(item.content),
    capturedAt: item.capturedAt || now,
    confidence: Number.isFinite(item.confidence) ? Math.max(0, Math.min(1, item.confidence)) : null
  })) : []
  if (!evidence.length) throw new Error('Fault Event 必须包含至少一条证据')
  return Object.freeze({
    id: clean(input.id) || `fault-${Date.now()}`,
    title: clean(input.title, '未命名异常'),
    severity: SEVERITIES.has(input.severity) ? input.severity : 'MEDIUM',
    source: SOURCES.has(input.source) ? input.source : evidence[0].source,
    page: clean(input.page),
    url: clean(input.url),
    environment: clean(input.environment),
    firstSeenAt: input.firstSeenAt || now,
    detectedAt: input.detectedAt || now,
    evidence,
    status: 'DETECTED',
    executionAllowed: false
  })
}

export function createInvestigationContext(faultEvent: any, input: Record<string, any> = {}) {
  if (!faultEvent?.id) throw new Error('Investigation Context 需要 Fault Event')
  const now = new Date().toISOString()
  return {
    id: clean(input.id) || `investigation-${Date.now()}`,
    faultEvent,
    page: input.page || faultEvent.page || '',
    environment: input.environment || faultEvent.environment || '',
    observations: Array.isArray(input.observations) ? [...input.observations] : [],
    evidence: [...faultEvent.evidence],
    questions: [],
    answers: [],
    knowledgeReferences: [],
    hypotheses: [],
    recommendations: [],
    state: 'STARTING',
    createdAt: input.createdAt || now,
    updatedAt: now,
    executionAllowed: false
  }
}

export const investigationStates = Object.freeze(['IDLE', 'STARTING', 'COLLECTING', 'WAITING_USER', 'ANALYZING', 'SEARCHING_KNOWLEDGE', 'REFINING', 'READY', 'RESOLVED', 'CANCELLED', 'ERROR'])
