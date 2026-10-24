const labels = { up: '正常', down: '异常', degraded: '降级', maintenance: '维护', unknown: '暂无采样' }
export function heartbeatCells(samples) {
  const recent = (Array.isArray(samples) ? samples : []).slice(-30).map(sample => {
    const status = Object.hasOwn(labels, sample?.status) ? sample.status : 'unknown'
    return { status, label: `${sample?.timestamp || '时间未知'} · ${labels[status]}` }
  })
  return [...Array.from({ length: 30 - recent.length }, () => ({ status: 'unknown', label: labels.unknown })), ...recent]
}
