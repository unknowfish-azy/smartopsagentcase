<template>
  <section class="research-page ml-stagger">
    <header class="research-header">
      <div><p class="eyebrow">NEURAL RESEARCH / 01</p><h1>联网检索</h1><p class="subtitle">让公开网页、GitHub 与本地知识形成一条可追溯的证据链。</p></div>
      <button class="runtime-pill" :class="{ online: runtime?.available }" type="button" @click="refreshRuntime">
        <i />{{ runtime ? (runtime.available ? '本地模型在线' : '本地模型未就绪') : '正在检测本地模型' }}<small>{{ runtime?.model || 'Ollama' }}</small>
      </button>
    </header>

    <section class="research-console" aria-label="联网检索工作台">
      <form class="search-form" @submit.prevent="runSearch">
        <label class="search-input"><span>检索问题</span><input v-model="query" type="search" maxlength="200" placeholder="例如：Kubernetes 1.31 网络策略排查" required /></label>
        <label class="scope-input"><span>来源范围</span><select v-model="scope"><option value="ALL">网页 + GitHub</option><option value="WEB">公开网页</option><option value="GITHUB">GitHub</option></select></label>
        <button class="primary-action" type="submit" :disabled="searching">{{ searching ? '检索中…' : '开始检索' }}</button>
      </form>
      <form class="fetch-form" @submit.prevent="readUrl(directUrl)">
        <label><span>指定网址读取</span><input v-model="directUrl" type="url" placeholder="https://docs.example.com/public-guide" required /></label>
        <button type="submit" :disabled="fetching">{{ fetching ? '读取中…' : '读取正文' }}</button>
        <p>仅访问公开或已授权页面；不绕过登录、验证码、付费墙和访问控制。</p>
      </form>
      <p v-if="error" class="message error" role="alert">{{ error }}</p>
      <div v-if="searchErrors.length" class="message warning" role="status"><b>部分来源未完成</b><span v-for="item in searchErrors" :key="item">{{ friendlyError(item) }}</span></div>

      <RelationGraph :nodes="graph.nodes" :edges="graph.edges" :active-id="activeId" :scanning="searching || fetching" @select="selectGraphNode" />
      <div class="console-caption"><span>{{ searching ? '正在建立来源连接…' : `${results.length} 个检索来源` }}</span><span>节点表示真实来源 · 连线表示检索路径</span></div>
    </section>

    <div class="research-layout">
      <main class="results-column">
        <div class="section-heading"><div><p class="eyebrow">EVIDENCE STREAM</p><h2>检索结果</h2></div><span>{{ searchStatus || 'READY' }}</span></div>
        <div v-if="searching" class="result-skeleton" aria-label="正在检索"><i v-for="index in 3" :key="index" /></div>
        <template v-else-if="results.length">
          <article v-for="result in results" :key="result.id" class="result-card" :class="{ selected: selectedResult?.id === result.id }">
            <button class="result-main" type="button" @click="selectResult(result)">
              <span class="result-kind">{{ result.kind }}</span><h3>{{ result.title }}</h3><p>{{ result.snippet || '该来源未提供摘要，请打开原文核验。' }}</p><small>{{ result.site }} · {{ formatTime(result.retrievedAt) }}</small>
            </button>
            <div class="result-actions"><a :href="result.url" target="_blank" rel="noopener noreferrer">打开原文</a><button type="button" @click="readUrl(result.url)">读取正文</button></div>
          </article>
        </template>
        <div v-else class="empty-state"><b>从一个问题开始</b><p>搜索结果会在这里形成证据流。没有结果时保持空白，不使用演示数据填充。</p></div>

        <section class="task-section"><div class="section-heading"><div><p class="eyebrow">TASK LEDGER</p><h2>最近任务</h2></div><button class="text-button" type="button" @click="refreshTasks">刷新</button></div>
          <div v-if="tasks.length" class="task-list"><article v-for="task in tasks" :key="task.id"><span class="task-status" :class="task.status.toLowerCase()">{{ task.status }}</span><div><b>{{ task.queryText }}</b><small>{{ task.taskType }} · {{ task.resultCount }} 条 · {{ formatTime(task.createdAt) }}</small></div><code v-if="task.errorCode">{{ task.errorCode }}</code></article></div>
          <p v-else class="muted">暂无联网检索任务。</p>
        </section>
      </main>

      <aside class="evidence-column">
        <div class="section-heading"><div><p class="eyebrow">SOURCE TRACE</p><h2>来源纪要</h2></div></div>
        <section v-if="page" class="page-evidence">
          <span class="evidence-label">正文已读取</span><h3>{{ page.title }}</h3><dl><div><dt>来源网站</dt><dd>{{ page.site }}</dd></div><div><dt>原始地址</dt><dd><a :href="page.url" target="_blank" rel="noopener noreferrer">{{ page.displayUrl }}</a></dd></div><div><dt>抓取时间</dt><dd>{{ formatTime(page.fetchedAt) }}</dd></div><div><dt>正文 SHA-256</dt><dd><code>{{ page.contentHash }}</code></dd></div></dl>
          <div class="candidate-gate"><div><b>{{ candidate ? `候选 #${candidate.id} 已进入人工审核` : '网页正文尚未进入知识库' }}</b><p>提交后仍待人工核对；采纳前不会成为正式知识，也不会修改模型。</p></div><button type="button" :disabled="submittingCandidate || !page.taskId" @click="submitCandidate">{{ submittingCandidate ? '提交中…' : candidate ? '再次核对候选' : '提交人工审核' }}</button><RouterLink v-if="candidate" to="/knowledge/review">打开知识审核</RouterLink></div>
          <pre>{{ page.content }}</pre>
        </section>
        <section v-else-if="selectedResult" class="source-evidence"><span class="evidence-label">{{ selectedResult.kind }}</span><h3>{{ selectedResult.title }}</h3><p>{{ selectedResult.snippet || '暂无摘要' }}</p><dl><div><dt>来源网站</dt><dd>{{ selectedResult.site }}</dd></div><div><dt>原始地址</dt><dd><a :href="selectedResult.url" target="_blank" rel="noopener noreferrer">{{ selectedResult.displayUrl }}</a></dd></div><div><dt>检索时间</dt><dd>{{ formatTime(selectedResult.retrievedAt) }}</dd></div><div><dt>源发布时间 / 更新</dt><dd>{{ selectedResult.publishedAt || '来源未提供' }}</dd></div></dl><p class="evidence-note">搜索摘要只是线索，关键结论仍需读取原文核验。</p><button class="primary-action full" type="button" @click="readUrl(selectedResult.url)">读取并核验正文</button></section>
        <div v-else class="empty-state compact"><b>尚未选择来源</b><p>点击拓扑节点或检索结果查看完整出处。</p></div>
        <section class="runtime-detail"><span>LOCAL RUNTIME</span><b>{{ runtime?.model || 'Ollama' }}</b><p>{{ runtime?.detail || '正在读取本地运行时状态。' }}</p><small>当前页面只检测模型状态；检索与网页抓取不消耗在线模型 token。</small></section>
      </aside>
    </div>

    <EvidenceCompare :pages="evidencePages" :selected-task-ids="selectedEvidenceIds" :comparison="comparison" :comparing="comparing" @toggle="toggleEvidence" @compare="compareEvidence" />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import RelationGraph from '../../components/research/RelationGraph.vue'
