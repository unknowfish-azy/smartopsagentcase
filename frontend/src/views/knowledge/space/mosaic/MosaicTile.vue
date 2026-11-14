<script setup>
/* MosaicTile.vue — 照片墙单格（纯 props，无内部响应式状态）
 * 四层配方：域色底 / 类型色条 / 短码+标题+标签 / risk 角标
 * 档位显隐由 #mw-world[data-size] 的 CSS 后代选择器控制（不在本组件做 v-if，避免 737 个逐帧响应式判定）。
 */
const props = defineProps({
  entry: { type: Object, required: true },
  tile: { type: Object, required: true },
  hit: { type: Boolean, default: false },
  dim: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
})
const emit = defineEmits(['open'])

const tileStyle = {
  '--mw-domain': props.tile.domainColor,
  '--mw-type': props.tile.typeColor,
  '--mw-risk': props.tile.riskColor,
  // 关键：按布局算出的世界坐标静态定位（一次性，不随缩放重算；缩放只改 #mw-world transform）
  transform: `translate3d(${props.tile.x}px, ${props.tile.y}px, 0)`,
}
const ariaLabel =
  `${props.tile.domainLabel} · ${props.tile.cls} · ${props.entry.title} · ${props.tile.risk.label}`
</script>

<template>
  <button
    class="mw-tile"
    :class="{ 'mw-tile--hit': hit, 'mw-tile--dim': dim, 'mw-tile--active': selected }"
    :data-card="tile.id"
    :style="tileStyle"
    :aria-label="ariaLabel"
    :title="entry.title"
    @click="emit('open', tile)"
  >
    <span class="mw-tile-bar"></span>
    <span class="mw-tile-code">{{ tile.short }}</span>
    <span class="mw-tile-title">{{ entry.title }}</span>
    <span class="mw-tile-tag">{{ (entry.tags && entry.tags[0]) || '' }}</span>
    <span class="mw-tile-sum">{{ entry.summary || '当前资料暂未记录摘要。' }}</span>
    <span class="mw-tile-type">{{ entry.type || '未分类' }}</span>
    <span class="mw-tile-risk">{{ tile.risk.short }}</span>
  </button>
</template>
