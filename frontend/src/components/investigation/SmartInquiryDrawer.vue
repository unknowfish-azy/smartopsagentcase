<template>
  <aside v-if="context.faultEvent && store.drawerOpen" class="inquiry-drawer" aria-label="Smart Investigation" aria-live="polite" @keydown.esc="close">
    <header class="inquiry-header">
      <div>
        <p class="eyebrow">SMART INVESTIGATION</p>
        <h2>{{ fault.title }}</h2>
      </div>
      <button class="close-button" type="button" aria-label="Close investigation" @click="close">×</button>
    </header>

    <div class="inquiry-body">
      <section class="fault-summary">
        <span class="severity" :class="`severity--${fault.severity.toLowerCase()}`">{{ fault.severity }}</span>
        <span>Detected {{ formatTime(fault.detectedAt) }}</span>
      </section>

      <section class="evidence-block">
        <div class="section-label">EVIDENCE</div>
        <ul>
          <li v-for="item in context.evidence" :key="item.id"><b>{{ item.source }}</b><span>{{ item.content }}</span></li>
        </ul>
      </section>

      <section v-if="currentQuestion" class="question-block">
        <div class="section-label">NEXT QUESTION · {{ currentQuestion.priority }}</div>
        <h3>{{ currentQuestion.prompt }}</h3>
        <p class="why"><b>为什么问？</b> {{ currentQuestion.why }}</p>
        <div v-if="currentQuestion.options" class="options" role="group" :aria-label="currentQuestion.prompt">
          <button v-for="option in currentQuestion.options" :key="option[0]" type="button" :class="{ selected: selectedValue === option[0] }" @click="selectOption(option)">{{ option[1] }}</button>
        </div>
        <textarea v-model="freeText" aria-label="补充观察" rows="2" placeholder="也可以直接描述你的观察…" @keydown.enter.exact.prevent="submitAnswer"></textarea>
        <button class="primary-button" type="button" :disabled="!selectedValue && !freeText.trim()" @click="submitAnswer">继续排查</button>
      </section>

      <section v-else class="ready-block">
        <div class="section-label">INVESTIGATION READY</div>
        <p>上下文已收集。请结合来源核对影响范围、变更时间与上游健康；目前尚未确认根因。</p>
        <article v-for="item in context.recommendations" :key="item.id" class="knowledge-card"><div><p>{{ item.text }}</p><small>{{ item.source }} · {{ item.section }} · {{ item.risk }}</small></div></article>
      </section>

      <section class="knowledge-block">
        <div class="section-heading"><div class="section-label">RELATED KNOWLEDGE</div><span>{{ knowledgeResults.length }} results</span></div>
        <article v-for="entry in knowledgeResults" :key="entry.id" class="knowledge-card">
          <div><h3>{{ entry.title }}</h3><p>{{ entry.summary }}</p><small>{{ entry.source }} · {{ entry.section }}</small></div>
          <button type="button" :disabled="isAdded(entry.id)" @click="addKnowledge(entry)">{{ isAdded(entry.id) ? '已加入' : '加入调查' }}</button>
        </article>
        <p v-if="!knowledgeResults.length" class="empty-state">暂未找到本地匹配知识，仍保留原始证据。</p>
      </section>

      <p class="safety-note">只提供证据与排查建议。当前调查不会执行任何远程命令。</p>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useCompanionStore } from '../../stores/companion.js'
import { normalizeAnswer } from '../../domain/investigation/inquiry.ts'
import { knowledgeReadApi } from '../../views/knowledge/knowledgeLibrary.js'

const store = useCompanionStore()
const selectedValue = ref('')
const freeText = ref('')
const context = computed(() => store.contextSnapshot)
const fault = computed(() => context.value?.faultEvent || {})
const currentQuestion = computed(() => context.value?.questions?.find(question => !context.value.answers.some(answer => answer.questionId === question.id)) || null)
const query = computed(() => [fault.value.title, ...(fault.value.evidence || []).map(item => item.content), ...(context.value?.answers || []).map(item => item.normalized?.value || item.original)].filter(Boolean).join(' '))
const knowledgeResults = computed(() => {
  if (!context.value.faultEvent || store.capabilities.knowledge.status === 'offline') return []
  const terms = query.value.split(/\s+/).filter(term => term.length > 2)
  const matches = terms.flatMap(term => knowledgeReadApi.search({ query: term }))
  const unique = new Map(matches.map(entry => [entry.id, entry]))
  return [...unique.values()].slice(0, 4)
})

watch(() => [context.value.id, currentQuestion.value?.id], () => { selectedValue.value = ''; freeText.value = '' })

