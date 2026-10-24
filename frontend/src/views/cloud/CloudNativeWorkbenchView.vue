<template>
  <article class="cloud-workbench">
    <header class="cloud-header"><div><p class="eyebrow">CLOUD NATIVE / ENGINEERING</p><h1>云原生工程</h1><p>先明确目标，再选择知识与只读工具。此页不连接集群，不执行命令。</p></div><strong class="environment-badge">{{ context.environment === 'production' ? '⚠ 生产环境 · 操作前核对' : cloudEnvironments[context.environment] }}</strong></header>
    <form class="context-panel" aria-label="诊断目标意图" @submit.prevent="applyContext">
      <div class="context-heading"><h2>目标上下文</h2><p>以下是手动填写的目标意图，不代表集群已连接或权限已验证。不要填写密码或令牌。</p></div>
      <div class="context-fields">
        <label>环境<select v-model="draft.environment"><option v-for="(label, key) in cloudEnvironments" :key="key" :value="key">{{ label }}</option></select></label>
        <label>集群 Context<input v-model.trim="draft.cluster" maxlength="128" placeholder="例如 team-prod（不自动连接）" autocomplete="off" /></label>
        <label>Namespace<input v-model.trim="draft.namespace" maxlength="63" placeholder="例如 orders（可留空）" autocomplete="off" /></label>
        <label>参考时间范围<select v-model="draft.timeRange"><option value="15m">最近 15 分钟</option><option value="1h">最近 1 小时</option><option value="6h">最近 6 小时</option></select></label>
      </div>
      <div class="context-footer"><button type="submit">应用上下文</button><span role="status">{{ contextMessage }}</span><small>应用后清空当前详情；跳转工具不会自动填入执行参数。</small></div>
      <p v-if="contextError" role="alert">{{ contextError }}</p>
    </form>
    <section class="domain-grid" aria-label="云原生知识领域">
      <button v-for="(section, index) in cloudSections" :key="section.title" type="button" class="domain-card" :aria-pressed="section === activeSection" @click="openSection(index)"><span>{{ section.kicker }}</span><strong>{{ section.title }}</strong><small>{{ section.summary }}</small><span>{{ section.items.length }} 项知识与工具</span></button>
    </section>
    <section v-if="activeSection" class="cloud-detail" aria-label="云原生详情">
      <header class="detail-heading"><div><p class="eyebrow">{{ activeSection.title }} / {{ activeResource ? activeResource.kind : 'OVERVIEW' }}</p><h2 ref="detailHeading" tabindex="-1">{{ activeResource?.label || activeSection.title }}</h2></div><button type="button" @click="backToOverview">{{ activeResource ? '返回领域列表' : '关闭详情' }}</button></header>
      <template v-if="activeResource">
        <p class="reference-notice">内置参考资料 · 未人工核验 · 执行前确认版本、真实 Context 和权限。</p>
        <div class="markdown-note" v-html="renderKnowledgeMarkdown(resourceMarkdown)"></div>
        <RouterLink class="open-route" :to="cloudResourceRoute(activeResource.to, context)">{{ activeResource.kind === 'TOOL' ? '进入只读工具，核对执行目标' : '进入知识库查看资料' }} →</RouterLink>
      </template>
      <template v-else>
        <p>{{ activeSection.summary }}</p>
        <div class="resource-grid"><button v-for="(item, index) in activeSection.items" :key="item.label" type="button" class="resource-card" @click="openResource(index)"><span>{{ item.kind }}</span><strong>{{ item.label }}</strong><small>{{ item.description }}</small><span>查看前置条件与验证步骤 →</span></button></div>
      </template>
    </section>
    <p v-else class="empty-guidance">选择一个领域开始。知识说明不等于诊断结果；没有连接与证据时，不显示虚构的集群健康状态。</p>
  </article>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { renderKnowledgeMarkdown } from '../../components/knowledge/renderKnowledgeMarkdown.js'
import { cloudSections } from './cloudWorkbenchCatalog.js'
import { cloudEnvironments, readCloudContext, validateCloudContext, cloudContextQuery, cloudResourceRoute } from './cloudContext.js'

