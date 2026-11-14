<template>
  <div ref="root" class="webgl-host">
    <canvas ref="canvas" class="webgl-host__canvas" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'

/**
 * 唯一 canvas 容器：把 canvas 的创建/销毁集中在一个组件里，
 * 避免不同视觉组件各自 new WebGLRenderer 抢上下文（MASTER.md 单 canvas 约束）。
 */
const emit = defineEmits(['mount'])
const root = ref(null)
const canvas = ref(null)

onMounted(() => {
  emit('mount', { canvas: canvas.value, container: root.value })
})
</script>

<style scoped>
.webgl-host {
  position: relative;
  width: 100%;
  max-width: 420px;
  margin-inline: auto;
  aspect-ratio: 3 / 4;
  overflow: hidden;
}

.webgl-host__canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
