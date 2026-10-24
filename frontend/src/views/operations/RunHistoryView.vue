<template>

  <section class="run-history" aria-labelledby="run-history-title">
    <header class="page-heading">
      <div>
        <p class="eyebrow">RUN HISTORY / 运行证据</p>
        <h1 id="run-history-title">运行记录中心</h1>
        <p>查询远程运维工具的命令、退出码、标准输出、错误输出与证据链。</p>
      </div>
      <button class="button" type="button" :disabled="loading" @click="loadRuns(page.page)">{{ loading ? '刷新中…' : '刷新记录' }}</button>
    </header>
    <form class="filters" @submit.prevent="loadRuns(1)">
      <label>Trace ID<input v-model="filters.traceId" type="search" placeholder="完整或部分 Trace ID" />
    </label>
    <label>工具<input v-model="filters.toolId" type="search" placeholder="例如 k8s.pods" />
  </label>
  <label>状态<select v-model="filters.status">
    <option value="">全部状态</option>
    <option value="SUCCESS">执行成功</option>
    <option value="FAILED">执行失败</option>
    <option value="RUNNING">执行中</option>
    <option value="CANCELLED">已取消</option>
  </select>
  </label>
  <label>开始时间<input v-model="filters.startedFrom" type="datetime-local" />
  </label>
  <label>结束时间<input v-model="filters.startedTo" type="datetime-local" />
  </label>
  <div class="actions">
    <button class="button primary" type="submit">查询</button>
    <button class="button ghost" type="button" @click="resetFilters">重置</button>
  </div>
  <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>
  </form>
  <div v-if="error" class="state error" role="alert">
    <strong>运行记录暂时无法加载</strong>
    <p>{{ error }}</p>
    <button class="button" @click="loadRuns(page.page)">重新加载</button>
  </div>
  <div v-else class="layout">
    <section class="list-panel" aria-label="运行记录列表">
      <div v-if="guideMode" class="guide-banner" role="note">
        <strong>当前显示演示数据</strong>
        <span>仅用于了解运行证据，不来自真实环境，不写入数据库，也不计入运行统计。</span>
      </div>
      <header class="panel-title">
        <div>
          <p class="eyebrow">RECORDS</p>
          <h2>执行记录</h2>
        </div>
        <span>{{ page.total }} 条<span v-if="guideMode">（演示）</span>
      </span>
    </header>
    <div v-if="loading && !page.items.length" class="state">正在读取运行记录…</div>
    <div v-else-if="!page.items.length" class="state">
      <strong>暂无匹配记录</strong>
      <p>远程工具执行完成后，记录会自动保存在这里。</p>
    </div>
    <button v-for="run in page.items" :key="run.id" class="run-row" :class="{ active: selectedId === run.id }" type="button" @click="selectRun(run.id)">
      <span class="row-top">
        <b>{{ run.toolId }}</b>
        <i :class="statusClass(run.status)">{{ run.isGuide ? '演示数据' : runStatusLabel(run.status) }}</i>
      </span>
      <code>{{ run.traceId }}</code>
      <span class="row-meta">
        <time>{{ formatTime(run.startedAt) }}</time>
        <span>{{ formatDuration(run.startedAt, run.endedAt) }}</span>
      </span>
      <small>{{ run.commandCount }} 条命令<span v-if="run.failedCommandCount"> · {{ run.failedCommandCount }} 条失败</span>
    </small>
  </button>
  <footer v-if="page.total > page.pageSize" class="pagination">
    <button :disabled="page.page <= 1" @click="loadRuns(page.page - 1)">上一页</button>
    <span>第 {{ page.page }} / {{ totalPages }} 页</span>
    <button :disabled="page.page >= totalPages" @click="loadRuns(page.page + 1)">下一页</button>
  </footer>
  </section>
  <section class="detail-panel" aria-live="polite">
    <div v-if="detailError" class="state error detail-error" role="alert">
      <strong>运行详情暂时无法加载</strong>
      <p>{{ detailError }}</p>
      <button class="button" :disabled="selectedId == null" @click="loadDetail(selectedId)">重新加载详情</button>
    </div>
    <div v-else-if="detailLoading" class="state">正在加载证据详情…</div>
    <div v-else-if="!detail" class="state">
      <strong>选择一条运行记录</strong>
      <p>这里将展示完整命令输出和运行证据。</p>
    </div>
    <template v-else>
      <header class="panel-title detail-title">
        <div>
          <p class="eyebrow">TRACE DETAIL</p>
          <h2>{{ detail.run.toolId }}</h2>
        </div>
        <div class="detail-actions">
          <button v-if="!detail.run.isGuide" class="button candidate-button" type="button" :disabled="candidateLoading" @click="createCandidate">
            {{ candidateLoading ? '正在生成…' : '沉淀为知识候选' }}
          </button>
          <i :class="statusClass(detail.run.status)">{{ runStatusLabel(detail.run.status) }}</i>
        </div>
      </header>
      <div v-if="detail.run.isGuide" class="guide-banner" role="note">
        <strong>虚拟运行记录</strong>
        <span>命令与输出均为示例，未连接真实主机或集群，不能由此生成正式知识候选。</span>
      </div>
      <div v-if="candidate || candidateError" class="candidate-feedback" :class="{ failed: candidateError }" role="status">
        <template v-if="candidate">
          <strong>已生成知识候选</strong>
          <span>状态：{{ candidateStatusLabel(candidate.status) }}</span>
          <span>候选标题：{{ candidate.title }}</span>
          <small>候选内容需经过人工审核后才能成为正式知识。</small>
        </template>
        <template v-else>
          <strong>知识候选生成失败</strong>
          <span>{{ candidateError }}</span>
        </template>
      </div>
      <dl class="facts">
        <div>
          <dt>Trace ID</dt>
          <dd>
            <DecodeText :value="detail.run.traceId" tag="code" />
            <button class="copy" @click="copyTrace(detail.run.traceId)">{{ copyFailed ? '复制失败，请重试' : copied ? '已复制' : '复制' }}</button>
          </dd>
        </div>
        <div>
          <dt>运行目标</dt>
          <dd>{{ detail.run.runtimeId }}</dd>
        </div>
        <div>
          <dt>会话 ID</dt>
          <dd>{{ detail.run.sessionId ?? '未关联' }}</dd>
        </div>
        <div>
          <dt>执行时间</dt>
          <dd>{{ formatTime(detail.run.startedAt) }}</dd>
        </div>
        <div>
          <dt>持续时间</dt>
          <dd>{{ formatDuration(detail.run.startedAt, detail.run.endedAt) }}</dd>
        </div>
      </dl>
      <section class="detail-section">
        <header>
          <h3>命令与输出</h3>
          <span>{{ detail.outputs.length }} 项</span>
        </header>
        <article v-for="output in detail.outputs" :key="output.id" class="command-card">
          <div class="command-head">
            <span>步骤 {{ output.sequenceNo }}</span>
            <b :class="`exit-${outputState(output.exitCode)}`">Exit {{ output.exitCode ?? '未知' }}</b>
          </div>
          <pre class="command"><code>{{ output.command }}</code></pre>
          <div class="outputs">
            <div>
              <h4>标准输出 stdout</h4>
              <pre :class="{ empty: !visibleOutput(output.stdout) }">{{ visibleOutput(output.stdout) || '无标准输出' }}</pre>
            </div>
            <div>
              <h4>错误输出 stderr</h4>
              <pre :class="{ empty: !visibleOutput(output.stderr) }">{{ visibleOutput(output.stderr) || '无错误输出' }}</pre>
            </div>
          </div>
        </article>
        <p v-if="!detail.outputs.length" class="empty">该运行记录没有命令输出。</p>
      </section>
      <section class="detail-section evidence">
        <header>
          <h3>运行证据</h3>
          <span>{{ detail.evidence.length }} 项</span>
        </header>
        <article v-for="item in detail.evidence" :key="item.id" class="evidence-row">
          <div>
            <b>{{ item.type }}</b>
            <code>{{ item.sourceRef || '无来源引用' }}</code>
          </div>
          <p>{{ item.content }}</p>
          <time>{{ formatTime(item.createdAt) }}</time>
        </article>
        <p v-if="!detail.evidence.length" class="empty">该运行记录没有附加证据。</p>
      </section>
    </template>
  </section>
  </div>
  </section>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { createKnowledgeCandidateFromRun, getOperationRun, getOperationRuns } from '../../api/operations.js'
