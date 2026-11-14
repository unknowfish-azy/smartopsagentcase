<script setup>
/* ===== 三视图：space（默认 3D 地图）/ grid（域内行）/ list（全量平铺） ===== */
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import { knowledgeDomains, knowledgeEntries } from '../knowledgeCatalog.js'
import { knowledgeReadApi } from '../knowledgeLibrary.js'
import { computeLayout, WORLD_DEFAULT } from './useSpaceLayout.js'
import { useSpaceCamera } from './useSpaceCamera.js'

const viewMode = ref('space')
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
function onViewModeChange (mode) { viewMode.value = mode }

// 网格视图：按域分组平铺，每个域一个 section，域内按 type 优先级 + 标题排序
const gridByDomain = computed(() => {
  return zones.map(z => ({
    zone: z,
    items: cards.filter(c => c.zoneId === z.id && (!hitIds.value.size || hitIds.value.has(c.id))),
  }))
})
// 列表视图：全量平铺（检索命中时只显示命中集）
const listItems = computed(() => {
  const src = hitIds.value.size
    ? cards.filter(c => hitIds.value.has(c.id))
    : cards
  return src.slice().sort((a, b) => {
    if (a.zoneId !== b.zoneId) return a.zoneId.localeCompare(b.zoneId)
    const ta = String(a.entry.title || ''), tb = String(b.entry.title || '')
    return ta.localeCompare(tb)
  })
})

/* ===== 方向键空间导航：在当前焦点卡所在域内按 row/col 邻近移动 ===== */
function findNeighborInZone (zoneId, rowDelta, colDelta, fromId) {
  const rowDeltaY = rowDelta * (124 + 12)   // cardH + gap
  const colDeltaX = colDelta * (200 + 12)
  const base = cardById.get(fromId)
  if (!base) return null
  const zCards = cards.filter(c => c.zoneId === zoneId)
  // 取所有候选，算到 targetPos 的距离，取最近的
  const targetX = base.x + colDeltaX
  const targetY = base.y + rowDeltaY
  let best = null, bestDist = Infinity
  for (const c of zCards) {
    if (c.id === fromId) continue
    const d = Math.hypot(c.x - targetX, c.y - targetY)
    // 方向约束：↑ 必须 y < base.y，↓ 必须 y > base.y，← 必须 x < base.x，→ 必须 x > base.x
    if (rowDelta === -1 && c.y >= base.y) continue
    if (rowDelta ===  1 && c.y <= base.y) continue
    if (colDelta === -1 && c.x >= base.x) continue
    if (colDelta ===  1 && c.x <= base.x) continue
    if (d < bestDist) { bestDist = d; best = c }
  }
  return best
}
function moveFocusByArrow (dir) {
  const cur = document.activeElement?.closest?.('.ks-card[data-card]')
  if (!cur) {
    // 无焦点时聚焦视口域的第一张卡
    const zone = mountedZoneIds.value[0]
    if (zone) {
      const first = document.querySelector(`.ks-zone[data-domain="${zone}"] .ks-card`)
      first?.focus()
    }
    return
  }
  const fromId = cur.dataset.card
  const base = cardById.get(fromId)
  if (!base) return
  let next = null
  if (dir === 'ArrowUp')    next = findNeighborInZone(base.zoneId, -1,  0, fromId)
  if (dir === 'ArrowDown')  next = findNeighborInZone(base.zoneId,  1,  0, fromId)
  if (dir === 'ArrowLeft')  next = findNeighborInZone(base.zoneId,  0, -1, fromId)
  if (dir === 'ArrowRight') next = findNeighborInZone(base.zoneId,  0,  1, fromId)
  if (next) {
    const dom = document.querySelector(`.ks-card[data-card="${next.id}"]`)
    dom?.focus()
    // reduced-motion 下不做相机平滑跟随，直接把焦点卡移到视口中心
    if (!reducedMotion && cam.lod.value >= 1 && !isInViewport(dom)) {
      const st = stageRef.value
      const rect = dom.getBoundingClientRect()
      const stRect = st.getBoundingClientRect()
      const cx = (rect.left + rect.width/2) - stRect.left
      const cy = (rect.top + rect.height/2) - stRect.top
      cam.tx.value += (st.clientWidth/2 - cx)
      cam.ty.value += (st.clientHeight/2 - cy)
      cam.apply(worldRef.value)
      renderMinimapViewport()
    }
  }
}
function isInViewport (el) {
  const st = stageRef.value?.getBoundingClientRect()
  const r = el.getBoundingClientRect()
  if (!st) return true
  return r.right > st.left && r.left < st.right && r.bottom > st.top && r.top < st.bottom
}

const stageRef = ref(null)
const worldRef = ref(null)
const dragging = ref(false)
const movedPx = ref(0)
let dragStartX = 0, dragStartY = 0, dragStartTx = 0, dragStartTy = 0

/* ===== 侧栏卡片详情 ===== */
const selectedCard = ref(null)
const selectedContent = ref('')
async function openCard (cardId) {
  const c = cardById.get(cardId)
  if (!c) return
  selectedCard.value = c
  // 异步拉完整正文（MARKDOWN 格式，pre 直接渲染）
  selectedContent.value = '… 加载中 …'
  try {
    const node = await knowledgeReadApi.node(c.entry.id)
    selectedContent.value = node?.content || ''
  } catch {
    selectedContent.value = '(完整正文加载失败)'
  }
}
function closeCard () { selectedCard.value = null; selectedContent.value = '' }
function onCardClick (e, card) {
  if (movedPx.value > 4) { movedPx.value = 0; return }
  openCard(card.id)
}
function onCardKeydown (e, card) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    openCard(card.id)
  }
}
// 侧栏里的「推断关系」候选：同域 + 同 platform / 同 service，取前 5 条
const relatedToSelected = computed(() => {
  const c = selectedCard.value
  if (!c) return []
  const domainCards = cards.filter(cc => cc.zoneId === c.zoneId && cc.id !== c.id)
  const platform = String(c.entry.platform || '')
  const service  = String(c.entry.service || '')
  return domainCards
    .filter(cc => String(cc.entry.platform || '') === platform || String(cc.entry.service || '') === service)
    .slice(0, 5)
})

