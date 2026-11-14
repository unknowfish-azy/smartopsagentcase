/**
 * 知识审核图谱的视图模型（DESIGN §4.1）。
 *
 * 单一事实来源：所有行的 y 在这里一次累加算出，DOM 与 <svg> 泳道层读同一份 rows，
 * 所以滚动、字体加载、密度切换都不会让泳道和行错位——不用 getBoundingClientRect 反推。
 *
 * 泳道归属采用 A1 + source_ref 回挂：
 *   - 已采纳候选按 entry.source_ref === candidate.trace_id 挂到条目泳道（零后端改动）；
 *   - 尚未关联条目的候选固定在最后一条「待归类」泳道。
 * 后端没有把条目置为 VERIFIED 的接口，因此本版不画「已入库」主干泳道，不呈现该假状态。
 */
export const DENSITY = Object.freeze({
  comfortable: { entry: 34, cand: 56, sub: 28, commit: 30, gap: 10, avatar: 28 },
  compact: { entry: 30, cand: 44, sub: 24, commit: 26, gap: 6, avatar: 22 }
})
export const ROW_HEIGHT = Object.freeze({
  entry: DENSITY.comfortable.entry,
  cand: DENSITY.comfortable.cand,
  sub: DENSITY.comfortable.sub,
  commit: DENSITY.comfortable.commit,
  gap: DENSITY.comfortable.gap
})
export const LANE_WIDTH = 22
export const LANE_PAD_X = 12
export const LANE_GAP_X = 12
export const QUIET_LANE_COLOR = 'var(--ds-lane-quiet)'
export const TOOL_LANE_COLORS = Object.freeze([
  'var(--ds-lane-1)',
  'var(--ds-lane-2)',
  'var(--ds-lane-3)',
  'var(--ds-lane-4)'
])
export const STATUS_ORDER = Object.freeze({ PENDING_REVIEW: 0, PROMOTED: 1, REJECTED: 2 })
export const STATUS_TEXT = Object.freeze({ PENDING_REVIEW: '待审', PROMOTED: '已采纳', REJECTED: '已驳回' })
export const HISTORY_LIMIT = 40

const UNASSIGNED_KEY = 'unassigned'

function timeOf(value) {
  if (!value) return 0
  const time = new Date(value).getTime()
  return Number.isNaN(time) ? 0 : time
}

function statusOrder(status) {
  return STATUS_ORDER[status] ?? 3
}

/** 待审 → 已采纳 → 已驳回；同状态内按创建时间由新到旧（DESIGN §2.1 排序）。 */
export function sortCandidates(candidates) {
  return [...candidates].sort((a, b) => {
    const byStatus = statusOrder(a?.status) - statusOrder(b?.status)
    if (byStatus !== 0) return byStatus
    return timeOf(b?.createdAt) - timeOf(a?.createdAt)
  })
}

/** 来源工具按首次出现顺序分配 lane-1..4；第 5 个起统一中性灰（DESIGN §11.2）。 */
export function buildToolColors(candidates) {
  const colors = new Map()
  const byAge = [...candidates].sort((a, b) => timeOf(a?.createdAt) - timeOf(b?.createdAt))
  for (const candidate of byAge) {
    const toolId = candidate?.toolId
    if (!toolId || colors.has(toolId)) continue
    colors.set(toolId, TOOL_LANE_COLORS[colors.size] || QUIET_LANE_COLOR)
  }
  return colors
}

function laneColorOf(group, index, colorMode, toolColors) {
  if (group.kind === 'unassigned') return QUIET_LANE_COLOR
  if (colorMode === 'entry') return TOOL_LANE_COLORS[index] || QUIET_LANE_COLOR
  const toolId = group.candidates[0]?.toolId
  return (toolId && toolColors.get(toolId)) || QUIET_LANE_COLOR
}

function latestAt(candidates) {
  return candidates.reduce((max, candidate) => Math.max(max, timeOf(candidate?.createdAt)), 0)
}

function assignY(rows) {
  let y = 0
  for (const row of rows) {
    row.y = y
    y += row.h
  }
  return y
}

export const laneCenter = lane => LANE_PAD_X + lane * LANE_WIDTH + LANE_WIDTH / 2

function isPending(row) {
  return row.kind === 'cand' && row.candidate?.status === 'PENDING_REVIEW'
}

/**
 * 一条泳道的实/虚分段（DESIGN §4）：待审是一段连续的虚线前缀，从条目行连到最后
 * 一条待审行（即「当前版本位置」），其后已决策事件转为实线。没有待审的泳道整段实线，
 * 历史区全是事件行，自然也是实线。返回的 top/bottom 已是像素 y，组件不再推算。
 */
export function laneSegments(rows, lane) {
  const laneRows = (rows || []).filter(row => row.lane === lane && row.kind !== 'gap')
  if (!laneRows.length) return []
  const centers = laneRows.map(row => row.y + row.h / 2)
  const last = centers.length - 1
  let lastPending = -1
  laneRows.forEach((row, index) => { if (isPending(row)) lastPending = index })
  if (lastPending === -1) {
    return [{ dashed: false, top: centers[0], bottom: centers[last] }]
  }
  if (lastPending === last) {
    return [{ dashed: true, top: centers[0], bottom: centers[last] }]
  }
  return [
    { dashed: true, top: centers[0], bottom: centers[lastPending] },
    { dashed: false, top: centers[lastPending], bottom: centers[last] }
  ]
}