import { candidateStatusLabel, cleanRunQuery, formatDuration, normalizeDateTime, outputState, runStatusLabel, validateRunTimeRange, visibleOutput } from '../../components/operations/operationRunHistory.js'
import DecodeText from '../../components/common/DecodeText.vue'
import { findRunHistoryGuide, runPageWithGuides } from '../../components/operations/runHistoryGuides.js'

const filters = ref({ traceId: '', toolId: '', status: '', startedFrom: '', startedTo: '' })
const page = ref({ items: [], total: 0, page: 1, pageSize: 20 })
const selectedId = ref(null), detail = ref(null), loading = ref(false), detailLoading = ref(false), error = ref(''), detailError = ref(''), copied = ref(false)
const candidateLoading = ref(false), candidate = ref(null), candidateError = ref('')
const guideMode = ref(false)
const formError = ref(''), copyFailed = ref(false)
let copyToken = 0, copyTimer
let listToken = 0
let detailToken = 0
const totalPages = computed(() => Math.max(1, Math.ceil(page.value.total / page.value.pageSize)))
const unwrap = response => response?.data ?? response
const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium', hour12: false })
const formatTime = value => value ? dateTimeFormatter.format(new Date(value)) : '—'
const statusClass = status => `status status-${String(status || '').toLowerCase()}`