/* ===== 布局（纯函数计算一次，会话内坐标恒定） ===== */
const layout = computeLayout(knowledgeEntries, knowledgeDomains)
const zones  = layout.zones
const cards  = layout.cards
const cardById = new Map(cards.map(c => [c.id, c]))
const domainById = new Map(zones.map(z => [z.id, z]))

/* ===== 相机 ===== */
const cam = useSpaceCamera()
const worldStyle = computed(() => ({
  transform: `translate3d(${cam.tx.value}px,${cam.ty.value}px,0) scale(${cam.k.value})`,
}))

/* ===== 关系连线（推断关系，不人工确认） =====
 * 规则：同 platform 实线、跨域虚线；单域连线 > 400 时只保留同 platform 与近距离对。 */
const LINES_PER_DOMAIN_CAP = 400
const lines = computed(() => {
  const byPlatform = new Map()
  for (const c of cards) {
    const key = String(c.entry.platform || '')
    if (!key) continue
    if (!byPlatform.has(key)) byPlatform.set(key, [])
    byPlatform.get(key).push(c)
  }
  const raw = []
  for (const list of byPlatform.values()) {
    if (list.length < 2) continue
    for (let i = 0; i < list.length - 1; i++) {
      const a = list[i], b = list[i + 1]
      const ax = a.x + a.w / 2, ay = a.y + a.h / 2
      const bx = b.x + b.w / 2, by = b.y + b.h / 2
      raw.push({
        ax, ay, bx, by,
        crossDomain: a.zoneId !== b.zoneId,
        zoneId: a.zoneId,
      })
    }
  }
  // 域内按 cap 裁剪：优先非跨域，再按距离升序
  const byZone = new Map()
  for (const ln of raw) {
    const arr = byZone.get(ln.zoneId) || []
    arr.push(ln)
    byZone.set(ln.zoneId, arr)
  }
  const out = []
  for (const arr of byZone.values()) {
    if (arr.length <= LINES_PER_DOMAIN_CAP) { out.push(...arr); continue }
    arr.sort((a, b) => {
      const aCross = a.crossDomain ? 1 : 0, bCross = b.crossDomain ? 1 : 0
      if (aCross !== bCross) return aCross - bCross
      const dA = Math.hypot(a.ax - a.bx, a.ay - a.by)
      const dB = Math.hypot(b.ax - b.bx, b.ay - b.by)
      return dA - dB
    })
    out.push(...arr.slice(0, LINES_PER_DOMAIN_CAP))
  }
  return out
})

/* ===== 检索（接 knowledgeReadApi.search，命中卡片 25% 不透明，首条 flyTo） ===== */
const queryText = ref('')
const hitIds = ref(new Set())
const hitCount = ref(0)
const hoverCardId = ref(null)

function applySearch (term) {
  const t = String(term || '').trim().toLowerCase()
  if (!t) {
    hitIds.value = new Set()
    hitCount.value = 0
    return
  }
  // 走 catalog 的 search：它已经做了 aliases + title/content/metadata 命中与排序
  const results = knowledgeReadApi.search({ query: t })
  const s = new Set(results.map(r => r.id))
  hitIds.value = s
  hitCount.value = results.length
  // 首条 flyTo 到其所在域（L0 到 L1）
  if (results.length && cam.k.value < 0.5) {
    const firstResult = results[0]
    const zoneId = String(firstResult.domain || '')
    const z = domainById.get(zoneId)
    if (z) {
      const st = stageRef.value
      cam.flyTo(z, worldRef.value, st)
      renderHUD(); renderMinimapViewport()
    }
  }
}

function onQueryInput (e) {
  queryText.value = e.target.value
  applySearch(e.target.value)
}

function lineWidthFactor () { return (1 / Math.max(0.1, cam.k.value)).toFixed(2) }

/* ===== 域级虚拟化（mountedZoneIds） + 卡级 IntersectionObserver =====
 * L0（k < 0.42）：零卡片挂载，只有域块。
 * L1/L2：只挂载与视口世界矩形相交的域（最多 6 个），搜索命中域 / 选中域强制包含。
 * 域内卡片：v-if = mountedCards.has(c.id)；卡片进入视口时 IO 回调加入，离开时 500ms 后移除。
 */
const mountedCards = ref(new Set())        // 真正挂载 DOM 的卡片 id
const mountedZoneIds = computed(() => {
  const st = stageRef.value
  const lod = cam.lod.value
  if (lod === 0) return []                  // L0：零卡片
  const vw = st?.clientWidth ?? 1200
  const vh = st?.clientHeight ?? 800
  const vx = -cam.tx.value / cam.k.value
  const vy = -cam.ty.value / cam.k.value
  const vrect = { x: vx, y: vy, w: vw / cam.k.value, h: vh / cam.k.value }
  const out = []
  for (const z of zones) {
    const intersects = z.x < vrect.x + vrect.w && z.x + z.w > vrect.x &&
                      z.y < vrect.y + vrect.h && z.y + z.h > vrect.y
    if (!intersects && cam.k.value >= 0.42) {
      // 非视口域：若 k > 0.8（L2 以上）强制挂载视口外一圈相邻域做「平移即现」；L1 不挂
      if (cam.k.value >= 1.05) {
        // 判断「相邻」——域距视口的最近距离 < 一个域宽
        const dx = Math.max(0, vrect.x - (z.x + z.w), z.x - (vrect.x + vrect.w))
        const dy = Math.max(0, vrect.y - (z.y + z.h), z.y - (vrect.y + vrect.h))
        if (Math.hypot(dx, dy) > Math.max(z.w, z.h) * 0.6) continue
      } else continue
    }
    out.push(z.id)
  }
  // 搜索命中域强制挂载（L1/L2 也必须能看到命中卡）
  if (hitIds.value.size && cam.k.value >= 0.42) {
    const hitDomains = new Set()
    for (const c of cards) if (hitIds.value.has(c.id)) hitDomains.add(c.zoneId)
    for (const id of hitDomains) if (!out.includes(id)) out.push(id)
  }
  // 选中域强制挂载
  if (selectedCard.value && !out.includes(selectedCard.value.zoneId)) out.push(selectedCard.value.zoneId)
  // cap 6 域（对应 DESIGN ≤ 3 个视口 + 相邻，但 linux 单域 225 卡 → 6 域仍能同时挂载 ≤ 800 卡，需要卡级 IO 再压）
  return out.slice(0, 6)
})

