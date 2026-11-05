<template>
  <article class="knowledge-space">
    <header class="knowledge-hero">
      <p class="editorial-label">02 / PERSONAL SYSTEM <span>个人系统</span></p>
      <div class="knowledge-rule" aria-hidden="true"></div>
      <div class="hero-row">
        <div>
          <h1><span class="title-cn">运维知识库</span><span class="title-en">KNOWLEDGE / CENTER</span></h1>
          <p class="hero-copy">以本地知识为先，按错误、服务、平台和风险快速找到可引用的排查依据。</p>
        </div>
        <div class="index-signal" aria-label="Knowledge index status">
          <span class="signal-dot" aria-hidden="true"></span>
          <strong>LOCAL INDEX</strong>
          <small>{{ totalEntries }} 条内置资料 / 使用前核验</small>
        </div>
      </div>
    </header>

    <nav class="knowledge-zone-tabs" aria-label="Knowledge zones">
      <RouterLink class="knowledge-zone-tab active" to="/knowledge">系统知识库</RouterLink>
      <RouterLink class="knowledge-zone-tab" to="/knowledge/personal">我的知识库</RouterLink>
      <RouterLink class="knowledge-zone-tab" to="/knowledge/quiz">题库</RouterLink>
    </nav>
    <section class="knowledge-toolbar" aria-label="Knowledge search">
      <div class="search-wrap">
        <label for="knowledge-query">SEARCH OPERATIONS KNOWLEDGE</label>
        <div class="search-line">
          <input id="knowledge-query" v-model="filters.query" type="search" placeholder="502 nginx / MySQL timeout / disk full" @keyup.enter="runSearch" />
          <button type="button" class="search-button" @click="runSearch">SEARCH</button>
        </div>
      </div>
      <div class="filter-wrap">
        <label for="knowledge-domain">DOMAIN</label>
        <select id="knowledge-domain" v-model="filters.domain" @change="runSearch">
          <option value="">ALL DOMAINS</option>
          <option v-for="domain in knowledgeDomains" :key="domain.id" :value="domain.id">{{ domain.label }}</option>
        </select>
      </div>
      <div class="filter-wrap">
        <label for="knowledge-platform">PLATFORM</label>
        <select id="knowledge-platform" v-model="filters.platform" @change="runSearch">
          <option value="">ALL PLATFORMS</option>
          <option v-for="platform in platforms" :key="platform" :value="platform">{{ platform }}</option>
        </select>
      </div>
    </section>

    <aside v-if="route.query.source === 'cloud-native'" class="knowledge-context">
      <strong>{{ cloudEnvironments[cloudIntent.environment] }} · 知识参考，不代表目标已验证</strong>
      <p>Context：{{ cloudIntent.cluster || '未指定' }} / Namespace：{{ cloudIntent.namespace || '未指定' }}</p>
      <RouterLink :to="{ path: '/cloud-native', query: cloudContextQuery(cloudIntent) }">返回云原生工作台</RouterLink>
    </aside>
    <KnowledgeCrawlPanel />
    <section class="knowledge-layout">
      <button class="knowledge-tree-toggle" type="button" :aria-expanded="mobileTreeOpen" @click="mobileTreeOpen = !mobileTreeOpen">
        <span>知识分类</span><small>{{ mobileTreeOpen ? '收起' : '展开' }}</small>
      </button>
      <aside class="domain-index" :class="{ 'domain-index--open': mobileTreeOpen }" aria-label="Knowledge domains">
        <ul class="knowledge-tree" aria-label="Nested knowledge tree">
          <KnowledgeTreeNode :node="knowledgeTree" :expanded-nodes="expandedNodes" :selected-id="selectedId" @select="selectTreeEntry" />
        </ul>
        <p class="editorial-label">KNOWLEDGE PACKS <span>知识包</span></p>
        <button v-for="(domain, index) in knowledgeDomains" :key="domain.id" type="button" :class="['domain-row', { active: filters.domain === domain.id }]" @click="selectDomain(domain.id)">
          <span class="domain-number">{{ String(index + 1).padStart(2, '0') }}</span>
          <span><strong>{{ domain.label }}</strong><small>{{ domain.detail }}</small></span>
          <span class="domain-arrow" aria-hidden="true">↗</span>
        </button>
        <div class="source-note"><span>INDEX SOURCE</span><strong>BUILT-IN + LOCAL</strong><p>搜索结果保留来源与章节。外部浏览器搜索不会自动触发。</p></div>
      </aside>

      <div class="knowledge-main-column">
      <div class="results-panel">
        <div class="results-heading"><div><p class="editorial-label">SEARCH RESULTS <span>检索结果</span></p><h2>{{ results.length }} <span>REFERENCES</span></h2></div><span class="result-state">{{ searched ? 'FILTERED' : 'CURATED' }} / OFFLINE READY</span></div>
        <div v-if="results.length" class="result-list">
          <article v-for="entry in visibleResults" :key="entry.id" class="result-row result-row--interactive" :class="{ selected: selectedId === entry.id }" role="button" tabindex="0" @click="openEntry(entry.id)" @keydown.enter="openEntry(entry.id)">
            <div class="result-topline"><span class="result-type">{{ entry.type }}</span><span class="result-risk">{{ entry.risk }}</span><span class="result-verified">未人工核验</span></div>
            <div class="result-head">
              <h3>{{ entry.title }}</h3>
              <button type="button" class="markdown-open" @click.stop="openMarkdown(entry)">详细笔记 ↗</button>
            </div>
            <p class="result-summary">{{ entry.summary }}</p>
            <p v-if="entry.matchReason" class="knowledge-match">{{ entry.matchReason }}</p>
            <div class="result-meta"><span>{{ entry.platform }} / {{ entry.service }}</span><span>{{ entry.section }} / {{ entry.version }}</span><span class="result-source" :title="entry.source">{{ entry.source }}</span></div>
          </article>
        </div>
        <div v-else class="empty-results"><strong>NO LOCAL MATCH</strong><p>换一个错误码、服务或平台关键词。知识库搜索不会调用 AI，也不会执行任何命令。</p></div>
        <nav v-if="resultPages > 1" class="knowledge-pagination" aria-label="知识结果分页"><button type="button" :disabled="resultPage <= 1" @click="resultPage--">上一页资料</button><span>第 {{ resultPage }} / {{ resultPages }} 页 · 每页 30 条</span><button type="button" :disabled="resultPage >= resultPages" @click="resultPage++">下一页资料</button></nav>
      </div>
      <section v-if="selectedView" class="knowledge-detail" aria-label="Knowledge detail">
    <nav class="knowledge-breadcrumb" aria-label="Knowledge path">
      <span v-for="(node, index) in selectedPath" :key="node.id">{{ index ? ' / ' : '' }}{{ node.label }}</span>
    </nav>
    <header class="knowledge-detail__header">
      <div><p class="editorial-label">KNOWLEDGE DETAIL <span>资料详情</span></p><h3>{{ selectedView.current.title }}</h3></div>
      <button type="button" class="detail-close" @click="closeEntry">返回列表</button>
    </header>
    <div class="knowledge-detail__meta"><span>{{ selectedView.current.type }}</span><span>{{ selectedView.current.platform }} / {{ selectedView.current.service }}</span><span>{{ selectedView.current.section }} / {{ selectedView.current.version }}</span><span>{{ selectedView.current.risk }}</span></div>
    <p class="knowledge-detail__summary">{{ selectedView.current.summary }}</p>
    <p class="knowledge-verification">内置参考资料，未人工核验。资料版本不等于适用组件版本；执行前核对目标环境。</p>
    <div class="knowledge-detail__body">{{ selectedView.current.content || selectedView.current.summary }}</div>
    <RouterLink v-if="selectedView.current.relatedTool" class="knowledge-detail__tool-link" :to="{ path: `/tools/${selectedView.current.relatedTool}`, query: { knowledge: selectedView.current.id } }">打开进程诊断工具</RouterLink>
    <div class="knowledge-detail__footer">
      <button type="button" :disabled="!selectedView.previous" @click="openEntry(selectedView.previous?.id)">上一条资料</button>
      <span>{{ selectedView.current.source }}</span>
      <button type="button" :disabled="!selectedView.next" @click="openEntry(selectedView.next?.id)">下一条资料</button>
    </div>
      </section>
      </div>
    </section>
    <Teleport to="body">
      <div v-if="markdownEntry" class="markdown-modal" role="dialog" aria-modal="true" aria-label="资料 Markdown 详情" @click.self="closeMarkdown">
        <article class="markdown-modal__panel">
          <header class="markdown-modal__header"><div><p class="editorial-label">KNOWLEDGE NOTE <span>详细运维笔记</span></p><h2>{{ markdownEntry.title }}</h2><p>{{ markdownEntry.source }} / {{ markdownEntry.version }}</p></div><button type="button" class="markdown-modal__close" aria-label="关闭资料详情" @click="closeMarkdown">×</button></header>
          <div class="markdown-modal__meta"><span>{{ markdownEntry.type }}</span><span>{{ markdownEntry.platform }} / {{ markdownEntry.service }}</span><span>{{ markdownEntry.risk }}</span></div>
          <div class="markdown-body" v-html="renderedMarkdown"></div>
        </article>
      </div>
    </Teleport>
  </article>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { getKnowledgePath, knowledgeDomains, knowledgeTree, searchKnowledgeEntries } from './knowledgeCatalog.js'
