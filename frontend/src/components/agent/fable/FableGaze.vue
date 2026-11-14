<template>
  <svg
    class="gaze"
    viewBox="0 0 560 560"
    :style="lookStyle"
    aria-hidden="true"
    focusable="false"
  >
    <defs>
      <radialGradient id="fg-iris" cx="40%" cy="34%" r="72%">
        <stop class="stop-hi" offset="0%" />
        <stop class="stop-mid" offset="46%" />
        <stop class="stop-lo" offset="84%" />
        <stop class="stop-deep" offset="100%" />
      </radialGradient>
      <radialGradient id="fg-inner" cx="50%" cy="50%" r="50%">
        <stop offset="48%" stop-color="#05070a" stop-opacity=".5" />
        <stop offset="100%" stop-color="#05070a" stop-opacity="0" />
      </radialGradient>
      <radialGradient id="fg-halo" cx="50%" cy="50%" r="50%">
        <stop class="stop-halo" offset="0%" />
        <stop class="stop-halo" offset="100%" stop-opacity="0" />
      </radialGradient>
      <radialGradient id="fg-vignette" cx="50%" cy="46%" r="52%">
        <stop offset="62%" stop-color="#05070a" stop-opacity="0" />
        <stop offset="100%" stop-color="#05070a" stop-opacity=".55" />
      </radialGradient>
      <radialGradient id="fg-pupil" cx="38%" cy="32%" r="74%">
        <stop offset="0%" stop-color="#161d25" />
        <stop offset="70%" stop-color="#080c11" />
        <stop offset="100%" stop-color="#04060a" />
      </radialGradient>
      <mask id="fg-aperture-mask" maskUnits="userSpaceOnUse" x="0" y="0" width="560" height="560">
        <g class="aperture-shape">
          <ellipse cx="280" cy="280" rx="212" ry="166" fill="#fff" />
        </g>
      </mask>
    </defs>

    <circle class="gaze-halo" cx="280" cy="280" r="182" fill="url(#fg-halo)" />

    <g class="gaze-rings">
      <circle cx="280" cy="280" r="256" class="ring ring--dotted" />
      <circle cx="280" cy="280" r="238" class="ring ring--thin" />
      <g class="gaze-arcs">
        <circle cx="280" cy="280" r="212" class="ring ring--segments" />
      </g>
    </g>

    <g class="gaze-ticks">
      <line
        v-for="tick in ticks"
        :key="`t${tick.angle}`"
        :x1="tick.x1"
        :y1="tick.y1"
        :x2="tick.x2"
        :y2="tick.y2"
        :class="{ 'tick--major': tick.major }"
      />
    </g>

    <g class="gaze-rays">
      <line v-for="ray in rays" :key="`r${ray.angle}`" :x1="ray.x1" :y1="ray.y1" :x2="ray.x2" :y2="ray.y2" />
    </g>

    <g class="gaze-spiral">
      <path :d="spiral" />
    </g>

    <g class="gaze-aperture" mask="url(#fg-aperture-mask)">
      <ellipse cx="280" cy="280" rx="212" ry="166" class="socket" />
      <g class="gaze-iris">
        <circle cx="280" cy="280" r="142" fill="url(#fg-iris)" />
        <g class="iris-streaks">
          <line
            v-for="streak in streaks"
            :key="`s${streak.angle}`"
            :x1="streak.x1"
            :y1="streak.y1"
            :x2="streak.x2"
            :y2="streak.y2"
            :style="{ opacity: streak.opacity }"
          />
        </g>
        <circle cx="280" cy="280" r="118" class="iris-ring iris-ring--dot" />
        <circle cx="280" cy="280" r="96" class="iris-ring" />
        <circle cx="280" cy="280" r="76" fill="url(#fg-inner)" />
        <circle cx="280" cy="280" r="140" class="iris-limbal" />
        <circle cx="280" cy="280" r="142" class="iris-rim" />
      </g>

      <g class="gaze-pupil">
        <circle cx="280" cy="280" r="54" fill="url(#fg-pupil)" />
        <circle cx="280" cy="280" r="54" class="pupil-edge" />
        <circle cx="263" cy="262" r="10" class="glint" />
        <circle cx="297" cy="298" r="4" class="glint glint--sm" />
      </g>

      <ellipse cx="280" cy="280" rx="212" ry="166" fill="url(#fg-vignette)" />
    </g>

    <g class="aperture-shape">
      <ellipse cx="280" cy="280" rx="212" ry="166" class="aperture-edge" />
      <line x1="40" y1="280" x2="66" y2="280" class="aperture-cap" />
      <line x1="494" y1="280" x2="520" y2="280" class="aperture-cap" />
    </g>

    <g class="gaze-orbit">
      <circle cx="280" cy="66" r="5" class="orbit-dot" />
      <circle cx="280" cy="494" r="3" class="orbit-dot orbit-dot--dim" />
    </g>

    <g class="gaze-cross">
      <line x1="280" y1="132" x2="280" y2="146" />
      <line x1="280" y1="414" x2="280" y2="428" />
      <line x1="132" y1="280" x2="146" y2="280" />
      <line x1="414" y1="280" x2="428" y2="280" />
    </g>
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** 归一化注视偏移，-1..1，由舞台指针位置换算。 */
  lookX: { type: Number, default: 0 },
  lookY: { type: Number, default: 0 }
})

