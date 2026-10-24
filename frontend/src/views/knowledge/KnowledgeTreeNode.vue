<template>
  <li class="knowledge-tree-node">
    <button type="button" :class="['knowledge-tree-node__button', { active: selectedId === node.id, leaf: node.kind === 'entry' }]" @click="selectNode">
      <span class="knowledge-tree-node__marker" aria-hidden="true">{{ node.children?.length ? (expandedNodes.has(node.id) ? '−' : '+') : '·' }}</span>
      <span class="knowledge-tree-node__label">{{ node.label }}</span>
      <small v-if="node.count">{{ node.count }}</small>
    </button>
    <ul v-if="node.children?.length && expandedNodes.has(node.id)" class="knowledge-tree-node__children">
      <KnowledgeTreeNode v-for="child in node.children" :key="child.id" :node="child" :expanded-nodes="expandedNodes" :selected-id="selectedId" @select="$emit('select', $event)" />
    </ul>
  </li>
</template>

<script setup>
defineOptions({ name: 'KnowledgeTreeNode' })

const props = defineProps({
  node: { type: Object, required: true },
  expandedNodes: { type: Object, required: true },
  selectedId: { type: String, default: null }
})
const emit = defineEmits(['select'])

function selectNode() {
  if (props.node.children?.length) {
    if (props.expandedNodes.has(props.node.id)) props.expandedNodes.delete(props.node.id)
    else props.expandedNodes.add(props.node.id)
  }
  if (props.node.kind === 'entry') emit('select', props.node)
}
</script>

<style scoped>
.knowledge-tree-node { list-style: none; }
.knowledge-tree-node__button { display: grid; grid-template-columns: 16px minmax(0, 1fr) auto; gap: 7px; align-items: center; width: 100%; min-height: 32px; padding: 6px 0; border: 0; border-top: 1px solid var(--smart-border); background: transparent; color: var(--smart-muted); text-align: left; font: 10px var(--font-mono); letter-spacing: .04em; cursor: pointer; }
.knowledge-tree-node__button:hover, .knowledge-tree-node__button.active { color: var(--smart-primary-strong); }
.knowledge-tree-node__button.active { background: color-mix(in srgb, var(--smart-primary-strong) 6%, transparent); }
.knowledge-tree-node__button.leaf { font-family: var(--font-cn); letter-spacing: 0; }
.knowledge-tree-node__marker { color: var(--smart-primary-strong); font: 13px var(--font-mono); text-align: center; }
.knowledge-tree-node__label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.knowledge-tree-node__button small { color: var(--smart-muted); font: 9px var(--font-mono); }
.knowledge-tree-node__children { margin: 0 0 0 12px; padding: 0; }
</style>
