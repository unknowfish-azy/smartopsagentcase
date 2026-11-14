<script setup>
/* MosaicWallView.vue — 照片墙主容器（T24 密铺 + T25 缩放平移 + T26 详情接线）
 * 设计依据：docs/design/knowledge-photo-wall-v1/DESIGN.md v1.1
 * 关键：缩放只写单容器 transform（useSpaceCamera.apply 命令式）+ data-size + --mw-inv-k（反缩放标签），
 *       不逐帧改 Vue 状态、不逐格 v-if；布局坐标只在 field 变化时重算。
 * 自管键盘（Ctrl+K 搜索 / Esc 关闭 / 方向键导航 / Enter 开详情），父级全局 onKeyDown 在 mosaic 下 early-return。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import { searchKnowledgeEntries, knowledgeDomains } from '../../knowledgeCatalog.js'
import { useSpaceCamera } from '../useSpaceCamera.js'
import { buildMosaic, sizeForK, BASE_TILE } from './mosaicLayout.js'
import MosaicTile from './MosaicTile.vue'
import MosaicDomainTag from './MosaicDomainTag.vue'
import MosaicDetailPopover from './MosaicDetailPopover.vue'
import FieldSearch from '../FieldSearch.vue'
import './mosaic.css'

/* —— 数据（全量 737 条，不截断） —— */
const entries = searchKnowledgeEntries({})

/* —— 舞台尺寸（决定列数） —— */
const stageRef = ref(null)
const worldRef = ref(null)
const stageSize = ref({ w: 1440, h: 800 })

const field = computed(() => buildMosaic(entries, knowledgeDomains, stageSize.value.w))

/* —— 相机（复用，禁改 useSpaceCamera.js） —— */
const cam = useSpaceCamera()

let lastSize = null
function applySize () {
  const s = sizeForK(cam.k.value).id
  if (!worldRef.value) return
  worldRef.value.dataset.size = s
  worldRef.value.style.setProperty('--mw-inv-k', String(1 / cam.k.value))
  // 仅当档位跨越 S0 边界时，批量更新 tile 的 tabindex（极廉价、偶发），避免逐帧写状态
  if (s !== lastSize) {
    if (s === 's0') {
      worldRef.value.querySelectorAll('.mw-tile').forEach(el => el.setAttribute('tabindex', '-1'))
    } else {
      worldRef.value.querySelectorAll('.mw-tile').forEach(el => el.setAttribute('tabindex', '0'))
    }
    lastSize = s
  }
}

function onWheel (e) {
  if (blocking.value) return
  e.preventDefault()
  const st = stageRef.value.getBoundingClientRect()
  cam.zoomAt(e.clientX - st.left, e.clientY - st.top, Math.exp(-e.deltaY * 0.0015), worldRef.value)
  applySize()
}
function zoomBy (factor) {
  if (blocking.value) return
  const st = stageRef.value.getBoundingClientRect()
  cam.zoomAt(st.width / 2, st.height / 2, factor, worldRef.value)
  applySize()
}
function onSlider (e) {
  if (blocking.value) return
  cam.apply(worldRef.value, { k: parseFloat(e.target.value) })
  applySize()
}
function overview () {
  if (blocking.value) return
  cam.fitOverview(worldRef.value, stageRef.value, { w: field.value.worldW, h: field.value.worldH })
  applySize()
}

/* —— 拖拽平移（禁旋转） —— */
const dragging = ref(false)
let dragStartX = 0, dragStartY = 0, dragStartTx = 0, dragStartTy = 0, moved = 0
function onPointerDown (e) {
  if (blocking.value) return
  if (e.target.closest('.mw-tag, .mw-pop, .mw-hud, .mw-domains')) return
  dragging.value = true
  moved = 0
  dragStartX = e.clientX; dragStartY = e.clientY
  dragStartTx = cam.tx.value; dragStartTy = cam.ty.value
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
}
function onPointerMove (e) {
  if (!dragging.value) return
  const dx = e.clientX - dragStartX, dy = e.clientY - dragStartY
  moved = Math.max(moved, Math.abs(dx) + Math.abs(dy))
  cam.tx.value = dragStartTx + dx
  cam.ty.value = dragStartTy + dy
  cam.apply(worldRef.value)
}
function onPointerUp () {
  dragging.value = false
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
}

/* —— 详情窗（T26） —— */
const selectedTile = ref(null)
const popPos = ref({ left: '0px', top: '0px' })
const blocking = computed(() => !!selectedTile.value || searchOpen.value)

