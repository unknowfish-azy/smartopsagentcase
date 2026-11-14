<template>
  <svg
    class="fat-blob"
    :class="{ 'fat-blob--breathe': breathe }"
    :viewBox="'0 0 200 210'"
    :style="[blobStyle, { width: sizePx, height: 'auto' }]"
    :data-tone="tone"
    :role="label ? 'img' : 'presentation'"
    :aria-label="label || undefined"
    :aria-hidden="label ? undefined : 'true'"
  >
    <defs>
      <linearGradient :id="`${uid}-base`" x1="18%" y1="2%" x2="82%" y2="100%">
        <stop class="b-stop-hi" offset="0%" />
        <stop class="b-stop-mid" offset="54%" />
        <stop class="b-stop-lo" offset="100%" />
      </linearGradient>
      <radialGradient :id="`${uid}-shade`" cx="72%" cy="80%" r="62%">
        <stop offset="0%" stop-color="#05070a" stop-opacity=".34" />
        <stop offset="100%" stop-color="#05070a" stop-opacity="0" />
      </radialGradient>
      <radialGradient :id="`${uid}-glow`" cx="30%" cy="24%" r="46%">
        <stop class="b-stop-glow" offset="0%" />
        <stop class="b-stop-glow" offset="100%" stop-opacity="0" />
      </radialGradient>
      <radialGradient :id="`${uid}-drop`" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="#05070a" stop-opacity=".42" />
        <stop offset="100%" stop-color="#05070a" stop-opacity="0" />
      </radialGradient>
      <linearGradient :id="`${uid}-rim`" x1="10%" y1="0%" x2="90%" y2="100%">
        <stop class="b-stop-rim" offset="0%" />
        <stop class="b-stop-rim" offset="46%" stop-opacity=".12" />
        <stop class="b-stop-rim" offset="100%" stop-opacity="0" />
      </linearGradient>
    </defs>

    <ellipse cx="100" cy="197" rx="58" ry="10" :fill="`url(#${uid}-drop)`" />
    <path :d="path" :fill="`url(#${uid}-base)`" />
    <path :d="path" :fill="`url(#${uid}-shade)`" />
    <path :d="path" :fill="`url(#${uid}-glow)`" />
    <ellipse
      cx="71"
      cy="57"
      rx="35"
      ry="24"
      transform="rotate(-24 71 57)"
      :fill="`url(#${uid}-glow)`"
      opacity=".55"
    />
    <path :d="path" fill="none" :stroke="`url(#${uid}-rim)`" stroke-width="1.4" />
  </svg>
</template>

<script setup>
import { computed } from 'vue'

let counter = 0

const props = defineProps({
  seed: { type: Number, default: 1 },
  tone: { type: String, default: 'clay' },
  size: { type: [Number, String], default: 96 },
  label: { type: String, default: '' },
  breathe: { type: Boolean, default: true },
  /** 体积缩放，来自 field.volume（0.85 – 1.15）。 */
  volume: { type: Number, default: 1 },
  /** 呼吸周期（秒），来自 field.pulse（2.4 – 6.0）。默认 4.0。 */
  pulse: { type: Number, default: 4 }
})

const uid = `blob${(counter += 1).toString(36)}${Math.abs(Math.round(props.seed * 13)).toString(36)}`
const sizePx = computed(() => (typeof props.size === 'number' ? `${props.size}px` : props.size))

/** 体积缩放 + 呼吸周期通过 CSS 变量传入（DESIGN §4：每个形变指回一个参数）。 */
const blobStyle = computed(() => ({
  '--blob-volume': String(props.volume ?? 1),
  '--breathe-duration': `${Math.max(0.1, props.pulse ?? 4).toFixed(2)}s`
}))

/**
 * 肥波轮廓：极坐标半径按低阶谐波起伏（k=2..5），再转成闭合三次贝塞尔。
 * 同一个 seed 永远得到同一团块，便于视觉回归与截图对比。
 */
function rng(seed) {
  let state = Math.floor(Math.abs(seed) * 9973) % 2147483647
  if (state <= 0) state = 123456789
  return () => {
    state = (state * 48271) % 2147483647
    return state / 2147483647
  }
}