// 用 mountedZoneIds 同步重置 mountedCards 的延迟卸载计时器
const pendingUnmount = new Map()   // cardId → timeoutId
let io = null
function setupCardIO () {
  if (!stageRef.value) return
  // 重新挂载时，把所有已注册卡 DOM 的 isIntersecting 扫一遍
  io = new IntersectionObserver((entries) => {
    const newMounted = new Set(mountedCards.value)
    for (const e of entries) {
      const id = e.target.dataset.card
      if (!id) continue
      if (e.isIntersecting) {
        const t = pendingUnmount.get(id)
        if (t) { clearTimeout(t); pendingUnmount.delete(id) }
        newMounted.add(id)
      } else {
        // 500ms 延迟卸载，避免平移时抖动
        if (!pendingUnmount.has(id)) {
          pendingUnmount.set(id, setTimeout(() => {
            mountedCards.value.delete(id)
            pendingUnmount.delete(id)
          }, 500))
        }
      }
    }
    mountedCards.value = newMounted
  }, { root: stageRef.value, rootMargin: '120px', threshold: 0 })
}

// 当 mountedZoneIds 变化时：把这些域的候选卡 DOM 注册到 IO，同时立刻把已挂载的卡从 IO 里断开
function watchMountedZones () {
  // 把非 mountedZoneIds 的卡从 mountedCards 里立刻清掉（不需要 500ms 延迟）
  const allowed = new Set(mountedZoneIds.value)
  const next = new Set()
  for (const id of mountedCards.value) {
    const c = cardById.get(id)
    if (c && allowed.has(c.zoneId)) next.add(id)
  }
  mountedCards.value = next
}

// hover 高亮：同 platform 的连线加粗
const hoverPlatform = computed(() => {
  const c = cards.find(cc => cc.id === hoverCardId.value)
  return c ? String(c.entry.platform || '') : ''
})

function refreshWorldCamera () {
  cam.apply(worldRef.value)
  renderHUD()
  renderMinimapViewport()
}

/* ===== 迷你地图（首次渲染 + 视口矩形实时更新） ===== */
const minimapInit = ref(false)
function renderMinimapOnce () {
  if (minimapInit.value) return
  const mm = document.getElementById('ks-minimap')
  if (!mm) return
  mm.innerHTML = zones.map(z => `
    <i style="left:${z.x / WORLD_DEFAULT.w * 100}%;top:${z.y / WORLD_DEFAULT.h * 100}%;
      width:${z.w / WORLD_DEFAULT.w * 100}%;height:${z.h / WORLD_DEFAULT.h * 100}%"></i>
  `).join('') + '<div class="ks-mm-vp" id="ks-mm-vp"></div>'
  minimapInit.value = true
}

function renderMinimapViewport () {
  const vp = document.getElementById('ks-mm-vp')
  const st = stageRef.value
  if (!vp || !st) return
  const vw = st.clientWidth / cam.k.value
  const vh = st.clientHeight / cam.k.value
  const vx = -cam.tx.value / cam.k.value
  const vy = -cam.ty.value / cam.k.value
  vp.style.left   = Math.max(0, Math.min(100, vx / WORLD_DEFAULT.w * 100)) + '%'
  vp.style.top    = Math.max(0, Math.min(100, vy / WORLD_DEFAULT.h * 100)) + '%'
  vp.style.width  = Math.max(2, Math.min(100, vw / WORLD_DEFAULT.w * 100)) + '%'
  vp.style.height = Math.max(2, Math.min(100, vh / WORLD_DEFAULT.h * 100)) + '%'
}

function onMinimapClick (e) {
  const st = stageRef.value
  const rect = e.currentTarget.getBoundingClientRect()
  const wx = (e.clientX - rect.left) / rect.width * WORLD_DEFAULT.w
  const wy = (e.clientY - rect.top) / rect.height * WORLD_DEFAULT.h
  cam.centerOn(wx, wy, Math.max(cam.k.value, 0.5), worldRef.value, st)
}

/* ===== HUD 标签（屏幕空间，域宽 < 92px 跳过） ===== */
function renderHUD () {
  const host = document.getElementById('ks-hud')
  const st = stageRef.value
  if (!host || !st) return
  const parts = []
  for (const z of zones) {
    const sx = z.x * cam.k.value + cam.tx.value
    const sy = z.y * cam.k.value + cam.ty.value + (40 * cam.k.value) / 2
    const sw = z.w * cam.k.value
    if (sw < 92) continue
    if (sx + sw < 0 || sx > st.clientWidth) continue
    if (sy < 8 || sy > st.clientHeight - 8) continue
    parts.push(
      `<span class="ks-lbl" style="left:${Math.max(2, sx + 4)}px;top:${sy}px;max-width:${Math.max(48, sw - 12)}px">
         <b>${z.label}</b><em>${z.n}</em>
       </span>`
    )
  }
  host.innerHTML = parts.join('')
}

