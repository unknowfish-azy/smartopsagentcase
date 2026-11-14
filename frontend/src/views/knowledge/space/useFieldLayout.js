/* useFieldLayout.js
 *
 * 纯函数，无 Vue / DOM / Date.now / Math.random 依赖。
 * 输入 atoms + domains + insights（+ 可选 binding threads） → 三层世界坐标。
 * 确定性保证：同输入 → 同输出（逐字段 deepEqual）。
 *
 * 坐标系（DESIGN §3.1）：
 *   X = 领域轴（domainPitch 等距铺开）
 *   Y = 抽象层级：evidence 0–140, knowledge 240–420, insight 520–660
 *   Z = 版本/时序（当前=0，历史为负）
 *
 * threads 参数来自 bindingIndex.js；本函数不做绑定计算，只负责把每条 thread
 * 的两端转成世界坐标（from = 洞察平面底边中点，to = 知识平面顶边中点）。
 */

export const FIELD = {
  domainPitch: 720,
  domainSpread: 260,
  evidence: { y0: 0,   y1: 140 },
  knowledge: { y0: 240, y1: 420 },
  insight:  { y0: 520, y1: 660 },
  zCurrent: 0,
  zHistoryMin: -1400,
  zFutureMax: 600,
  planeW: 260,
  planeH: 150,
  planeGap: 28,
  staleAfterDays: 365,
  staleDepth: 900,      // 过期知识沿 -Z 后退的最大像素
  insightLift: 70,      // 洞察层交替高度
}

// 复用 useSpaceLayout.js 的 type 优先级 —— RUNBOOK/DIAGNOSIS 在前，ENGINEERING 其次
const TYPE_PRIORITY = {
  RUNBOOK: 0, INCIDENT: 1, ENGINEERING: 2, 'ENGINEERING KNOWLEDGE': 2,
  QUESTION: 3, WRONG_ANSWER: 4, DIAGNOSIS_RUNBOOK: 0, 'DIAGNOSIS RUNBOOK': 0,
  ANTI_PATTERN: 5,
}
function typeRank (entry) {
  const t = String(entry?.type || '').toUpperCase()
  if (!t) return 99
  for (const [key, rank] of Object.entries(TYPE_PRIORITY)) {
    if (t.includes(key)) return rank
  }
  return 60
}

function clamp (v, a, b) { return v < a ? a : v > b ? b : v }

/**
 * 域锚点 X 坐标：按 domains 顺序等距铺开，世界水平居中。
 * 额外在 entries 中出现但 domains 里没有的 domain，按 id 字母序追加在右侧。
 */
