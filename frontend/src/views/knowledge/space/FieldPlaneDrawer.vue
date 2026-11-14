<!--
  FieldPlaneDrawer.vue — 知识平面详情侧拉抽屉（B1 增强版）。
  展示：照片式域色头带、标题、类型、风险色标、标签云、关联知识、分段内容、证据数。
-->
<script setup>
import { computed } from 'vue'
import { knowledgeEntries } from '../knowledgeCatalog.js'

const props = defineProps({
  entry: { type: Object, required: true },
  domain: { type: Object, default: null },
  evidenceCount: { type: Number, default: 0 },
})

const emit = defineEmits(['close', 'navigate'])

const entryType = computed(() => props.entry?.type || 'KNOWLEDGE')

/* —— 风险等级 —— */
function riskInfo (r) {
  const k = String(r || '').toUpperCase()
  if (k.includes('HIGH') || k.includes('CRITICAL')) return { label: '高危', color: '#ef4444' }
  if (k.includes('MEDIUM')) return { label: '中危', color: '#f59e0b' }
  if (k.includes('LOW') || k.includes('READ')) return { label: '低危/只读', color: '#22c55e' }
  return null
}
const risk = computed(() => riskInfo(props.entry?.risk || props.entry?.risk_level))

/* —— 标签 —— */
const tags = computed(() => (Array.isArray(props.entry?.tags) ? props.entry.tags : []))

/* —— 关联知识 —— */
const relatedEntries = computed(() => {
  const ids = Array.isArray(props.entry?.relatedIds) ? props.entry.relatedIds : []
  return ids
    .map(id => knowledgeEntries.find(e => String(e.id) === String(id)))
    .filter(Boolean)
    .slice(0, 8)
})

/* —— 域渐变头带（与卡片一致）—— */
const DOMAIN_GRADIENTS = {
  linux: 'linear-gradient(135deg,#1e3a5f 0%,#0f766e 100%)',
  'cloud-operations': 'linear-gradient(135deg,#3b1d6e 0%,#6d28d9 100%)',
  docker: 'linear-gradient(135deg,#0c4a6e 0%,#2563eb 100%)',
  mysql: 'linear-gradient(135deg,#7c2d12 0%,#ea580c 100%)',
  nginx: 'linear-gradient(135deg,#14532d 0%,#16a34a 100%)',
  ubuntu: 'linear-gradient(135deg,#7f1d1d 0%,#dc2626 100%)',
  centos: 'linear-gradient(135deg,#581c87 0%,#9333ea 100%)',
  network: 'linear-gradient(135deg,#134e4a 0%,#0d9488 100%)',
  'web-lamp': 'linear-gradient(135deg,#7f1d1d 0%,#f97316 100%)',
  'linux-services': 'linear-gradient(135deg,#0c4a6e 0%,#0891b2 100%)',
}
const headerGradient = computed(() => DOMAIN_GRADIENTS[String(props.entry?.domain || '')] || 'linear-gradient(135deg,#1e293b 0%,#475569 100%)')

/* —— 内容按段落分段 —— */
const contentParagraphs = computed(() => {
  const c = String(props.entry?.content || '')
  if (!c) return []
  return c.split(/\n{2,}/).map(s => s.trim()).filter(Boolean)
})

function navigateTo (e) {
  emit('navigate', e)
  emit('close')
}
</script>

<template>
  <div class="fpd-overlay" @click.self="emit('close')">
    <aside class="fpd-drawer" role="dialog" aria-label="知识条目详情">
      <!-- 照片式域色头带 -->
      <div class="fpd-banner" :style="{ background: headerGradient }">
        <div class="fpd-banner-inner">
          <span class="fpd-domain">{{ domain?.label || entry.domain || '—' }}</span>
          <span class="fpd-type">{{ entryType }}</span>
          <span v-if="risk" class="fpd-risk" :style="{ color: risk.color }">
            <span class="fpd-risk-dot" :style="{ background: risk.color }"></span>
            {{ risk.label }}
          </span>
        </div>
        <button type="button" class="fpd-close" aria-label="关闭" @click="emit('close')">✕</button>
      </div>

      <div class="fpd-body">
        <h2 class="fpd-title">{{ entry.title || '未命名条目' }}</h2>

        <!-- 标签云 -->
        <div v-if="tags.length" class="fpd-tags">
          <span v-for="(t, i) in tags" :key="i" class="fpd-tag">{{ t }}</span>
        </div>

        <!-- 元信息 -->
        <div class="fpd-meta">
          <span>ID：{{ entry.id }}</span>
          <span>证据：{{ evidenceCount }} 条</span>
          <span v-if="entry.version">v{{ entry.version }}</span>
        </div>

        <!-- 关联知识 -->
        <section v-if="relatedEntries.length" class="fpd-section">
          <h3>关联知识</h3>
          <ul class="fpd-related">
            <li v-for="r in relatedEntries" :key="r.id" class="fpd-related-item" @click="navigateTo(r)">
              <span class="fpd-related-title">{{ r.title }}</span>
              <span class="fpd-related-type">{{ r.type }}</span>
            </li>
          </ul>
        </section>

        <!-- 分段内容 -->
        <section class="fpd-section">
          <h3>内容</h3>
          <div v-if="contentParagraphs.length" class="fpd-content">
            <p v-for="(p, i) in contentParagraphs" :key="i">{{ p }}</p>
          </div>
          <p v-else class="fpd-empty">（无内容）</p>
        </section>
      </div>

      <footer class="fpd-foot">
        <span class="fpd-hint">按 Esc 关闭 · 点击关联知识可跳转</span>
      </footer>
    </aside>
  </div>
