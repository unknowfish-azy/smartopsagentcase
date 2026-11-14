/**
 * deskModel.js — 洞察台纯函数层
 *
 * 职责：字段归一化、时间分箱、关联判定、筛选、格式化、确定性演示数据。
 * 全部为纯函数，不依赖 Vue / DOM / 接口，可直接单测。
 *
 * 设计约束（见 docs/design/inspector-desk-v1/DESIGN.md §5 §7）：
 *   - 关联只认 traceId 命中，禁止用时间邻近猜测；
 *   - 统计接口返回全量聚合，窗口聚合由前端按分箱计算；
 *   - 演示数据为确定性合成，不得写入持久化。
 */

export const SEVERITIES = Object.freeze([
  { key: 'CRITICAL', cn: '严重', color: '#f85149' },
  { key: 'HIGH', cn: '高', color: '#f0883e' },
  { key: 'WARN', cn: '警告', color: '#d29922' },
  { key: 'PASS', cn: '通过', color: '#3fb950' }
])

export const TOOLS = Object.freeze([
  { key: 'mysql-query', cn: 'MySQL 查询', color: '#2496ed' },
  { key: 'docker-compose-status', cn: 'Compose 巡检', color: '#7ad7f5' },
  { key: 'prometheus-query', cn: '指标查询', color: '#3fb950' },
  { key: 'k8s-storage', cn: '存储巡检', color: '#f0883e' },
  { key: 'loki-log-query', cn: '日志查询', color: '#a383a6' }
])

export const WINDOW_MS = Object.freeze({ '24h': 86400000, '7d': 604800000, '30d': 2592000000 })

export const BIN_COUNTS = Object.freeze({ '24h': 12, '7d': 14, '30d': 15 })

const SEVERITY_BY_KEY = Object.fromEntries(SEVERITIES.map(s => [s.key, s]))
const TOOL_BY_KEY = Object.fromEntries(TOOLS.map(t => [t.key, t]))

export const severityMeta = key => SEVERITY_BY_KEY[key] || { cn: key || '—', color: '#5d6b78' }
export const toolMeta = key => TOOL_BY_KEY[key] || { cn: key || '—', color: '#5d6b78' }

/* ---------- 字段归一化 ---------- */

/**
 * 把后端事件列表归一化为洞察台内部结构。
 * 后端字段：id, taskId, createdAt, severity（traceId/category/target 可能缺失）。
 */
export function normalizeEvents(raw) {
  if (!Array.isArray(raw)) return []
  return raw.map(item => {
    const at = toTimestamp(item.createdAt ?? item.at ?? item.time)
    return {
      id: item.id,
      at: at || Date.now(),
      severity: normalizeSeverity(item.severity),
      taskId: item.taskId || item.task || 'unknown',
      category: item.category || null,
      target: item.target || null,
      traceId: item.traceId || null
    }
  }).filter(e => e.id != null)
}

/**
 * 把后端运行记录归一化。
 * 后端字段：id, toolId, startedAt, endedAt, status, traceId, commandCount, failedCommandCount。
 */
export function normalizeRuns(raw) {
  if (!Array.isArray(raw)) return []
  return raw.map(item => {
    const started = toTimestamp(item.startedAt ?? item.at ?? item.time)
    const ended = toTimestamp(item.endedAt)
    const duration = started && ended ? Math.max(0, (ended - started) / 1000) : (item.duration || 0)
    return {
      id: item.id,
      at: started || Date.now(),
      tool: item.toolId || item.tool || 'unknown',
      status: normalizeRunStatus(item.status),
      duration,
      traceId: item.traceId || null,
      exitCode: item.exitCode ?? null
    }
  }).filter(r => r.id != null)
}

function toTimestamp(value) {
  if (value == null) return 0
  if (typeof value === 'number') return value
  const t = Date.parse(value)
  return Number.isNaN(t) ? 0 : t
}