async function loadRuns(targetPage = 1) {
  formError.value = Object.values(validateRunTimeRange(filters.value.startedFrom, filters.value.startedTo))[0] || ''
  if (formError.value) return
  const token = ++listToken
  ++detailToken
  detailError.value = ''
  detailLoading.value = false
  loading.value = true
  error.value = ''
  try {
    const query = cleanRunQuery({ ...filters.value, startedFrom: normalizeDateTime(filters.value.startedFrom), startedTo: normalizeDateTime(filters.value.startedTo), page: targetPage, pageSize: page.value.pageSize })
    const nextPage = runPageWithGuides(unwrap(await getOperationRuns(query)), query)
    if (token !== listToken) return
    page.value = nextPage
    guideMode.value = page.value.guideMode
    if (!page.value.items.some(item => item.id === selectedId.value)) { selectedId.value = page.value.items[0]?.id ?? null; detail.value = null; resetCopy(); candidate.value = null; candidateError.value = '' }
    if (selectedId.value) await loadDetail(selectedId.value)
  } catch (cause) { if (token === listToken) error.value = cause.message || '请检查后端服务和数据库连接。' } finally { if (token === listToken) loading.value = false }
}
async function loadDetail(id) {
  if (id == null) return
  const token = ++detailToken
  detailLoading.value = true
  detailError.value = ''
  try {
    const nextDetail = findRunHistoryGuide(id) || unwrap(await getOperationRun(id))
    if (token === detailToken) detail.value = nextDetail
  } catch (cause) {
    if (token === detailToken) { detailError.value = cause.message || '运行详情加载失败。'; detail.value = null }
  } finally {
    if (token === detailToken) detailLoading.value = false
  }
}
function selectRun(id) {
  if (id !== selectedId.value) {
    resetCopy()
    selectedId.value = id
    candidate.value = null
    candidateError.value = ''
    loadDetail(id)
  }
}
async function createCandidate() {
  if (!detail.value?.run?.id || detail.value.run.isGuide || candidateLoading.value) return
  candidateLoading.value = true
  candidateError.value = ''
  try {
    candidate.value = unwrap(await createKnowledgeCandidateFromRun(detail.value.run.id))
  } catch (cause) {
    candidate.value = null
    candidateError.value = cause.message || '请稍后重试，运行记录不会被修改。'
  } finally {
    candidateLoading.value = false
  }
}
function resetFilters() { filters.value = { traceId: '', toolId: '', status: '', startedFrom: '', startedTo: '' }; loadRuns(1) }
function resetCopy() {
  ++copyToken
  window.clearTimeout(copyTimer)
  copied.value = false
  copyFailed.value = false
}
async function copyTrace(value) {
  resetCopy()
  const token = copyToken
  try {
    await navigator.clipboard.writeText(value)
    if (token !== copyToken) return
    copied.value = true
    copyTimer = window.setTimeout(resetCopy, 1400)
  } catch {
    if (token === copyToken) copyFailed.value = true
  }
}
onBeforeUnmount(() => { ++detailToken; ++listToken; resetCopy() })
onMounted(() => loadRuns(1))
</script>

