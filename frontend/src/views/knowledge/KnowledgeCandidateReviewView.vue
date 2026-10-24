<template>
  <section class="review-workbench">
    <header class="page-heading">
      <div><p class="eyebrow">KNOWLEDGE REVIEW</p><h1>知识候选审核</h1><p>核对运行证据、适用环境与结论边界，再进入正式审核流程。</p></div>
      <span class="pending-count">待人工审核 {{ page.total }}</span>
    </header>

    <div v-if="error" class="state error" role="alert"><strong>候选资料暂时无法加载</strong><p>{{ error }}</p><button @click="loadCandidates(page.page)">重新加载</button></div>
    <div v-else class="review-layout">
      <aside class="candidate-list" aria-label="知识候选列表">
        <div v-if="guideMode" class="guide-banner" role="note">
          <strong>当前显示演示数据</strong>
          <span>示例仅用于引导审核流程，不写入数据库，也不计入待审核统计。</span>
        </div>
        <header><div><p class="eyebrow">REVIEW QUEUE</p><h2>审核队列</h2></div><span>{{ page.total }} 条</span></header>
        <p v-if="loading && !page.items.length" class="state">正在读取候选资料…</p>
        <p v-else-if="!page.items.length" class="state">当前没有待审核知识候选。</p>
        <button v-for="item in page.items" :key="item.id" class="candidate-row" :class="{ active: selectedId === item.id }" @click="selectCandidate(item.id)">
          <span><b>{{ item.title }}</b><i>{{ item.isGuide ? '演示数据' : candidateStatusLabel(item.status) }}</i></span>
          <p>{{ item.summary }}</p><code>{{ item.traceId }}</code><time>{{ formatTime(item.createdAt) }}</time>
        </button>
        <footer v-if="page.total > page.pageSize"><button :disabled="page.page <= 1" @click="loadCandidates(page.page - 1)">上一页</button><span>{{ page.page }} / {{ totalPages }}</span><button :disabled="page.page >= totalPages" @click="loadCandidates(page.page + 1)">下一页</button></footer>
      </aside>

      <main class="candidate-detail" aria-live="polite">
        <p v-if="detailLoading" class="state">正在加载 Markdown 资料…</p>
        <div v-else-if="!detail" class="state"><strong>选择一条知识候选</strong><p>这里会展示完整中文笔记、来源 Trace 和审核边界。</p></div>
        <template v-else>
          <header class="detail-header"><div><p class="eyebrow">CANDIDATE DETAIL</p><h2>{{ detail.title }}</h2><p>{{ detail.summary }}</p></div><i>{{ detail.isGuide ? '虚拟引导资料' : candidateStatusLabel(detail.status) }}</i></header>
          <dl class="facts"><div><dt>来源 Trace</dt><dd><DecodeText :value="detail.traceId" tag="code" /></dd></div><div><dt>来源工具</dt><dd>{{ detail.toolId }}</dd></div><div><dt>运行记录</dt><dd>#{{ detail.sourceRunId }}</dd></div><div><dt>生成时间</dt><dd>{{ formatTime(detail.createdAt) }}</dd></div></dl>
          <div class="review-notice"><strong>人工审核要求</strong><span>区分事实、推测与待验证项；核对敏感信息、组件版本、风险、回滚和验证结果。</span></div>
          <article class="markdown-document" aria-label="候选知识 Markdown 预览" v-html="renderedMarkdown"></article>
        </template>
      </main>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getKnowledgeCandidate, getKnowledgeCandidates } from '../../api/operations.js'
import { candidateStatusLabel } from '../../components/operations/operationRunHistory.js'
import { reviewQueueWithGuide } from '../../components/knowledge/knowledgeCandidateGuide.js'
import { renderKnowledgeMarkdown } from '../../components/knowledge/renderKnowledgeMarkdown.js'
import DecodeText from '../../components/common/DecodeText.vue'

const page = ref({ items: [], total: 0, page: 1, pageSize: 20 })
const guideMode = ref(false)
const selectedId = ref(null), detail = ref(null), loading = ref(false), detailLoading = ref(false), error = ref('')
const totalPages = computed(() => Math.max(1, Math.ceil(page.value.total / page.value.pageSize)))
const renderedMarkdown = computed(() => renderKnowledgeMarkdown(detail.value?.contentMarkdown))
const unwrap = response => response?.data ?? response
const formatTime = value => value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium', hour12: false }).format(new Date(value)) : '—'