/* ===== 状态行 ===== */
const stat = computed(() => {
  const st = stageRef.value
  const cp = cam.worldPointOfViewportCenter(st)
  const cz = zones.find(z => cp.x >= z.x && cp.x <= z.x + z.w && cp.y >= z.y && cp.y <= z.y + z.h)
  return {
    total: knowledgeEntries.length,
    domains: zones.length,
    domainLabel: cz?.label ?? '—',
    lod: cam.lod.value,
    scale: Math.round(cam.k.value * 100),
    mountedCards: mountedCards.value.size,
  }
})

/* ===== 交互 ===== */
function onWheel (e) {
  e.preventDefault()
  const st = stageRef.value.getBoundingClientRect()
  cam.zoomAt(e.clientX - st.left, e.clientY - st.top, Math.exp(-e.deltaY * 0.0015), worldRef.value)
  renderHUD()
  renderMinimapViewport()
}

function onPointerDown (e) {
  if (e.target.closest('.ks-minimap,.ks-legend')) return
  dragging.value = true
  movedPx.value = 0
  dragStartX = e.clientX; dragStartY = e.clientY
  dragStartTx = cam.tx.value; dragStartTy = cam.ty.value
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
}
function onPointerMove (e) {
  if (!dragging.value) return
  const dx = e.clientX - dragStartX, dy = e.clientY - dragStartY
  movedPx.value = Math.max(movedPx.value, Math.abs(dx) + Math.abs(dy))
  cam.tx.value = dragStartTx + dx
  cam.ty.value = dragStartTy + dy
  cam.apply(worldRef.value)
  renderHUD()
  renderMinimapViewport()
}
function onPointerUp () {
  dragging.value = false
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
}

function onZoneClick (e, zone) {
  // 拖拽不触发 flyTo
  if (movedPx.value > 4) { movedPx.value = 0; return }
  const st = stageRef.value
  cam.flyTo(zone, worldRef.value, st)
  renderHUD()
  renderMinimapViewport()
}

function onZoneHeadClick (e, zone) {
  e.stopPropagation()
  const st = stageRef.value
  cam.flyTo(zone, worldRef.value, st)
  renderHUD()
  renderMinimapViewport()
}