function tileById (id) {
  return field.value.tiles.find(t => t.id === id) || null
}
function computePos (tile) {
  const st = stageRef.value.getBoundingClientRect()
  const sx = tile.x * cam.k.value + cam.tx.value
  const sy = tile.y * cam.k.value + cam.ty.value
  const sw = BASE_TILE * cam.k.value
  const sh = BASE_TILE * cam.k.value
  let left = sx + sw + 14
  if (left + 452 > st.width) left = sx - 452 - 14
  if (left < 12) left = 12
  let top = sy + sh / 2 - 120
  if (top < 12) top = 12
  if (top + 300 > st.height) top = st.height - 312
  if (top < 12) top = 12
  return { left: left + 'px', top: top + 'px' }
}
function openTile (tile) {
  if (moved > 4) { moved = 0; return }
  if (!tile) return
  if (lastSize === 's0') {
    // S0 档点击 → 放大到 S2 并居中该格，不打开详情
    cam.apply(worldRef.value, { k: 1.0 })
    cam.centerOn(tile.x + BASE_TILE / 2, tile.y + BASE_TILE / 2, 1.0, worldRef.value, stageRef.value)
    applySize()
    return
  }
  selectedTile.value = tile
  nextTick(() => { popPos.value = computePos(tile) })
}
function closeTile () {
  const id = selectedTile.value?.id
  selectedTile.value = null
  if (id) {
    const el = worldRef.value?.querySelector(`.mw-tile[data-card="${id}"]`)
    el?.focus()
  }
}
function navigate (id) {
  const t = tileById(id)
  if (!t) return
  selectedTile.value = t
  nextTick(() => { popPos.value = computePos(t) })
}

/* —— 域筛选（降饱和，不重排） —— */
const activeDomain = ref(null)
function toggleDomain (id) {
  activeDomain.value = activeDomain.value === id ? null : id
}
function dimmed (t) {
  if (selectedTile.value && selectedTile.value.id !== t.id) return true
  if (activeDomain.value && t.entry.directory.domainId !== activeDomain.value) return true
  return false
}
function isHit (t) {
  return searchHitId.value === t.id
}

/* —— 搜索（Ctrl+K 复用 FieldSearch） —— */
const searchOpen = ref(false)
const searchQuery = ref('')
const searchResults = ref([])
const searchHitId = ref(null)
function openSearch () { searchOpen.value = true }
function onSearchInput (v) {
  searchQuery.value = v
  searchResults.value = v.trim() ? searchKnowledgeEntries({ query: v }).slice(0, 60) : []
  searchHitId.value = null
}
function onSearchSelect (entry) {
  const t = tileById(entry.id)
  searchOpen.value = false
  if (!t) return
  cam.apply(worldRef.value, { k: 1.0 })
  cam.centerOn(t.x + BASE_TILE / 2, t.y + BASE_TILE / 2, 1.0, worldRef.value, stageRef.value)
  applySize()
  searchHitId.value = t.id
}

/* —— 键盘（自管；父级 onKeyDown 在 mosaic 下 early-return） —— */
function onKey (e) {
  if (e.ctrlKey && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault(); openSearch(); return
  }
  if (e.key === 'Escape') {
    if (selectedTile.value) { closeTile(); return }
    if (searchOpen.value) { searchOpen.value = false; return }
    return
  }
  if (blocking.value) return
  if (e.key.startsWith('Arrow')) {
    e.preventDefault()
    moveFocus(e.key)
  } else if (e.key === 'Enter' || e.key === ' ') {
    if (document.activeElement?.classList?.contains('mw-tile')) {
      e.preventDefault()
      const id = document.activeElement.dataset.card
      openTile(tileById(id))
    }
  }
}
function moveFocus (dir) {
  const tiles = field.value.tiles
  const f = tiles.find(t => t.id === focusedId.value)
  if (!f) {
    const first = stageRef.value?.querySelector('.mw-tile')
    first?.focus(); if (first) focusedId.value = first.dataset.card
    return
  }
  let target = null
  if (dir === 'ArrowRight') target = tiles.find(t => t.row === f.row && t.col === f.col + 1)
  if (dir === 'ArrowLeft') target = tiles.find(t => t.row === f.row && t.col === f.col - 1)
  if (dir === 'ArrowDown') target = tiles.find(t => t.col === f.col && t.row === f.row + 1)
  if (dir === 'ArrowUp') target = tiles.find(t => t.col === f.col && t.row === f.row - 1)
  if (target) {
    const el = worldRef.value?.querySelector(`.mw-tile[data-card="${target.id}"]`)
    el?.focus(); if (el) focusedId.value = target.id
  }
}
const focusedId = ref(null)