async function loadCandidates(targetPage = 1) {
  loading.value = true; error.value = ''
  try {
    const result = reviewQueueWithGuide(unwrap(await getKnowledgeCandidates({ status: 'PENDING_REVIEW', page: targetPage, pageSize: page.value.pageSize })))
    page.value = result
    guideMode.value = result.guideMode
    if (!page.value.items.some(item => item.id === selectedId.value)) { selectedId.value = page.value.items[0]?.id ?? null; detail.value = null }
    if (selectedId.value) await loadDetail(selectedId.value)
  } catch (cause) { error.value = cause.message || '请检查后端服务和数据库连接。' } finally { loading.value = false }
}
async function loadDetail(id) {
  detailLoading.value = true
  try {
    const selected = page.value.items.find(item => item.id === id)
    detail.value = selected?.isGuide ? selected : unwrap(await getKnowledgeCandidate(id))
  }
  catch (cause) { error.value = cause.message || '候选详情加载失败。'; detail.value = null }
  finally { detailLoading.value = false }
}
function selectCandidate(id) { if (id !== selectedId.value) { selectedId.value = id; loadDetail(id) } }
onMounted(() => loadCandidates(1))
</script>

<style scoped>
.review-workbench{max-width:1480px;margin:0 auto;padding:12px 0 40px;color:var(--smart-text);font-family:var(--font-cn)}.page-heading,.candidate-list>header,.detail-header,.candidate-row>span,.candidate-list>footer{display:flex;align-items:center;justify-content:space-between;gap:18px}.eyebrow{margin:0 0 8px;color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.14em}.page-heading h1{margin:0;font-size:clamp(28px,3vw,38px);font-weight:560}.page-heading p:not(.eyebrow),.detail-header p{color:var(--smart-muted);font-size:12px}.pending-count,.detail-header>i,.candidate-row i{border:1px solid #d69a50;border-radius:999px;padding:6px 10px;color:#d69a50;font-size:10px;font-style:normal}.review-layout{display:grid;grid-template-columns:minmax(310px,390px) minmax(0,1fr);gap:18px;margin-top:24px;align-items:start}.candidate-list,.candidate-detail{min-width:0;border:1px solid var(--smart-border);border-radius:12px;background:var(--smart-surface);overflow:hidden}.candidate-list>header,.detail-header{padding:20px;border-bottom:1px solid var(--smart-border)}h2{margin:0;font-size:18px;font-weight:560}.candidate-list>header>span{color:var(--smart-muted);font-size:11px}.candidate-row{display:block;width:100%;padding:16px 20px;border:0;border-bottom:1px solid var(--smart-border);text-align:left;color:var(--smart-text);background:transparent;cursor:pointer}.candidate-row:hover,.candidate-row.active{background:color-mix(in srgb,var(--smart-primary-strong) 9%,transparent)}.candidate-row.active{box-shadow:inset 3px 0 var(--smart-primary-strong)}.candidate-row b{font-size:12px}.candidate-row p{margin:9px 0;color:var(--smart-muted);font-size:10px;line-height:1.6}.candidate-row code,.candidate-row time{display:block;color:var(--smart-muted);font:10px var(--font-mono)}.candidate-row time{margin-top:6px}.candidate-list>footer{padding:13px}.candidate-list button,.state button{border:1px solid var(--smart-border);border-radius:7px;padding:7px 10px;color:var(--smart-text);background:var(--smart-bg)}.candidate-list>footer span{font-size:10px;color:var(--smart-muted)}.candidate-detail{min-height:650px}.detail-header{align-items:flex-start}.detail-header p{max-width:760px;line-height:1.7}.facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:0;border-bottom:1px solid var(--smart-border)}.facts div{min-width:0;padding:15px 18px;border-right:1px solid var(--smart-border)}.facts dt{color:var(--smart-muted);font-size:10px}.facts dd{margin:7px 0 0;font-size:11px;overflow-wrap:anywhere}.review-notice{display:flex;gap:16px;padding:13px 20px;border-bottom:1px solid var(--smart-border);border-left:3px solid #d69a50;background:color-mix(in srgb,#d69a50 6%,var(--smart-surface));font-size:11px}.review-notice span{color:var(--smart-muted)}.markdown-document{max-width:860px;padding:30px 34px 44px;color:var(--smart-text);font:14px/1.85 var(--font-cn)}.markdown-document :deep(h1),.markdown-document :deep(h2),.markdown-document :deep(h3){margin:30px 0 12px;color:var(--smart-text);font-family:var(--font-cn);font-weight:620;line-height:1.35}.markdown-document :deep(h1){margin-top:0;font-size:26px}.markdown-document :deep(h2){padding-bottom:8px;border-bottom:1px solid var(--smart-border);font-size:19px}.markdown-document :deep(h3){font-size:16px}.markdown-document :deep(p){margin:0 0 14px;color:var(--smart-muted)}.markdown-document :deep(ul),.markdown-document :deep(ol){margin:0 0 18px;padding-left:25px;color:var(--smart-muted)}.markdown-document :deep(li){margin:7px 0;padding-left:3px}.markdown-document :deep(code){padding:2px 6px;border:1px solid var(--smart-border);border-radius:4px;background:color-mix(in srgb,var(--smart-primary-strong) 8%,transparent);color:var(--smart-primary-strong);font:12px/1.6 var(--font-mono)}.markdown-document :deep(pre){overflow:auto;margin:18px 0;padding:17px 19px;border:1px solid var(--smart-border);border-radius:8px;background:color-mix(in srgb,var(--smart-bg) 84%,#000);box-shadow:inset 3px 0 var(--smart-primary-strong)}.markdown-document :deep(pre code){padding:0;border:0;background:transparent;color:var(--smart-text);white-space:pre}.markdown-document :deep(blockquote){margin:18px 0;padding:14px 17px;border-left:3px solid #d69a50;background:color-mix(in srgb,#d69a50 7%,transparent)}.markdown-document :deep(blockquote p){margin:0;color:var(--smart-text)}.markdown-document :deep(.task-list-item){display:flex;align-items:flex-start;gap:9px;list-style:none;margin-left:-22px}.markdown-document :deep(.task-list-item input){margin-top:6px;accent-color:var(--smart-primary-strong)}.state{padding:60px 24px;text-align:center;color:var(--smart-muted);font-size:12px}.error{margin-top:24px;border:1px solid var(--smart-border);border-left:3px solid #e06b72;border-radius:12px;background:var(--smart-surface)}
.guide-banner{display:grid;gap:5px;padding:13px 20px;border-bottom:1px solid color-mix(in srgb,#d69a50 45%,var(--smart-border));background:color-mix(in srgb,#d69a50 8%,var(--smart-surface));font-size:11px}.guide-banner strong{color:#d69a50}.guide-banner span{color:var(--smart-muted);line-height:1.55}
@media(max-width:980px){.review-layout{grid-template-columns:1fr}.facts{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.page-heading,.detail-header{align-items:flex-start;flex-direction:column}.facts{grid-template-columns:1fr}.review-notice{flex-direction:column}.markdown-document{padding:18px 14px}}

/* 两栏独立滚动：审核队列与候选详情各自一条滚动条，头部吸顶 */
.review-workbench {
  padding-bottom: 0;
  /* 抵消 .content 的底部留白，避免整页多出一条滚动条 */
  margin-bottom: -96px;
}
@media (max-width: 1023px) { .review-workbench { margin-bottom: -64px; } }
@media (max-width: 767px) { .review-workbench { margin-bottom: -56px; } }
.review-layout {
  height: clamp(440px, calc(100dvh - 320px), 880px);
  align-items: stretch;
}
.candidate-list,
.candidate-detail {
  min-height: 0;
  overflow: hidden auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}
.candidate-list > header,
.detail-header {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--smart-surface);
}
.candidate-list > footer {
  position: sticky;
  bottom: 0;
  z-index: 2;
  border-top: 1px solid var(--smart-border);
  background: var(--smart-surface);
}
@media (max-width: 980px) {
  .review-layout { height: auto; }
  .candidate-list, .candidate-detail { overflow: visible; }
  .candidate-list > header, .detail-header, .candidate-list > footer { position: static; }
}
</style>