import { knowledgeEntryView } from './knowledgeLibrary.js'
import KnowledgeTreeNode from './KnowledgeTreeNode.vue'
import KnowledgeCrawlPanel from '../../components/knowledge/KnowledgeCrawlPanel.vue'
import { readCloudContext, cloudContextQuery, cloudEnvironments } from '../cloud/cloudContext.js'

const filters = reactive({ query: '', domain: '', platform: '' })
const route = useRoute()
const cloudIntent = computed(() => readCloudContext(route.query))
const searched = ref(false)
const results = ref(searchKnowledgeEntries())
const totalEntries = searchKnowledgeEntries().length
const resultPage = ref(1)
const resultPages = computed(() => Math.max(1, Math.ceil(results.value.length / 30)))
const visibleResults = computed(() => results.value.slice((resultPage.value - 1) * 30, resultPage.value * 30))
const selectedId = ref(typeof route.query.entry === 'string' ? route.query.entry : null)
const markdownEntry = ref(null)
const expandedNodes = reactive(new Set(['knowledge-root']))
/* 移动端默认收起知识分类，避免把检索结果压到很下面。 */
const mobileTreeOpen = ref(false)
const platforms = computed(() => [...new Set(searchKnowledgeEntries().map(entry => entry.platform))])
const selectedView = computed(() => selectedId.value ? knowledgeEntryView(selectedId.value, results.value) : null)
const selectedPath = computed(() => selectedId.value ? getKnowledgePath(selectedId.value) : [])
const renderedMarkdown = computed(() => markdownEntry.value ? renderMarkdown(buildDetailedNote(markdownEntry.value)) : '')

