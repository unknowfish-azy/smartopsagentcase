<template>
  <section class="hc-card hc-result" aria-labelledby="hc-result-title">
    <!-- 头部：目标 · 耗时 · 结论 -->
    <header class="hc-result-head">
      <h3 id="hc-result-title">{{ toolLabel }}诊断</h3>
      <span class="hc-result-scope" v-if="scope">{{ scopeText }}</span>
      <span class="hc-result-chip" v-if="summaryChip">{{ summaryChip }}</span>
      <span class="hc-v-grow" aria-hidden="true"></span>
      <span class="hc-row-meta" v-if="durationText">
        <span>{{ durationText }}</span>
        <span>{{ endedAtText }}</span>
      </span>
      <button class="hc-btn hc-btn-small" type="button" :disabled="loading" @click="$emit('rerun')">
        {{ loading ? '诊断中…' : '重新诊断' }}
      </button>
    </header>

    <!-- 诊断中占位：失败后不阻塞旧结果（§5 "旧结果仅作参考" 诚实做法） -->
    <div v-if="loading && !result && !failureError" class="hc-result-loading" role="status">
      <span class="hc-spinner" aria-hidden="true"></span>
      正在执行 {{ toolLabel }} 诊断…
    </div>

    <!-- 证据完整性横幅（§8.3） -->
    <EvidenceBanner
      v-if="result"
      :permission-denied="result.permissionDenied"
      :data-missing="result.dataMissing"
      :unverified="result.unverified"
      :truncated="result.truncated"
    />

    <!-- 检查未完成（DESIGN §8.4：只在结果面板内部报错） -->
    <div v-if="failureError" class="hc-result-error" role="alert">
      <b>检查未完成：</b>{{ failureError }}
      <p class="hc-result-error-note">这不代表目标服务不健康</p>
      <button class="hc-btn hc-btn-small" type="button" @click="$emit('rerun')">重试</button>
    </div>

    <!-- 空态 -->
    <div v-if="!result && !failureError" class="hc-result-empty">
      选择授权目标后运行。结果会在这里就地展开，失败时只报「检查未完成」，不改写服务健康状态。
    </div>

    <template v-if="result && !failureError">
      <!-- 分层（network / kubernetes 有 layers） -->
      <section
        v-for="(layer, i) in layers"
        :key="`layer-${i}-${layer.name}`"
        class="hc-layer"
        :class="{ 'hc-layer--collapsed': collapsedLayers.has(i) }"
      >
        <button
          class="hc-layer-head"
          type="button"
          :aria-expanded="!collapsedLayers.has(i)"
          @click="toggleLayer(i)"
        >
          <span class="hc-st" :class="`hc-st--${statusVisualOf(layer.status).cls}`" aria-hidden="true">
            {{ statusVisualOf(layer.status).icon }}
          </span>
          <span class="hc-layer-name">{{ layer.name }}</span>
          <span class="hc-layer-sum">{{ layer.summary }}</span>
          <span class="hc-row-meta"><span>{{ layer.checks?.length || 0 }} 项检查</span></span>
        </button>

        <div class="hc-layer-body">
          <!-- 阻断说明（§8.4：BLOCKED 渲染成"被阻断（不是故障）"，不许用故障红） -->
          <div v-if="layer.blockedBy" class="hc-blocked">
            <b>被阻断（不是故障）</b>：{{ layer.blockedBy }}
          </div>

          <div v-for="(c, j) in (layer.checks || [])" :key="`${i}-${j}-${c.name}`" class="hc-check">
            <span class="hc-st hc-st--sm" :class="`hc-st--${statusVisualOf(c.status).cls}`" aria-hidden="true">
              {{ statusVisualOf(c.status).icon }}
            </span>
            <span class="hc-check-name">{{ c.name }}</span>
            <span class="hc-check-cmd" :title="c.command">{{ c.command || '' }}</span>
            <span class="hc-check-ev" :title="c.evidence">{{ c.evidence || '' }}</span>
          </div>
        </div>
      </section>

      <!-- 简单检查列表（host / database 直接用 checks[]） -->
      <template v-if="!layers.length && simpleChecks.length">
        <div v-for="(c, j) in simpleChecks" :key="`simple-${j}-${c.name}`" class="hc-check hc-check--simple">
          <span class="hc-st hc-st--sm" :class="`hc-st--${statusVisualOf(c.status).cls}`" aria-hidden="true">
            {{ statusVisualOf(c.status).icon }}
          </span>
          <span class="hc-check-name">{{ c.name }}</span>
          <span class="hc-check-cmd" :title="c.command">{{ c.command || '' }}</span>
          <span class="hc-check-ev" :title="c.evidence">{{ c.evidence || '' }}</span>
        </div>
      </template>

      <!-- 发现 findings（按 severity 排序） -->
      <div v-if="sortedFindings.length" class="hc-findings">
        <h4>发现 {{ sortedFindings.length }}</h4>
        <div v-for="(f, k) in sortedFindings" :key="`finding-${k}`" class="hc-finding" :class="`hc-finding--${f.severity}`">
          <span class="hc-finding-sev">{{ f.severity }}</span>
          <span>
            {{ f.message }}
            <br>
            <span class="hc-finding-res">{{ f.resourceKind }}/{{ f.resourceName }} · {{ f.type }}</span>
          </span>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import EvidenceBanner from './EvidenceBanner.vue'
