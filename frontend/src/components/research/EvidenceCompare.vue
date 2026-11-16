<template>
  <section class="evidence-compare" aria-label="跨来源证据对比">
    <div class="compare-heading"><div><p class="eyebrow">EVIDENCE CROSS-CHECK</p><h2>跨来源证据对比</h2></div><span>{{ selectedTaskIds.length }} / 4 已选择</span></div>
    <div v-if="pages.length" class="evidence-picker">
      <label v-for="page in pages" :key="page.taskId" :class="{ selected: selectedTaskIds.includes(page.taskId) }">
        <input type="checkbox" :checked="selectedTaskIds.includes(page.taskId)" @change="$emit('toggle', page.taskId)" />
        <span><b>#{{ page.taskId }} · {{ page.site }}</b><small>{{ page.title }}</small></span>
      </label>
    </div>
    <div v-else class="compare-empty">读取至少两个公开网址后，可在这里选择服务端快照进行对比。</div>
    <div class="compare-actions"><p>只做证据对比，不输出真伪评分；重合度高也可能是相互转载。</p><button type="button" :disabled="selectedTaskIds.length < 2 || comparing" @click="$emit('compare')">{{ comparing ? '对比中…' : '对比选中证据' }}</button></div>

    <template v-if="comparison">
      <p class="comparison-disclaimer" role="status">{{ comparison.disclaimer }}</p>
      <div class="comparison-grid">
        <article v-for="(item, index) in comparison.items" :key="item.taskId" class="source-assessment">
          <details :open="index === 0"><summary><span>#{{ item.taskId }} · {{ item.site }}</span><small>{{ item.taskType }} · {{ item.contentLength }} 字符</small></summary>
            <h3>{{ item.title }}</h3><a :href="item.url" target="_blank" rel="noopener noreferrer">{{ item.url }}</a>
            <dl><div><dt>抓取时间</dt><dd>{{ formatTime(item.fetchedAt) }}</dd></div><div><dt>正文 SHA-256</dt><dd><code>{{ item.contentHash }}</code></dd></div></dl>
            <h4 class="signal-heading">来源信号</h4><ul><li v-for="signal in item.signals" :key="signal.code" :class="signal.state.toLowerCase()"><span>{{ signal.label }} · {{ stateLabel(signal.state) }}</span><p>{{ signal.detail }}</p></li></ul>
          </details>
        </article>
      </div>
      <div class="overlap-list"><h3>文本重合线索</h3><article v-for="pair in comparison.pairs" :key="`${pair.leftTaskId}-${pair.rightTaskId}`"><div><b>#{{ pair.leftTaskId }} ↔ #{{ pair.rightTaskId }}</b><span>{{ pair.differentHosts ? '不同域名' : '相同域名' }}</span></div><strong>文本重合度 {{ (pair.textOverlap * 100).toFixed(1) }}%</strong><small>{{ overlapLabel(pair.overlapLevel) }}</small><p>{{ pair.note }}</p></article></div>
    </template>
  </section>
</template>

<script setup>
defineProps({
  pages: { type: Array, default: () => [] },
  selectedTaskIds: { type: Array, default: () => [] },
  comparison: { type: Object, default: null },
  comparing: { type: Boolean, default: false }
})
defineEmits(['toggle', 'compare'])
function stateLabel(state) { return ({ PASS: '已核验', WARN: '需注意', UNKNOWN: '未核验' })[state] || state }
function overlapLabel(level) { return ({ HIGH: '高重合', PARTIAL: '部分重合', LOW: '低重合' })[level] || level }
function formatTime(value) { if (!value) return '时间未提供'; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false }) }
</script>