const rad = deg => (deg * Math.PI) / 180
const cx = 280
const cy = 280
const round = value => Number(value.toFixed(2))

const ticks = Array.from({ length: 36 }, (_, index) => {
  const angle = index * 10
  const major = angle % 90 === 0
  const outer = major ? 198 : 188
  return {
    angle,
    major,
    x1: round(cx + Math.cos(rad(angle)) * 172),
    y1: round(cy + Math.sin(rad(angle)) * 172),
    x2: round(cx + Math.cos(rad(angle)) * outer),
    y2: round(cy + Math.sin(rad(angle)) * outer)
  }
})

const rays = [16, 72, 128, 196, 244, 308].map(angle => ({
  angle,
  x1: round(cx + Math.cos(rad(angle)) * 134),
  y1: round(cy + Math.sin(rad(angle)) * 134),
  x2: round(cx + Math.cos(rad(angle)) * 250),
  y2: round(cy + Math.sin(rad(angle)) * 250)
}))

/** 虹膜放射纹理：固定种子，保证每次渲染一致。 */
const streaks = (() => {
  let seed = 90210
  const random = () => {
    seed = (seed * 48271) % 2147483647
    return seed / 2147483647
  }
  return Array.from({ length: 30 }, (_, index) => {
    const angle = (index / 30) * 360 + random() * 6
    const inner = 72 + random() * 16
    const outer = 118 + random() * 22
    return {
      angle,
      x1: round(cx + Math.cos(rad(angle)) * inner),
      y1: round(cy + Math.sin(rad(angle)) * inner),
      x2: round(cx + Math.cos(rad(angle)) * outer),
      y2: round(cy + Math.sin(rad(angle)) * outer),
      opacity: Number((0.1 + random() * 0.26).toFixed(2))
    }
  })
})()

const spiral = (() => {
  let path = ''
  const turns = 1.7
  const steps = 78
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps
    const angle = t * Math.PI * 2 * turns
    const r = 138 + t * 62
    path += `${i === 0 ? 'M' : 'L'}${round(cx + Math.cos(angle) * r)} ${round(cy + Math.sin(angle) * r)}`
  }
  return path
})()

const lookStyle = computed(() => ({
  '--look-x': `${(props.lookX * 10).toFixed(2)}px`,
  '--look-y': `${(props.lookY * 8).toFixed(2)}px`,
  '--look-x-soft': `${(props.lookX * 4).toFixed(2)}px`,
  '--look-y-soft': `${(props.lookY * 3).toFixed(2)}px`
}))
</script>

<style scoped>
.gaze {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}

.gaze-halo {
  opacity: .34;
  transition: opacity 900ms var(--fab-ease);
}

