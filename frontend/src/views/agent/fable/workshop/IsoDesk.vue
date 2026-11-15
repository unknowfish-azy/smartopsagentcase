<template>
  <!-- 单张等距工位：地板影 + 桌台（顶/左/右三面）+ 终端 + 几何小人 + 标签（DESIGN §5） -->
  <g
    class="ws-desk"
    :class="{ 'is-lit': state === 'lit', 'is-rehearsal': state === 'rehearsal' }"
    :data-tone="desk.tone"
    :transform="`translate(${desk.sx} ${desk.sy})`"
    role="button"
    tabindex="0"
    :aria-label="ariaLabel"
    @click="$emit('select', desk)"
    @keydown.enter.prevent="$emit('select', desk)"
    @keydown.space.prevent="$emit('select', desk)"
    @mouseenter="hover = true"
    @mouseleave="hover = false"
    @focus="hover = true"
    @blur="hover = false"
  >
    <!-- 键盘命中区（可见描边由 :focus-visible 控制） -->
    <rect class="ws-desk-hit" x="-48" y="-58" width="96" height="92" rx="6" />

    <!-- 地板影 -->
    <ellipse class="ws-desk-shadow" cx="0" cy="2" rx="36" ry="17" />

    <!-- 几何小人（画在桌台之前 → 立在桌后；E6 注视 = 头部随活跃方向微移） -->
    <g class="ws-figure" :transform="`translate(-4 -8)`">
      <path class="ws-figure-body" d="M-5 0 L5 0 L8.5 15 L-8.5 15 Z" />
      <circle class="ws-figure-head" cx="0" cy="-7" r="5" :transform="`translate(${gazeX} ${gazeY})`" />
      <path v-if="state === 'lit'" class="ws-figure-arm" d="M5 -2 L13 -9" />
    </g>

    <!-- 桌台：前左立面（D-C）/ 前右立面（C-B）/ 顶面（z = 18px） -->
    <polygon class="ws-desk-face-left" points="-44.8,-22.8 9.6,4.4 9.6,22.4 -44.8,-4.8" />
    <polygon class="ws-desk-face-right" points="9.6,4.4 44.8,-13.2 44.8,4.8 9.6,22.4" />
    <polygon
      class="ws-desk-top"
      points="-9.6,-40.4 44.8,-13.2 9.6,4.4 -44.8,-22.8"
    />

    <!-- 终端：支架 + 屏面（亮灯 = E1，屏面填充工位 tone 并发光） -->
    <polygon class="ws-terminal-foot" points="-4,-26 8,-19.5 3,-17 -9,-23.5" />
    <polygon class="ws-terminal-screen" points="-8,-41 10,-31.5 10,-19.5 -8,-29" />

    <!-- 标签（走正文令牌，进 T11 对比度矩阵） -->
    <text class="ws-desk-cn" y="34">{{ desk.labelCn }}</text>
    <text class="ws-desk-en" y="45">{{ desk.labelEn }}</text>

    <!-- tooltip（门禁 5：亮灯可溯源：闭环 id / stage / 耗时 / 时间） -->
    <g v-if="hover && info" class="ws-desk-tip" :transform="`translate(${-46} ${-92})`">
      <rect x="0" y="0" width="150" height="42" rx="4" />
      <text y="12">{{ tipLine1 }}</text>
      <text y="23">{{ tipLine2 }}</text>
      <text y="34">{{ tipLine3 }}</text>
    </g>
  </g>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  /** buildWorkshop 产出的工位几何（含 sx/sy/id/tone/label） */
  desk: { type: Object, required: true },
  /** 四态之一：idle / lit / pulsing / rehearsal（pulsing 与 lit 同帧态，仅动画差异） */
  state: { type: String, default: 'idle' },
  /** deskActivity 命中的闭环信息（无则不可溯源，tooltip 不出现） */
  info: { type: Object, default: null },
  /** E6 注视：小人头部朝向活跃工位的微移（-1..1） */
  gaze: { type: Object, default: () => ({ dx: 0, dy: 0 }) }
})

defineEmits(['select'])

const hover = ref(false)

const gazeX = computed(() => Math.max(-1, Math.min(1, Number(props.gaze?.dx) || 0)) * 2)
const gazeY = computed(() => Math.max(-1, Math.min(1, Number(props.gaze?.dy) || 0)) * 1)

const ariaLabel = computed(() => {
  const base = `${props.desk.labelCn}工位`
  if (props.state === 'lit' && props.info) return `${base}，亮灯，正在处理闭环 ${props.info.loopId}`
  if (props.state === 'rehearsal') return `${base}，演练态`
  return `${base}，空闲`
})

