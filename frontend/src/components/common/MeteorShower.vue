<template>
  <div class="meteor-shower" :class="{ 'is-paused': hidden }" aria-hidden="true">
    <div v-for="(meteor, index) in meteors" :key="index" class="meteor-flight" :style="{ '--x': `${meteor.x}vw`, '--y': `${meteor.y}vh`, '--delay': `${meteor.delay}s`, '--duration': `${meteor.duration}s`, '--length': `${meteor.length}px` }"><span class="meteor-streak" /></div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
const hidden = ref(false)
const meteors = [
  { x: 8, y: 5, delay: -1, duration: 9, length: 110 },
  { x: 36, y: -8, delay: -4.1, duration: 11, length: 150 },
  { x: 63, y: 2, delay: -7, duration: 13, length: 95 },
  { x: -5, y: 32, delay: -5.8, duration: 10, length: 130 },
  { x: 47, y: 20, delay: -2.7, duration: 12, length: 80 },
  { x: 20, y: 15, delay: -9, duration: 14, length: 120 },
]
function syncVisibility() { hidden.value = document.hidden }
onMounted(() => { syncVisibility(); document.addEventListener('visibilitychange', syncVisibility) })
onBeforeUnmount(() => document.removeEventListener('visibilitychange', syncVisibility))
</script>

<style scoped>
.meteor-shower { position: fixed; inset: 0; overflow: hidden; pointer-events: none; z-index: 0; }
.meteor-flight { position: absolute; left: var(--x); top: var(--y); animation: meteor-flight var(--duration) var(--delay) linear infinite; opacity: 0; }
.meteor-streak { display: block; width: var(--length); height: 1.5px; transform: rotate(38deg); transform-origin: right center; background: linear-gradient(90deg, transparent, #85d6fb80 65%, #e7faff); border-radius: 100%; filter: drop-shadow(0 0 4px #82dcff); animation: meteor-shimmer 1.3s ease-in-out infinite; }
.meteor-streak::after { content: ''; position: absolute; right: 0; top: -1px; width: 4px; height: 4px; border-radius: 50%; background: #effcff; box-shadow: 0 0 8px #91dfff; }
@keyframes meteor-flight { 0% { transform: translate(-12vw, -9vw); opacity: 0; } 4% { opacity: .65; } 28% { opacity: .6; } 34% { transform: translate(58vw, 45vw); opacity: 0; } 100% { transform: translate(58vw, 45vw); opacity: 0; } }
@keyframes meteor-shimmer { 0%, 100% { opacity: .28; } 50% { opacity: 1; } }
.is-paused .meteor-flight, .is-paused .meteor-streak { animation-play-state: paused; }
:global([data-theme='light'] .meteor-streak) { background: linear-gradient(90deg, transparent, var(--smart-effect-primary) 65%, var(--smart-effect-strong)); filter: none; }
:global([data-theme='light'] .meteor-streak::after) { background: var(--smart-effect-strong); box-shadow: none; }
@media (max-width: 767px) { .meteor-flight:nth-child(n+4) { display: none; } .meteor-streak { width: calc(var(--length) * .6); } }
@media (prefers-reduced-motion: reduce) { .meteor-shower { display: none; } .meteor-flight, .meteor-streak { animation: none; } }
</style>