/* ===== 键盘 ===== */
function onKeyDown (e) {
  // 检索输入框内部走独立逻辑
  if (e.target.id === 'ks-query') {
    if (e.key === 'Escape') { e.target.value = ''; applySearch(''); e.target.blur() }
    return
  }
  // 方向键：空间视图内按卡片邻近移动
  if (viewMode.value === 'space' && (e.key === 'ArrowUp' || e.key === 'ArrowDown' || e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
    e.preventDefault()
    moveFocusByArrow(e.key)
    return
  }
  // Enter：打开当前 focus 的卡片（三视图都支持）
  if ((e.key === 'Enter' || e.key === ' ') && e.target?.dataset?.card) {
    e.preventDefault()
    openCard(e.target.dataset.card)
    return
  }
  if (e.key === '/') {
    e.preventDefault()
    document.getElementById('ks-query')?.focus()
    return
  }
  if (e.key === '0') {
    cam.fitOverview(worldRef.value, stageRef.value)
    renderHUD(); renderMinimapViewport()
    return
  }
  if (e.key === 'Escape') {
    if (selectedCard.value) { closeCard(); return }
    if (viewMode.value !== 'space') { viewMode.value = 'space'; return }
    if (cam.k.value > 1.05) {
      const st = stageRef.value
      const cp = cam.worldPointOfViewportCenter(st)
      const cz = zones.find(z => cp.x >= z.x && cp.x <= z.x + z.w && cp.y >= z.y && cp.y <= z.y + z.h) || zones[0]
      cam.flyTo(cz, worldRef.value, st)
    } else {
      cam.fitOverview(worldRef.value, stageRef.value)
    }
    renderHUD(); renderMinimapViewport()
  }
}

/* ===== 启动 ===== */
function init () {
  cam.fitOverview(worldRef.value, stageRef.value)
  renderMinimapOnce()
  renderMinimapViewport()
  renderHUD()
  setupCardIO()
}

let ro = null
onMounted(() => {
  init()
  ro = new ResizeObserver(() => {
    renderMinimapViewport()
    renderHUD()
  })
  ro.observe(stageRef.value)
  window.addEventListener('keydown', onKeyDown)

  // 域级 → 卡级：每次 mountedZoneIds 变，把新出现的域的候选卡 DOM observe 到 IO，旧域立刻清 mountedCards
  watch(mountedZoneIds, async () => {
    watchMountedZones()
    await nextTick()
    // 给新挂载的 DOM 注册到 IO（IO 会用 initial 交叉率触发回调，自动把可见卡加入 mountedCards）
    worldRef.value?.querySelectorAll('.ks-card').forEach(el => {
      const id = el.dataset.card
      if (id && !pendingUnmount.has(id)) {
        try { io?.observe(el) } catch {}
      }
    })
    // 全局可见性刷新（相机 k / tx / ty 变时也触发，但用 watchEffect 会太频繁，这里手动在 wheel/drag/zoneClick 里调）
  }, { immediate: false })
})
onBeforeUnmount(() => {
  ro?.disconnect()
  window.removeEventListener('keydown', onKeyDown)
  io?.disconnect()
})
</script>

<template>
  <article class="ks-root">
    <header class="ks-bar">
      <div class="ks-brand"><b>知识空间</b><span>SPATIAL IA</span></div>
      <div class="ks-stat">
        <b>{{ stat.total }}</b> 条 · <b>{{ stat.domains }}</b> 个域 · 当前 <b>{{ stat.domainLabel }}</b>
        <span class="ks-stat-lod">· L{{ stat.lod }} · {{ stat.scale }}% · {{ stat.mountedCards }} 卡</span>
      </div>
      <span class="ks-grow"></span>
      <label class="ks-search">
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="5.5" cy="5.5" r="4"/><path d="M8.6 8.6 11.5 11.5"/></svg>
        <input id="ks-query" :value="queryText" @input="onQueryInput" placeholder="检索条目…" aria-label="检索知识条目">
        <kbd>/</kbd>
        <span v-if="hitCount > 0" class="ks-hit-badge">{{ hitCount }}</span>
      </label>
      <button class="ks-pill" type="button" :class="{ 'ks-pill--on': viewMode === 'space' }" @click="onViewModeChange('space')">空间</button>
      <button class="ks-pill" type="button" :class="{ 'ks-pill--on': viewMode === 'grid' }" @click="onViewModeChange('grid')">网格</button>
      <button class="ks-pill" type="button" :class="{ 'ks-pill--on': viewMode === 'list' }" @click="onViewModeChange('list')">列表</button>
      <button class="ks-pill" type="button" @click="cam.fitOverview(worldRef, stageRef); renderHUD(); renderMinimapViewport()" v-if="viewMode === 'space'">总览 0</button>
    </header>

    <!-- ============ 空间视图（默认） ============ -->
    <div v-if="viewMode === 'space'" ref="stageRef" class="ks-stage" :class="{ dragging }" @wheel.passive="onWheel" @pointerdown="onPointerDown">
      <div ref="worldRef" class="ks-world" :style="worldStyle" :data-lod="cam.lod">
        <!-- 关系连线（推断，不是人工确认的依赖）
             L0 只画跨域主 platform 粗线帮助认布局；L1/L2 画视口域内完整集 -->
        <svg class="ks-links" aria-hidden="true">
          <line
            v-for="(ln, i) in lines.filter(l => mountedZoneIds.length === 0
              ? l.crossDomain
              : mountedZoneIds.includes(l.zoneId))"
            :key="i"
            :x1="ln.ax" :y1="ln.ay" :x2="ln.bx" :y2="ln.by"
            :stroke="ln.crossDomain ? 'rgba(159,190,207,.10)' : 'rgba(159,190,207,.18)'"
            :stroke-width="hoverPlatform && !ln.crossDomain && ln.platform === hoverPlatform
              ? (parseFloat(lineWidthFactor()) * 1.6).toFixed(2)
              : lineWidthFactor()"
            :stroke-dasharray="ln.crossDomain ? '6 5' : undefined"
            stroke-linecap="round"
          />
        </svg>

        <div
          v-for="z in zones" :key="z.id"
          class="ks-zone"
          :class="{ 'ks-zone--mounted': mountedZoneIds.includes(z.id) }"
          :data-domain="z.id"
          :style="{ left: z.x + 'px', top: z.y + 'px', width: z.w + 'px', height: z.h + 'px' }"
          @click="onZoneClick($event, z)"
          role="region"
          :aria-label="`${z.label} 域，${z.n} 条`"
        >
          <div class="ks-zone-head" @click.stop="onZoneHeadClick($event, z)">
            <span class="ks-zone-bar"></span>
            <span class="ks-zone-name">{{ z.label }}</span>
            <span class="ks-zone-count">{{ z.n }}</span>
          </div>
          <!-- L0（mountedZoneIds 为空）零卡片；L1/L2 域级过滤 + IntersectionObserver 卡级过滤 -->
          <template v-if="mountedZoneIds.includes(z.id)">
            <template v-for="c in cards.filter(cc => cc.zoneId === z.id)" :key="c.id">
            <button
              v-if="mountedCards.has(c.id)"
              class="ks-card"
              :class="{
                'ks-card--hit': hitIds.size && hitIds.has(c.id),
                'ks-card--dim': hitIds.size && !hitIds.has(c.id),
                'ks-card--hover': hoverCardId === c.id,
              }"
              :data-card="c.id"
              :style="{ left: c.x + 'px', top: c.y + 'px', width: c.w + 'px', height: c.h + 'px' }"
              :aria-label="`${c.entry.title}，${c.entry.type || '未分类'}`"
              :aria-expanded="selectedCard?.id === c.id"
              @click="onCardClick($event, c)"
              @mouseenter="hoverCardId = c.id"
              @mouseleave="hoverCardId = hoverCardId === c.id ? null : hoverCardId"
              @keydown="onCardKeydown($event, c)"
            >
              <span class="ks-card-bar"></span>
              <span class="ks-card-body">
                <span class="ks-card-title">{{ c.entry.title }}</span>
                <span class="ks-card-sum">{{ c.entry.summary }}</span>
                <span class="ks-card-foot"><span class="ks-chip">{{ c.entry.type || '未分类' }}</span></span>
              </span>
            </button>
            </template>
          </template>
        </div>
      </div>

      <!-- HUD 标签层：屏幕空间，不随相机缩小 -->
      <div id="ks-hud" class="ks-hud-labels" aria-hidden="true"></div>

      <!-- 迷你地图 + 图例 -->
      <div id="ks-minimap" class="ks-minimap" role="button" tabindex="0" aria-label="迷你地图，点击跳转" @click="onMinimapClick"></div>
      <div class="ks-legend">
        <b>连线是推断关系</b>：同一 platform 的条目连线，不是人工确认的依赖。<br>
        缩放即导航 · 滚轮缩放 / 拖拽平移 / 点域块进分区 / <b>Esc</b> 逐级回退 / <b>0</b> 总览
      </div>

      <!-- 卡片详情侧栏（P3 新增） -->
      <aside v-if="selectedCard" class="ks-side" role="dialog" aria-modal="true" aria-label="知识条目详情">
        <button class="ks-side-close" aria-label="关闭侧栏" @click="closeCard">×</button>
        <header class="ks-side-header">
          <div class="ks-side-meta">
            <span class="ks-chip">{{ selectedCard.entry.type || '未分类' }}</span>
            <span class="ks-chip">{{ selectedCard.entry.platform }}</span>
            <span class="ks-chip">{{ domainById.get(selectedCard.zoneId)?.label }}</span>
          </div>
          <h2>{{ selectedCard.entry.title }}</h2>
        </header>
        <div class="ks-side-body">
          <h3>摘要</h3>
          <p>{{ selectedCard.entry.summary || '当前资料暂未记录摘要。' }}</p>
          <h3>完整正文</h3>
          <pre class="ks-side-content">{{ selectedContent || '…' }}</pre>
          <h3>来源</h3>
          <p>{{ selectedCard.entry.source || '未注明' }} · {{ selectedCard.entry.version || '未标注' }}</p>
          <h3>推断关系 · {{ relatedToSelected.length }}</h3>
          <div class="ks-side-rel">
            <a v-for="r in relatedToSelected" :key="r.id" href="#"
               @click.prevent="openCard(r.id)"
               :aria-label="`切换到 ${r.entry.title}`">{{ r.entry.title }}</a>
            <p v-if="!relatedToSelected.length" class="ks-side-empty">同域内没有同 platform / 同 service 的条目。</p>
          </div>
          <h3>风险</h3>
          <p>{{ selectedCard.entry.risk || '未标注风险' }}</p>
        </div>
      </aside>
    </div>

    <!-- ============ 网格视图：域分组 + 横向卡 ============ -->
    <div v-else-if="viewMode === 'grid'" class="ks-alternate">
      <section v-for="g in gridByDomain" :key="g.zone.id" class="ks-grid-section"
               role="region" :aria-label="`${g.zone.label} 域，${g.items.length} 条`">
        <header class="ks-grid-head">
          <span class="ks-zone-bar"></span>
          <span class="ks-grid-name">{{ g.zone.label }}</span>
          <span class="ks-grid-count">{{ g.items.length }}</span>
        </header>
        <div v-if="g.items.length" class="ks-grid-row">
          <button v-for="c in g.items" :key="c.id" class="ks-alter-card" :class="{ 'ks-card--hit': hitIds.size && hitIds.has(c.id), 'ks-card--dim': hitIds.size && !hitIds.has(c.id) }"
                  :data-card="c.id" @click="onCardClick($event, c)" @keydown="onCardKeydown($event, c)"
                  :aria-label="`${c.entry.title}，${c.entry.type || '未分类'}`" :aria-expanded="selectedCard?.id === c.id">
            <span class="ks-alter-title">{{ c.entry.title }}</span>
            <span class="ks-alter-sum">{{ c.entry.summary }}</span>
            <span class="ks-chip">{{ c.entry.type || '未分类' }}</span>
          </button>
        </div>
        <p v-else class="ks-grid-empty">无条目</p>
      </section>
    </div>

    <!-- ============ 列表视图：全量平铺 ============ -->
    <div v-else class="ks-alternate ks-list">
      <button v-for="c in listItems" :key="c.id" class="ks-list-row"
              :class="{ 'ks-card--hit': hitIds.size && hitIds.has(c.id), 'ks-card--dim': hitIds.size && !hitIds.has(c.id), 'ks-list-row--open': selectedCard?.id === c.id }"
              :data-card="c.id" @click="onCardClick($event, c)" @keydown="onCardKeydown($event, c)"
              :aria-label="`${c.entry.title}，${c.entry.type || '未分类'}`" :aria-expanded="selectedCard?.id === c.id">
        <span class="ks-list-domain">{{ domainById.get(c.zoneId)?.label }}</span>
        <span class="ks-list-title">{{ c.entry.title }}</span>
        <span class="ks-list-sum">{{ c.entry.summary }}</span>
        <span class="ks-chip">{{ c.entry.type || '未分类' }}</span>
      </button>
      <p v-if="!listItems.length" class="ks-grid-empty">检索无结果，或知识库暂无命中条目。</p>
    </div>

    <!-- 三视图共用侧栏（grid / list 也支持） -->
    <aside v-if="selectedCard && viewMode !== 'space'" class="ks-side ks-side--alt" role="dialog" aria-modal="true" aria-label="知识条目详情">
      <button class="ks-side-close" aria-label="关闭侧栏" @click="closeCard">×</button>
      <header class="ks-side-header">
        <div class="ks-side-meta">
          <span class="ks-chip">{{ selectedCard.entry.type || '未分类' }}</span>
          <span class="ks-chip">{{ selectedCard.entry.platform }}</span>
          <span class="ks-chip">{{ domainById.get(selectedCard.zoneId)?.label }}</span>
        </div>
        <h2>{{ selectedCard.entry.title }}</h2>
      </header>
      <div class="ks-side-body">
        <h3>摘要</h3><p>{{ selectedCard.entry.summary || '当前资料暂未记录摘要。' }}</p>
        <h3>完整正文</h3><pre class="ks-side-content">{{ selectedContent || '…' }}</pre>
        <h3>来源</h3><p>{{ selectedCard.entry.source || '未注明' }} · {{ selectedCard.entry.version || '未标注' }}</p>
        <h3>推断关系 · {{ relatedToSelected.length }}</h3>
        <div class="ks-side-rel">
          <a v-for="r in relatedToSelected" :key="r.id" href="#" @click.prevent="openCard(r.id)">{{ r.entry.title }}</a>
        </div>
      </div>
    </aside>
  </article>