</template>

<style scoped>
.fpd-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(4px);
  z-index: 60;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 24px;
}
.fpd-drawer {
  width: min(560px, 92vw);
  max-height: 80vh;
  background: var(--ds-surface-raised, #14181f);
  border: 1px solid var(--ds-color-border);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  animation: fpd-pop-in .2s ease;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(0,0,0,.6), 0 0 0 1px rgba(122,215,245,.1);
}
@keyframes fpd-pop-in {
  from { transform: scale(.92); opacity: 0; }
  to   { transform: scale(1); opacity: 1; }
}

/* 照片式域色头带 */
.fpd-banner {
  position: relative;
  padding: 20px 16px 14px;
  flex-shrink: 0;
}
.fpd-banner-inner {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.fpd-domain {
  color: #fff;
  font: 600 11px var(--ds-font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.fpd-type {
  color: rgba(255,255,255,.85);
  font: 10px var(--ds-font-mono);
  padding: 2px 6px;
  border: 1px solid rgba(255,255,255,.3);
  border-radius: 3px;
}
.fpd-risk {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font: 600 10px var(--ds-font-mono);
}
.fpd-risk-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  box-shadow: 0 0 5px currentColor;
}
.fpd-close {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 28px;
  height: 28px;
  border: 1px solid rgba(255,255,255,.3);
  border-radius: 50%;
  background: rgba(0,0,0,.25);
  color: #fff;
  cursor: pointer;
  font-size: 13px;
  transition: all .15s;
}
.fpd-close:hover {
  background: rgba(0,0,0,.5);
  border-color: #fff;
}

.fpd-body {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}
.fpd-title {
  margin: 16px;
  color: var(--ds-color-text);
  font: 600 17px/1.5 var(--ds-font-cn);
}

/* 标签云 */
.fpd-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 16px 12px;
}
.fpd-tag {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 4px;
  background: rgba(122,215,245,.12);
  color: var(--ds-accent, #7ad7f5);
  font-family: var(--ds-font-mono, monospace);
}

.fpd-meta {
  display: flex;
  gap: 16px;
  padding: 0 16px 12px;
  color: var(--ds-color-muted);
  font: 11px var(--ds-font-mono);
  border-bottom: 1px solid var(--ds-color-border);
  flex-wrap: wrap;
}

.fpd-section {
  padding: 14px 16px;
  border-bottom: 1px solid var(--ds-color-border);
}
.fpd-section h3 {
  margin: 0 0 10px;
  color: var(--ds-color-muted);
  font: 500 11px var(--ds-font-mono);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

/* 关联知识 */
.fpd-related {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.fpd-related-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(255,255,255,.03);
  border: 1px solid rgba(255,255,255,.06);
  cursor: pointer;
  transition: all .15s;
}
.fpd-related-item:hover {
  background: rgba(122,215,245,.08);
  border-color: rgba(122,215,245,.3);
}
.fpd-related-title {
  font-size: 12px;
  color: var(--ds-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.fpd-related-type {
  font-size: 9px;
  color: var(--ds-color-muted);
  font-family: var(--ds-font-mono);
  margin-left: 8px;
  flex-shrink: 0;
}

/* 内容 */
.fpd-content p {
  margin: 0 0 12px;
  color: var(--ds-color-text);
  font: 13px/1.7 var(--ds-font-cn);
  word-break: break-word;
}
.fpd-content p:last-child { margin-bottom: 0; }
.fpd-empty {
  color: var(--ds-color-muted);
  font-style: italic;
  margin: 0;
}

.fpd-foot {
  padding: 10px 16px;
  border-top: 1px solid var(--ds-color-border);
  flex-shrink: 0;
}
.fpd-hint {
  color: var(--ds-color-muted);
  font: 10px var(--ds-font-mono);
  opacity: 0.7;
}
</style>