function buildDomainAnchors (domains, atoms) {
  const counts = new Map()
  for (const a of atoms) {
    const id = String(a?.domain || 'undefined')
    counts.set(id, (counts.get(id) || 0) + 1)
  }
  const seen = new Set()
  const ordered = []
  for (const d of domains) {
    const id = String(d.id)
    seen.add(id)
    ordered.push({ id, label: d.label || id, detail: d.detail || '', n: counts.get(id) || 0 })
  }
  for (const [id, n] of [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    if (!seen.has(id)) ordered.push({ id, label: id.toUpperCase(), detail: 'UNREGISTERED', n })
  }
  const n = ordered.length
  for (let i = 0; i < n; i++) {
    ordered[i].x = (i - (n - 1) / 2) * FIELD.domainPitch
  }
  return ordered
}

/**
 * 知识平面 Z 坐标：
 *   freshness.status === 'FRESH' → 0
 *   有 freshness 且 status !== 'FRESH' → -clamp(staleDays / staleAfterDays, 0, 1) * staleDepth
 *   freshness 缺失 → 0 且 staleness = 'UNKNOWN'（不得冒充 FRESH）
 */
function computeKnowledgeZ (atom, nowMs, staleAfterDays) {
  const fresh = atom?.freshness
  if (!fresh) return { z: FIELD.zCurrent, staleness: 'UNKNOWN' }
  if (fresh.status === 'FRESH') return { z: FIELD.zCurrent, staleness: 'FRESH' }
  // 有 verifiedAt 才计算过期天数
  if (fresh.verifiedAt) {
    const verifiedMs = new Date(fresh.verifiedAt).getTime()
    const days = (nowMs - verifiedMs) / 86400000
    const depth = clamp(days / Math.max(1, staleAfterDays), 0, 1) * FIELD.staleDepth
    return { z: -Math.round(depth), staleness: fresh.status || 'STALE' }
  }
  return { z: FIELD.zCurrent, staleness: fresh.status || 'UNKNOWN' }
}

/**
 * 域内知识平面排布：typeRank → title → id 排序。
 *
 * 层级语义（DESIGN P1/P2）：
 *   y 固定在知识层中间 —— 所有知识平面处于同一抽象高度；
 *   x = 域锚点 ±domainSpread 内密集排布左右；
 *   z = 域内 row 方向前后深度 + 版本时序偏移。
 *
 * 不把 y 当域内排布方向（DESIGN §3.1 已锁 y = 抽象层级），
 * 否则 linux 域 225 条知识会把 y 撑到 6000+，破坏三层结构。
 */
function layoutKnowledgePlanes (atomsInDomain, anchorX, yBase, zByAtomId) {
  const sorted = atomsInDomain
    .slice()
    .sort((a, b) => {
      const ra = typeRank(a), rb = typeRank(b)
      if (ra !== rb) return ra - rb
      const ta = String(a.title || ''), tb = String(b.title || '')
      if (ta !== tb) return ta.localeCompare(tb)
      return String(a.id || '').localeCompare(String(a.id || ''))
    })
  const count = sorted.length
  if (count === 0) return []
  // cols = 域内 x 方向可排的列数：受 domainSpread 限制（±260px → 总宽 520px）
  // 260px 平面 + 28px gap = 288px/列 → 最多 2 列（2×288 = 576 > 520）
  const cols = Math.max(1, Math.min(2, Math.floor((FIELD.domainSpread * 2 + FIELD.planeGap) /
    (FIELD.planeW + FIELD.planeGap))))
  const rows = Math.ceil(count / cols)
  const rowDepthStep = FIELD.planeW + FIELD.planeGap  // z 方向平面间距 ≈ 288px

  const planes = []
  for (let i = 0; i < count; i++) {
    const col = i % cols
    const row = Math.floor(i / cols)
    const atom = sorted[i]
    // y 固定在知识层中间
    const y = yBase
    // x：域锚点为中心，col 左右散布
    const x = anchorX + (col - (cols - 1) / 2) * (FIELD.planeW + FIELD.planeGap)
    // z：row 前后排布 + 原子自身版本偏移（freshness 决定）
    const rowOffset = (row - (rows - 1) / 2) * rowDepthStep
    const versionZ = zByAtomId.get(atom.id)?.z ?? FIELD.zCurrent
    const z = rowOffset + versionZ

    planes.push({
      id: `kp-${atom.id}`,
      kind: 'knowledge',
      atomId: atom.id,
      insightId: undefined,
      x: Math.round(x),
      y,
      z: Math.round(z),
      w: FIELD.planeW,
      h: FIELD.planeH,
      domainId: String(atom.domain || 'undefined'),
      lodHint: 'mid',
    })
  }
  return planes
}

/**
 * 洞察平面位置：
 *   - 有绑定 atoms → 取这些知识平面 x 的均值（知识平面已在 planes 里）
 *   - operational（无绑定）→ 用其所在域的锚点 x
 *   - y = insight.y0 + (index % 2) * insightLift（避免同高重叠）
 */
function layoutInsightPlanes (insights, anchors, knowledgePlanes, bindingThreads, yBase) {
  // 从 threads 建立 insightId → atomIds 集合
  const threadsByInsight = new Map()
  if (bindingThreads) {
    for (const t of bindingThreads) {
      if (!threadsByInsight.has(t.insightId)) threadsByInsight.set(t.insightId, new Set())
      threadsByInsight.get(t.insightId).add(t.atomId)
    }
  }
  // atomId → knowledge plane（用于取 x）
  const planeByAtomId = new Map()
  for (const p of knowledgePlanes) {
    if (p.atomId) planeByAtomId.set(p.atomId, p)
  }
  // 域锚点 index
  const anchorById = new Map()
  for (const a of anchors) anchorById.set(a.id, a.x)

  const planes = []
  for (let i = 0; i < insights.length; i++) {
    const ins = insights[i]
    const threads = threadsByInsight.get(ins.id)
    let x
    if (threads && threads.size > 0) {
      let sumX = 0, n = 0
      for (const atomId of threads) {
        const p = planeByAtomId.get(atomId)
        if (p) { sumX += p.x; n++ }
      }
      if (n > 0) { x = sumX / n }
      else { x = anchorById.get(String(ins.domain || '')) ?? 0 }
    } else {
      // operational：用其 badge 推断域（ALERTS/SERVERS/HEALTH → linux；KNOWLEDGE → 居中）
      const badgeDomain = badgeToDefaultDomain(ins.badge)
      x = anchorById.get(badgeDomain) ?? 0
    }
    planes.push({
      id: `ip-${ins.id}`,
      kind: 'insight',
      atomId: undefined,
      insightId: ins.id,
      x: Math.round(x),
      y: yBase + (i % 2) * FIELD.insightLift,
      z: FIELD.zCurrent,
      w: FIELD.planeW,
      h: FIELD.planeH,
      domainId: undefined,
      lodHint: 'mid',
    })
  }
  return planes
}

function badgeToDefaultDomain (badge) {
  switch (String(badge || '').toUpperCase()) {
    case 'ALERTS':
    case 'SERVERS':
    case 'INSPECTOR': return 'linux'
    case 'KNOWLEDGE': return 'cloud-operations'
    default: return 'linux'
  }
}

/**
 * 证据带：每个有 evidenceRefs 的知识原子生成 1 条带。
 * 无 evidenceRefs → 不生成（否则 L0 会堆满无意义的空条带）。
 */
function buildEvidenceBands (atoms, knowledgePlanes) {
  const planeByAtomId = new Map()
  for (const p of knowledgePlanes) {
    if (p.atomId) planeByAtomId.set(p.atomId, p)
  }
  const bands = []
  for (const a of atoms) {
    const refs = a?.evidenceRefs
    if (!Array.isArray(refs) || refs.length === 0) continue
    const kp = planeByAtomId.get(a.id)
    if (!kp) continue
    // 证据带对齐知识平面 x 中心，在 L0 层底上方
    bands.push({
      id: `eb-${a.id}`,
      x: kp.x,
      y: FIELD.evidence.y1 - 20,
      z: kp.z,
      w: Math.max(FIELD.planeW, refs.length * 8),
      h: 24,
      density: refs.length,
      source: refs[0]?.source || '',
    })
  }
  return bands
}

/**
 * 绑定 thread → 世界坐标线段。
 * from = 洞察平面底边中点；to = 知识平面顶边中点。
 */
function buildThreads (bindingThreads, knowledgePlanes, insightPlanes) {
  const ipById = new Map()
  for (const p of insightPlanes) ipById.set(p.insightId, p)
  const kpById = new Map()
  for (const p of knowledgePlanes) kpById.set(p.atomId, p)

  const out = []
  if (!bindingThreads) return out
  for (const t of bindingThreads) {
    const ip = ipById.get(t.insightId)
    const kp = kpById.get(t.atomId)
    if (!ip || !kp) continue
    out.push({
      insightId: t.insightId,
      atomId: t.atomId,
      relation: t.relation,
      weight: t.weight,
      stale: !!t.stale,
      from: { x: ip.x, y: ip.y + ip.h / 2, z: ip.z },
      to:   { x: kp.x, y: kp.y,           z: kp.z },
    })
  }
  // 稳定排序：(insightId, atomId) 字典序
  out.sort((a, b) => {
    if (a.insightId !== b.insightId) return a.insightId.localeCompare(b.insightId)
    return a.atomId.localeCompare(b.atomId)
  })
  return out
}

function buildAxes (anchors) {
  const domains = anchors.map(a => ({ id: a.id, label: a.label, x: a.x }))
  const layers = [
    { id: 'evidence',  label: '证据层',  y: FIELD.evidence.y0 },
    { id: 'knowledge', label: '知识层',  y: FIELD.knowledge.y0 },
    { id: 'insight',   label: '洞察层',  y: FIELD.insight.y0 },
  ]
  return { domains, layers }
}

function computeStats (atoms, insights, planes, evidenceBands, threads) {
  let staleAtoms = 0
  for (const a of atoms) {
    if (a?.freshness?.status && a.freshness.status !== 'FRESH') staleAtoms++
  }
  return {
    atoms: atoms.length,
    insights: insights.length,
    planes: planes.length,
    evidenceBands: evidenceBands.length,
    threads: threads.length,
    staleAtoms,
  }
}

/**
 * 三层世界坐标主函数。
 *
 * @param {Array} atoms     知识原子数组（KnowledgeAtom[]）
 * @param {Array} domains   域定义数组（{id, label, detail}[]）
 * @param {Array} insights  洞察数组（Insight[]）
 * @param {Object} [options]
 * @param {Array}  [options.threads]       来自 bindingIndex.js 的 threads（可选，没传 → 空数组）
 * @param {number} [options.now]            当前时间戳 ms；不传 → Date.now()（但建议显式传入以便单测）
 * @param {number} [options.staleAfterDays] 过期判定阈值，默认 365
 * @returns {{planes, evidenceBands, threads, axes, stats}}
 */
export function computeField (atoms, domains, insights, options = {}) {
  // 默认值
  atoms    = Array.isArray(atoms)    ? atoms    : []
  domains  = Array.isArray(domains)  ? domains  : []
  insights = Array.isArray(insights) ? insights : []
  const bindingThreads = Array.isArray(options.threads) ? options.threads : []
  // 强制显式传入 now，避免 Date.now() 在单测里造成非确定性
  if (options.now === undefined) {
    throw new TypeError('computeField: options.now must be explicitly provided (ms timestamp)')
  }
  const nowMs = options.now
  const staleAfterDays = options.staleAfterDays ?? FIELD.staleAfterDays

  // 1) 域锚点
  const anchors = buildDomainAnchors(domains, atoms)

  // 2) 知识平面：按域分组 + 域内 x+z 排布
  //    y 固定在知识层中间（DESIGN P2：所有知识处于同一抽象高度）
  const yMid = (FIELD.knowledge.y0 + FIELD.knowledge.y1) / 2  // = 330
  const atomsByDomain = new Map()
  for (const a of atoms) {
    const id = String(a?.domain || 'undefined')
    if (!atomsByDomain.has(id)) atomsByDomain.set(id, [])
    atomsByDomain.get(id).push(a)
  }
  const knowledgePlanes = []
  for (const anchor of anchors) {
    const domainAtoms = atomsByDomain.get(anchor.id) || []
    if (domainAtoms.length === 0) continue
    // 每个 atom 的 z（版本时序偏移）单独算
    const zByAtom = new Map()
    for (const a of domainAtoms) {
      const { z } = computeKnowledgeZ(a, nowMs, staleAfterDays)
      zByAtom.set(a.id, z)
    }
    const domainPlanes = layoutKnowledgePlanes(domainAtoms, anchor.x, yMid, zByAtom)
    knowledgePlanes.push(...domainPlanes)
  }

  // 3) 洞察平面
  const insightPlanes = layoutInsightPlanes(insights, anchors, knowledgePlanes, bindingThreads, FIELD.insight.y0)

  // 4) 合并所有 planes 并稳定排序
  const allPlanes = [...knowledgePlanes, ...insightPlanes]
  allPlanes.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind.localeCompare(b.kind)
    if (a.x !== b.x) return a.x - b.x
    if (a.y !== b.y) return a.y - b.y
    return (a.id || '').localeCompare(b.id || '')
  })

  // 5) 证据带
  const evidenceBands = buildEvidenceBands(atoms, knowledgePlanes)

  // 6) 绑定 thread → 世界坐标
  const threads = buildThreads(bindingThreads, knowledgePlanes, insightPlanes)

  // 7) 轴定义 + 统计
  const axes = buildAxes(anchors)
  const stats = computeStats(atoms, insights, allPlanes, evidenceBands, threads)

  return {
    planes: allPlanes,
    evidenceBands,
    threads,
    axes,
    stats,
  }
}