function applyRouteFilters(query) {
  filters.query = typeof query.query === 'string' ? query.query.replace(/\+/g, ' ') : ''
  filters.domain = typeof query.domain === 'string' ? query.domain : ''
  filters.platform = typeof query.platform === 'string' ? query.platform : ''
  runSearch()
}

watch(() => route.query.entry, entry => {
  selectedId.value = typeof entry === 'string' ? entry : null
})

watch(() => route.query, query => applyRouteFilters(query), { immediate: true })

function runSearch() {
  resultPage.value = 1
  searched.value = true
  results.value = searchKnowledgeEntries(filters)
  if (selectedId.value && !results.value.some(entry => entry.id === selectedId.value)) selectedId.value = null
}

function selectDomain(domain) {
  filters.domain = filters.domain === domain ? '' : domain
  runSearch()
}

function selectTreeEntry(entry) {
  if (entry.kind === 'entry') openEntry(entry.id)
}

function openEntry(entryId) {
  if (entryId) selectedId.value = entryId
}

function closeEntry() {
  selectedId.value = null
}

function openMarkdown(entry) { markdownEntry.value = entry }
function closeMarkdown() { markdownEntry.value = null }

function buildDetailedNote(entry) {
  const content = String(entry.content || entry.summary || '').trim()
  const sentences = content.split(/[。；;\n]+/).map(item => item.trim()).filter(Boolean)
  const commandPattern = /(?:kubectl|docker|ctr|crictl|systemctl|journalctl|curl|wget|ping|traceroute|tracepath|dig|nslookup|ss|netstat|ip|iptables|ipvsadm|df|du|free|top|ps|iostat|vmstat|sar|grep|sed|awk|mysql|redis-cli|nginx|openssl|chmod|chown|find|ls|cat)\b[^，。；;\n]*/gi
  const commands = [...new Set((content.match(commandPattern) || []).map(command => command.trim()))]
  const causeLines = sentences.filter(item => /(原因|导致|包括|可能|不匹配|失败|异常|压力|耗尽|超时|拒绝|错误)/.test(item))
  const checkLines = sentences.filter(item => /(检查|确认|查看|收集|比较|结合|定位|判断|区分)/.test(item))
  const verifyLines = sentences.filter(item => /(验证|恢复|成功|Ready|健康|真实请求|错误率|延迟)/i.test(item))
  const riskLines = sentences.filter(item => /(不要|禁止|风险|确认|审批|回滚|避免|不能|不得)/.test(item))
  const asList = items => items.length ? items.map(item => `- ${item}。`).join('\n') : '- 当前资料暂未记录。'
  const steps = checkLines.length ? checkLines.map((item, index) => `${index + 1}. ${item}。`).join('\n') : '1. 当前资料暂未记录详细操作步骤。'
  const commandBlocks = commands.length ? commands.map((command, index) => `### 指令 ${index + 1}\n\n\`\`\`bash\n${command}\n\`\`\`\n\n- 风险等级：${entry.risk || '未标注'}\n- 执行说明：请结合目标环境补齐参数，执行前核对命令作用范围。`).join('\n\n') : '- 当前资料没有可直接提取的操作指令。'
  return `# ${entry.title}\n\n## 一、知识概述\n\n${entry.summary || '当前资料暂未记录摘要。'}\n\n## 二、适用场景与环境\n\n- 平台：${entry.platform || '未标注'}\n- 服务或组件：${entry.service || '未标注'}\n- 资料类型：${entry.type || '未标注'}\n- 适用版本：${entry.version || '未标注'}\n- 标签：${(entry.tags || []).join('、') || '未标注'}\n\n## 三、故障现象与观察重点\n\n${asList(checkLines)}\n\n## 四、常见报错原因\n\n${asList(causeLines)}\n\n> 以上原因仅来自当前资料正文。没有证据时应作为待验证方向，不能直接认定为根因。\n\n## 五、操作前检查\n\n${asList(checkLines)}\n\n## 六、操作指令\n\n${commandBlocks}\n\n## 七、详细操作步骤\n\n${steps}\n\n## 八、结果验证\n\n${asList(verifyLines)}\n\n## 九、风险与注意事项\n\n- 资料风险标记：${entry.risk || '未标注'}\n${asList(riskLines)}\n\n## 十、原始笔记\n\n${content || '当前资料暂未记录正文。'}\n\n## 十一、资料来源\n\n- 来源：${entry.source || '未标注'}\n- 章节：${entry.section || '未标注'}\n- 版本：${entry.version || '未标注'}\n`
}

