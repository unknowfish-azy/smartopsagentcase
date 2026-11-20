<script setup>
/**
 * 轮速圆形指针表盘：正上方为 0，左右对称 ±120°，正转绿、倒车橙。
 * 控制台遥测面板与设备详情弹窗共用，保证两处读数与视觉一致。
 */
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, default: '' },
  speed: { type: Number, default: null },
  angular: { type: Number, default: null },
  max: { type: Number, default: 0.6 }
})

/* 刻度角度（0 = 正上方，正数顺时针）：-120° ~ +120° */
const TICKS = [-120, -60, 0, 60, 120]

const valid = computed(() => Number.isFinite(props.speed))
const reverse = computed(() => valid.value && props.speed < 0)
const angle = computed(() => {
  if (!valid.value || !(props.max > 0)) return 0
  const ratio = Math.max(-1, Math.min(1, props.speed / props.max))
  return ratio * 120
})
const speedText = computed(() => (valid.value ? `${props.speed.toFixed(3)} m/s` : '—'))
const valueText = computed(() =>
  valid.value ? `${props.speed >= 0 ? '+' : ''}${props.speed.toFixed(2)}` : '—'
)
const angularText = computed(() =>
  Number.isFinite(props.angular) ? `${props.angular.toFixed(2)} rad/s` : '—'
)
</script>

<template>
  <div class="wheel-gauge">
    <div class="wheel-gauge-label">
      <span>{{ label }}</span>
      <span class="wheel-gauge-speed">{{ speedText }}</span>
    </div>
    <svg
      class="wheel-dial"
      viewBox="0 0 100 100"
      role="img"
      :aria-label="`${label}轮速 ${speedText}`"
    >
      <path class="wheel-dial-arc" d="M 17.09 69 A 38 38 0 1 1 82.91 69" />
      <line
        v-for="tick in TICKS"
        :key="tick"
        class="wheel-dial-tick"
        x1="50"
        y1="12"
        x2="50"
        y2="16.5"
        :transform="`rotate(${tick} 50 50)`"
      />
      <g
        class="wheel-dial-needle"
        :class="{ 'is-reverse': reverse }"
        :style="{ transform: `rotate(${angle}deg)`, transformOrigin: '50px 50px' }"
      >
        <line x1="50" y1="52" x2="50" y2="18" />
        <circle cx="50" cy="50" r="3.4" />
      </g>
      <text class="wheel-dial-value" x="50" y="72">{{ valueText }}</text>
      <text class="wheel-dial-unit" x="50" y="83">m/s</text>
    </svg>
    <span class="wheel-gauge-sub">角速度 {{ angularText }}</span>
  </div>
</template>

<style scoped>
.wheel-gauge {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 0;
}

.wheel-gauge-label {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  width: 100%;
  gap: 8px;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
}

.wheel-gauge-speed {
  color: var(--ds-color-text);
  font-family: var(--ds-font-mono);
  font-size: var(--ds-font-sm);
  font-variant-numeric: tabular-nums;
}

/* 圆形指针表盘：240° 弧 + 对称指针（左负右正） */
.wheel-dial {
  width: 100%;
  max-width: 132px;
  height: auto;
  overflow: visible;
}

.wheel-dial-arc {
  fill: none;
  stroke: rgba(128, 134, 146, 0.25);
  stroke-width: 7;
  stroke-linecap: round;
}

.wheel-dial-tick {
  stroke: var(--ds-color-muted);
  stroke-width: 2;
  stroke-linecap: round;
  opacity: 0.6;
}

.wheel-dial-needle {
  transition: transform 120ms linear;
}

.wheel-dial-needle line {
  stroke: var(--ds-color-success);
  stroke-width: 3;
  stroke-linecap: round;
}

.wheel-dial-needle circle {
  fill: var(--ds-color-success);
}

.wheel-dial-needle.is-reverse line {
  stroke: var(--ds-color-warning);
}

.wheel-dial-needle.is-reverse circle {
  fill: var(--ds-color-warning);
}

.wheel-dial-value {
  fill: var(--ds-color-text);
  font-family: var(--ds-font-mono);
  font-size: 15px;
  text-anchor: middle;
}

.wheel-dial-unit {
  fill: var(--ds-color-muted);
  font-size: 8px;
  text-anchor: middle;
}

.wheel-gauge-sub {
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  font-variant-numeric: tabular-nums;
}
</style>
