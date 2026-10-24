const MODES = new Set(['NORMAL', 'FOCUS', 'QUIET'])
const SEVERITY = { INFO: 0, LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 }

export function resolveAttention({ severity = 'INFO', confidence = 0, duration = 0, businessImpact = 'low', userMode = 'NORMAL', incidentState = 'IDLE' } = {}) {
  const mode = MODES.has(userMode) ? userMode : 'NORMAL'
  const level = SEVERITY[severity] ?? 0
  if (level >= 4 || businessImpact === 'critical' || incidentState === 'CRITICAL') return 'visual_hint'
  if (mode === 'QUIET') return 'silent'
  if (mode !== 'NORMAL' && level <= 1 && businessImpact === 'low') return 'silent'
  if (level >= 3 || businessImpact === 'high') return 'visual_hint'
  if (mode === 'FOCUS') return 'silent'
  if (duration > 300 || confidence >= 0.9) return 'badge'
  return mode === 'NORMAL' ? 'badge' : 'silent'
}

export const capabilityStatuses = Object.freeze(['available', 'degraded', 'offline'])
