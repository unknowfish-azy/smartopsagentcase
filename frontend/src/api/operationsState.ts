export function splitPane(state, paneId, direction = 'vertical') {
  const pane = state.panes.find((item) => item.id === paneId)
  if (!pane || state.panes.length >= 4) return state
  const nextId = `${paneId}-${state.panes.length + 1}`
  return {
    ...state,
    layout: direction === 'horizontal' ? 'SPLIT_HORIZONTAL' : 'SPLIT_VERTICAL',
    panes: [...state.panes, { id: nextId, runtimeId: pane.runtimeId }]
  }
}

export function orderOperationSessions(sessions = []) {
  return [...sessions].sort((left, right) => {
    const leftTime = Date.parse(left.lastConnectedAt || '')
    const rightTime = Date.parse(right.lastConnectedAt || '')
    const normalizedLeft = Number.isFinite(leftTime) ? leftTime : -Infinity
    const normalizedRight = Number.isFinite(rightTime) ? rightTime : -Infinity
    return normalizedRight - normalizedLeft
  })
}

export function canConnect(capability) {
  return capability?.status === 'SUPPORTED'
}

export function capabilityLabel(capability) {
  if (!capability) return 'CAPABILITY UNKNOWN'
  return capability.status === 'SUPPORTED' ? 'BRIDGE READY' : capability.status.replaceAll('_', ' ')
}