import EvidenceCompare from '../../components/research/EvidenceCompare.vue'
import { addEvidencePage, toggleEvidenceTask } from '../../components/research/evidenceSelection.js'
import { researchGraph } from '../../components/research/relationGraph.js'
import { compareWebResearchEvidence, fetchWebResearchPage, getWebResearchRuntime, listWebResearchTasks, searchWebResearch, submitWebResearchCandidate } from '../../api/webResearch.ts'

const unwrap = value => value?.data ?? value
const query = ref(''), scope = ref('ALL'), directUrl = ref('')
const results = ref([]), tasks = ref([]), runtime = ref(null), selectedResult = ref(null), page = ref(null)
const searching = ref(false), fetching = ref(false), submittingCandidate = ref(false), error = ref(''), searchErrors = ref([]), searchStatus = ref(''), activeId = ref('query')
const candidate = ref(null)
const evidencePages = ref([]), selectedEvidenceIds = ref([]), comparison = ref(null), comparing = ref(false)
const graph = computed(() => researchGraph(query.value, results.value, runtime.value))

function formatTime(value) { if (!value) return '时间未提供'; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false }) }
function friendlyError(code) { if (code.includes('403') || code.includes('429')) return `${code}：来源服务拒绝或限流，请稍后重试`; if (code.includes('OUTBOUND')) return `${code}：目标未通过公网安全检查`; return `${code}：该来源暂时不可用` }
function selectResult(result) { selectedResult.value = result; page.value = null; candidate.value = null; activeId.value = result.id; error.value = '' }
function selectGraphNode(node) { activeId.value = node.id; if (node.result) selectResult(node.result) }