const route = useRoute(), router = useRouter()
const context = computed(() => readCloudContext(route.query))
const draft = reactive({ ...context.value })
const contextError = ref(''), contextMessage = ref(''), detailHeading = ref(null)
const validIndex = value => typeof value === 'string' && /^(0|[1-9]\d?)$/.test(value) ? Number(value) : -1
const activeSection = computed(() => cloudSections[validIndex(route.query.section)] || null)
const activeResource = computed(() => activeSection.value?.items[validIndex(route.query.resource)] || null)
const resourceMarkdown = computed(() => {
  const item = activeResource.value
  if (!item) return ''
  return `## 任务说明\n\n${item.description}\n\n## 前置条件\n\n- 已确认真实 Context、Namespace 和读取权限。\n- 页面目标只是意图，不能替代远程环境验证。\n\n## 检查步骤\n\n${item.steps.map((step, index) => `${index + 1}. ${step}`).join('\n')}\n\n## 常见问题\n\n${item.errors}\n\n## 结果验证\n\n${item.verify}\n\n## 安全边界\n\n- 工具页面先预览参数和命令，再人工确认。\n- 只读检查不能替代业务验证；不自动修改生产资源。`
})
watch(context, value => { Object.assign(draft, value); contextError.value = '' })
async function applyContext() {
  contextError.value = validateCloudContext(draft).join(' ')
  if (contextError.value) return
  await router.replace({ path: '/cloud-native', query: cloudContextQuery(draft) })
  contextMessage.value = '目标意图已保存，尚未连接集群。'
}
async function focusDetail() { await nextTick(); detailHeading.value?.focus({ preventScroll: true }) }
async function openSection(index) { await router.replace({ query: { ...route.query, section: String(index), resource: undefined } }); focusDetail() }
async function openResource(index) { await router.replace({ query: { ...route.query, resource: String(index) } }); focusDetail() }
async function backToOverview() {
  await router.replace({ query: { ...route.query, section: activeResource.value ? route.query.section : undefined, resource: undefined } })
  if (activeSection.value) focusDetail()
}
</script>

<style scoped>
.cloud-workbench{max-width:1480px;margin:0 auto;padding:16px 0 48px;color:var(--smart-text)}.cloud-header,.detail-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;flex-wrap:wrap}.cloud-header{padding:12px 0 24px;border-bottom:1px solid var(--smart-border-strong)}.eyebrow{color:var(--smart-primary-strong);font:11px var(--font-mono);letter-spacing:.08em}.cloud-header h1{margin:12px 0;font:500 clamp(30px,4vw,48px)/1.15 var(--font-cn)}.cloud-header p,.context-heading p,.context-footer small,.empty-guidance,.reference-notice{color:var(--smart-muted);line-height:1.7}.environment-badge{padding:12px 16px;background:var(--smart-surface);border:1px solid var(--smart-border-strong);font-size:13px}.context-panel,.cloud-detail{margin:24px 0;padding:22px;border:1px solid var(--smart-border-strong);background:var(--smart-surface);border-radius:10px}.context-heading h2{font-size:18px;margin:0}.context-fields{display:grid;grid-template-columns:1fr 2fr 1fr 1fr;gap:14px}.context-fields label{display:grid;gap:8px;font-size:13px}.cloud-workbench :is(input,select,button){min-height:44px;border:1px solid var(--smart-border-strong);background:var(--smart-surface);color:var(--smart-text);padding:10px 12px;border-radius:6px;font:inherit}.context-fields :is(input,select){width:100%;min-width:0;box-sizing:border-box;font-size:13px}.cloud-workbench button{cursor:pointer}.cloud-workbench :is(button,a,input,select):focus-visible{outline:2px solid var(--smart-primary-strong);outline-offset:3px}.context-footer{display:flex;align-items:center;flex-wrap:wrap;gap:14px;margin-top:18px;font-size:13px}.domain-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.domain-card,.resource-card{display:grid;gap:12px;text-align:left;align-content:start}.domain-card{min-height:190px}.domain-card[aria-pressed=true]{border-color:var(--smart-primary-strong);background:color-mix(in srgb,var(--smart-primary-strong) 8%,var(--smart-surface))}.domain-card span,.resource-card span{font-size:11px;color:var(--smart-primary-strong)}.domain-card strong{font-size:20px}.domain-card small,.resource-card small{color:var(--smart-muted);line-height:1.7;font-size:13px}.resource-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:20px}.detail-heading h2{margin:8px 0 0;font-size:24px}.reference-notice{padding:12px;border-left:3px solid var(--smart-primary-strong)}.open-route{display:inline-flex;align-items:center;min-height:44px;margin-top:18px;color:var(--smart-primary-strong);font-weight:600}.markdown-note{font:14px/1.85 var(--font-cn);overflow-wrap:anywhere}.markdown-note :deep(h2){margin:22px 0 10px;font-size:18px}.markdown-note :deep(pre){overflow:auto;padding:16px;background:var(--smart-bg);border:1px solid var(--smart-border)}.markdown-note :deep(code){color:var(--smart-primary-strong)}.empty-guidance{padding:24px;border:1px dashed var(--smart-border-strong)}@media(max-width:1000px){.context-fields,.domain-grid,.resource-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.context-fields,.domain-grid,.resource-grid{grid-template-columns:1fr}.context-panel,.cloud-detail{padding:16px}.domain-card{min-height:140px}}
</style>
