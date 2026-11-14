<script setup>
/* MosaicDomainTag.vue — 域 / service 浮标签（屏幕空间，由父级定位；不随相机缩小）
 * 作为 #mw-world 的子元素，父级用 --mw-inv-k 反缩放保持恒定屏幕字号。
 */
defineProps({
  label: { type: String, required: true },
  color: { type: String, default: 'var(--ds-chart-neutral)' },
  kind: { type: String, default: 'domain' },   // 'domain' | 'fold' | 'service'
  worldX: { type: Number, default: 0 },
  worldY: { type: Number, default: 0 },
})
const emit = defineEmits(['jump'])
</script>

<template>
  <button
    class="mw-tag"
    :class="`mw-tag--${kind}`"
    :style="{ left: worldX + 'px', top: worldY + 'px', '--mw-tag': color }"
    type="button"
    @click="emit('jump')"
  >
    {{ label }}
  </button>
</template>