async function runSearch() {
  if (!query.value.trim() || searching.value) return
  searching.value = true; error.value = ''; searchErrors.value = []; page.value = null; candidate.value = null
  evidencePages.value = []; selectedEvidenceIds.value = []; comparison.value = null
  try {
    const response = unwrap(await searchWebResearch({ query: query.value.trim(), scope: scope.value, limit: 8 }))
    results.value = response.results || []; searchErrors.value = response.errors || []; searchStatus.value = response.status || 'SUCCESS'
    selectedResult.value = results.value[0] || null; activeId.value = selectedResult.value?.id || 'query'
    await refreshTasks()
  } catch (cause) { error.value = cause.message || '联网检索失败'; results.value = []; searchStatus.value = 'FAILED' }
  finally { searching.value = false }
}
async function readUrl(url) {
  if (!url || fetching.value) return
  directUrl.value = url; fetching.value = true; error.value = ''; candidate.value = null
  try {
    const fetched = unwrap(await fetchWebResearchPage({ url }))
    page.value = fetched
    const basket = addEvidencePage(evidencePages.value, selectedEvidenceIds.value, fetched)
    evidencePages.value = basket.pages; selectedEvidenceIds.value = basket.selectedTaskIds; comparison.value = null
    activeId.value = 'query'; await refreshTasks()
  }
  catch (cause) { page.value = null; error.value = cause.message || '网页读取失败' }
  finally { fetching.value = false }
}
function toggleEvidence(taskId) {
  selectedEvidenceIds.value = toggleEvidenceTask(evidencePages.value, selectedEvidenceIds.value, taskId)
  comparison.value = null
}
async function compareEvidence() {
  if (selectedEvidenceIds.value.length < 2 || comparing.value) return
  comparing.value = true; error.value = ''
  try { comparison.value = unwrap(await compareWebResearchEvidence({ taskIds: selectedEvidenceIds.value })) }
  catch (cause) { comparison.value = null; error.value = cause.message || '证据对比失败，请重试' }
  finally { comparing.value = false }
}
async function submitCandidate() {
  if (!page.value?.taskId || submittingCandidate.value) return
  submittingCandidate.value = true; error.value = ''
  try { candidate.value = unwrap(await submitWebResearchCandidate(page.value.taskId)) }
  catch (cause) { error.value = cause.message || '候选提交失败，请重试' }
  finally { submittingCandidate.value = false }
}
async function refreshRuntime() { try { runtime.value = unwrap(await getWebResearchRuntime()) } catch (cause) { runtime.value = { available: false, model: 'Ollama', detail: cause.message || '运行时状态读取失败' } } }
async function refreshTasks() { try { tasks.value = unwrap(await listWebResearchTasks(12)) || [] } catch { /* 主任务结果优先，任务账本失败不覆盖检索结果 */ } }
onMounted(() => { refreshRuntime(); refreshTasks() })
</script>