<style scoped>
.evidence-compare{margin-top:34px;padding-top:24px;border-top:1px solid var(--smart-border)}.compare-heading{display:flex;justify-content:space-between;align-items:end;gap:16px}.eyebrow{margin:0 0 8px;color:var(--smart-primary-strong);font:9px var(--font-mono);letter-spacing:.12em}.compare-heading h2{margin:0;font-size:20px;font-weight:400}.compare-heading>span{color:var(--smart-muted);font:10px var(--font-mono)}.evidence-picker{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:18px 0}.evidence-picker label{display:flex;gap:9px;min-width:0;padding:12px;border:1px solid var(--smart-border);cursor:pointer}.evidence-picker label.selected{border-color:var(--smart-primary-strong);background:color-mix(in srgb,var(--smart-primary-strong) 5%,transparent)}.evidence-picker input{width:14px;min-height:14px;margin-top:2px;accent-color:var(--smart-primary-strong)}.evidence-picker span{min-width:0}.evidence-picker b,.evidence-picker small{display:block;overflow-wrap:anywhere}.evidence-picker b{font-size:11px;font-weight:500}.evidence-picker small{margin-top:5px;color:var(--smart-muted);font-size:10px}.compare-empty{margin:18px 0;padding:24px;border:1px dashed var(--smart-border);color:var(--smart-muted);font-size:12px;text-align:center}.compare-actions{display:flex;justify-content:space-between;align-items:center;gap:18px}.compare-actions p{margin:0;color:var(--smart-muted);font-size:11px}.compare-actions button{min-height:38px;padding:8px 14px;border:1px solid var(--smart-primary-strong);background:var(--smart-primary-strong);color:var(--smart-bg)}.compare-actions button:disabled{opacity:.45}.comparison-disclaimer{padding:12px 14px;margin:18px 0;border-left:2px solid var(--smart-warning,#d9a84e);color:var(--smart-muted);background:color-mix(in srgb,var(--smart-warning,#d9a84e) 5%,transparent);font-size:11px;line-height:1.7}.comparison-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.source-assessment{padding:14px;border:1px solid var(--smart-border);min-width:0}.source-assessment summary{display:flex;justify-content:space-between;gap:12px;cursor:pointer;color:var(--smart-primary-strong);font-size:11px}.source-assessment summary small{color:var(--smart-muted);font:9px var(--font-mono)}.source-assessment h3{margin:14px 0 6px;font-size:14px;font-weight:500;overflow-wrap:anywhere}.source-assessment a{display:block;color:var(--smart-primary-strong);font-size:10px;overflow-wrap:anywhere}.source-assessment dl{margin:12px 0}.source-assessment dl>div{padding:8px 0;border-top:1px solid var(--smart-border)}dt{margin-bottom:4px;color:var(--smart-muted);font:9px var(--font-mono)}dd{margin:0;font-size:10px;overflow-wrap:anywhere}dd code{font-size:8px}.signal-heading{margin:12px 0 0;font-size:11px;font-weight:400}.source-assessment ul{padding:0;margin:0;list-style:none}.source-assessment li{padding:9px 0;border-top:1px solid var(--smart-border)}.source-assessment li>span{font-size:10px}.source-assessment li.pass>span{color:var(--smart-success,#64b99a)}.source-assessment li.warn>span{color:var(--smart-warning,#d9a84e)}.source-assessment li.unknown>span{color:var(--smart-muted)}.source-assessment li p{margin:5px 0 0;color:var(--smart-muted);font-size:10px;line-height:1.6}.overlap-list{margin-top:18px}.overlap-list>h3{font-size:14px;font-weight:400}.overlap-list article{display:grid;grid-template-columns:minmax(160px,1fr) auto auto;gap:8px 14px;align-items:center;padding:12px 0;border-top:1px solid var(--smart-border)}.overlap-list article>div{display:flex;gap:10px;align-items:center}.overlap-list b{font-size:11px}.overlap-list span,.overlap-list small{color:var(--smart-muted);font-size:10px}.overlap-list strong{font-size:12px;font-weight:500}.overlap-list p{grid-column:1/-1;margin:0;color:var(--smart-muted);font-size:10px}@media(max-width:980px){.evidence-picker{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:720px){.comparison-grid{grid-template-columns:1fr}.compare-actions{align-items:flex-start;flex-direction:column}.compare-actions button{width:100%}.overlap-list article{grid-template-columns:1fr auto}.overlap-list article>small{grid-column:1/-1}}@media(max-width:480px){.evidence-picker{grid-template-columns:1fr}.source-assessment summary{flex-direction:column}}
</style>
