/**
 * 监控面板纯函数：速率计算 / 历史封顶 / 字节格式化。
 * 数据全部来自真实采样；缺失字段不推测，显示为不可用。
 */

export function pushHistory(history, sample, cap = 60) {
  const point = { at: sample?.sampledAt || '', cpu: numOrNull(sample?.cpuPercent), mem: memPercentOf(sample) }
  if (point.cpu == null && point.mem == null) return history
  const next = [...history, point]
  return next.length > cap ? next.slice(next.length - cap) : next
}

export function memPercentOf(sample) {
  const total = sample?.memTotalKb
  const available = sample?.memAvailableKb
  if (!Number.isFinite(total) || !Number.isFinite(available) || total <= 0) return null
  const used = total - available
  return Math.max(0, Math.min(100, (used * 100) / total))
}

export function netRate(prev, next) {
  if (!prev || !next) return null
  const rx = Number.isFinite(prev.netRxBytes) && Number.isFinite(next.netRxBytes) ? next.netRxBytes - prev.netRxBytes : null
  const tx = Number.isFinite(prev.netTxBytes) && Number.isFinite(next.netTxBytes) ? next.netTxBytes - prev.netTxBytes : null
  if (rx == null && tx == null) return null
  const seconds = secondsBetween(prev.sampledAt, next.sampledAt)
  if (!seconds || seconds <= 0) return null
  return {
    rxPerSec: rx == null ? null : Math.max(0, rx / seconds),
    txPerSec: tx == null ? null : Math.max(0, tx / seconds)
  }
}

function secondsBetween(from, to) {
  try {
    const a = new Date(from).getTime()
    const b = new Date(to).getTime()
    if (!Number.isFinite(a) || !Number.isFinite(b)) return null
    return (b - a) / 1000
  } catch {
    return null
  }
}

function numOrNull(value) {
  return Number.isFinite(value) ? value : null
}

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return '—'
  if (bytes < 1024) return `${Math.round(bytes)} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) { value /= 1024; unitIndex += 1 }
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[unitIndex]}`
}

export function formatRate(perSec) {
  if (!Number.isFinite(perSec)) return '—'
  return `${formatBytes(perSec)}/s`
}

export function formatKb(kb) {
  return formatBytes(Number.isFinite(kb) ? kb * 1024 : NaN)
}

/** CPU/内存迷你趋势线。只在采样到达时调用一次，无连续动画（reduced-motion 安全）。 */
export function drawSparkline(canvas, history, palette) {
  if (!canvas || !canvas.getContext) return false
  const context = canvas.getContext('2d')
  const width = canvas.width
  const height = canvas.height
  context.clearRect(0, 0, width, height)
  if (!history.length) return false
  context.strokeStyle = palette?.grid || 'rgba(122,215,245,.16)'
  context.lineWidth = 1
  context.beginPath()
  context.moveTo(0, height / 2)
  context.lineTo(width, height / 2)
  context.stroke()
  drawSeries(context, history.map(point => point.cpu).filter(v => v != null), width, height, palette?.cpu || '#7ad7f5')
  drawSeries(context, history.map(point => point.mem).filter(v => v != null), width, height, palette?.mem || '#8ce99a')
  return true
}

function drawSeries(context, values, width, height, color) {
  if (values.length < 2) return
  context.strokeStyle = color
  context.lineWidth = 1.5
  context.beginPath()
  values.forEach((value, index) => {
    const x = (index / (values.length - 1)) * (width - 4) + 2
    const y = height - 4 - (Math.max(0, Math.min(100, value)) / 100) * (height - 8)
    if (index === 0) context.moveTo(x, y)
    else context.lineTo(x, y)
  })
  context.stroke()
}

export function readSparklinePalette() {
  const styles = typeof getComputedStyle === 'function' ? getComputedStyle(document.body) : null
  return {
    grid: styles?.getPropertyValue('--smart-border')?.trim() || 'rgba(122,215,245,.16)',
    cpu: styles?.getPropertyValue('--smart-primary-strong')?.trim() || '#7ad7f5',
    mem: styles?.getPropertyValue('--smart-success')?.trim() || '#8ce99a'
  }
}