function renderMarkdown(source) {
  const escapeHtml = value => String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]))
  const inline = value => escapeHtml(value).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/\*([^*]+)\*/g, '<em>$1</em>')
  const output = []
  let listType = null
  let inCode = false
  let codeLanguage = 'text'
  let codeLines = []
  const closeList = () => { if (listType) { output.push(`</${listType}>`); listType = null } }
  for (const line of String(source || '').replace(/\r\n?/g, '\n').split('\n')) {
    if (line.trim().startsWith('```')) {
      if (inCode) { output.push(`<pre><code class="language-${escapeHtml(codeLanguage)}">${escapeHtml(codeLines.join('\n'))}</code></pre>`); inCode = false; codeLines = [] } else { closeList(); inCode = true; codeLanguage = line.trim().slice(3).trim() || 'text' }
      continue
    }
    if (inCode) { codeLines.push(line); continue }
    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    const item = line.match(/^\s*([-*+]\s+|\d+[.)]\s+)(.+)$/)
    if (heading) { closeList(); const level = heading[1].length; output.push(`<h${level}>${inline(heading[2])}</h${level}>`) }
    else if (item) { const type = /^\d/.test(item[1]) ? 'ol' : 'ul'; if (listType !== type) { closeList(); output.push(`<${type}>`); listType = type } output.push(`<li>${inline(item[2])}</li>`) }
    else if (!line.trim()) closeList()
    else { closeList(); output.push(`<p>${inline(line)}</p>`) }
  }
  if (inCode) output.push(`<pre><code class="language-${escapeHtml(codeLanguage)}">${escapeHtml(codeLines.join('\n'))}</code></pre>`)
  closeList()
  return output.join('')
}
</script>

