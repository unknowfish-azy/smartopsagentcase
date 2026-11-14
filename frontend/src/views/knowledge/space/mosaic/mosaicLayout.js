/* mosaicLayout.js — 照片墙布局纯函数（无 Vue 依赖，可单测）
 *
 * 设计依据：docs/design/knowledge-photo-wall-v1/DESIGN.md v1.1 §4.2 / §4.3 / §6.5
 *  - 稳定排序：域登记顺序 → serviceId → sectionId → id（与 knowledgeTree 分组一致）
 *  - 网格坐标：cols = floor((stageW + GAP) / (BASE + GAP))，index → (col,row)
 *  - 域段标签：每段首格上方一枚浮标签（屏幕空间，不随相机缩小）；小域（≤2 条）统一折叠为「其他域 · N 条」
 *  - service 小标签：连续同 serviceId 段 ≥4 格才出（screen-space 浮标签）
 *  - 布局结果与 k（缩放）无关：缩放只改容器 transform + data-size，不重算坐标
 *
 * 颜色：域色按登记顺序循环 5 图表色（DESIGN §4.1：10 域 → 5 色循环）；类型色由 mosaicType 解析后注入。
 */

import { normalizeKnowledgeType, normalizeRisk, TYPE_CLASS_COLORS, RISK_COLORS } from './mosaicType.js'

export const BASE_TILE = 108
export const TILE_GAP = 1
export const SMALL_DOMAIN_MAX = 2          // 域条目数 ≤ 此值视为「小域」，折叠进「其他域」
export const SERVICE_RUN_MIN = 4            // 连续同 serviceId 段 ≥ 此值才出 service 小标签

export const SIZE_STEPS = [
  { id: 's0', k: 0.26, px: 28 },
  { id: 's1', k: 0.52, px: 56 },
  { id: 's2', k: 1.00, px: 108 },
  { id: 's3', k: 1.85, px: 200 },
]

// 5 图表色，域色按登记顺序循环取用
export const DOMAIN_COLORS = [
  'var(--ds-chart-1)', 'var(--ds-chart-2)', 'var(--ds-chart-3)',
  'var(--ds-chart-4)', 'var(--ds-chart-5)',
]

export function sizeForK (k) {
  if (k < 0.39) return SIZE_STEPS[0]
  if (k < 0.76) return SIZE_STEPS[1]
  if (k < 1.42) return SIZE_STEPS[2]
  return SIZE_STEPS[3]
}

/* 列数按「屏幕间距」计算：世界以 BASE_TILE 排布，相机以 k 缩放，
 * 所以 cols = floor(stageW / (BASE_TILE * k))。默认用 S0 档 k，保证总览时整面墙铺满视口宽度。
 * 注意：列数只在布局期按总览 k 决定一次；之后缩放只改相机 transform，不重算坐标（DESIGN §6.5）。 */
export function colsForStage (stageWidth, k = SIZE_STEPS[0].k) {
  const sw = stageWidth > 0 ? stageWidth : 1440
  return Math.max(1, Math.floor(sw / (BASE_TILE * k)))
}

/* 把 entry 的 directory 规整出来（全部条目都带 directory，这里做防御） */
function dirOf (entry) {
  const d = entry.directory || {}
  return {
    domainId: String(d.domainId || entry.domain || 'uncategorized'),
    serviceId: String(d.serviceId || entry.service || 'general'),
    sectionId: String(d.sectionId || entry.section || 'general'),
  }
}

export function buildMosaic (entries, domains, stageWidth) {
  const order = new Map(domains.map((d, i) => [d.id, i]))
  const labelById = new Map(domains.map(d => [d.id, d.label ?? d.id]))

  // 稳定排序：域登记顺序 → serviceId → sectionId → id
  const sorted = [...entries].sort((a, b) => {
    const da = dirOf(a), db = dirOf(b)
    const oa = order.get(da.domainId) ?? 99
    const ob = order.get(db.domainId) ?? 99
    if (oa !== ob) return oa - ob
    if (da.serviceId !== db.serviceId) return da.serviceId.localeCompare(db.serviceId)
    if (da.sectionId !== db.sectionId) return da.sectionId.localeCompare(db.sectionId)
    return String(a.id).localeCompare(String(b.id))
  })

  // 域计数 + 小域合计
  const counts = new Map()
  for (const e of sorted) {
    const id = dirOf(e).domainId
    counts.set(id, (counts.get(id) || 0) + 1)
  }
  let smallTotal = 0
  for (const [, c] of counts) if (c <= SMALL_DOMAIN_MAX) smallTotal += c

  const cols = colsForStage(stageWidth)
  const rows = Math.ceil(sorted.length / cols)

  const tiles = sorted.map((entry, i) => {
    const col = i % cols
    const row = Math.floor(i / cols)
    const d = dirOf(entry)
    const t = normalizeKnowledgeType(entry.type)
    const r = normalizeRisk(entry.risk)
    const dcIdx = (order.get(d.domainId) ?? 0) % DOMAIN_COLORS.length
    return {
      id: String(entry.id),
      entry,
      col, row,
      x: col * (BASE_TILE + TILE_GAP),
      y: row * (BASE_TILE + TILE_GAP),
      cls: t.cls,
      short: t.short,
      risk: r,
      domainLabel: labelById.get(d.domainId) || d.domainId,
      typeColor: TYPE_CLASS_COLORS[t.cls],
      domainColor: DOMAIN_COLORS[dcIdx],
      riskColor: RISK_COLORS[r.key],
      serviceTag: null,
    }
  })

  // 域段标签（屏幕空间浮标签，不随相机缩小）
  const tags = []
  let prevDomain = null
  for (const tile of tiles) {
    const dom = tile.entry.directory.domainId
    if (dom !== prevDomain) {
      const c = counts.get(dom) || 0
      const isSmall = c <= SMALL_DOMAIN_MAX
      tags.push({
        domainId: dom,
        isSmall,
        label: isSmall ? `其他域 · ${smallTotal} 条` : `${labelById.get(dom) || dom} · ${c} 条`,
        count: c,
        worldX: tile.x,
        worldY: tile.y,
        color: tile.domainColor,
      })
      prevDomain = dom
    }
  }

  // service 小标签：连续同 serviceId 段 ≥ SERVICE_RUN_MIN 才出（屏幕空间浮标签）
  const serviceTags = []
  let runService = null
  let runStart = null
  let runLen = 0
  const closeRun = (i) => {
    if (runLen >= SERVICE_RUN_MIN && runStart != null) {
      const first = tiles[runStart]
      serviceTags.push({
        serviceId: runService,
        label: runService.toUpperCase(),
        count: runLen,
        worldX: first.x,
        worldY: first.y,
      })
    }
    runService = null
    runStart = null
    runLen = 0
  }
  for (let i = 0; i < tiles.length; i++) {
    const svc = tiles[i].entry.directory.serviceId
    const dom = tiles[i].entry.directory.domainId
    if (svc !== runService || dom !== tiles[runStart == null ? i : runStart].entry.directory.domainId) {
      closeRun(i)
      runService = svc
      runStart = i
      runLen = 1
    } else {
      runLen++
    }
  }
  closeRun(tiles.length)

  const worldW = cols * BASE_TILE + (cols - 1) * TILE_GAP
  const worldH = rows * BASE_TILE + (rows - 1) * TILE_GAP

  return {
    tiles,
    tags,
    serviceTags,
    cols,
    rows,
    worldW,
    worldH,
    total: tiles.length,
  }
}