function blobPath(seed) {
  const random = rng(seed)
  const lobes = 3 + Math.round(random() * 2)
  const phases = Array.from({ length: lobes + 1 }, () => random() * Math.PI * 2)
  const amps = Array.from({ length: lobes + 1 }, (_, k) => (k < 2 ? 0 : 0.05 + random() * 0.055))
  const cx = 100
  const cy = 96
  const radius = 80
  const steps = 34
  const points = []

  for (let i = 0; i < steps; i += 1) {
    const theta = (i / steps) * Math.PI * 2
    let r = 1
    for (let k = 2; k <= lobes; k += 1) {
      r += (amps[k] * Math.sin(k * theta + phases[k])) / Math.sqrt(k - 1)
    }
    const x = cx + Math.cos(theta) * radius * r
    let y = cy + Math.sin(theta) * radius * r * 1.06
    // 底部略微压平，让它像坐在纸面上，而不是悬空
    if (y > cy) y = cy + (y - cy) * (1 - 0.1 * ((y - cy) / (radius * 1.06)))
    points.push([x, y])
  }

  const at = index => points[(index + steps) % steps]
  const f = value => Number(value.toFixed(2))
  let path = `M${f(points[0][0])} ${f(points[0][1])}`
  for (let i = 0; i < steps; i += 1) {
    const [p0x, p0y] = at(i - 1)
    const [p1x, p1y] = at(i)
    const [p2x, p2y] = at(i + 1)
    const [p3x, p3y] = at(i + 2)
    const c1x = p1x + (p2x - p0x) / 6
    const c1y = p1y + (p2y - p0y) / 6
    const c2x = p2x - (p3x - p1x) / 6
    const c2y = p2y - (p3y - p1y) / 6
    path += ` C${f(c1x)} ${f(c1y)} ${f(c2x)} ${f(c2y)} ${f(p2x)} ${f(p2y)}`
  }
  return `${path} Z`
}

/** seed 变化时重新生成轮廓；同一 seed 永远得到同一团块。 */
const path = computed(() => blobPath(props.seed))
</script>

<style scoped>
.fat-blob {
  --b-hi: #f8d6b8;
  --b-mid: #da7452;
  --b-lo: #8e3a24;
  --b-glow: #fff3e2;
  --b-rim: #ffe9d2;
  display: block;
  overflow: visible;
  transform-origin: 50% 92%;
  transform: scale(var(--blob-volume, 1));
}

.fat-blob[data-tone='apricot'] { --b-hi: #fce0c4; --b-mid: #f0a06e; --b-lo: #96502f; }
.fat-blob[data-tone='butter'] { --b-hi: #f9edc4; --b-mid: #e7c461; --b-lo: #85671f; }
.fat-blob[data-tone='sage'] { --b-hi: #e0ebd8; --b-mid: #a2b99a; --b-lo: #4f6549; }
.fat-blob[data-tone='plum'] { --b-hi: #e4d6e6; --b-mid: #a383a6; --b-lo: #573f5c; }
.fat-blob[data-tone='gaze'] { --b-hi: #d9f4fd; --b-mid: #8fdcf7; --b-lo: #2c6a83; }

.b-stop-hi { stop-color: var(--b-hi); }
.b-stop-mid { stop-color: var(--b-mid); }
.b-stop-lo { stop-color: var(--b-lo); }
.b-stop-glow { stop-color: var(--b-glow); stop-opacity: .42; }
.b-stop-rim { stop-color: var(--b-rim); stop-opacity: .5; }

.fat-blob--breathe {
  animation: fat-breathe var(--breathe-duration, 7.4s) var(--fab-ease-io, cubic-bezier(.4, 0, .2, 1)) infinite;
}

@keyframes fat-breathe {
  0%, 100% { transform: scale(var(--blob-volume, 1)); }
  38% { transform: scale(calc(var(--blob-volume, 1) * 1.016), calc(var(--blob-volume, 1) * 0.982)); }
  62% { transform: scale(calc(var(--blob-volume, 1) * 0.994), calc(var(--blob-volume, 1) * 1.008)); }
}

@media (prefers-reduced-motion: reduce) {
  .fat-blob--breathe { animation: none; }
}
</style>