/** 驳回原因由后端追加在 summary 末尾（KnowledgeCandidateService#reject），这里只读取展示。 */
export function rejectReasonOf(summary) {
  const matched = /驳回原因：\s*([^\n]+)/.exec(summary || '')
  return matched ? matched[1].trim() : ''
}

/**
 * @param {object} input
 * @param {Array} input.candidates 候选（含 id/traceId/toolId/status/createdAt/summary）
 * @param {Array} input.entries 知识条目（含 id/title/version/verificationStatus/sourceRef/createdAt）
 * @param {'tool'|'entry'} [input.colorMode]
 * @param {boolean} [input.hideEntryRows] 省略条目行时把条目信息合并到候选行
 */
export function buildReviewGraph({ candidates = [], entries = [], colorMode = 'tool', hideEntryRows = false, density = 'comfortable' } = {}) {
  const metrics = DENSITY[density] || DENSITY.comfortable
  const candidateList = (candidates || []).filter(Boolean)
  const entryList = (entries || []).filter(Boolean)

  const entryByTrace = new Map()
  for (const entry of entryList) {
    if (entry.sourceRef) entryByTrace.set(String(entry.sourceRef), entry)
  }

  const groups = []
  const groupByEntryId = new Map()
  const unassigned = { key: UNASSIGNED_KEY, kind: 'unassigned', entry: null, candidates: [] }

  for (const candidate of candidateList) {
    const entry = candidate.traceId ? entryByTrace.get(String(candidate.traceId)) : null
    if (!entry) {
      unassigned.candidates.push(candidate)
      continue
    }
    const key = `entry-${entry.id}`
    if (!groupByEntryId.has(key)) {
      const group = { key, kind: 'entry', entry, candidates: [] }
      groupByEntryId.set(key, group)
      groups.push(group)
    }
    groupByEntryId.get(key).candidates.push(candidate)
  }

  groups.sort((a, b) => latestAt(b.candidates) - latestAt(a.candidates))
  if (unassigned.candidates.length) groups.push(unassigned)

  const toolColors = buildToolColors(candidateList)
  const lanes = groups.map((group, index) => ({
    index,
    key: group.key,
    kind: group.kind,
    name: group.kind === 'entry' ? (group.entry.title || `条目 #${group.entry.id}`) : '待归类',
    color: laneColorOf(group, index, colorMode, toolColors)
  }))

  const nowRows = []
  groups.forEach((group, groupIndex) => {
    const lane = groupIndex
    if (groupIndex > 0) {
      nowRows.push({ id: `gap-${group.key}`, kind: 'gap', lane: null, h: metrics.gap })
    }
    if (!hideEntryRows || group.kind === 'unassigned') {
      nowRows.push({
        id: group.kind === 'entry' ? `entry-${group.entry.id}` : 'entry-unassigned',
        kind: 'entry',
        lane,
        h: metrics.entry,
        entry: group.entry,
        unassigned: group.kind === 'unassigned',
        total: group.candidates.length,
        pending: group.candidates.filter(candidate => candidate.status === 'PENDING_REVIEW').length
      })
    }
    for (const candidate of sortCandidates(group.candidates)) {
      nowRows.push({
        id: `candidate-${candidate.id}`,
        kind: 'cand',
        lane,
        h: metrics.cand,
        candidate,
        entry: group.entry
      })
    }
  })

  const nowHeight = assignY(nowRows)

  const laneIndexByGroupKey = new Map(groups.map((group, index) => [group.key, index]))
  const unassignedLane = laneIndexByGroupKey.get(UNASSIGNED_KEY) ?? null
  const events = []
  for (const candidate of candidateList) {
    if (candidate.status !== 'PROMOTED' && candidate.status !== 'REJECTED') continue
    const entry = candidate.traceId ? entryByTrace.get(String(candidate.traceId)) : null
    const lane = entry && groupByEntryId.has(`entry-${entry.id}`)
      ? laneIndexByGroupKey.get(`entry-${entry.id}`)
      : unassignedLane
    events.push({
      id: `event-${candidate.id}`,
      kind: candidate.status === 'PROMOTED' ? 'adopt' : 'reject',
      at: entry?.createdAt || candidate.createdAt,
      candidateCreatedAt: candidate.createdAt,
      candidate,
      entry: entry || null,
      lane
    })
  }
  events.sort((a, b) => timeOf(b.at) - timeOf(a.at))
  const historyTruncated = events.length > HISTORY_LIMIT
  const histRows = events.slice(0, HISTORY_LIMIT).map(event => ({
    id: event.id,
    kind: 'commit',
    lane: event.lane,
    h: metrics.commit,
    event
  }))
  const histHeight = assignY(histRows)

  return {
    lanes,
    nowRows,
    histRows,
    nowHeight,
    histHeight,
    historyTruncated,
    padLeft: LANE_PAD_X + lanes.length * LANE_WIDTH + LANE_GAP_X,
    laneX: laneCenter,
    metrics,
    avatarSize: metrics.avatar,
    toolColors,
    entryByTrace,
    stats: {
      pending: candidateList.filter(candidate => candidate.status === 'PENDING_REVIEW').length,
      promoted: candidateList.filter(candidate => candidate.status === 'PROMOTED').length,
      rejected: candidateList.filter(candidate => candidate.status === 'REJECTED').length,
      total: candidateList.length,
      entryLanes: lanes.filter(lane => lane.kind === 'entry').length,
      unassigned: unassigned.candidates.length
    }
  }
}
