/* useSpaceLayout.js
 *
 * 纯函数，无 Vue 依赖、无 DOM 访问。输入 entries + domains，输出世界布局：
 *   { zones: [ { id, label, detail, x, y, w, h, n, cols, rows } ],
 *     cards: [ { id, entry, domainId, x, y, w, h, zoneId, col, row } ] }
 *
 * 算法：DESIGN §3.2 —— 面积 √n 归一 → 递归二分切块 → 域内网格排列。
 * 确定性保证：同输入 → 同输出（逐字段 deepEqual 通过）。
 */

export const WORLD_DEFAULT = { w: 3200, h: 2000 }
export const CARD_DEFAULT  = { w: 200, h: 124, gap: 12, headH: 40, pad: 12, maxCols: 6 }

/* 卡片内容分档：判据是**屏幕像素**（世界尺寸 × 相机缩放 k），不是世界像素。
 * 同一张卡在不同缩放下可读性不同，所以档位必须逐卡算，不能用全局 LOD 一刀切。
 *   < 44×22            → micro：只剩色条
 *   44×22 ~ 124×80     → title：2 行标题
 *   ≥ 124×80           → full：标题 + 摘要 + 类型 chip
 */
export function screenTier (card, k) {
  const wpx = card.w * k
  const hpx = card.h * k
  if (wpx < 44 || hpx < 22) return 'micro'
  if (wpx >= 124 && hpx >= 80) return 'full'
  return 'title'
}

// type 优先级：用于域内排序，RUNBOOK 类在前，ENGINEERING 其次，最后其余。
const TYPE_PRIORITY = {
  RUNBOOK: 0, INCIDENT: 1, ENGINEERING: 2, 'ENGINEERING KNOWLEDGE': 2,
  QUESTION: 3, WRONG_ANSWER: 4, DIAGNOSIS_RUNBOOK: 0, 'DIAGNOSIS RUNBOOK': 0,
  ANTI_PATTERN: 5,
}

function typeRank (entry) {
  const t = String(entry.type || '').toUpperCase()
  if (!t) return 99
  for (const [key, rank] of Object.entries(TYPE_PRIORITY)) {
    if (t.includes(key)) return rank
  }
  return 60
}

// squarified treemap 的简化版：按累计面积到半下刀，交替横竖切块。
function split (items, box, out, horizontal) {
  if (items.length === 1) {
    out.push({ ...items[0], ...box })
    return
  }
  const totalArea = items.reduce((a, b) => a + b.area, 0)
  let acc = 0
  let cut = 1
  for (let i = 0; i < items.length - 1; i++) {
    acc += items[i].area
    if (acc >= totalArea / 2) { cut = i + 1; break }
  }
  const leftItems  = items.slice(0, cut)
  const rightItems = items.slice(cut)
  const leftArea   = leftItems.reduce((a, b) => a + b.area, 0)
  const ratio      = leftArea / totalArea

  if (horizontal) {
    const wl = Math.round(box.w * ratio)
    split(leftItems,  { x: box.x,     y: box.y, w: wl,       h: box.h }, out, false)
    split(rightItems, { x: box.x + wl, y: box.y, w: box.w - wl, h: box.h }, out, false)
  } else {
    const hl = Math.round(box.h * ratio)
    split(leftItems,  { x: box.x, y: box.y,      w: box.w, h: hl },       out, true)
    split(rightItems, { x: box.x, y: box.y + hl, w: box.w, h: box.h - hl }, out, true)
  }
}

export function computeLayout (entries, domains, { w = WORLD_DEFAULT.w, h = WORLD_DEFAULT.h,
  cardW = CARD_DEFAULT.w, cardH = CARD_DEFAULT.h, gap = CARD_DEFAULT.gap,
  headH = CARD_DEFAULT.headH, pad = CARD_DEFAULT.pad, maxCols = CARD_DEFAULT.maxCols } = {}) {

  // 1) 每域条目数（entries 里可能有 domain 不在 domains 里的——先按 entries 实际值聚合）
  const counts = new Map()
  for (const e of entries) {
    const id = String(e.domain || 'undefined')
    counts.set(id, (counts.get(id) || 0) + 1)
  }

  // 2) 域清单：domains 里有的先排；entries 里出现但 domains 里没有的，按 id 字母序追加
  const seen   = new Set()
  const domainList = []
  for (const d of domains) {
    const id = String(d.id)
    seen.add(id)
    domainList.push({ id, label: d.label || id, detail: d.detail || '', n: counts.get(id) || 0 })
  }
  for (const [id, n] of [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    if (!seen.has(id)) domainList.push({ id, label: id.toUpperCase(), detail: 'UNREGISTERED', n })
  }

  // 3) √n 归一，按面积降序切块
  const weights = domainList.map(d => d.n === 0 ? 0 : Math.sqrt(d.n))
  const sumW = weights.reduce((a, b) => a + b, 0) || 1
  const items = domainList
    .map((d, i) => ({ d, area: weights[i] / sumW * w * h }))
    .sort((a, b) => b.area - a.area)

  const zones = []
  if (items.length === 0) {
    return { zones: [], cards: [] }
  }
  if (items.length === 1) {
    zones.push({ ...items[0], x: 0, y: 0, w, h, cols: 0, rows: 0 })
  } else {
    split(items, { x: 0, y: 0, w, h }, zones, true)
  }

  // 4) 域内卡片网格 + 排序
  const cards = []
  for (const z of zones) {
    const innerX = z.x + pad
    const innerY = z.y + headH + pad
    const innerW = z.w - pad * 2
    const innerH = z.h - headH - pad * 2
    const cols   = Math.max(1, Math.min(maxCols, Math.floor((innerW + gap) / (cardW + gap))))
    const rows   = Math.max(1, Math.ceil((innerH + gap) / (cardH + gap)))

    const inDomain = entries
      .filter(e => String(e.domain || 'undefined') === z.d.id)
      .slice()
      .sort((a, b) => {
        const ra = typeRank(a), rb = typeRank(b)
        if (ra !== rb) return ra - rb
        const ta = String(a.title || ''), tb = String(b.title || '')
        if (ta !== tb) return ta.localeCompare(tb)
        return String(a.id || '').localeCompare(String(b.id || ''))
      })

    for (let i = 0; i < inDomain.length; i++) {
      const e = inDomain[i]
      const col = i % cols
      const row = Math.floor(i / cols)
      cards.push({
        id: `${z.d.id}-${i}`,
        entry: e,
        domainId: z.d.id,
        zoneId: z.d.id,
        col, row,
        x: innerX + col * (cardW + gap),
        y: innerY + row * (cardH + gap),
        w: cardW,
        h: cardH,
      })
    }

    // 附加 cols/rows 回 zone（用于 HUD 计算、迷你地图、单测断言）
    z.cols = cols
    z.rows = rows
    z.n    = inDomain.length
    z.id   = z.d.id
    z.label = z.d.label
    z.detail = z.d.detail
    delete z.d  // 避免泄漏原始域对象
  }

  return { zones, cards }
}
