<template>
  <!--
    解码文本（主题二配方 C）：真实值先以随机字符呈现，再逐字落定。
    无障碍：role="img" + aria-label 固定为真实值，落定过程的中间态对
    屏幕阅读器不可见（role=img 的后代内容默认被辅助技术忽略）。
    reduced-motion 双通道（visualMode store + prefers-reduced-motion）下
    直接显示终值，不做动画。
  -->
  <component :is="tag" class="decode-text" role="img" :aria-label="text || undefined">
    {{ display }}
  </component>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { decodeDurationFor, frameText } from './decodeText.js'
import { visualMode } from '../../visual/visualMode.js'

const props = defineProps({
  /** 目标真实值（如 traceId / taskId） */
  value: { type: [String, Number], default: '' },
  /** 覆盖时长（毫秒）；0 = 按长度自动（240–400ms） */
  duration: { type: Number, default: 0 },
  /** 渲染标签，默认 span；嵌 <code> 场景可传 'code' */
  tag: { type: String, default: 'span' }
})

const text = computed(() => (props.value == null ? '' : String(props.value)))
const display = ref('')
let rafId = 0

const prefersReducedMotion = () => {
  if (visualMode.value === 'reduced-motion') return true
  return globalThis.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false
}

function stop() {
  if (rafId) { cancelAnimationFrame(rafId); rafId = 0 }
}

function run() {
  stop()
  const target = text.value
  if (!target) { display.value = ''; return }
  // 减少动态偏好：一步到位，避免用户在任何模式下等到半解码状态。
  if (prefersReducedMotion()) { display.value = target; return }
  const total = props.duration > 0 ? props.duration : decodeDurationFor([...target].length)
  const start = performance.now()
  const step = now => {
    const progress = Math.min(1, (now - start) / total)
    display.value = frameText(target, progress)
    if (progress < 1) rafId = requestAnimationFrame(step)
    else rafId = 0
  }
  rafId = requestAnimationFrame(step)
}

watch(text, run, { immediate: true })
// 视觉模式切换时立即落定：不允许停留在随机字符状态。
watch(visualMode, run)
onBeforeUnmount(stop)
</script>

<style scoped>
/* 等宽数字：落定过程中字符宽度不跳动，布局稳定。 */
.decode-text { font-variant-numeric: tabular-nums; }
</style>