function formatDuration(ms) {
  if (!Number.isFinite(ms)) return '—'
  return ms >= 60_000 ? `${(ms / 60_000).toFixed(1)}min` : `${(ms / 1000).toFixed(1)}s`
}

function formatTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString('zh-CN', { hour12: false })
}

const tipLine1 = computed(() => `LOOP ${props.info?.loopId || '—'}`)
const tipLine2 = computed(() => `STAGE ${props.info?.stage || '—'} · ${formatDuration(props.info?.durationMs)}`)
const tipLine3 = computed(() => `AT ${formatTime(props.info?.updatedAt)}`)
</script>

<style scoped>
.ws-desk {
  cursor: pointer;
  outline: none;
}

.ws-desk-hit {
  fill: transparent;
  stroke: transparent;
  stroke-width: 1;
}

.ws-desk:focus-visible .ws-desk-hit {
  stroke: var(--fab-gaze, #7ad7f5);
  stroke-dasharray: 3 3;
}

.ws-desk-shadow {
  fill: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  opacity: 0.18;
}

/* tone → 点缀色（≤15% 面积，DESIGN §5）；几何体走 surface 令牌保证双主题同构 */
.ws-desk[data-tone='sage'] { --ws-tone: var(--fab-sage, #8bcfb4); }
.ws-desk[data-tone='clay'] { --ws-tone: var(--fab-clay, #2496ed); }
.ws-desk[data-tone='butter'] { --ws-tone: var(--fab-butter, #d9b96d); }
.ws-desk[data-tone='apricot'] { --ws-tone: var(--fab-apricot, #7ad7f5); }
.ws-desk[data-tone='gaze'] { --ws-tone: var(--fab-gaze, #7ad7f5); }
.ws-desk[data-tone='plum'] { --ws-tone: var(--fab-plum, #9b8cf0); }

.ws-desk-top {
  fill: var(--ds-surface-raised, #151A21);
  stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  stroke-width: 1;
}
.ws-desk-face-left {
  fill: var(--ds-surface-base, #0E1116);
  stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  stroke-width: 0.6;
}
.ws-desk-face-right {
  fill: color-mix(in srgb, var(--ds-surface-base, #0E1116) 50%, var(--ds-surface-overlay, #1B212A) 50%);
  stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  stroke-width: 0.6;
}

.ws-figure-body {
  fill: var(--fab-paper-46, rgba(232, 242, 247, 0.46));
}
.ws-figure-head {
  fill: var(--fab-paper-72, rgba(232, 242, 247, 0.72));
  transition: transform 0.6s var(--fab-ease-io, cubic-bezier(0.4, 0, 0.2, 1));
}
.ws-figure-arm {
  stroke: var(--fab-paper-72, rgba(232, 242, 247, 0.72));
  stroke-width: 2;
  stroke-linecap: round;
  fill: none;
}

.ws-terminal-foot {
  fill: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
}
.ws-terminal-screen {
  fill: var(--ds-surface-base, #0E1116);
  stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  stroke-width: 0.8;
  transition: fill 0.3s var(--fab-ease-io, cubic-bezier(0.4, 0, 0.2, 1));
}

.ws-desk.is-lit .ws-terminal-screen {
  fill: var(--ws-tone, var(--fab-gaze, #7ad7f5));
}

.ws-desk-cn {
  fill: var(--fab-paper-72, rgba(232, 242, 247, 0.72));
  font: 9px/1 var(--fab-mono, ui-monospace, monospace);
  text-anchor: middle;
}
.ws-desk-en {
  fill: var(--fab-paper-46, rgba(232, 242, 247, 0.46));
  font: 6.5px/1 var(--fab-mono, ui-monospace, monospace);
  letter-spacing: 0.12em;
  text-anchor: middle;
}

.ws-desk.is-rehearsal .ws-terminal-screen,
.ws-desk.is-rehearsal .ws-figure-head {
  opacity: 0.5;
}

.ws-desk-tip rect {
  fill: var(--ds-surface-raised, #151A21);
  stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
}
.ws-desk-tip text {
  x: 7;
  fill: var(--fab-paper-72, rgba(232, 242, 247, 0.72));
  font: 8px/1 var(--fab-mono, ui-monospace, monospace);
}
.ws-desk-tip text:first-of-type {
  fill: var(--ws-tone, var(--fab-gaze, #7ad7f5));
}
</style>