import { statusVisual as resolveStatusVisual } from './healthGroups.js'

const props = defineProps({
  toolLabel: { type: String, required: true },
  result: { type: Object, default: null },
  failureError: { type: String, default: null },
  loading: { type: Boolean, default: false }
})
defineEmits(['rerun'])

function statusVisualOf(status) {
  return resolveStatusVisual(status || 'NOT_CHECKED')
}

// --- scope 格式化 ---
const scopeText = computed(() => {
  const s = props.result?.scope
  if (!s) return ''
  if (typeof s === 'string') return s
  // Network 结果 scope 是对象：{ context, namespace, host, port, service }
  if (typeof s === 'object') {
    const parts = []
    if (s.context) parts.push(s.context)
    if (s.namespace) parts.push(s.namespace)
    if (s.host) {
      const port = s.port ? `:${s.port}` : ''
      parts.push(`${s.host}${port}`)
    }
    return parts.join(' / ')
  }
  return ''
})

const durationText = computed(() => {
  const ms = props.result?.durationMs
  if (ms == null) return ''
  return `${(ms / 1000).toFixed(1)}s`
})

const endedAtText = computed(() => {
  const t = props.result?.endedAt
  if (!t) return ''
  const ms = typeof t === 'number' ? t : Date.parse(t)
  if (!Number.isFinite(ms)) return ''
  return new Date(ms).toLocaleTimeString('zh-CN', { hour12: false })
})

// --- 头部 chip：发现数 + 未完成层数 ---
const summaryChip = computed(() => {
  const r = props.result
  if (!r) return ''
  const findings = r.findings?.length || 0
  const blockedLayers = (r.layers || []).filter(l => l.blockedBy).length
  const unverified = (r.layers || []).filter(l => l.status === 'UNVERIFIED').length
  const parts = []
  if (findings) parts.push(`${findings} 处发现`)
  if (blockedLayers) parts.push(`${blockedLayers} 层被阻断`)
  if (unverified) parts.push(`${unverified} 层未验证`)
  if (!parts.length) {
    const totalLayers = r.layers?.length || 0
    if (totalLayers) parts.push(`${totalLayers} 层全过`)
    else return ''
  }
  return parts.join(' · ')
})

// --- layers（network / kubernetes）---
const collapsedLayers = ref(new Set())
const layers = computed(() => props.result?.layers || [])
function toggleLayer(i) {
  const s = new Set(collapsedLayers.value)
  s.has(i) ? s.delete(i) : s.add(i)
  collapsedLayers.value = s
}

// --- simple checks（host / database 直接 checks[]）---
const simpleChecks = computed(() => props.result?.checks || [])

// --- findings 按 severity 排序 ---
const SEV_ORDER = { high: 0, medium: 1, low: 2, info: 3 }
const sortedFindings = computed(() => {
  const list = props.result?.findings || []
  return [...list].sort((a, b) => (SEV_ORDER[a.severity] ?? 99) - (SEV_ORDER[b.severity] ?? 99))
})
</script>

<style scoped>
.hc-result { margin-top: 18px; }

.hc-result-head {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--ds-hairline);
  flex-wrap: wrap;
}
.hc-result-head h3 { margin: 0; font-size: var(--ds-type-h3-size); font-weight: var(--ds-type-h3-weight); }
.hc-result-scope { color: var(--ds-color-muted); font: 12px/1 var(--ds-font-mono); }
.hc-result-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 9px; border-radius: var(--ds-radius-pill);
  font-size: 11.5px;
  border: 1px solid color-mix(in srgb, var(--ds-semantic-warning) 38%, transparent);
  background: var(--ds-pill-warning-bg);
  color: var(--ds-semantic-warning);
}

.hc-v-grow { flex: 1; }

.hc-row-meta {
  display: flex; align-items: center; gap: 8px;
  color: var(--ds-semantic-neutral); font-size: 11.5px;
  white-space: nowrap; font-variant-numeric: tabular-nums;
}

.hc-result-error {
  margin: 14px 16px;
  padding: 12px 14px;
  border-radius: var(--ds-radius-md);
  border: 1px solid color-mix(in srgb, var(--ds-semantic-danger) 34%, transparent);
  background: color-mix(in srgb, var(--ds-semantic-danger) 8%, transparent);
  color: var(--ds-color-text);
  font-size: 13px;
}
.hc-result-error b { color: var(--ds-semantic-danger); }
.hc-result-error-note {
  margin: 8px 0 12px;
  color: var(--ds-color-muted);
  font-size: 12px;
  font-style: italic;
}

