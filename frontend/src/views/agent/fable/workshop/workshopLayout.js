/**
 * Agent 工坊 · 等距布局纯函数（T28，DESIGN §3/§5）
 *
 * 工坊是 Agent 构成场的第二视图：6 张工具工位（2 行 × 3 列）环绕
 * 中央闭环轨道（4 站菱形），墙屏 + 服务器机柜靠后墙。纯函数，无
 * Vue/DOM 依赖；颜色一律由组件经 CSS 令牌取色，这里只产几何。
 *
 * 等距投影：2:1 轴测（DESIGN §5）。
 *   sx = (x − y) · tw
 *   sy = (x + y) · th − z · tz
 */

export const WORKSHOP_UNIT = Object.freeze({ tw: 32, th: 16, tz: 24 })
export const WORKSHOP_GRID = Object.freeze({ w: 12, d: 8 })
const VIEWBOX_PAD = 28
const WALL_HEIGHT_TILES = 3

/** 窄屏退化阈值（门禁 4）：<768px 工坊退化为工位状态列表；视口未知时保守退化。 */
export const NARROW_VIEWPORT_MAX = 768

export function isNarrowViewport(width) {
  return !(Number(width) >= NARROW_VIEWPORT_MAX)
}

/** 2:1 轴测换算：网格坐标 (x, y, z) → 屏幕坐标。 */
export function iso(x, y, z = 0) {
  return {
    sx: (x - y) * WORKSHOP_UNIT.tw,
    sy: (x + y) * WORKSHOP_UNIT.th - z * WORKSHOP_UNIT.tz
  }
}

/** 逆换算：屏幕坐标 + 高度 z → 网格坐标（用于单测往返校验）。 */
export function inverseIso(sx, sy, z = 0) {
  const a = sx / WORKSHOP_UNIT.tw
  const b = (sy + z * WORKSHOP_UNIT.tz) / WORKSHOP_UNIT.th
  return { x: (a + b) / 2, y: (b - a) / 2 }
}