<style scoped>
.research-page{max-width:1440px;margin:0 auto;color:var(--smart-text)}.research-header{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding:46px 0 26px;border-bottom:1px solid var(--smart-border)}.eyebrow{margin:0 0 10px;color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.13em}.research-header h1{margin:0 0 8px;font-size:clamp(30px,4vw,42px);font-weight:400}.subtitle{margin:0;color:var(--smart-muted);font-size:13px}.runtime-pill{display:grid;grid-template-columns:8px auto;gap:2px 8px;align-items:center;min-width:190px;padding:12px 14px;border:1px solid var(--smart-border);background:var(--smart-surface);color:var(--smart-muted);text-align:left}.runtime-pill i{grid-row:1/3;width:7px;height:7px;border-radius:50%;background:var(--smart-danger)}.runtime-pill.online i{background:var(--smart-success,#64b99a)}.runtime-pill small{font:9px var(--font-mono);color:var(--smart-muted)}.research-console{margin-top:24px}.search-form{display:grid;grid-template-columns:minmax(0,1fr) 180px 132px;gap:12px;align-items:end}.search-form label,.fetch-form label{display:grid;gap:7px}.search-form label span,.fetch-form label span{color:var(--smart-muted);font:10px var(--font-mono);letter-spacing:.08em}input,select{width:100%;min-height:46px;padding:11px 13px;border:1px solid var(--smart-border);border-radius:0;background:color-mix(in srgb,var(--smart-surface) 80%,transparent);color:var(--smart-text);outline:none}input:focus,select:focus{border-color:var(--smart-primary-strong);box-shadow:0 0 0 1px var(--smart-primary-strong)}button{min-height:42px;padding:9px 13px;border:1px solid var(--smart-border);background:var(--smart-surface);color:var(--smart-text)}button:disabled{opacity:.5;cursor:wait}.primary-action{border-color:var(--smart-primary-strong);background:var(--smart-primary-strong);color:var(--smart-bg);font-weight:600}.primary-action.full{width:100%;margin-top:16px}.fetch-form{display:grid;grid-template-columns:minmax(0,1fr) 110px;gap:12px;align-items:end;margin:16px 0 20px}.fetch-form p{grid-column:1/-1;margin:0;color:var(--smart-muted);font-size:10px}.message{padding:11px 13px;margin:0 0 14px;font-size:12px}.message.error{border-left:2px solid var(--smart-danger);color:var(--smart-danger);background:color-mix(in srgb,var(--smart-danger) 6%,transparent)}.message.warning{display:grid;gap:3px;border-left:2px solid var(--smart-warning,#d9a84e);color:var(--smart-warning,#d9a84e);background:color-mix(in srgb,var(--smart-warning,#d9a84e) 6%,transparent)}.console-caption{display:flex;justify-content:space-between;gap:12px;padding:10px 2px;color:var(--smart-muted);font:9px var(--font-mono)}.research-layout{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(280px,.75fr);gap:28px;margin-top:30px}.section-heading{display:flex;justify-content:space-between;align-items:end;gap:12px;margin-bottom:14px}.section-heading h2{margin:0;font-size:19px;font-weight:400}.section-heading>span{color:var(--smart-muted);font:9px var(--font-mono)}.result-card{display:grid;grid-template-columns:minmax(0,1fr) 96px;border-top:1px solid var(--smart-border);transition:background .18s,border-color .18s}.result-card.selected{background:color-mix(in srgb,var(--smart-primary-strong) 5%,transparent);border-top-color:var(--smart-primary-strong)}.result-main{min-width:0;padding:18px 14px 18px 0;border:0;background:transparent;text-align:left}.result-main h3{margin:7px 0;font-size:16px;font-weight:500;overflow-wrap:anywhere}.result-main p{margin:0 0 9px;color:var(--smart-muted);font-size:12px;line-height:1.7;overflow-wrap:anywhere}.result-main small{color:var(--smart-muted);font:9px var(--font-mono)}.result-kind{color:var(--smart-primary-strong);font:9px var(--font-mono);letter-spacing:.1em}.result-actions{display:grid;align-content:center;gap:7px}.result-actions a,.result-actions button{padding:6px 8px;border:0;background:transparent;color:var(--smart-primary-strong);font-size:11px;text-align:right}.empty-state{padding:42px 20px;border:1px dashed var(--smart-border);text-align:center;color:var(--smart-muted)}.empty-state b{color:var(--smart-text);font-weight:400}.empty-state p{margin:8px auto 0;max-width:420px;font-size:12px}.empty-state.compact{padding:28px 16px}.result-skeleton{display:grid;gap:10px}.result-skeleton i{display:block;height:112px;background:linear-gradient(100deg,var(--smart-surface),color-mix(in srgb,var(--smart-primary-strong) 8%,var(--smart-surface)),var(--smart-surface));background-size:220% 100%;animation:skeleton 1.4s ease infinite}.task-section{margin-top:34px}.task-list{border-top:1px solid var(--smart-border)}.task-list article{display:grid;grid-template-columns:64px minmax(0,1fr);gap:10px;padding:11px 0;border-bottom:1px solid var(--smart-border)}.task-list b{display:block;font-size:12px;font-weight:400;overflow-wrap:anywhere}.task-list small{color:var(--smart-muted);font:9px var(--font-mono)}.task-list code{grid-column:2;color:var(--smart-danger);font-size:9px;overflow-wrap:anywhere}.task-status{font:9px var(--font-mono);color:var(--smart-primary-strong)}.task-status.failed{color:var(--smart-danger)}.task-status.partial{color:var(--smart-warning,#d9a84e)}.text-button{min-height:28px;padding:3px 7px;border:0;background:none;color:var(--smart-primary-strong);font-size:11px}.evidence-column{min-width:0}.source-evidence,.page-evidence,.runtime-detail{padding:18px;border-left:1px solid var(--smart-border);background:color-mix(in srgb,var(--smart-surface) 56%,transparent)}.evidence-label{color:var(--smart-primary-strong);font:9px var(--font-mono)}.source-evidence h3,.page-evidence h3{margin:9px 0;font-size:17px;font-weight:400;overflow-wrap:anywhere}.source-evidence>p{color:var(--smart-muted);font-size:12px;line-height:1.7}dl{margin:18px 0}dl>div{padding:10px 0;border-top:1px solid var(--smart-border)}dt{margin-bottom:5px;color:var(--smart-muted);font:9px var(--font-mono)}dd{margin:0;font-size:11px;overflow-wrap:anywhere}dd a{color:var(--smart-primary-strong)}dd code{font-size:9px}.evidence-note{padding-left:10px;border-left:2px solid var(--smart-warning,#d9a84e)}.candidate-gate{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 14px;align-items:center;margin:0 0 16px;padding:14px 0;border-top:1px solid var(--smart-border);border-bottom:1px solid var(--smart-border)}.candidate-gate b{font-size:12px;font-weight:500}.candidate-gate p{margin:5px 0 0;color:var(--smart-muted);font-size:10px;line-height:1.6}.candidate-gate button{border-color:var(--smart-primary-strong);color:var(--smart-primary-strong);font-size:11px}.candidate-gate a{grid-column:1/-1;color:var(--smart-primary-strong);font-size:11px}.page-evidence pre{max-height:480px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--smart-muted);font:11px/1.75 var(--font-mono)}.runtime-detail{margin-top:22px}.runtime-detail>span{color:var(--smart-primary-strong);font:9px var(--font-mono)}.runtime-detail b{display:block;margin:9px 0;font-weight:400}.runtime-detail p,.runtime-detail small,.muted{color:var(--smart-muted);font-size:11px;line-height:1.7}@keyframes skeleton{to{background-position:-220% 0}}@media(max-width:980px){.research-layout{grid-template-columns:1fr}.evidence-column{display:grid;grid-template-columns:1fr 1fr;gap:18px}.evidence-column>.section-heading{grid-column:1/-1}.runtime-detail{margin-top:0}}@media(max-width:720px){.research-header{align-items:flex-start;flex-direction:column;padding-top:30px}.runtime-pill{width:100%}.search-form{grid-template-columns:1fr}.fetch-form{grid-template-columns:1fr}.fetch-form button{width:100%}.research-layout{gap:20px}.evidence-column{display:block}.runtime-detail{margin-top:18px}.console-caption{flex-direction:column}.result-card{grid-template-columns:minmax(0,1fr) 76px}}@media(max-width:520px){.candidate-gate{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){.result-skeleton i{animation:none}}
</style>