function normalizeSeverity(value) {
  const up = String(value || '').toUpperCase()
  return SEVERITY_BY_KEY[up] ? up : (up === 'WARNING' ? 'WARN' : (up === 'OK' ? 'PASS' : 'WARN'))
}

function normalizeRunStatus(value) {
  const up = String(value || '').toUpperCase()
  if (up === 'SUCCESS' || up === 'SUCCEEDED' || up === 'OK') return 'SUCCESS'
  if (up === 'FAILED' || up === 'FAIL' || up === 'ERROR') return 'FAILED'
  if (up === 'TIMEOUT' || up === 'TIMED_OUT') return 'TIMEOUT'
  return up || 'UNKNOWN'
}

/* ---------- 时间分箱 ---------- */

/**
 * 把事件按时间窗分箱，返回每箱各等级的计数。
 * 空数组返回空箱列表（每箱计数全 0）。
 */
export function binEvents(events, windowKey, start, end) {
  const count = BIN_COUNTS[windowKey] || 12
  const span = Math.max(1, end - start)
  const list = Array.from({ length: count }, (_, i) => ({
    from: start + (span / count) * i,
    to: start + (span / count) * (i + 1),
    CRITICAL: 0, HIGH: 0, WARN: 0, PASS: 0
  }))
  for (const event of events) {
    if (event.at < start || event.at > end) continue
    const idx = Math.min(count - 1, Math.floor(((event.at - start) / span) * count))
    const sev = SEVERITY_BY_KEY[event.severity] ? event.severity : 'WARN'
    list[idx][sev] += 1
  }
  return list
}

/* ---------- 关联判定（四态） ---------- */

/**
 * 判定事件与运行的关联状态。
 * 只认 traceId 命中；时间相近不算关联。
 *
 * 返回：
 *   { kind: 'linked', run }
 *   { kind: 'miss', traceId }
 *   { kind: 'no-trace' }
 */
export function linkState(event, runsByTrace) {
  if (!event || !event.traceId) return { kind: 'no-trace' }
  const run = runsByTrace.get(event.traceId)
  if (!run) return { kind: 'miss', traceId: event.traceId }
  return { kind: 'linked', run }
}

/** 反向：运行是否命中纠察事件 */
export function linkStateRun(run, eventsByTrace) {
  if (!run || !run.traceId) return { kind: 'no-trace' }
  const event = eventsByTrace.get(run.traceId)
  if (!event) return { kind: 'miss', traceId: run.traceId }
  return { kind: 'linked', event }
}

export function runsByTraceMap(runs) {
  const map = new Map()
  for (const run of runs) {
    if (run.traceId) map.set(run.traceId, run)
  }
  return map
}

export function eventsByTraceMap(events) {
  const map = new Map()
  for (const event of events) {
    if (event.traceId) map.set(event.traceId, event)
  }
  return map
}

/* ---------- 四种文案（不许改写，与 DESIGN.md §5 一致） ---------- */

export function linkText(state) {
  switch (state.kind) {
    case 'linked':
      return `已关联 ${state.run.id} · 切到「运行」可看到高亮`
    case 'miss':
      return `有 traceId（${state.traceId}），但运行记录里没有命中——可能超出窗口或未被采集`
    case 'no-trace':
      return '没有 traceId · 无法定位运行记录'
    default:
      return '未关联'
  }
}

export function linkTextRun(state) {
  switch (state.kind) {
    case 'linked':
      return `已关联 ${state.event.id} · 切到「纠察」可看到高亮`
    case 'miss':
      return `有 traceId（${state.traceId}），但纠察里没有命中（可能超出窗口）`
    case 'no-trace':
      return '没有 traceId · 无法定位纠察事件'
    default:
      return '未关联'
  }
}

/* ---------- 筛选 ---------- */