<style scoped>
.form-error {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--smart-danger, #e06b72);
  font-size: 12px;
}
.detail-error {
  margin: 16px;
}
.exit-unknown, .status-unknown {
  color: var(--smart-muted);
}
.run-history {
  max-width: 1480px;
  margin: 0 auto;
  padding: 12px 0 40px;
  color: var(--smart-text);
  font-family: var(--font-cn);
  padding-bottom: 0;
  /* 抵消 .content 底部留白，避免整页多出一条滚动条 */
  margin-bottom: -96px;
}
.page-heading,.panel-title,.detail-section>header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}
.eyebrow {
  margin: 0 0 9px;
  color: var(--smart-primary-strong);
  font: 10px var(--font-mono);
  letter-spacing: .14em;
}
.page-heading h1 {
  margin: 0;
  font-size: clamp(28px,3vw,38px);
  font-weight: 560;
}
.page-heading p:not(.eyebrow) {
  color: var(--smart-muted);
  font-size: 13px;
}
.button,.pagination button,.copy {
  min-height: 40px;
  border: 1px solid var(--smart-border);
  border-radius: 8px;
  padding: 8px 15px;
  color: var(--smart-text);
  background: var(--smart-surface);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.primary {
  border-color: transparent;
  background: var(--smart-primary-strong);
  color: var(--smart-bg);
  font-weight: 650;
}
.ghost {
  border-color: transparent;
  background: transparent;
  color: var(--smart-muted);
}
button:disabled {
  opacity: .45;
  cursor: wait;
}
button:focus-visible,input:focus-visible,select:focus-visible {
  outline: 2px solid var(--smart-primary-strong);
  outline-offset: 3px;
}
.filters {
  display: grid;
  grid-template-columns: 1.2fr 1fr .8fr 1fr 1fr auto;
  align-items: end;
  gap: 12px;
  margin: 26px 0 18px;
  padding: 17px;
  border: 1px solid var(--smart-border);
  border-radius: 12px;
  background: var(--smart-surface);
}
.filters label {
  display: grid;
  gap: 7px;
  min-width: 0;
  color: var(--smart-muted);
  font-size: 11px;
}
.filters input,.filters select {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  min-height: 40px;
  border: 1px solid var(--smart-border);
  border-radius: 7px;
  padding: 8px 11px;
  color: var(--smart-text);
  background: var(--smart-bg);
}
.actions {
  display: flex;
  gap: 6px;
}
.layout {
  display: grid;
  grid-template-columns: minmax(300px,380px) minmax(0,1fr);
  gap: 18px;
  height: clamp(420px, calc(100dvh - 420px), 880px);
  align-items: stretch;
}
.list-panel,.detail-panel {
  min-width: 0;
  border: 1px solid var(--smart-border);
  border-radius: 12px;
  background: var(--smart-surface);
  min-height: 0;
  overflow: hidden auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}
.panel-title {
  padding: 20px;
  border-bottom: 1px solid var(--smart-border);
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--smart-surface);
}
h2,h3 {
  margin: 0;
  font-weight: 560;
}
.panel-title h2 {
  font-size: 18px;
}
.panel-title>span,.detail-section header span {
  color: var(--smart-muted);
  font-size: 11px;
}
.run-row {
  display: block;
  width: 100%;
  padding: 17px 20px;
  border: 0;
  border-bottom: 1px solid var(--smart-border);
  text-align: left;
  color: var(--smart-text);
  background: transparent;
  cursor: pointer;
  transition: background 150ms;
}
.run-row:hover,.run-row.active {
  background: color-mix(in srgb,var(--smart-primary-strong) 9%,transparent);
}
.run-row.active {
  box-shadow: inset 3px 0 var(--smart-primary-strong);
}
.row-top,.row-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}
.status {
  font-style: normal;
  font-size: 10px;
  border: 1px solid currentColor;
  border-radius: 999px;
  padding: 4px 8px;
}
.status-success,.exit-success {
  color: #4fb58b;
}
.status-failed,.exit-failed {
  color: #e06b72;
}
.status-running {
  color: #d69a50;
}
.status-cancelled {
  color: var(--smart-muted);
}
.run-row>code {
  display: block;
  margin: 11px 0;
  color: var(--smart-muted);
  font: 11px var(--font-mono);
  overflow-wrap: anywhere;
}
.row-meta,.run-row small {
  color: var(--smart-muted);
  font-size: 10px;
}
.run-row small {
  display: block;
  margin-top: 8px;
}
.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px;
}
.pagination button {
  min-height: 34px;
  padding: 6px 10px;
}
.pagination span {
  font-size: 10px;
  color: var(--smart-muted);
}
.state {
  padding: 60px 24px;
  text-align: center;
  color: var(--smart-muted);
  font-size: 12px;
}
.state strong {
  color: var(--smart-text);
  font-size: 14px;
}
.error {
  border: 1px solid var(--smart-border);
  border-left: 3px solid #e06b72;
  border-radius: 12px;
  background: var(--smart-surface);
}
.detail-panel {
  min-height: 520px;
}
.facts {
  display: grid;
  grid-template-columns: repeat(5,minmax(0,1fr));
  margin: 0;
  border-bottom: 1px solid var(--smart-border);
}
.facts div {
  min-width: 0;
  padding: 16px 18px;
  border-right: 1px solid var(--smart-border);
}
.facts dt {
  color: var(--smart-muted);
  font-size: 10px;
}
.facts dd {
  margin: 8px 0 0;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.facts code {
  font: 11px var(--font-mono);
}
.copy {
  min-height: 26px;
  margin-left: 8px;
  padding: 3px 8px;
}
.detail-section {
  padding: 22px;
}
.detail-section header {
  margin-bottom: 15px;
}
.detail-section h3 {
  font-size: 15px;
}
.command-card {
  margin-top: 12px;
  border: 1px solid var(--smart-border);
  border-radius: 10px;
  overflow: hidden;
}
.command-head {
  display: flex;
  justify-content: space-between;
  padding: 11px 14px;
  color: var(--smart-muted);
  font-size: 10px;
  background: var(--smart-bg);
}
.command {
  margin: 0;
  padding: 14px;
  overflow: auto;
  background: #090d12;
  color: #d8e4ec;
  font: 12px/1.7 var(--font-mono);
}
.outputs {
  display: grid;
  grid-template-columns: 1fr 1fr;
}
.outputs>div {
  min-width: 0;
  padding: 14px;
}
.outputs>div+div {
  border-left: 1px solid var(--smart-border);
}
.outputs h4 {
  margin: 0 0 9px;
  color: var(--smart-muted);
  font-size: 10px;
}
.outputs pre {
  min-height: 54px;
  max-height: 280px;
  margin: 0;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font: 11px/1.7 var(--font-mono);
}
.empty {
  color: var(--smart-muted);
  font-style: italic;
}
.evidence {
  border-top: 1px solid var(--smart-border);
}
.evidence-row {
  display: grid;
  grid-template-columns: minmax(150px,.65fr) minmax(0,1.5fr) auto;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid var(--smart-border);
  font-size: 11px;
}
.evidence-row b,.evidence-row code {
  display: block;
}
.evidence-row code,.evidence-row time {
  margin-top: 6px;
  color: var(--smart-muted);
  font: 10px var(--font-mono);
}
.evidence-row p {
  margin: 0;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.detail-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}
.candidate-button {
  min-height: 34px;
  padding: 6px 12px;
  border-color: color-mix(in srgb,var(--smart-primary-strong) 55%,var(--smart-border));
  color: var(--smart-primary-strong);
  background: color-mix(in srgb,var(--smart-primary-strong) 8%,var(--smart-surface));
  font-weight: 650;
}
.candidate-feedback {
  display: grid;
  grid-template-columns: auto auto minmax(180px,1fr);
  align-items: center;
  gap: 8px 18px;
  padding: 13px 20px;
  border-bottom: 1px solid var(--smart-border);
  border-left: 3px solid #4fb58b;
  background: color-mix(in srgb,#4fb58b 6%,var(--smart-surface));
  font-size: 11px;
}
.candidate-feedback strong {
  font-size: 12px;
}
.candidate-feedback small {
  grid-column: 1/-1;
  color: var(--smart-muted);
}
.candidate-feedback.failed {
  grid-template-columns: auto minmax(0,1fr);
  border-left-color: #e06b72;
  background: color-mix(in srgb,#e06b72 6%,var(--smart-surface));
}
.guide-banner {
  display: grid;
  gap: 5px;
  padding: 12px 20px;
  border-bottom: 1px solid color-mix(in srgb,#d69a50 45%,var(--smart-border));
  background: color-mix(in srgb,#d69a50 8%,var(--smart-surface));
  font-size: 11px;
}
.guide-banner strong {
  color: #d69a50;
}
.guide-banner span {
  color: var(--smart-muted);
  line-height: 1.5;
}
@media(max-width:1180px) {
  .filters {
    grid-template-columns: repeat(3,minmax(0,1fr));
  }
  .layout {
    grid-template-columns: 320px minmax(0,1fr);
  }
  .facts {
    grid-template-columns: repeat(2,minmax(0,1fr));
  }
}
@media(max-width:800px) {
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .filters {
    grid-template-columns: 1fr 1fr;
  }
  .layout {
    grid-template-columns: 1fr;
  }
  .outputs {
    grid-template-columns: 1fr;
  }
  .outputs>div+div {
    border-left: 0;
    border-top: 1px solid var(--smart-border);
  }
  .evidence-row {
    grid-template-columns: 1fr;
  }
}
@media(max-width:520px) {
  .filters,.facts {
    grid-template-columns: 1fr;
  }
  .actions button {
    flex: 1;
  }
  .detail-title {
    align-items: flex-start;
  }
  .detail-actions {
    align-items: flex-end;
    flex-direction: column;
  }
  .candidate-feedback {
    grid-template-columns: 1fr;
  }
  .candidate-feedback small {
    grid-column: auto;
  }
  .detail-section {
    padding: 17px 14px;
  }
}
@media(prefers-reduced-motion:reduce) {
  .run-row {
    transition: none;
  }
}
/* 两栏独立滚动：执行记录与 Trace 详情各自一条滚动条，面板头吸顶 */
@media (max-width: 1023px) {
  .run-history {
    margin-bottom: -64px;
  }
}
@media (max-width: 767px) {
  .run-history {
    margin-bottom: -56px;
  }
}
.list-panel > footer.pagination {
  position: sticky;
  bottom: 0;
  z-index: 2;
  border-top: 1px solid var(--smart-border);
  background: var(--smart-surface);
}
@media (max-width: 800px) {
  .layout {
    height: auto;
  }
  .list-panel, .detail-panel {
    overflow: visible;
  }
  .panel-title, .list-panel > footer.pagination {
    position: static;
  }
}

</style>
