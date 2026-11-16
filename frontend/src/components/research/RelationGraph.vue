<template>
  <div class="relation-graph" :class="{ 'is-scanning': scanning }">
    <svg viewBox="0 0 760 320" role="img" :aria-label="ariaLabel">
      <g class="graph-edges" aria-hidden="true">
        <path
          v-for="(edge, index) in graph.edges"
          :key="edge.id"
          class="graph-edge"
          :class="[`edge--${edge.kind || 'watch'}`, { 'is-active': activeId === edge.to.id }]"
          :d="`M ${edge.from.x} ${edge.from.y} Q ${edge.controlX} ${edge.controlY} ${edge.to.x} ${edge.to.y}`"
          :style="{ '--edge-order': index }"
        />
      </g>
      <line v-if="scanning" class="graph-scan" x1="40" y1="28" x2="720" y2="292" aria-hidden="true" />
      <g
        v-for="(node, index) in graph.nodes"
        :key="node.id"
        class="graph-node"
        :class="[`node--${String(node.status || 'idle').toLowerCase()}`, { 'is-active': activeId === node.id }]"
        :transform="`translate(${node.x} ${node.y})`"
        :style="{ '--node-order': index }"
        tabindex="0"
        role="button"
        :aria-label="`${node.label}，${node.type || '节点'}`"
        @click="emit('select', node)"
        @keydown.enter.prevent="emit('select', node)"
        @keydown.space.prevent="emit('select', node)"
      >
        <circle class="node-halo" r="24" />
        <circle class="node-ring" r="12" />
        <circle class="node-core" r="4" />
        <text class="node-label" y="34" text-anchor="middle">{{ shortNodeLabel(node.label) }}</text>
        <text class="node-type" y="49" text-anchor="middle">{{ node.type }}</text>
      </g>
    </svg>
    <div v-if="!graph.nodes.length" class="graph-empty">输入问题或登记来源后，这里会生成真实关系拓扑。</div>
    <div class="graph-legend" aria-hidden="true"><span><i class="legend-ready" />已连接</span><span><i class="legend-changed" />发现变更</span><span><i class="legend-offline" />离线 / 失败</span></div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { layoutRelationGraph, shortNodeLabel } from './relationGraph.js'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  activeId: { type: [String, Number], default: '' },
  scanning: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '知识来源关系网状动态图' },
})
const emit = defineEmits(['select'])
const graph = computed(() => layoutRelationGraph(props.nodes, props.edges))
</script>

<style scoped>
.relation-graph{position:relative;min-width:0;border-top:1px solid var(--smart-border);border-bottom:1px solid var(--smart-border);background:linear-gradient(135deg,color-mix(in srgb,var(--smart-primary-strong) 3%,transparent),transparent 58%);overflow:hidden}.relation-graph svg{display:block;width:100%;height:auto;min-height:250px}.graph-edge{fill:none;stroke:color-mix(in srgb,var(--smart-primary-strong) 36%,var(--smart-border));stroke-width:1;stroke-dasharray:3 7;animation:edge-flow 7s linear infinite;animation-delay:calc(var(--edge-order)*-420ms);transition:stroke .2s,stroke-width .2s}.graph-edge.is-active{stroke:var(--smart-primary-strong);stroke-width:1.8}.edge--changed{stroke:var(--smart-warning,#d9a84e);stroke-dasharray:5 5}.edge--runtime{stroke:color-mix(in srgb,var(--smart-success,#64b99a) 54%,transparent)}.graph-node{cursor:pointer;outline:none;animation:node-arrive .35s ease both;animation-delay:calc(var(--node-order)*38ms)}.node-halo{fill:color-mix(in srgb,var(--smart-primary-strong) 6%,transparent);stroke:none;transform-origin:center;animation:node-breathe 4.8s ease-in-out infinite;animation-delay:calc(var(--node-order)*-370ms)}.node-ring{fill:var(--smart-surface);stroke:var(--smart-primary-strong);stroke-width:1.2}.node-core{fill:var(--smart-primary-strong)}.node-label{fill:var(--smart-text);font:12px var(--font-cn)}.node-type{fill:var(--smart-muted);font:8px var(--font-mono);letter-spacing:.09em}.graph-node:hover .node-ring,.graph-node:focus-visible .node-ring,.graph-node.is-active .node-ring{stroke-width:2.5;filter:drop-shadow(0 0 4px color-mix(in srgb,var(--smart-primary-strong) 42%,transparent))}.graph-node:focus-visible .node-label{fill:var(--smart-primary-strong)}.node--changed .node-ring{stroke:var(--smart-warning,#d9a84e)}.node--changed .node-core{fill:var(--smart-warning,#d9a84e)}.node--offline .node-ring{stroke:var(--smart-danger)}.node--offline .node-core{fill:var(--smart-danger)}.node--idle{opacity:.68}.graph-scan{stroke:var(--smart-primary-strong);stroke-width:1.4;stroke-dasharray:2 8;opacity:.7;animation:scan-pulse 1.4s ease-in-out infinite}.graph-empty{position:absolute;inset:0;display:grid;place-items:center;padding:30px;color:var(--smart-muted);font-size:12px;text-align:center;pointer-events:none}.graph-legend{display:flex;gap:18px;justify-content:flex-end;padding:0 14px 10px;color:var(--smart-muted);font:9px var(--font-mono)}.graph-legend span{display:flex;align-items:center;gap:6px}.graph-legend i{width:5px;height:5px;border-radius:50%;background:var(--smart-primary-strong)}.graph-legend .legend-changed{background:var(--smart-warning,#d9a84e)}.graph-legend .legend-offline{background:var(--smart-danger)}@keyframes edge-flow{to{stroke-dashoffset:-50}}@keyframes node-arrive{from{opacity:0}to{opacity:1}}@keyframes node-breathe{0%,100%{transform:scale(.9);opacity:.4}50%{transform:scale(1.14);opacity:.9}}@keyframes scan-pulse{0%,100%{opacity:.12}50%{opacity:.8}}@media(max-width:640px){.relation-graph svg{min-height:220px}.node-label{font-size:14px}.node-type{font-size:10px}.graph-legend{justify-content:center;flex-wrap:wrap}}@media(prefers-reduced-motion:reduce){.graph-edge,.node-halo,.graph-node,.graph-scan{animation:none!important}}:global([data-visual-mode='reduced-motion']) .graph-edge,:global([data-visual-mode='reduced-motion']) .node-halo,:global([data-visual-mode='reduced-motion']) .graph-node,:global([data-visual-mode='reduced-motion']) .graph-scan{animation:none!important}
</style>
