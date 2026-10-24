<template>
  <svg ref="host" class="spider" :class="[`spider--${state}`, { 'spider--pet': pet }]" :style="{ width: `${size}px`, height: `${size}px` }" viewBox="0 0 100 100" role="img" aria-label="Kubernetes 集群拓扑">
    <g class="legs"><path v-for="leg in legs" :key="leg.id" :d="leg.path" /><path v-for="leg in branches" :key="leg" :d="leg" class="branch" /></g>
    <g class="nodes"><circle v-for="node in nodes" :key="node.id" :cx="node.x" :cy="node.y" r="3.1"><title>{{ node.label }}</title></circle></g>
    <polygon class="core" points="50,40 58,45 58,55 50,60 42,55 42,45" /><circle class="core-ring" cx="50" cy="50" r="14" />
    <g v-if="!reducedMotion" class="flows"><circle v-for="leg in legs" :key="`flow-${leg.id}`" r="1.45"><animateMotion dur="4.8s" repeatCount="indefinite" :path="leg.path" /></circle></g>
  </svg>
</template>
<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getEcosystemTide } from './organismMotion'
import { getStellarFlowField } from './stellarOcean'
const props = defineProps({ state: { type: String, default: 'observing' }, size: { type: Number, default: 36 }, pet: { type: Boolean, default: false } })
const host = ref(null)
const reducedMotion = ref(false)
let query
let frame = 0
let visible = true
const legs = [{ id:'node',path:'M50 50 L32 23 L18 16'},{id:'pod',path:'M50 50 L22 35 L10 34'},{id:'service',path:'M50 50 L23 48 L10 50'},{id:'ingress',path:'M50 50 L24 64 L12 70'},{id:'deploy',path:'M50 50 L35 76 L22 87'},{id:'network',path:'M50 50 L68 23 L82 16'},{id:'storage',path:'M50 50 L78 36 L90 34'},{id:'metrics',path:'M50 50 L77 64 L88 70'}]
const branches=['M32 23 L26 11','M22 35 L14 25','M23 64 L16 78','M35 76 L43 90','M68 23 L74 11','M78 36 L86 25','M77 64 L84 78','M65 76 L57 90']
const nodes=[{id:'n1',x:18,y:16,label:'NODE / worker-01 / Ready'},{id:'n2',x:10,y:34,label:'POD / nginx-prod / Running'},{id:'n3',x:10,y:50,label:'SERVICE / gateway / Healthy'},{id:'n4',x:12,y:70,label:'INGRESS / public / Ready'},{id:'n5',x:22,y:87,label:'DEPLOYMENT / api / Available'},{id:'n6',x:82,y:16,label:'NODE / worker-03 / Ready'},{id:'n7',x:90,y:34,label:'POD / agent / Running'},{id:'n8',x:88,y:70,label:'METRIC / cluster / Healthy'}]
function render(time = 0) {
  if (reducedMotion.value || !visible) return
  const field = getStellarFlowField(0.34, -0.18, time, 0.43)
  const tide = getEcosystemTide(time, props.state === 'scanning' ? 'observing' : props.state)
  const scale = Math.max(0.35, Math.min(4, props.size / 70))
  host.value?.style.setProperty('transform', `translate(${(field.x * scale).toFixed(2)}px, ${(field.y * scale).toFixed(2)}px)`)
  host.value?.style.setProperty('--ocean-pulse', `${(0.45 + tide.release * 0.45).toFixed(2)}`)
  frame = requestAnimationFrame(render)
}
function syncMotion() { reducedMotion.value = query.matches; cancelAnimationFrame(frame); if (!reducedMotion.value && visible) frame = requestAnimationFrame(render) }
function visibilityChange() { visible = !document.hidden; syncMotion() }
onMounted(() => { query = window.matchMedia('(prefers-reduced-motion: reduce)'); syncMotion(); query.addEventListener('change', syncMotion); document.addEventListener('visibilitychange', visibilityChange) })
onBeforeUnmount(() => { cancelAnimationFrame(frame); query?.removeEventListener('change', syncMotion); document.removeEventListener('visibilitychange', visibilityChange) })
</script>
<style scoped>
.spider{overflow:visible;color:#7ad7f5;will-change:transform}.legs path{fill:none;stroke:currentColor;stroke-width:1.1;stroke-opacity:.34;stroke-linecap:round}.legs .branch{stroke-opacity:.15;stroke-width:.8}.nodes circle{fill:#7ad7f5;stroke:#05090d;stroke-width:1.2}.core{fill:#2496ed;stroke:#b8eeff;stroke-width:.8}.core-ring{fill:none;stroke:#7ad7f5;stroke-width:.6;stroke-opacity:var(--ocean-pulse,.4);animation:heartbeat 3.2s ease-in-out infinite}.flows circle{fill:#e8f7ff;opacity:var(--ocean-pulse,.72);filter:drop-shadow(0 0 2px #7ad7f5)}.spider--warning .legs path:nth-child(3),.spider--error .legs path:nth-child(3){stroke:#d9b96d;stroke-opacity:.8}.spider--error .nodes circle:nth-child(3){opacity:.18}.spider--pet .legs path:not(.branch){transform-box:fill-box;transform-origin:center;animation:pet-leg 6.8s ease-in-out infinite}.spider--pet .legs path:nth-child(2){animation-delay:-1.4s;animation-duration:7.7s}.spider--pet .legs path:nth-child(3){animation-delay:-3.1s;animation-duration:6.2s}.spider--pet .legs path:nth-child(4){animation-delay:-.7s;animation-duration:8.1s}.spider--pet .legs path:nth-child(5){animation-delay:-4.3s;animation-duration:7.2s}.spider--pet .legs path:nth-child(6){animation-delay:-2.2s;animation-duration:6.5s}.spider--pet .legs path:nth-child(7){animation-delay:-5.5s;animation-duration:7.9s}.spider--pet .legs path:nth-child(8){animation-delay:-1.9s;animation-duration:6.9s}.spider--pet.spider--observing .legs path:not(.branch){animation-name:pet-scan}.spider--pet.spider--thinking .legs{transform:scale(.91);transform-origin:50px 50px}.spider--pet.spider--executing .flows circle{animation:pet-flow .7s linear infinite}.spider--pet.spider--sleeping{opacity:.48}.spider--pet.spider--sleeping .legs{transform:scale(.78);transform-origin:50px 50px}.spider--pet.spider--sleeping .flows{display:none}@keyframes heartbeat{0%,100%{transform:scale(.94);opacity:.35}50%{transform:scale(1.08);opacity:.9}}@keyframes pet-leg{0%,100%{transform:rotate(0deg) scale(1)}45%{transform:rotate(.8deg) scale(1.025)}70%{transform:rotate(-.45deg) scale(.985)}}@keyframes pet-scan{0%,100%{transform:scale(1)}48%{transform:scale(1.08)}72%{transform:scale(1.025)}}@keyframes pet-flow{to{opacity:.7;filter:drop-shadow(0 0 4px #b8eeff)}}@media(prefers-reduced-motion:reduce){.core-ring,.spider--pet .legs path:not(.branch),.spider--pet .flows circle{animation:none}}
</style>
