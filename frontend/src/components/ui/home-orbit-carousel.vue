<template>
  <section class="orbit-carousel" aria-label="探索智维功能" aria-roledescription="轮播" @mouseenter="hovered = true" @mouseleave="hovered = false" @focusin="focused = true" @focusout="onFocusOut" @keydown="onKeydown">
    <div class="orbit-stage">
      <div class="orbit-ring" :style="{ transform: `translateZ(calc(-1 * var(--orbit-depth))) rotateY(${-step * angle}deg)` }">
        <article v-for="(slide, index) in slides" :key="slide.title" class="orbit-card" :class="[`orbit-card-${index}`, { 'orbit-card-visible': isFrontArc(index) }]" :style="{ transform: `rotateY(${index * angle}deg) translateZ(var(--orbit-depth))` }" :inert="active !== index" :aria-hidden="active !== index" aria-roledescription="slide" :aria-label="`${index + 1} / ${slides.length}: ${slide.label}`">
          <div class="card-grid" aria-hidden="true"></div>
          <div class="card-heading"><span>{{ slide.eyebrow }}</span><span>0{{ index + 1 }} / 0{{ slides.length }}</span></div>
          <div class="card-body"><p class="card-kicker">{{ slide.kicker }}</p><h2>{{ slide.title }}</h2><p class="card-description">{{ slide.description }}</p></div>
          <div class="knowledge-words"><span v-for="word in slide.words" :key="word">{{ word }}</span></div>
          <div class="card-links"><RouterLink v-for="link in slide.links" :key="link.to" :to="link.to">{{ link.name }} <span aria-hidden="true">↗</span></RouterLink></div>
        </article>
      </div>
    </div>
    <div class="orbit-controls">
      <button type="button" aria-label="上一张" @click="move(-1)">←</button>
      <div class="orbit-tabs"><button v-for="(slide, index) in slides" :key="slide.title" type="button" :aria-label="`显示${slide.label}`" :aria-pressed="active === index" @click="select(index)"><span>0{{ index + 1 }}</span><span class="tab-title">{{ slide.label }}</span></button></div>
      <button type="button" aria-label="下一张" @click="move(1)">→</button>
      <button type="button" class="play-control" :aria-label="paused ? '播放轮播' : '暂停轮播'" :disabled="reducedMotion" @click="paused = !paused">{{ reducedMotion ? '静态' : paused ? '播放' : '暂停' }}</button>
    </div>
    <p class="orbit-hint">{{ reducedMotion ? '已遵循减少动态效果设置 · 手动切换' : '自动巡航 · 悬停或键盘聚焦时暂停' }}<span class="sr-only" aria-live="polite">{{ paused || focused ? `当前：${slides[active].title}` : '' }}</span></p>
  </section>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { visualMode } from '../../visual/visualMode.js'

const props = defineProps({ slides: { type: Array, required: true } })
const angle = computed(() => 360 / props.slides.length)
const step = ref(0)
const active = computed(() => ((step.value % props.slides.length) + props.slides.length) % props.slides.length)
function isFrontArc(index) {
  const distance = Math.abs(index - active.value)
  return Math.min(distance, props.slides.length - distance) <= 1
}
const paused = ref(false)
const hovered = ref(false)
const focused = ref(false)
const systemReducedMotion = ref(false)
const reducedMotion = computed(() => systemReducedMotion.value || visualMode.value === 'reduced-motion')
let timer, media
const updateMotion = () => { systemReducedMotion.value = media.matches }
function move(direction) { paused.value = true; step.value += direction }
function select(index) {
  paused.value = true
  const count = props.slides.length
  let delta = index - active.value
  if (delta > count / 2) delta -= count
  if (delta < -count / 2) delta += count
  step.value += delta
}
function onFocusOut(event) { focused.value = event.currentTarget.contains(event.relatedTarget) }
function onKeydown(event) {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  // Keep focus on a persistent control before making the current face inert.
  event.currentTarget.querySelector(`[aria-label="${event.key === 'ArrowLeft' ? '上一张' : '下一张'}"]`).focus()
  move(event.key === 'ArrowLeft' ? -1 : 1)
}
onMounted(() => {
  media = window.matchMedia('(prefers-reduced-motion: reduce)')
  updateMotion()
  media.addEventListener('change', updateMotion)
  timer = window.setInterval(() => { if (!paused.value && !hovered.value && !focused.value && !reducedMotion.value && !document.hidden) step.value++ }, 4500)
})
onBeforeUnmount(() => { clearInterval(timer); media?.removeEventListener('change', updateMotion) })
</script>

