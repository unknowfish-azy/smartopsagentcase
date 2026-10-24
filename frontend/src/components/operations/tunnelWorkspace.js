export function tunnelStatusLabel(status) {
  return ['RUNNING', 'STOPPED', 'STARTING', 'ERROR'].includes(status) ? status : 'UNKNOWN'
}

export function tunnelTypeLabel(type) {
  return ({ LOCAL: 'LOCAL FORWARD', REMOTE: 'REMOTE FORWARD', DYNAMIC: 'SOCKS / DYNAMIC' })[type] || 'UNKNOWN'
}

export function canStartTunnel({ runtimeOnline, protocol, status }) {
  return Boolean(runtimeOnline && protocol === 'SSH' && status === 'STOPPED')
}