function selectOption(option) { selectedValue.value = option[0]; freeText.value = '' }
function submitAnswer() {
  if (!currentQuestion.value) return
  const raw = freeText.value.trim() || selectedValue.value
  if (!raw) return
  const normalized = normalizeAnswer(currentQuestion.value, raw)
  store.recordAnswer({ questionId: currentQuestion.value.id, original: raw, normalized, confidence: normalized.confidence })
  selectedValue.value = ''
  freeText.value = ''
}
function isAdded(id) { return context.value?.knowledgeReferences?.some(reference => reference.documentId === id) }
function addKnowledge(entry) {
  store.addKnowledgeReference({ documentId: entry.id, title: entry.title, source: entry.source, section: entry.section, matchedText: entry.summary, risk: entry.risk || 'UNKNOWN', score: null })
}
function close() { store.closeInvestigation() }
function formatTime(value) { return value ? new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(value)) : '—' }
</script>

<style scoped>
.inquiry-drawer{position:fixed;z-index:20;top:76px;right:20px;width:min(410px,calc(100vw - 32px));max-height:calc(100vh - 96px);display:flex;flex-direction:column;border:1px solid rgba(122,215,245,.3);background:rgba(5,9,13,.96);box-shadow:0 24px 70px rgba(0,0,0,.42);color:var(--smart-text)}
.inquiry-header{display:flex;justify-content:space-between;gap:16px;padding:20px;border-bottom:1px solid rgba(159,190,207,.14)}.eyebrow,.section-label{margin:0;color:var(--smart-muted);font:10px var(--font-mono);letter-spacing:.12em}.inquiry-header h2{margin:7px 0 0;color:var(--smart-primary-strong);font:600 17px var(--font-cn)}.close-button{width:28px;height:28px;border:1px solid rgba(159,190,207,.18);background:transparent;color:var(--smart-muted);font-size:20px;cursor:pointer}.close-button:hover{color:var(--smart-text);border-color:var(--smart-primary-strong)}.inquiry-body{overflow:auto;padding:18px 20px 20px}.fault-summary{display:flex;align-items:center;gap:10px;color:var(--smart-muted);font:11px var(--font-mono)}.severity{padding:3px 6px;border:1px solid currentColor;font-size:9px}.severity--critical,.severity--high{color:#e19b8b}.severity--medium{color:#d9b96d}.severity--low,.severity--info{color:#8bc8a7}.evidence-block,.question-block,.knowledge-block{margin-top:20px}.evidence-block ul{display:grid;gap:7px;margin:9px 0 0;padding:0;list-style:none}.evidence-block li{display:flex;gap:9px;padding:8px 10px;border-left:2px solid rgba(122,215,245,.5);background:rgba(77,179,255,.06);font:12px var(--font-cn)}.evidence-block b{color:var(--smart-primary-strong);font:9px var(--font-mono)}.question-block h3{margin:9px 0 8px;font:600 15px var(--font-cn)}.why{margin:0 0 12px;color:var(--smart-muted);font:12px/1.6 var(--font-cn)}.why b{color:var(--smart-text)}.options{display:grid;gap:7px}.options button,.knowledge-card button,.primary-button{padding:9px 10px;border:1px solid rgba(159,190,207,.2);background:rgba(7,16,24,.9);color:var(--smart-text);font:12px var(--font-cn);text-align:left;cursor:pointer}.options button:hover,.options button.selected{border-color:var(--smart-primary-strong);background:rgba(77,179,255,.12);color:var(--smart-primary-strong)}textarea{width:100%;box-sizing:border-box;margin-top:10px;resize:vertical;border:1px solid rgba(159,190,207,.2);background:#071018;color:var(--smart-text);padding:9px;font:12px/1.5 var(--font-cn)}textarea:focus{outline:1px solid var(--smart-primary-strong)}.primary-button{width:100%;margin-top:10px;background:var(--smart-primary-strong);color:#041018;text-align:center;font-weight:600}.primary-button:disabled{cursor:not-allowed;opacity:.4}.ready-block p,.empty-state,.safety-note{color:var(--smart-muted);font:12px/1.6 var(--font-cn)}.section-heading{display:flex;justify-content:space-between;align-items:center}.section-heading span{color:var(--smart-muted);font:10px var(--font-mono)}.knowledge-card{display:flex;justify-content:space-between;gap:10px;margin-top:9px;padding:10px;border:1px solid rgba(159,190,207,.14);background:rgba(7,16,24,.66)}.knowledge-card h3{margin:0;color:var(--smart-text);font:12px var(--font-cn)}.knowledge-card p{margin:5px 0;color:var(--smart-muted);font:11px/1.45 var(--font-cn)}.knowledge-card small{color:var(--smart-primary-strong);font:9px var(--font-mono)}.knowledge-card button{flex:0 0 auto;align-self:center;padding:6px;font-size:10px}.knowledge-card button:disabled{opacity:.5}.safety-note{margin:20px 0 0;padding-top:12px;border-top:1px solid rgba(159,190,207,.12)}
@media(max-width:767px){.inquiry-drawer{top:auto;right:8px;bottom:8px;width:calc(100vw - 16px);max-height:78vh}.inquiry-header{padding:15px}.inquiry-body{padding:14px 15px 16px}}
</style>