/* —— 挂载 / 卸载 —— */
let ro = null
onMounted(() => {
  const st = stageRef.value
  if (st) {
    const r = st.getBoundingClientRect()
    stageSize.value = { w: r.width || 1440, h: r.height || 800 }
  }
  cam.fitOverview(worldRef.value, stageRef.value, { w: field.value.worldW, h: field.value.worldH })
  applySize()
  window.addEventListener('keydown', onKey)
  if (st) {
    ro = new ResizeObserver(() => {
      if (blocking.value) return
      const r = st.getBoundingClientRect()
      stageSize.value = { w: r.width || 1440, h: r.height || 800 }
      // 重新总览适配新视口（不破坏坐标，仅相机复位）
      cam.fitOverview(worldRef.value, stageRef.value, { w: field.value.worldW, h: field.value.worldH })
      applySize()
    })
    ro.observe(st)
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  ro?.disconnect()
  onPointerUp()
})

/* 屏幕尺寸变化导致 field 重算后，确保世界尺寸同步 */
watch(() => field.value.worldW, () => {
  if (worldRef.value) {
    worldRef.value.style.width = field.value.worldW + 'px'
    worldRef.value.style.height = field.value.worldH + 'px'
  }
})
</script>

<template>
  <div class="mw-root">
    <div class="mw-hud">
      <div class="mw-hud-left">
        <span class="mw-title">知识库 · KNOWLEDGE WALL</span>
        <span class="mw-count">{{ field.total }} 格 · {{ knowledgeDomains.length }} 个域 · 照片墙</span>
      </div>
      <div class="mw-hud-right">
        <button class="mw-btn" type="button" @click="openSearch">搜索 <kbd>Ctrl K</kbd></button>
        <div class="mw-zoom">
          <button type="button" aria-label="缩小" @click="zoomBy(1 / 1.25)">−</button>
          <input
            type="range"
            :min="cam.kMin" :max="cam.kMax" step="0.01"
            :value="cam.k.value"
            aria-label="缩放"
            @input="onSlider"
          >
          <button type="button" aria-label="放大" @click="zoomBy(1.25)">+</button>
          <button type="button" @click="overview">总览</button>
          <span class="mw-zoom-label">{{ Math.round(cam.k.value * 100) }}%</span>
        </div>
      </div>
    </div>

    <div class="mw-domains">
      <button
        v-for="d in knowledgeDomains" :key="d.id"
        type="button"
        class="mw-chip"
        :class="{ 'mw-chip--on': activeDomain === d.id }"
        @click="toggleDomain(d.id)"
      >{{ d.label }}</button>
      <button v-if="activeDomain" type="button" class="mw-chip-clear" @click="activeDomain = null">清除筛选</button>
    </div>

    <div
      ref="stageRef"
      class="mw-stage"
      :class="{ 'mw-stage--busy': dragging }"
      @wheel.prevent="onWheel"
      @pointerdown="onPointerDown"
    >
      <div
        ref="worldRef"
        class="mw-world"
        :style="{ width: field.worldW + 'px', height: field.worldH + 'px' }"
      >
        <MosaicTile
          v-for="t in field.tiles" :key="t.id"
          :entry="t.entry" :tile="t"
          :hit="isHit(t)" :dim="dimmed(t)" :selected="!!selectedTile && selectedTile.id === t.id"
          @open="openTile"
        />
        <MosaicDomainTag
          v-for="tag in field.tags" :key="'d' + tag.domainId"
          :label="tag.label" :color="tag.color" :kind="tag.isSmall ? 'fold' : 'domain'"
          :world-x="tag.worldX" :world-y="tag.worldY"
          @jump="toggleDomain(tag.domainId)"
        />
        <MosaicDomainTag
          v-for="st in field.serviceTags" :key="'s' + st.serviceId + st.worldX"
          :label="st.label" :kind="'service'"
          :world-x="st.worldX" :world-y="st.worldY"
        />
      </div>

      <MosaicDetailPopover
        v-if="selectedTile"
        :entry="selectedTile.entry" :tile="selectedTile" :pos="popPos"
        @close="closeTile" @navigate="navigate"
      />
      <FieldSearch
        v-if="searchOpen"
        :query="searchQuery" :results="searchResults"
        @update:query="onSearchInput" @select="onSearchSelect" @close="searchOpen = false"
      />
    </div>
  </div>
</template>