.stop-hi { stop-color: var(--fab-apricot); }
.stop-mid { stop-color: var(--fab-clay); }
.stop-lo { stop-color: var(--fab-clay-deep); }
.stop-deep { stop-color: #241410; }
.stop-halo { stop-color: var(--fab-clay); stop-opacity: .26; }

.ring {
  fill: none;
  stroke: var(--fab-paper);
  vector-effect: non-scaling-stroke;
}

.ring--dotted {
  stroke-opacity: .34;
  stroke-width: 1;
  stroke-dasharray: 1 14;
}

.ring--thin {
  stroke-opacity: .14;
  stroke-width: 1;
}

.ring--segments {
  stroke-opacity: .28;
  stroke-width: 1.2;
  stroke-dasharray: 52 38;
}

.gaze-arcs {
  transform-origin: 280px 280px;
  transform: rotate(var(--gaze-rot-outer, 0deg));
  transition: transform 1100ms var(--fab-ease);
}

.gaze-ticks {
  transform-origin: 280px 280px;
  transform: rotate(var(--gaze-rot-ticks, 0deg));
  transition: transform 1000ms var(--fab-ease);
}

.gaze-ticks line {
  stroke: var(--fab-paper);
  stroke-opacity: .2;
  stroke-width: 1;
}

.gaze-ticks .tick--major {
  stroke-opacity: .42;
}

.gaze-rays line {
  stroke: var(--fab-paper);
  stroke-opacity: .08;
  stroke-width: 1;
  transition: stroke-opacity 700ms var(--fab-ease-io);
}

.fable[data-state='analyze'] .gaze-rays line { stroke-opacity: .28; }
.fable[data-state='execute'] .gaze-rays line { stroke-opacity: .2; }
.fable[data-state='decide'] .gaze-rays line { stroke-opacity: .14; }

.gaze-spiral path {
  fill: none;
  stroke: var(--fab-plum);
  stroke-opacity: 0;
  stroke-width: 1.2;
  stroke-dasharray: 3 5;
  transform-origin: 280px 280px;
  transform: rotate(0deg);
  transition: stroke-opacity 700ms var(--fab-ease-io), transform 1600ms var(--fab-ease);
}

.fable[data-state='reflect'] .gaze-spiral path {
  stroke-opacity: .8;
  transform: rotate(-42deg);
}

/* 孔径：同一组 shape 同时用于遮罩与描边，保证两者一起开合 */
.aperture-shape {
  transform-origin: 280px 280px;
  transform: scaleY(var(--aperture, 1));
  transition: transform 900ms var(--fab-ease);
}

.socket {
  fill: #070b10;
}

.aperture-edge {
  fill: none;
  stroke: var(--fab-paper);
  stroke-opacity: .55;
  stroke-width: 1.2;
  vector-effect: non-scaling-stroke;
}

.aperture-cap {
  stroke: var(--fab-paper);
  stroke-opacity: .8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.gaze-iris {
  transform: translate(calc(var(--look-x-soft, 0px) + var(--gaze-iris-x, 0px)), calc(var(--look-y-soft, 0px) + var(--gaze-iris-y, 0px)));
  transition: transform 620ms var(--fab-ease);
}

.iris-streaks line {
  stroke: #f8dcc0;
  stroke-width: 1.1;
}

.iris-ring {
  fill: none;
  stroke: var(--fab-paper);
  stroke-opacity: .2;
  stroke-width: 1;
}

.iris-ring--dot {
  stroke-dasharray: 1 6;
}

.iris-limbal {
  fill: none;
  stroke: #2a1710;
  stroke-opacity: .5;
  stroke-width: 10;
}

.iris-rim {
  fill: none;
  stroke: var(--fab-apricot);
  stroke-opacity: .38;
  stroke-width: 1.4;
}

.gaze-pupil {
  transform: translate(var(--look-x, 0px), var(--look-y, 0px)) scale(var(--gaze-pupil, 1));
  transform-origin: 280px 280px;
  transition: transform 700ms var(--fab-ease);
}

.pupil-edge {
  fill: none;
  stroke: var(--fab-apricot);
  stroke-opacity: .3;
  stroke-width: 1.4;
}

.glint {
  fill: #fbf3e4;
  opacity: .84;
}

.glint--sm {
  opacity: .4;
}

.gaze-orbit {
  transform-origin: 280px 280px;
  animation: gaze-orbit 16s linear infinite;
  animation-play-state: paused;
  opacity: 0;
  transition: opacity 500ms var(--fab-ease-io);
}

.fable[data-state='execute'] .gaze-orbit {
  opacity: 1;
  animation-play-state: running;
}

.orbit-dot {
  fill: var(--fab-gaze);
}

.orbit-dot--dim {
  fill: var(--fab-sage);
  opacity: .7;
}

@keyframes gaze-orbit {
  to { transform: rotate(360deg); }
}

.gaze-cross line {
  stroke: var(--fab-paper);
  stroke-opacity: .36;
  stroke-width: 1;
}

@media (prefers-reduced-motion: reduce) {
  .gaze * {
    animation: none !important;
    transition: none !important;
  }
}

.fable[data-reduced='true'] .gaze * {
  animation: none !important;
  transition: none !important;
}
</style>