<style scoped>
.knowledge-zone-tabs{display:flex;gap:8px;padding:18px 0 0;border-bottom:1px solid var(--smart-border)}.knowledge-zone-tab{padding:10px 14px;color:var(--smart-muted);text-decoration:none;border-bottom:2px solid transparent;font:12px var(--font-cn)}.knowledge-zone-tab:hover,.knowledge-zone-tab.active{color:var(--smart-primary-strong);border-color:var(--smart-primary-strong)}
.knowledge-context{padding:16px;margin:18px 0;border:1px solid var(--smart-border-strong);background:var(--smart-surface);color:var(--smart-text);overflow-wrap:anywhere}.knowledge-context p{color:var(--smart-muted)}.knowledge-context a{color:var(--smart-primary-strong)}.knowledge-pagination{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;padding:16px;color:var(--smart-muted);font-size:12px}.knowledge-pagination button{min-height:44px;border:1px solid var(--smart-border-strong);background:var(--smart-surface);color:var(--smart-text);padding:8px 12px;cursor:pointer}.knowledge-pagination button:disabled{opacity:.55;cursor:not-allowed}.knowledge-pagination button:focus-visible{outline:2px solid var(--smart-primary-strong);outline-offset:3px}
.knowledge-match{color:var(--smart-primary-strong)!important;font-size:12px}.knowledge-verification{display:block;color:var(--smart-muted);line-height:1.7;margin:8px 0}
.knowledge-space { position: relative; isolation: isolate; padding-bottom: 0; }
/* 用静态渐变替代 WebGL 着色器背景：保留氛围，去掉每帧绘制的 GPU 开销。 */
.knowledge-space::before { content: ''; position: fixed; z-index: 0; inset: 0; opacity: .5; pointer-events: none; background: radial-gradient(circle at 70% 18%, rgba(51, 204, 188, .2), transparent 34%), radial-gradient(circle at 24% 76%, rgba(40, 118, 206, .18), transparent 38%); }
:global([data-theme='light']) .knowledge-space::before { opacity: .34; background: radial-gradient(circle at 70% 18%, rgba(40, 162, 151, .16), transparent 34%), radial-gradient(circle at 24% 76%, rgba(42, 112, 190, .12), transparent 38%); }
.knowledge-space > * { position: relative; z-index: 1; }
.knowledge-breadcrumb { margin: 0 0 18px; color: var(--smart-muted); font: 10px/1.6 var(--font-mono); overflow-wrap: anywhere; }
.knowledge-hero { padding: 64px 0 48px; border-bottom: 1px solid var(--smart-border); }
.editorial-label { margin: 0 0 16px; color: var(--smart-primary-strong); font: var(--label-size) var(--font-mono); letter-spacing: .13em; }
.editorial-label span { margin-left: 10px; color: var(--smart-muted); font-family: var(--font-cn); letter-spacing: 0; }
.knowledge-rule { width: min(100%, 620px); margin-bottom: 24px; border-top: 1px solid var(--smart-border); }
.hero-row { display: flex; align-items: end; justify-content: space-between; gap: 36px; }
h1 { display: grid; gap: 14px; margin: 0; font-family: var(--font-display); font-weight: 400; }
.title-cn { color: var(--smart-text); font-family: var(--font-cn); font-size: clamp(2.35rem, 5vw, 4.5rem); line-height: 1.06; }
.title-en { color: var(--smart-primary-strong); font: 400 clamp(1.25rem, 2.4vw, 2.2rem)/1.1 var(--font-mono); letter-spacing: .08em; }
.hero-copy { max-width: 480px; margin: 24px 0 0; color: var(--smart-muted); font-family: var(--font-cn); line-height: 1.8; }
.index-signal { display: grid; gap: 7px; min-width: 150px; padding: 14px 0 4px 20px; border-left: 1px solid var(--smart-border); }
.index-signal strong, .index-signal small { font: 10px var(--font-mono); letter-spacing: .1em; }.index-signal strong { color: var(--smart-text); }.index-signal small { color: var(--smart-muted); }
.signal-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--smart-primary-strong); box-shadow: 0 0 0 5px var(--smart-primary-soft); }
.knowledge-toolbar { display: grid; grid-template-columns: minmax(0, 1fr) 170px 170px; gap: 20px; align-items: end; padding: 28px 0; border-bottom: 1px solid var(--smart-border); }
.knowledge-toolbar label, .filter-wrap label { display: block; margin-bottom: 9px; color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .12em; }
.search-line { display: flex; gap: 10px; }.search-line input, select { width: 100%; min-height: 40px; border: 1px solid var(--smart-border-strong); border-radius: 0; background: var(--smart-surface); color: var(--smart-text); font: 12px var(--font-mono); outline: none; }
.search-line input { padding: 0 13px; }.search-line input:focus, select:focus { border-color: var(--smart-primary-strong); }.search-line input::placeholder { color: var(--smart-muted); }
select { padding: 0 9px; }.search-button { min-width: 92px; border: 1px solid var(--smart-primary-strong); background: var(--smart-primary-strong); color: var(--smart-accent-foreground); font: 10px var(--font-mono); letter-spacing: .08em; cursor: pointer; }
.knowledge-layout { display: grid; grid-template-columns: minmax(250px, 300px) minmax(0, 1fr); gap: clamp(28px, 4vw, 48px); align-items: start; min-height: 0; padding-top: 40px; }
.domain-index, .knowledge-main-column { min-height: 0; }
.domain-index { padding-right: clamp(20px, 2vw, 28px); border-right: 1px solid var(--smart-border); }.knowledge-tree { margin: 0; padding: 0; }.domain-index > .domain-row { display: none; }.domain-row { display: grid; grid-template-columns: 28px minmax(0, 1fr) 16px; gap: 12px; width: 100%; padding: 14px 0; border: 0; border-top: 1px solid var(--smart-border); background: transparent; color: var(--smart-muted); text-align: left; cursor: pointer; }.domain-row:last-of-type { border-bottom: 1px solid var(--smart-border); }.domain-row:hover, .domain-row.active { color: var(--smart-primary-strong); }.domain-number, .domain-arrow { font: 10px var(--font-mono); }.domain-row strong, .domain-row small { display: block; }.domain-row strong { font: 12px var(--font-mono); letter-spacing: .08em; }.domain-row small { margin-top: 4px; font: 12px var(--font-cn); color: var(--smart-muted); }.domain-arrow { justify-self: end; }.source-note { margin-top: 30px; padding-top: 16px; border-top: 1px solid var(--smart-border); }.source-note span, .source-note strong { display: block; font: 9px var(--font-mono); letter-spacing: .1em; }.source-note span { color: var(--smart-muted); }.source-note strong { margin-top: 8px; color: var(--smart-primary-strong); }.source-note p { max-width: 230px; color: var(--smart-muted); font: 12px/1.7 var(--font-cn); }
.knowledge-tree :deep(.knowledge-tree-node__button) { min-height: 28px; padding: 5px 0; }
/* 移动端分类开关：桌面/平板宽度不显示（目录本身常驻）。 */
.knowledge-tree-toggle { display: none; align-items: center; justify-content: space-between; width: 100%; min-height: 44px; padding: 0 14px; border: 1px solid var(--smart-border-strong); background: var(--smart-surface); color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .06em; cursor: pointer; }
.knowledge-tree-toggle small { color: var(--smart-muted); font: 10px var(--font-mono); }
.knowledge-main-column { padding-right: 0; }
.results-heading { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin-bottom: 18px; }.results-heading .editorial-label { margin-bottom: 8px; }.results-heading h2 { margin: 0; color: var(--smart-text); font: 400 28px var(--font-mono); }.results-heading h2 span { color: var(--smart-muted); font-size: 11px; letter-spacing: .1em; }.result-state { color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .08em; }
.result-row { padding: 20px 0 22px; border-top: 1px solid var(--smart-border); }.result-row:last-child { border-bottom: 1px solid var(--smart-border); }.result-topline, .result-meta { display: flex; flex-wrap: wrap; gap: 8px 16px; }.result-type, .result-risk, .result-meta, .result-verified { color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .08em; }.result-risk { color: var(--smart-primary-strong); }.result-verified { margin-left: auto; }.result-head { display: flex; align-items: start; justify-content: space-between; gap: 18px; margin: 10px 0 9px; }.result-head h3 { flex: 1; min-width: 0; }.result-row h3 { margin: 0; color: var(--smart-text); font: 400 17px/1.45 var(--font-cn); }.result-row p { max-width: 680px; margin: 0 0 13px; color: var(--smart-muted); font: 13px/1.7 var(--font-cn); }.result-summary { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }.result-meta { padding-top: 10px; border-top: 1px dashed var(--smart-border); }.result-source { flex-basis: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.empty-results { padding: 46px 0; border-top: 1px solid var(--smart-border); border-bottom: 1px solid var(--smart-border); }.empty-results strong { color: var(--smart-text); font: 11px var(--font-mono); letter-spacing: .1em; }.empty-results p { max-width: 430px; color: var(--smart-muted); font: 13px/1.7 var(--font-cn); }
.result-row--interactive { cursor: pointer; }.result-row--interactive:hover, .result-row--interactive:focus-visible, .result-row--interactive.selected { box-shadow: inset 2px 0 0 var(--smart-primary-strong); background: color-mix(in srgb, var(--smart-primary-strong) 5%, transparent); outline: none; }.knowledge-detail { margin-top: 28px; padding: 24px 0 0; border-top: 1px solid var(--smart-primary-strong); }.knowledge-detail__header { display: flex; align-items: start; justify-content: space-between; gap: 20px; }.knowledge-detail__header .editorial-label { margin-bottom: 8px; }.knowledge-detail__header h3 { margin: 0; color: var(--smart-text); font: 400 26px var(--font-cn); }.detail-close, .knowledge-detail__footer button { border: 1px solid var(--smart-border-strong); background: transparent; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .06em; cursor: pointer; }.detail-close { min-height: 34px; padding: 0 12px; }.knowledge-detail__meta { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0; color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .08em; }.knowledge-detail__meta span:last-child { color: var(--smart-primary-strong); }.knowledge-detail__summary { max-width: 760px; margin: 0 0 18px; color: var(--smart-text); font: 15px/1.8 var(--font-cn); }.knowledge-detail__body { padding: 18px 0; border-top: 1px solid var(--smart-border); border-bottom: 1px solid var(--smart-border); color: var(--smart-muted); font: 14px/1.9 var(--font-cn); white-space: pre-wrap; }.knowledge-detail__footer { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 14px; padding-top: 18px; color: var(--smart-muted); font: 10px var(--font-mono); }.knowledge-detail__footer button { min-height: 34px; padding: 0 12px; }.knowledge-detail__footer button:disabled { opacity: .35; cursor: default; }
/* 桌面端双栏：页面自然滚动，两栏不再各自限高，避免出现嵌套滚动条。 */
@media (min-width: 1024px) {
  .knowledge-main-column { padding-right: 4px; }
  /* 左栏目录吸顶：结果列表很长时分类导航仍在视野内；树展开超出视口时才在栏内滚动。
     72 = 吸顶顶栏 56 + 16 间距；底边预留 32 避免贴边。 */
  .domain-index { position: sticky; top: 72px; max-height: calc(100dvh - 104px); overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--smart-border) transparent; }
}
/* 768–1023：固定侧栏占位后内容区不足两栏阅读宽度，退回单列并保留知识目录。 */
@media (min-width: 768px) and (max-width: 1023px) {
  .knowledge-layout { grid-template-columns: minmax(0, 1fr); gap: 32px; padding-top: 32px; }
  .domain-index { padding-right: 0; border-right: 0; padding-bottom: 22px; border-bottom: 1px solid var(--smart-border); }
  .knowledge-main-column { padding-right: 0; }
  .knowledge-toolbar { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .results-heading { align-items: start; flex-direction: column; gap: 10px; }
}
@media (max-width: 767px) { .knowledge-hero { padding: 18px 0 20px; }.knowledge-hero .editorial-label, .knowledge-rule, .title-en, .hero-copy, .index-signal { display: none; }.knowledge-hero h1 { font-size: 30px; }.hero-row { display: grid; gap: 20px; }.knowledge-toolbar { grid-template-columns: 1fr 1fr; gap: 12px 14px; }.search-wrap { grid-column: 1 / -1; }.search-line { display: grid; grid-template-columns: 1fr auto; }.knowledge-space :deep(.knowledge-crawl) { margin: 16px 0; }.knowledge-space :deep(.crawl-note) { display: none; }.knowledge-layout { grid-template-columns: 1fr; gap: 32px; padding-top: 8px; }.knowledge-tree-toggle { display: flex; }.domain-index { display: none; }.domain-index--open { display: block; padding-right: 0; border-right: 0; }.knowledge-main-column { padding-right: 0; }.results-heading { align-items: start; flex-direction: column; gap: 12px; }.result-meta { line-height: 1.7; }.knowledge-detail__header { display: grid; }.knowledge-detail__header h3 { font-size: 21px; }.knowledge-detail__footer { grid-template-columns: 1fr 1fr; }.knowledge-detail__footer span { grid-column: 1 / -1; order: -1; line-height: 1.6; } }
.markdown-open { flex: none; margin: 2px 0 0; padding: 0 0 2px; border: 0; border-bottom: 1px dashed var(--smart-border-strong); background: transparent; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .04em; cursor: pointer; white-space: nowrap; }.markdown-open:hover { border-bottom-style: solid; }.markdown-modal { position: fixed; z-index: 100; inset: 0; display: grid; place-items: center; padding: 24px; background: rgba(2, 8, 12, .78); backdrop-filter: blur(8px); }.markdown-modal__panel { width: min(920px, 100%); max-height: min(84vh, 900px); overflow: auto; padding: 0 34px 38px; border: 1px solid var(--smart-border-strong); background: var(--smart-surface); box-shadow: 0 24px 80px rgba(0, 0, 0, .5); }.markdown-modal__header { position: sticky; z-index: 2; top: 0; display: flex; justify-content: space-between; gap: 24px; margin: 0 -34px; padding: 30px 34px 20px; border-bottom: 1px solid var(--smart-border); background: var(--smart-surface); box-shadow: 0 10px 24px rgba(2, 8, 12, .22); }.markdown-modal__header h2 { margin: 0 0 8px; color: var(--smart-text); font: 400 28px var(--font-cn); }.markdown-modal__header p:last-child { margin: 0; color: var(--smart-muted); font: 10px var(--font-mono); }.markdown-modal__close { position: sticky; top: 30px; flex: 0 0 36px; width: 36px; height: 36px; border: 1px solid var(--smart-border-strong); background: var(--smart-surface); color: var(--smart-text); font: 24px/1 var(--font-mono); cursor: pointer; }.markdown-modal__close:hover, .markdown-modal__close:focus-visible { border-color: var(--smart-primary-strong); color: var(--smart-primary-strong); outline: none; }.markdown-modal__meta { display: flex; flex-wrap: wrap; gap: 12px; padding: 16px 0; color: var(--smart-primary-strong); font: 10px var(--font-mono); }.markdown-body { color: var(--smart-text); font: 14px/1.85 var(--font-cn); }.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { margin: 24px 0 10px; color: var(--smart-text); font-family: var(--font-cn); font-weight: 600; }.markdown-body :deep(p) { margin: 0 0 14px; color: var(--smart-muted); }.markdown-body :deep(ul), .markdown-body :deep(ol) { margin: 0 0 16px; padding-left: 24px; color: var(--smart-muted); }.markdown-body :deep(li) { margin: 5px 0; }.markdown-body :deep(code) { padding: 2px 5px; border: 1px solid var(--smart-border); background: rgba(76, 214, 168, .08); color: var(--smart-primary-strong); font: 12px var(--font-mono); }.markdown-body :deep(pre) { overflow: auto; margin: 16px 0; padding: 16px; border: 1px solid var(--smart-border); background: rgba(0, 0, 0, .24); }.markdown-body :deep(pre code) { padding: 0; border: 0; background: transparent; color: var(--smart-text); white-space: pre; }
</style>
