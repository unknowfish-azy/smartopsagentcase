<script setup>
/* MosaicDetailPopover.vue — 锚定格子的悬浮详情窗（T26）
 * 形态：屏幕空间浮层（非全屏遮罩、非右侧抽屉）；世界不动、邻居降饱和由父级处理。
 * 字段按真实数据降级：summary 缺 → 项目文案；applicableVersion 占位符 → —；
 * evidenceRefs 不渲染；level/verification/category 不渲染；关联知识仅 relatedIds 存在时渲染。
 * 行为：Esc/外部点击关闭、焦点陷阱、打开聚焦关闭键、关闭回焦父级负责。
 */
import { ref, onMounted, nextTick } from 'vue'
import { normalizeRisk, isPlaceholderVersion } from './mosaicType.js'

const props = defineProps({
  entry: { type: Object, required: true },
  tile: { type: Object, required: true },
  pos: { type: Object, required: true },   // { left, top } 屏幕坐标（stage 内）
})
const emit = defineEmits(['close', 'navigate'])

const closeBtn = ref(null)
const panel = ref(null)

onMounted(async () => {
  await nextTick()
  closeBtn.value?.focus()
})

function onKeydown (e) {
  if (e.key === 'Escape') { e.stopPropagation(); emit('close'); return }
  if (e.key === 'Tab') {
    // 简单焦点陷阱：仅在关闭键与面板内可聚焦元素间循环
    const focusables = panel.value?.querySelectorAll('button, a[href], [tabindex]:not([tabindex="-1"])')
    if (!focusables || !focusables.length) return
    const first = focusables[0], last = focusables[focusables.length - 1]
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }
}

function onContentClick (e) {
  // 点击浮层外部（stage）由父级处理；此处仅阻止冒泡到 stage 的拖拽/缩放
  e.stopPropagation()
}

const risk = normalizeRisk(props.entry.risk)
const apVersion = isPlaceholderVersion(props.entry.applicableVersion)
  ? '—'
  : (props.entry.applicableVersion || '—')
const contentParas = Array.isArray(props.entry.content)
  ? props.entry.content
  : String(props.entry.content || '').split(/\n\n+/).filter(Boolean)
const related = Array.isArray(props.entry.relatedIds) ? props.entry.relatedIds : []
</script>

<template>
  <div
    ref="panel"
    class="mw-pop"
    :style="pos"
    role="dialog"
    aria-modal="false"
    :aria-label="`${tile.domainLabel} 知识详情：${entry.title}`"
    @keydown="onKeydown"
    @pointerdown="onContentClick"
  >
    <button ref="closeBtn" class="mw-pop-close" aria-label="关闭详情" @click="emit('close')">×</button>
    <header class="mw-pop-head" :style="{ '--mw-domain': tile.domainColor }">
      <div class="mw-pop-banner">
        <span class="mw-pop-domain">{{ tile.domainLabel }}</span>
        <span class="mw-pop-type">{{ entry.type || '未分类' }}</span>
      </div>
      <h2 class="mw-pop-title">{{ entry.title }}</h2>
    </header>
    <div class="mw-pop-body">
      <div class="mw-pop-kv">
        <span>{{ entry.platform || '—' }}</span>
        <span v-for="t in (entry.tags || [])" :key="t">{{ t }}</span>
      </div>

      <p class="mw-pop-section">目录</p>
      <div class="mw-pop-row">{{ entry.directory?.pathKey || '—' }}</div>

      <p class="mw-pop-section">来源 / 版本 / 适用版本</p>
      <div class="mw-pop-row">
        <b>来源</b> {{ entry.source || '未注明' }} ·
        <b>版本</b> {{ entry.version || '未标注' }} ·
        <b>适用</b> {{ apVersion }}
      </div>

      <p class="mw-pop-section">摘要</p>
      <div class="mw-pop-row">{{ entry.summary || '当前资料暂未记录摘要。' }}</div>

      <p class="mw-pop-section">风险</p>
      <div class="mw-pop-row">{{ risk.label }}（原始：{{ entry.risk || '未标注' }}）</div>

      <p class="mw-pop-section">核验状态</p>
      <div class="mw-pop-row">未核验 · UNVERIFIED</div>

      <p class="mw-pop-section">正文</p>
      <div class="mw-pop-content" v-for="(p, i) in contentParas" :key="i">{{ p }}</div>

      <template v-if="related.length">
        <p class="mw-pop-section">关联知识 · {{ related.length }}</p>
        <div class="mw-pop-rel">
          <a v-for="rid in related" :key="rid" @click.prevent="emit('navigate', rid)">{{ rid }}</a>
        </div>
      </template>
      <p v-else class="mw-pop-empty">该项暂无关联知识。</p>
    </div>
  </div>
</template>