<style scoped>
.orbit-carousel { --orbit-depth: 730px; width: 100%; }
.orbit-stage { height: clamp(500px, 67dvh, 740px); display: grid; place-items: center; perspective: 1500px; overflow: clip; }
.orbit-ring { position: relative; width: min(660px, 70%); height: clamp(410px, 51dvh, 540px); transform-style: preserve-3d; transition: transform 1.2s cubic-bezier(.22,.7,.18,1); }
.orbit-card { position: absolute; inset: 0; display: flex; flex-direction: column; padding: 28px 32px; border: 1px solid color-mix(in srgb, var(--smart-primary) 45%, var(--smart-border)); border-radius: 18px; background: linear-gradient(135deg, color-mix(in srgb, var(--smart-primary) 8%, transparent), color-mix(in srgb, var(--smart-surface) 28%, transparent) 70%); box-shadow: 0 18px 40px #0001, inset 0 1px 0 #ffffff20; backface-visibility: hidden; transform-style: preserve-3d; }
.orbit-card-1 { background: linear-gradient(135deg, #34b99b0d, color-mix(in srgb, var(--smart-surface) 28%, transparent) 70%); }
.orbit-card-2 { background: linear-gradient(135deg, #8c80db0d, color-mix(in srgb, var(--smart-surface) 28%, transparent) 70%); }
.orbit-card { visibility: hidden; border-color: color-mix(in srgb, var(--smart-primary-strong) 35%, transparent); box-shadow: inset 0 1px 0 #ffffff55, inset 1px 0 0 #ffffff18, inset 0 -1px 0 #ffffff12, 0 16px 40px #0002; }
.orbit-card-visible { visibility: visible; }
.orbit-card::before { content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none; background: linear-gradient(118deg, #ffffff18 0%, #ffffff05 24%, transparent 42%, #ffffff08 70%, transparent 71%); }
.card-body, .card-links, .knowledge-words, .card-heading { backface-visibility: hidden; }
.card-body { border-radius: 12px; background: radial-gradient(ellipse at 32% 48%, color-mix(in srgb, var(--smart-surface) 36%, transparent), transparent 75%); }
.card-description, .card-links, .card-kicker, .knowledge-words { text-shadow: 0 1px 3px var(--smart-surface), 0 0 8px var(--smart-surface); }
.card-grid { position: absolute; inset: 0; border-radius: inherit; background-image: linear-gradient(var(--smart-border) 1px, transparent 1px), linear-gradient(90deg,var(--smart-border) 1px,transparent 1px); background-size: 36px 36px; opacity: .24; pointer-events: none; }
.card-heading { display: flex; justify-content: space-between; gap: 10px; color: var(--smart-muted); font: 10px var(--font-mono); letter-spacing: .12em; transform: translateZ(16px); }
.card-body { transform: translateZ(35px); }
.card-kicker { margin: 26px 0 8px; font-size: 12px; color: var(--smart-primary-strong); }
.card-body h2 { white-space: pre-line; margin: 0; font-size: clamp(34px, 4.4vw, 62px); line-height: 1.2; letter-spacing: .04em; color: var(--smart-text); text-shadow: 1px 1px 0 var(--smart-border), 2px 2px 0 var(--smart-border), 3px 3px 0 var(--smart-border), 0 9px 18px #0003; }
.card-description { max-width: 420px; margin: 12px 0 0; color: var(--smart-muted); font-size: 13px; line-height: 1.8; }
.knowledge-words { display: flex; flex-wrap: wrap; gap: 8px 16px; margin: 20px 0; transform: translateZ(48px); font: 12px var(--font-mono); color: var(--smart-primary-strong); text-shadow: 0 4px 8px #0003; }
.card-links { display: flex; flex-wrap: wrap; gap: 9px 18px; margin-top: auto; padding-top: 15px; border-top: 1px solid var(--smart-border); transform: translateZ(20px); }
.card-links a { color: var(--smart-text); font-size: 12px; padding: 3px 0; }
.card-links a span { margin-left: 8px; color: var(--smart-primary-strong); }
.orbit-controls { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 10px; }
.orbit-controls button { min-width: 40px; min-height: 40px; border: 1px solid var(--smart-border); border-radius: 8px; background: var(--smart-surface); color: var(--smart-muted); cursor: pointer; }
.orbit-controls button:hover, .orbit-controls button[aria-pressed=true] { color: var(--smart-primary-strong); border-color: var(--smart-primary); }
.orbit-controls button:focus-visible, .card-links a:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 4px; }
.orbit-tabs { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; }
.orbit-tabs button { display: flex; align-items: center; gap: 8px; padding: 0 12px; font-size: 12px; }
.orbit-tabs button span:first-child { font: 10px var(--font-mono); }
.play-control { font-size: 11px; padding: 0 10px; }
.orbit-controls button:disabled { cursor: default; opacity: .5; }
.orbit-hint { text-align: center; font-size: 11px; color: var(--smart-muted); margin: 16px 0 0; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
@media (max-width: 767px) {
  .orbit-carousel { --orbit-depth: 365px; }
  .orbit-stage { height: 490px; perspective: 1000px; }
  .orbit-ring { width: 86%; height: 420px; }
  .orbit-card { padding: 22px 19px; }
  .card-heading { font-size: 8px; letter-spacing: .06em; }
  .card-kicker { margin-top: 24px; font-size: 11px; }
  .card-body { transform: translateZ(15px); }
  .knowledge-words { transform: translateZ(20px); font-size: 11px; gap: 10px; }
  .card-description { font-size: 12px; }
  .card-links { gap: 8px 12px; transform: translateZ(10px); }
  .orbit-tabs { order: 4; width: 100%; margin-top: 8px; }
  .orbit-tabs button { min-height: 36px; padding: 0 8px; font-size: 11px; }
  .orbit-controls { gap: 6px; }
}
@media (prefers-reduced-motion: reduce) { .orbit-ring { transition: none; } }
:global([data-theme='light'] .orbit-card) {
  border-color: var(--smart-border);
  background: var(--smart-card);
  box-shadow: 0 16px 34px rgba(16, 53, 70, .12);
}
:global([data-theme='light'] .orbit-card::before) { background: linear-gradient(118deg, rgba(255, 255, 255, .72), rgba(255, 255, 255, 0) 46%); }
:global([data-theme='light'] .card-body) { background: #f7fafb; }
:global([data-theme='light'] .card-heading),
:global([data-theme='light'] .card-description),
:global([data-theme='light'] .card-links),
:global([data-theme='light'] .knowledge-words) { text-shadow: none; }
:global([data-theme='light'] .card-body h2) { text-shadow: none; }
:global([data-theme='light'] .card-description) { color: var(--smart-muted); }
</style>
