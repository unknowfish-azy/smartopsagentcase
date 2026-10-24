export const companionStates = Object.freeze({
  spider: Object.freeze(['SLEEPING', 'IDLE', 'OBSERVING', 'SUSPICIOUS', 'ANOMALY', 'INVESTIGATING', 'RECOVERING']),
  jellyfish: Object.freeze(['WAIT', 'CONTEXT_BUILDING', 'TRIAGING', 'QUESTIONING', 'SEARCHING', 'RECOMMENDING']),
  whale: Object.freeze(['STABLE', 'DEGRADED', 'UNKNOWN']),
  interaction: Object.freeze(['FOCUS', 'QUIET', 'NORMAL'])
})

export const defaultCompanionStates = Object.freeze({ spider: 'IDLE', jellyfish: 'WAIT', whale: 'UNKNOWN', interaction: 'NORMAL' })