function deskId(en) {
  return String(en || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

/**
 * 构建工坊布局。
 * @param {Array<{cn:string, en:string, tone:string}>} tools 6 件工具
 * @param {Array<{cn:string, en:string}>} loopSteps 4 站闭环
 * @param {number} cols 每列工位数（默认 3，即 2×3）
 */
export function buildWorkshop(tools, loopSteps, cols = 3) {
  const list = Array.isArray(tools) ? tools : []
  const steps = Array.isArray(loopSteps) ? loopSteps : []
  const rows = Math.max(1, Math.ceil(list.length / Math.max(1, cols)))
  const marginX = 1.8
  const colSpan = WORKSHOP_GRID.w - marginX * 2
  const rowYBack = 1.0
  const rowYFront = WORKSHOP_GRID.d - 1.0

  const desks = []
  list.forEach((tool, index) => {
    const row = Math.floor(index / cols)
    const col = index % cols
    const x = cols > 1 ? marginX + (col * colSpan) / (cols - 1) : WORKSHOP_GRID.w / 2
    const y = rows > 1 ? rowYBack + (row * (rowYFront - rowYBack)) / (rows - 1) : (rowYBack + rowYFront) / 2
    const p = iso(x, y, 0)
    desks.push({
      id: deskId(tool.en),
      tone: tool.tone || 'gaze',
      labelCn: tool.cn || '',
      labelEn: tool.en || '',
      col,
      row,
      x,
      y,
      z: 0,
      sx: p.sx,
      sy: p.sy,
      depth: x + y // 画家序：depth 大者后画（在前排）
    })
  })
  desks.sort((a, b) => a.depth - b.depth)

  // 中央闭环轨道：4 站菱形（感知→规划→执行→核查）
  const cx = WORKSHOP_GRID.w / 2
  const cy = WORKSHOP_GRID.d / 2
  const trackOffsets = [
    { dx: 0, dy: -0.8 },
    { dx: 1.6, dy: 0 },
    { dx: 0, dy: 0.8 },
    { dx: -1.6, dy: 0 }
  ]
  const track = steps.slice(0, trackOffsets.length).map((step, i) => {
    const x = cx + trackOffsets[i].dx
    const y = cy + trackOffsets[i].dy
    const p = iso(x, y, 0)
    return { cn: step.cn, en: step.en, index: i, x, y, sx: p.sx, sy: p.sy }
  })

  // 墙屏：后右墙（沿 +x 方向）挂屏（z + height ≤ 墙高 3·tz=72，不穿墙沿）
  const screenAnchor = iso(2.0, 0, 1.1)
  const screen = {
    x: 2.0,
    y: 0,
    z: 1.1,
    lenTiles: 3.2,
    height: 42,
    sx: screenAnchor.sx,
    sy: screenAnchor.sy
  }

  // 服务器机柜：后右角落，3 颗心跳 LED 在前脸
  const cabinetAnchor = iso(11.2, 0.4, 0)
  const cabinet = {
    x: 11.2,
    y: 0.4,
    z: 0,
    width: 26,
    height: 64,
    sx: cabinetAnchor.sx,
    sy: cabinetAnchor.sy,
    leds: [
      { dx: 8, dy: -30 },
      { dx: 8, dy: -22 },
      { dx: 8, dy: -14 }
    ]
  }

  const floor = [
    [0, 0],
    [WORKSHOP_GRID.w, 0],
    [WORKSHOP_GRID.w, WORKSHOP_GRID.d],
    [0, WORKSHOP_GRID.d]
  ].map(([x, y]) => ({ x, y, ...iso(x, y, 0) }))

  // 视口包络：地板四角 + 全部锚点，含墙体/工位向上伸出量
  const points = [
    ...floor,
    ...desks,
    ...track,
    { sx: screen.sx, sy: screen.sy - screen.height },
    { sx: cabinet.sx, sy: cabinet.sy - cabinet.height }
  ]
  const minX = Math.min(...points.map(p => p.sx)) - VIEWBOX_PAD
  const maxX = Math.max(...points.map(p => p.sx)) + VIEWBOX_PAD
  const minY =
    Math.min(...points.map(p => p.sy)) - WALL_HEIGHT_TILES * WORKSHOP_UNIT.tz - VIEWBOX_PAD
  const maxY = Math.max(...points.map(p => p.sy)) + VIEWBOX_PAD

  return {
    unit: WORKSHOP_UNIT,
    grid: WORKSHOP_GRID,
    desks,
    track,
    trackCenter: { ...iso(cx, cy), x: cx, y: cy },
    screen,
    cabinet,
    floor,
    viewBox: { x: minX, y: minY, width: maxX - minX, height: maxY - minY }
  }
}

/** 闭环耗时（ms）：updatedAt / reviewedAt − createdAt；无效返回 null。 */
export function loopDuration(loop) {
  if (!loop || typeof loop !== 'object') return null
  const end = loop.updatedAt || loop.reviewedAt
  if (!end || !loop.createdAt) return null
  const ms = new Date(end).getTime() - new Date(loop.createdAt).getTime()
  return Number.isFinite(ms) && ms >= 0 ? ms : null
}

/**
 * 真实闭环 → 工位亮灯映射（T30，DESIGN §4 E1）。
 * stage 真实取值：ANALYZE → MEMORIZE → DECIDE → REVIEW → LEARNED。
 * 映射：ANALYZE→混合检索；MEMORIZE→审计留痕；DECIDE→风险策略
 * （requiresHuman 命中→人工审批；已出决策→安全执行）；REVIEW→结果核查；
 * LEARNED→审计留痕。每工位只保留最近一条。
 */
export function deskActivity(loops) {
  const byDesk = new Map()
  if (!Array.isArray(loops)) return []
  for (const loop of loops) {
    if (!loop || typeof loop !== 'object') continue
    const stage = String(loop.stage || '').toUpperCase()
    const info = {
      loopId: String(loop.id || ''),
      stage,
      title: String(loop.title || ''),
      requiresHuman: Boolean(loop.requiresHuman),
      updatedAt: loop.updatedAt || null,
      durationMs: loopDuration(loop)
    }
    const push = deskId$ => {
      if (!deskId$ || byDesk.has(deskId$)) return
      byDesk.set(deskId$, { deskId: deskId$, ...info })
    }
    if (stage === 'ANALYZE') push('hybrid-retrieval')
    else if (stage === 'MEMORIZE') push('audit-trail')
    else if (stage === 'DECIDE') {
      push('risk-policy')
      if (info.requiresHuman) push('human-gate')
      else if (loop.decision) push('executor')
    } else if (stage === 'REVIEW') push('inspector')
    else if (stage === 'LEARNED') push('audit-trail')
  }
  return [...byDesk.values()]
}

/**
 * 墙屏 sparkline（DESIGN §4 E4）：近 N 轮闭环耗时（秒），
 * 按创建时间从旧到新排列（折线从左到右）。无效记录跳过。
 */
export function sparklineFromLoops(loops, n = 12) {
  if (!Array.isArray(loops)) return []
  return loops
    .filter(loop => loop && typeof loop === 'object')
    .map(loop => ({ t: new Date(loop.createdAt || 0).getTime() || 0, v: loopDuration(loop) }))
    .filter(item => item.v != null && item.v > 0)
    .sort((a, b) => a.t - b.t)
    .slice(-Math.max(2, n))
    .map(item => Math.round((item.v / 1000) * 10) / 10)
}