</template>

<style scoped>
.ks-root{position:relative;isolation:isolate;height:100%;display:flex;flex-direction:column;background:var(--ds-surface-base);color:var(--ds-color-text);overflow:hidden}

.ks-bar{display:flex;align-items:center;gap:10px;height:56px;padding:0 16px;border-bottom:1px solid var(--ds-color-border);background:var(--ds-surface-base);flex:0 0 auto}
.ks-brand{display:flex;align-items:baseline;gap:8px;white-space:nowrap}
.ks-brand b{font-size:14px;font-weight:500}
.ks-brand span{font:11px/1 var(--ds-font-mono);letter-spacing:.12em;color:var(--ds-color-muted);text-transform:uppercase}
.ks-stat{font:11.5px var(--ds-font-mono);color:var(--ds-color-muted);white-space:nowrap;font-variant-numeric:tabular-nums}
.ks-stat b{color:var(--ds-color-text);font-weight:500}
.ks-stat-lod{margin-left:auto;color:var(--ds-semantic-neutral)}
.ks-grow{flex:1}
.ks-search{display:flex;align-items:center;gap:7px;height:32px;padding:0 10px;min-width:240px;border:1px solid var(--ds-color-border);border-radius:var(--ds-radius-md);background:rgba(0,0,0,.28);color:var(--ds-color-muted)}
.ks-search input{width:100%;border:0;background:none;color:var(--ds-color-text);font:12.5px var(--ds-font-cn);outline:none}
.ks-search kbd{font:10px var(--ds-font-mono);color:var(--ds-color-muted);border:1px solid var(--ds-hairline);border-radius:3px;padding:1px 4px}
.ks-pill{height:30px;padding:0 11px;border:1px solid var(--ds-color-border);border-radius:var(--ds-radius-md);color:var(--ds-color-muted);font-size:12.5px;white-space:nowrap;background:transparent;cursor:pointer}
.ks-pill:hover{background:rgba(232,242,247,.05);border-color:var(--ds-color-border-strong);color:var(--ds-color-text)}
.ks-pill--on{background:rgba(122,215,245,.1);color:var(--ds-color-text);border-color:rgba(122,215,245,.35)}