.hc-result-empty {
  padding: 24px 16px;
  color: var(--ds-semantic-neutral);
  font-size: 12.5px;
  line-height: 1.5;
  border-top: 1px solid var(--ds-hairline);
}

/* ---- layers ---- */
.hc-layer { border-top: 1px solid var(--ds-hairline); }
.hc-layer:first-of-type { border-top: none; }
.hc-layer-head {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 11px 16px;
  text-align: left;
  border: none; background: transparent; cursor: pointer;
  transition: background var(--ds-duration-micro) var(--ds-ease-out);
}
.hc-layer-head:hover { background: color-mix(in srgb, var(--smart-text) 4%, transparent); }
.hc-layer-name { font-size: 13px; font-weight: 500; white-space: nowrap; }
.hc-layer-sum { color: var(--ds-color-muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hc-layer--collapsed .hc-layer-body { display: none; }
.hc-layer-body { padding: 0 16px 12px; }

/* ---- checks inside layers ---- */
.hc-check {
  display: grid;
  grid-template-columns: 18px 150px minmax(0, 1fr) auto;
  gap: 10px; align-items: baseline;
  padding: 7px 0;
  border-top: 1px dashed color-mix(in srgb, var(--smart-surface) 6%, transparent);
  font-size: 12.5px;
}
.hc-check:first-child { border-top: none; }
.hc-check--simple { grid-template-columns: 18px minmax(0, 1fr); }

.hc-st--sm { width: 16px; height: 16px; font-size: 9px; }
.hc-check-name { color: var(--ds-color-text); font-size: 12.5px; }
.hc-check-cmd {
  font: 11.5px/1 var(--ds-font-mono);
  color: var(--ds-color-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.hc-check-ev {
  color: var(--ds-semantic-neutral);
  font-size: 11.5px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* ---- blockedBy (DESIGN §8.4：不许用故障红) ---- */
.hc-blocked {
  margin: 0 0 10px;
  padding: 9px 11px;
  border-radius: var(--ds-radius-md);
  background: color-mix(in srgb, var(--smart-bg) 28%, transparent);
  border-left: 2px solid var(--ds-semantic-neutral);
  color: var(--ds-color-muted);
  font-size: 12px;
}
.hc-blocked b { color: var(--ds-color-text); font-weight: 500; }

/* ---- findings ---- */
.hc-findings {
  padding: 12px 16px;
  border-top: 1px solid var(--ds-hairline);
}
.hc-findings h4 {
  margin: 0 0 8px;
  font: var(--ds-type-overline-size)/1 var(--ds-font-mono);
  letter-spacing: .12em;
  color: var(--ds-semantic-neutral);
  text-transform: uppercase;
}
.hc-finding {
  display: grid;
  grid-template-columns: 56px 1fr;
  gap: 10px;
  padding: 8px 10px;
  margin-bottom: 6px;
  border-radius: var(--ds-radius-md);
  background: color-mix(in srgb, var(--ds-semantic-danger) 6%, transparent);
  border-left: 2px solid var(--ds-semantic-danger);
  font-size: 12.5px;
}
.hc-finding--medium {
  background: color-mix(in srgb, var(--ds-semantic-warning) 6%, transparent);
  border-left-color: var(--ds-semantic-warning);
}
.hc-finding--low {
  background: color-mix(in srgb, var(--ds-semantic-info) 6%, transparent);
  border-left-color: var(--ds-semantic-info);
}
.hc-finding-sev {
  color: var(--ds-semantic-danger);
  font: 11px/1 var(--ds-font-mono);
  text-transform: uppercase;
  font-weight: 600;
}
.hc-finding--medium .hc-finding-sev { color: var(--ds-semantic-warning); }
.hc-finding--low .hc-finding-sev { color: var(--ds-semantic-info); }
.hc-finding-res {
  color: var(--ds-semantic-neutral);
  font: 11.5px/1 var(--ds-font-mono);
}

/* ---- 响应式 ---- */
@media (max-width: 767px) {
  .hc-check { grid-template-columns: 18px 1fr; gap: 6px; }
  .hc-check-cmd, .hc-check-ev { grid-column: 2; white-space: normal; word-break: break-all; }
}

/* ---- loading ---- */
.hc-result-loading {
  display: flex; align-items: center; gap: 10px;
  padding: 20px 16px;
  border-top: 1px solid var(--ds-hairline);
  color: var(--ds-color-muted);
  font-size: 13px;
}
.hc-spinner {
  width: 14px; height: 14px;
  border: 2px solid var(--ds-color-border);
  border-top-color: var(--ds-color-primary-strong);
  border-radius: 50%;
  animation: hc-spin 0.7s linear infinite;
}
@keyframes hc-spin { to { transform: rotate(360deg); } }

@media (prefers-reduced-motion: reduce) {
  .hc-spinner { animation: none; }
}
</style>