export function filterEvents(events, { severity = 'ALL', linkedOnly = false, runsByTrace }) {
  return events.filter(event => {
    if (severity !== 'ALL' && event.severity !== severity) return false
    if (linkedOnly) {
      if (!event.traceId) return false
      if (!runsByTrace.has(event.traceId)) return false
    }
    return true
  })
}

export function filterRuns(runs, { tool = 'ALL', linkedOnly = false, eventsByTrace }) {
  return runs.filter(run => {
    if (tool !== 'ALL' && run.tool !== tool) return false
    if (linkedOnly) {
      if (!run.traceId) return false
      if (!eventsByTrace.has(run.traceId)) return false
    }
    return true
  })
}

/* ---------- 格式化 ---------- */

export const fmtTime = ts => {
  if (!ts) return '—'
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })
}

export const fmtDateTime = ts => {
  if (!ts) return '—'
  return new Date(ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function windowRange(windowKey, end = Date.now()) {
  const span = WINDOW_MS[windowKey] || WINDOW_MS['24h']
  return { start: end - span, end, span }
}

/* ---------- 确定性演示数据 ---------- */

function rng(seed) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 4294967296
  }
}

const DEMO_TASKS = ['mysql-conn', 'compose-ps', 'prom-mem', 'k8s-pvc', 'loki-502', 'redis-latency', 'disk-inode', 'nginx-upstream']
const DEMO_CATEGORIES = ['DATABASE', 'CLOUD_NATIVE', 'OBSERVABILITY', 'STABILITY']

/**
 * 生成确定性的演示数据。同一 windowKey 永远产出相同序列。
 * 注意：演示数据不得写入持久化，也不得当成接口兜底。
 */
export function buildDemoData(windowKey) {
  const span = WINDOW_MS[windowKey] || WINDOW_MS['24h']
  const end = Date.now() - 600000
  const start = end - span
  const random = rng(windowKey === '24h' ? 20261119 : windowKey === '7d' ? 7719 : 3019)

  const eventCount = windowKey === '24h' ? 12 : windowKey === '7d' ? 34 : 96
  const events = []
  for (let i = 0; i < eventCount; i += 1) {
    const at = start + random() * span
    const roll = random()
    const severity = roll > 0.78 ? 'PASS' : roll > 0.46 ? 'WARN' : roll > 0.2 ? 'HIGH' : 'CRITICAL'
    const task = DEMO_TASKS[Math.floor(random() * DEMO_TASKS.length)]
    events.push({
      id: `EV-${1040 + i}`,
      at,
      severity,
      taskId: task,
      category: DEMO_CATEGORIES[Math.floor(random() * DEMO_CATEGORIES.length)],
      target: `${task.split('-')[0]}-${Math.floor(random() * 3) + 1}`,
      traceId: random() > 0.35 ? `tr_${Math.floor(random() * 1e6).toString(16).padStart(6, '0')}` : null
    })
  }
  events.sort((a, b) => a.at - b.at)

  const runCount = windowKey === '24h' ? 38 : windowKey === '7d' ? 98 : 240
  const runs = []
  for (let i = 0; i < runCount; i += 1) {
    const at = start + random() * span
    const roll = random()
    const status = roll > 0.82 ? 'FAILED' : roll > 0.74 ? 'TIMEOUT' : 'SUCCESS'
    const tool = TOOLS[Math.floor(random() * TOOLS.length)]
    const linked = events.find(event => event.traceId && Math.abs(event.at - at) < span * 0.02 && random() > 0.55)
    runs.push({
      id: `RUN-${5400 + i}`,
      at,
      tool: tool.key,
      status,
      duration: 2 + random() * 34,
      traceId: linked ? linked.traceId : random() > 0.6 ? `tr_${Math.floor(random() * 1e6).toString(16).padStart(6, '0')}` : null,
      exitCode: status === 'SUCCESS' ? 0 : status === 'FAILED' ? 1 : null
    })
  }
  runs.sort((a, b) => a.at - b.at)

  return { start, end, events, runs }
}