.ks-stage{position:relative;flex:1 1 auto;overflow:hidden;cursor:grab;background:radial-gradient(120% 90% at 50% 0%,rgba(16,22,29,1) 0%,rgba(10,14,19,1) 60%,rgba(7,10,14,1) 100%)}
.ks-stage.dragging{cursor:grabbing}
.ks-world{position:absolute;left:0;top:0;width:3200px;height:2000px;transform-origin:0 0;will-change:transform}
.ks-links{position:absolute;left:0;top:0;width:3200px;height:2000px;pointer-events:none;overflow:visible}

.ks-card--dim{opacity:.25}
.ks-card--hit{border-color:var(--ds-focus-ring-color);box-shadow:0 0 0 1px rgba(122,215,245,.35),var(--ds-elevation-2)}
.ks-card--hover{z-index:6;border-color:var(--ds-chart-1);box-shadow:var(--ds-elevation-2)}

.ks-zone{position:absolute;border:1px solid var(--ds-color-border);border-radius:var(--ds-radius-lg);background:rgba(21,26,33,.72);box-shadow:var(--ds-elevation-1);transition:border-color 150ms var(--ds-ease-out),background 150ms var(--ds-ease-out);cursor:pointer}
.ks-zone:hover{border-color:var(--ds-color-border-strong);background:rgba(27,33,42,.82)}
.ks-zone-head{position:absolute;left:0;top:0;right:0;display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--ds-hairline);cursor:pointer}
.ks-zone-bar{width:3px;height:14px;border-radius:2px;flex:0 0 auto;background:var(--ds-chart-1)}
.ks-zone-name{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ks-zone-count{margin-left:auto;font:11px var(--ds-font-mono);color:var(--ds-color-muted);font-variant-numeric:tabular-nums;white-space:nowrap}

.ks-card{position:absolute;border-radius:var(--ds-radius-md);border:1px solid var(--ds-color-border);background:var(--ds-surface-raised);box-shadow:var(--ds-elevation-1);overflow:hidden;text-align:left;cursor:pointer;transition:box-shadow 150ms var(--ds-ease-out),border-color 150ms var(--ds-ease-out)}
.ks-card:hover{box-shadow:var(--ds-elevation-2);border-color:var(--ds-color-border-strong);z-index:5}
.ks-card-bar{position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--ds-chart-1)}
.ks-card-body{padding:11px 12px 10px 15px;height:100%;display:flex;flex-direction:column;gap:6px}
.ks-card-title{font-size:13px;font-weight:500;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;color:var(--ds-color-text)}
.ks-card-sum{font-size:11.5px;color:var(--ds-color-muted);line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.ks-card-foot{margin-top:auto;display:flex;align-items:center;gap:6px}
.ks-chip{font:10px/1 var(--ds-font-mono);letter-spacing:.04em;color:var(--ds-semantic-neutral);border:1px solid var(--ds-hairline);border-radius:var(--ds-radius-sm);padding:3px 5px;white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis}

/* LOD：L0 卡片不挂正文；L1 不显示摘要；L2 全显示 */
.ks-world[data-lod="0"] .ks-card-title,.ks-world[data-lod="0"] .ks-card-sum,.ks-world[data-lod="0"] .ks-card-foot{display:none}
.ks-world[data-lod="0"] .ks-card{background:rgba(232,242,247,.05);border-color:rgba(159,190,207,.10)}
.ks-world[data-lod="1"] .ks-card-sum{display:none}

.ks-hud-labels{position:absolute;inset:0;pointer-events:none;z-index:12;overflow:hidden}
.ks-lbl{position:absolute;display:flex;align-items:center;gap:6px;transform:translate(-1px,-50%);overflow:hidden;max-width:100%;padding:2px 6px;border-radius:var(--ds-radius-sm);background:rgba(10,14,19,.72);white-space:nowrap}
.ks-lbl b{font-size:12px;font-weight:500;color:var(--ds-color-text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ks-lbl em{font:10.5px var(--ds-font-mono);font-style:normal;color:var(--ds-color-muted)}

.ks-minimap{position:absolute;right:16px;bottom:16px;width:148px;height:96px;border:1px solid var(--ds-color-border);border-radius:var(--ds-radius-md);background:rgba(14,17,22,.92);z-index:15;cursor:pointer;overflow:hidden}
.ks-minimap i{position:absolute;border-radius:2px;opacity:.5;background:var(--ds-chart-1)}
.ks-mm-vp{position:absolute;border:1px solid var(--ds-focus-ring-color);border-radius:2px;background:rgba(122,215,245,.08);pointer-events:none}
.ks-legend{position:absolute;left:16px;bottom:16px;z-index:15;max-width:330px;padding:9px 11px;border:1px solid var(--ds-color-border);border-radius:var(--ds-radius-md);background:rgba(14,17,22,.92);font-size:11px;color:var(--ds-color-muted);line-height:1.6}
.ks-legend b{color:var(--ds-color-text);font-weight:500}

.ks-hit-badge{height:18px;padding:0 7px;border-radius:999px;background:var(--ds-chart-1);color:#071018;font:10px var(--ds-font-mono);font-weight:600;display:inline-flex;align-items:center;margin-left:6px}

.ks-side{position:absolute;right:0;top:0;bottom:0;width:400px;z-index:22;border-left:1px solid var(--ds-color-border);background:var(--ds-surface-overlay);display:flex;flex-direction:column;transform:translateX(0);box-shadow:var(--ds-elevation-3)}
.ks-side-close{position:absolute;right:12px;top:12px;width:28px;height:28px;border-radius:var(--ds-radius-md);color:var(--ds-color-muted);font-size:16px;cursor:pointer;background:transparent;border:1px solid var(--ds-hairline)}
.ks-side-close:hover{background:rgba(232,242,247,.06);color:var(--ds-color-text)}
.ks-side-header{padding:18px 20px 12px;border-bottom:1px solid var(--ds-hairline)}
.ks-side-header h2{margin:8px 0 0;color:var(--ds-color-text);font:500 18px/1.4 var(--ds-font-cn)}
.ks-side-meta{display:flex;gap:6px;flex-wrap:wrap}
.ks-side-body{flex:1;overflow:auto;padding:14px 20px 28px;font-size:13px;color:var(--ds-color-muted);line-height:1.7}
.ks-side-body h3{margin:14px 0 6px;font:11px/1 var(--ds-font-mono);letter-spacing:.12em;color:var(--ds-semantic-neutral);text-transform:uppercase}
.ks-side-body p{margin:4px 0}
.ks-side-content{margin:4px 0 0;padding:12px 14px;border:1px solid var(--ds-hairline);border-radius:var(--ds-radius-md);background:rgba(0,0,0,.25);font-size:12.5px;white-space:pre-wrap;font-family:var(--ds-font-cn);color:var(--ds-color-text);line-height:1.6;max-height:360px;overflow:auto}
.ks-side-rel{display:flex;flex-direction:column;gap:6px}
.ks-side-rel a{color:var(--ds-color-muted);text-decoration:none;border-left:2px solid var(--ds-color-border);padding-left:8px;font-size:12px}
.ks-side-rel a:hover{color:var(--ds-color-text);border-color:var(--ds-chart-1)}
.ks-side-empty{margin:0;color:var(--ds-semantic-neutral);font-size:12px}

/* ---------- 网格视图 ---------- */
.ks-alternate{flex:1;overflow:auto;padding:18px 22px;display:flex;flex-direction:column;gap:14px;background:var(--ds-surface-base)}
.ks-grid-section{border:1px solid var(--ds-color-border);border-radius:var(--ds-radius-lg);background:rgba(21,26,33,.6);padding:14px 16px}
.ks-grid-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.ks-grid-name{font-size:13px;font-weight:500}
.ks-grid-count{margin-left:auto;font:11px var(--ds-font-mono);color:var(--ds-color-muted)}
.ks-grid-row{display:flex;flex-wrap:wrap;gap:10px}
.ks-alter-card{min-width:180px;max-width:220px;text-align:left;border:1px solid var(--ds-color-border);border-radius:var(--ds-radius-md);background:var(--ds-surface-raised);padding:10px 12px;display:flex;flex-direction:column;gap:4px;cursor:pointer;color:var(--ds-color-text)}
.ks-alter-card:hover{border-color:var(--ds-color-border-strong);box-shadow:var(--ds-elevation-2)}
.ks-alter-title{font-size:12.5px;font-weight:500;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.ks-alter-sum{font-size:11px;color:var(--ds-color-muted);line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.ks-grid-empty{margin:0;color:var(--ds-semantic-neutral);font-size:12px}

/* ---------- 列表视图 ---------- */
.ks-list{gap:0;padding:0}
.ks-list-row{display:grid;grid-template-columns:140px 1fr 2fr auto;gap:12px;align-items:center;padding:10px 20px;border-top:1px solid var(--ds-hairline);background:transparent;border-left:3px solid transparent;border-radius:0;color:var(--ds-color-muted);cursor:pointer;text-align:left}
.ks-list-row:hover{background:rgba(232,242,247,.04);border-left-color:var(--ds-chart-1)}
.ks-list-row--open{background:rgba(232,242,247,.06);border-left-color:var(--ds-focus-ring-color)}
.ks-list-domain{font:11px var(--ds-font-mono);letter-spacing:.08em;color:var(--ds-semantic-neutral);text-transform:uppercase}
.ks-list-title{font-size:12.5px;font-weight:500;color:var(--ds-color-text)}
.ks-list-sum{font-size:11.5px;color:var(--ds-color-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

.ks-side--alt{right:0}

@media (prefers-reduced-motion: reduce){*{transition:none!important;animation:none!important}}
@media (max-width:900px){.ks-brand span,.ks-stat-lod{display:none}.ks-search{min-width:120px}.ks-legend{display:none}.ks-stat{font-size:10px}}
</style>
