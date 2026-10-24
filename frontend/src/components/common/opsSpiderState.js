const SLEEP_AFTER_MS = 30 * 60 * 1000
const OPS_SPIDER_ACTIONS = Object.freeze([
  { id: 'chat', label: 'AI 对话', route: '/chat', direction: 'upper-left' },
  { id: 'agent', label: '智能体', route: '/agent', direction: 'top' },
  { id: 'cluster', label: '集群', route: '/servers', direction: 'upper-right' },
  { id: 'terminal', label: '终端', route: '/connections', direction: 'right' },
  { id: 'knowledge', label: '知识库', route: '/knowledge', direction: 'lower-right' },
  { id: 'alerts', label: '告警', action: 'investigation', direction: 'bottom' },
  { id: 'sleep', label: '休眠', action: 'sleep', direction: 'lower-left' },
  { id: 'hide', label: '隐藏', action: 'hide', direction: 'left' }
])

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value))
}

function bounds({ viewportWidth, viewportHeight, size, inset, safeLeft = inset }) {
  return {
    left: safeLeft,
    top: inset,
    right: Math.max(inset, viewportWidth - size - inset),
    bottom: Math.max(inset, viewportHeight - size - inset)
  }
}

export function resolveOpsSpiderState({ routeName = '', agentState = 'idle', inactiveMs = 0 } = {}) {
  if (inactiveMs >= SLEEP_AFTER_MS) return 'sleeping'
  if (['thinking', 'executing', 'warning', 'error', 'recovering', 'observing'].includes(agentState)) return agentState
  if (routeName === 'InspectorCenter' || routeName === 'InspectorStatistics' || routeName === 'Connections') return 'observing'
  return 'idle'
}

export function resolveOpsSpiderSize({ width = 1440, routeName = '' } = {}) {
  if (routeName === 'Connections') return 52
  if (width < 768) return 52
  if (width < 1024) return 60
  return 68
}

export function cornerPosition(corner, input) {
  const safe = bounds(input)
  const isRight = corner.includes('right')
  const isBottom = corner.includes('bottom')
  return { x: isRight ? safe.right : safe.left, y: isBottom ? safe.bottom : safe.top }
}

export function snapOpsSpiderPosition(input) {
  const safe = bounds(input)
  const x = clamp(input.x, safe.left, safe.right)
  const y = clamp(input.y, safe.top, safe.bottom)
  const horizontal = x - safe.left < safe.right - x ? safe.left : safe.right
  const vertical = y - safe.top < safe.bottom - y ? safe.top : safe.bottom
  return { x: horizontal, y: vertical }
}

export function clampOpsSpiderPosition(input) {
  const safe = bounds(input)
  return { x: clamp(input.x, safe.left, safe.right), y: clamp(input.y, safe.top, safe.bottom) }
}

export function shouldBeginOpsSpiderDrag({ menuOpen = false, interactiveTarget = false } = {}) {
  return !menuOpen && !interactiveTarget
}

export function resolveOpsSpiderPanelPosition({ x, y, size, panelWidth, panelHeight, viewportWidth, viewportHeight, safeLeft = 12, inset = 12, gap = 12 }) {
  const right = Math.max(inset, viewportWidth - panelWidth - inset)
  const bottom = Math.max(inset, viewportHeight - panelHeight - inset)
  const left = Math.min(safeLeft, right)
  const preferredX = x + size / 2 > viewportWidth / 2 ? x + size - panelWidth : x
  const preferredY = y >= panelHeight + gap + inset ? y - panelHeight - gap : y + size + gap
  return { left: clamp(preferredX, left, right) - x, top: clamp(preferredY, inset, bottom) - y }
}

export function calculateOpsSpiderDragPosition({ pointerX, pointerY, grabOffsetX, grabOffsetY, ...viewport }) {
  return clampOpsSpiderPosition({ x: pointerX - grabOffsetX, y: pointerY - grabOffsetY, ...viewport })
}

export function snapOpsSpiderToNearbyEdge({ x, y, threshold = 48, ...viewport }) {
  const safe = bounds(viewport)
  const position = clampOpsSpiderPosition({ x, y, ...viewport })
  const leftDistance = position.x - safe.left
  const rightDistance = safe.right - position.x
  const topDistance = position.y - safe.top
  const bottomDistance = safe.bottom - position.y
  const nearest = Math.min(leftDistance, rightDistance, topDistance, bottomDistance)
  if (nearest > threshold) return position
  if (nearest === leftDistance) return { ...position, x: safe.left }
  if (nearest === rightDistance) return { ...position, x: safe.right }
  if (nearest === topDistance) return { ...position, y: safe.top }
  return { ...position, y: safe.bottom }
}

export function getOpsSpiderActions() {
  return OPS_SPIDER_ACTIONS
}

export { SLEEP_AFTER_MS }