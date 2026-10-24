<template>
  <article class="tools-page">
    <header class="tools-header">
      <div><p class="editorial-label">OPS WORKBENCH / TOOLS</p><h1>{{ activeTool.title }}</h1><p>{{ activeTool.subtitle }}</p></div>
      <div v-if="isDiagnosticTool" class="bridge-state"><span>CONTROLLED DIAGNOSTIC</span><strong>授权目标 / 本地工具</strong></div><div v-else-if="observabilitySource || isHarborBrowser" class="bridge-state"><span>HTTP DATA SOURCE</span><strong>后端只读数据源查询</strong></div>
      <div v-else class="bridge-state"><span class="status-dot" :class="bridgeOnline ? 'online' : 'offline'"></span><span>LOCAL OPERATIONS BRIDGE</span><strong>{{ bridgeOnline ? 'ONLINE / 在线' : 'REQUIRES BRIDGE / 需启动桥接' }}</strong></div>
    </header>
    <aside v-if="fromCloud" class="cloud-context-notice" aria-label="云原生目标提示">
      <strong>{{ cloudEnvironments[cloudIntent.environment] }} · 目标意图，非连接证明</strong>
      <p>Context：{{ cloudIntent.cluster || '未指定' }} / Namespace：{{ cloudIntent.namespace || '未指定' }} / 参考时间：{{ cloudIntent.timeRange }}</p>
      <p>不会自动切换远程 Context，也不会自动填入执行参数。请核对当前会话与目标；此提示不替代服务端授权。</p>
      <label><input v-model="cloudAcknowledged" type="checkbox" />我已核对当前远程会话、实际 Context、Namespace 和工具参数</label>
      <RouterLink :to="{ path: '/cloud-native', query: cloudContextQuery(cloudIntent) }">返回云原生工作台</RouterLink>
    </aside>
    <nav class="tool-nav" aria-label="工具分类">
      <section v-for="group in groups" :key="group.label"><p>{{ group.label }}</p><RouterLink v-for="tool in group.items" :key="tool.id" :to="fromCloud ? { path: `/tools/${tool.id}`, query: cloudContextQuery(cloudIntent) } : `/tools/${tool.id}`" :class="{ active: tool.id === selectedTool }">{{ tool.label }}</RouterLink></section>
    </nav>
    <details class="operation-tool-workspace">
      <summary>云计算 / 云原生能力覆盖与接入计划（12 个领域）</summary>
      <p class="tool-note">以下表示系统实现进度，不是环境健康状态。优先级 1：核心依赖；2：功能完善；3：进阶增强。已有模板需核验外部适配器后才能使用。</p>
      <div class="tool-definition-grid">
        <section v-for="area in cloudCoverage" :key="area.domain">
          <h2>{{ area.domain }} · 优先级 {{ area.priority }}</h2>
          <p class="tool-note">知识：{{ area.knowledge }}</p>
          <p class="tool-note">工具：{{ area.tools }}</p>
          <p class="tool-note"><strong>{{ area.status }}</strong></p>
          <p class="tool-note">{{ area.next }}</p>
          <RouterLink v-if="area.toolId" :to="`/tools/${area.toolId}`">打开对应工具</RouterLink>
          <RouterLink v-else :to="{ path: '/knowledge', query: { query: area.domain } }">检索现有知识</RouterLink>
        </section>
      </div>
    </details>
    <section class="tool-panel">
      <div class="tool-toolbar"><span>{{ activeTool.label }}</span><div><input v-if="!isDiagnosticTool && !observabilitySource && !isHarborBrowser" v-model="query" placeholder="搜索工具输出" /><button v-if="!isProcessTool && !isDiagnosticTool && !observabilitySource && !isHarborBrowser" type="button" :disabled="!bridgeOnline" @click="runTool">{{ running ? '运行中' : '执行' }}</button></div></div>
      <NetworkDiagnosticTool v-if="selectedTool === 'service-http-check'" />
      <NetworkDiagnosticTool v-else-if="selectedTool === 'service-certificate-check'" certificate-mode />
      <ConfigDiffTool v-else-if="selectedTool === 'config-diff'" />
      <ObservabilityQuery v-if="observabilitySource" :source="observabilitySource" />
      <HarborBrowser v-else-if="isHarborBrowser" />
      <div v-else-if="isProcessTool" class="process-workspace">
        <div class="process-context"><strong>READ-ONLY PROCESS DIAGNOSTICS</strong><span v-if="knowledgeContext">KNOWLEDGE: {{ knowledgeContext }}</span><RouterLink v-if="knowledgeContext" :to="{ path: '/knowledge', query: { entry: knowledgeContext } }">返回知识详情</RouterLink><small>不读取本机或 SSH 数据，不执行命令。</small></div>
        <div class="process-scenarios" role="list" aria-label="进程诊断场景">
          <button v-for="scenario in processDiagnosticScenarios" :key="scenario.id" type="button" :class="['process-scenario', { active: scenario.id === selectedScenarioId }]" @click="selectedScenarioId = scenario.id">{{ scenario.label }}</button>
        </div>
        <div v-if="selectedScenario" class="process-detail">
          <div><h2>{{ selectedScenario.label }}</h2><p>{{ selectedScenario.symptoms.join(' / ') }}</p></div>
          <section><h3>需要确认的证据</h3><ul><li v-for="item in selectedScenario.evidence" :key="item">{{ item }}</li></ul></section>
          <section><h3>READ-ONLY COMMAND PREVIEW</h3><div class="command-preview"><code v-for="item in selectedScenario.commands" :key="item.command"><span>{{ item.command }}</span><small>{{ item.purpose }} / READ ONLY</small></code></div></section>
          <section class="process-risk"><h3>风险边界</h3><p>{{ selectedScenario.risk }}</p><p>验证：{{ selectedScenario.verification.join('；') }}</p><p>升级：{{ selectedScenario.escalation }}</p></section>
        </div>
      </div>
      <div v-else class="operation-tool-workspace">
        <div class="tool-definition-header">
          <div><strong>{{ activeTool.label }}</strong><p>{{ activeTool.subtitle }}</p></div>
          <div class="tool-badges"><span>{{ activeTool.readOnly ? 'READ ONLY / 只读' : 'MUTATING / 变更' }}</span><span :class="`risk-${activeTool.riskLevel.toLowerCase()}`">RISK {{ activeTool.riskLevel }}</span><span v-if="activeTool.requireConfirm">REQUIRE CONFIRM / 需要确认</span></div>
        </div>
        <div class="tool-definition-grid">
          <section>
            <h2>参数</h2>
            <div v-if="activeTool.parameters.length" class="tool-parameters">
              <label v-for="parameter in activeTool.parameters" :key="parameter.id"><span>{{ parameter.label }}</span><input v-model="toolValues[parameter.id]" :placeholder="parameter.defaultValue || parameter.id" /></label>
            </div>
            <p v-else class="tool-note">该工具不需要额外参数。</p>
            <p v-if="previewError" class="tool-error" role="alert">{{ previewError }}</p>
          </section>
          <section>
            <h2>命令预览</h2>
            <div class="command-preview"><code v-for="command in commandPreview" :key="command"><span>{{ command }}</span><small>{{ activeTool.readOnly ? 'READ ONLY' : `RISK ${activeTool.riskLevel} · 执行前确认` }}</small></code></div>
          </section>
          <section>
            <h2>运行证据</h2>
            <p v-if="activeTool.prerequisite" class="tool-note"><strong>前置条件：</strong>{{ activeTool.prerequisite }}</p>
            <p v-if="activeTool.troubleshooting" class="tool-note"><strong>排查说明：</strong>{{ activeTool.troubleshooting }}</p>
            <ul><li v-for="item in activeTool.evidence" :key="item">{{ item }}</li></ul>
            <p v-if="activeTool.rollback" class="tool-note"><strong>回滚：</strong>{{ activeTool.rollback }}</p>
          </section>
          <section class="bridge-gate">
            <h2>执行入口</h2>
            <p>{{ bridgeOnline ? 'Bridge 已连接，等待对应 capability 接口返回真实数据。' : 'Bridge 离线。当前仅允许检查参数和命令预览，不会伪造执行结果。' }}</p>
            <span class="capability-chip">CAPABILITY: {{ activeTool.capability }}</span>
            <button v-if="!bridgeOnline" type="button" @click="openConnections">打开连接中心</button>
          </section>
        </div>
        <section v-if="runError || runResult" class="tool-run-result" aria-live="polite">
          <p v-if="runError" class="tool-error">{{ runError }}</p>
          <template v-if="runResult">
            <header><strong>{{ runResult.status }}</strong><span>TraceId: {{ runResult.traceId }}</span><span>{{ formatTime(runResult.startedAt) }} → {{ formatTime(runResult.endedAt) }}</span></header>
            <article v-for="command in filteredRunCommands" :key="`${command.command}-${command.startedAt}`" class="command-result">
              <div><code>{{ command.command }}</code><span :class="command.exitCode === 0 ? 'exit-ok' : 'exit-failed'">exitCode {{ command.exitCode }}</span></div>
              <section><h3>stdout</h3><pre>{{ command.stdout || '（无标准输出）' }}</pre></section>
              <section v-if="command.stderr"><h3>stderr</h3><pre>{{ command.stderr }}</pre></section>
            </article>
          </template>
        </section>
      </div>
    </section>
    <footer class="tool-footer"><span>连接</span><i>→</i><span>观察</span><i>→</i><span>操作</span><i>→</i><span>记忆</span><small>STATUS / {{ observabilitySource || isHarborBrowser ? 'HTTP DATA SOURCE' : bridgeOnline ? 'READY' : 'BRIDGE REQUIRED' }}</small></footer>
  </article>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getProcessDiagnosticScenario, processDiagnosticScenarios } from './processDiagnostics.js'
import { findOperationTool, operationToolGroups, previewOperationToolCommands } from './toolCatalog.js'
import { executeOperationTool } from '../../api/operations.js'
import { getActiveOperationRuntime } from '../../api/operationRuntimeState.js'
import { cloudCoverage } from './cloudCoverage.js'
import ObservabilityQuery from '../../components/operations/ObservabilityQuery.vue'
import HarborBrowser from '../../components/operations/HarborBrowser.vue'
import NetworkDiagnosticTool from '../../components/diagnostics/NetworkDiagnosticTool.vue'
import ConfigDiffTool from '../../components/diagnostics/ConfigDiffTool.vue'
import { readCloudContext, cloudContextQuery, cloudEnvironments } from '../cloud/cloudContext.js'

const route = useRoute()
const router = useRouter()
const fromCloud = computed(() => route.query.source === 'cloud-native')
const cloudIntent = computed(() => readCloudContext(route.query))
const cloudAcknowledged = ref(false)
const query = ref('')
const running = ref(false)
const activeRuntime = ref(getActiveOperationRuntime())
const bridgeOnline = computed(() => Boolean(activeRuntime.value?.runtimeId))
const runResult = ref(null)
const runError = ref('')
const groups = operationToolGroups
const selectedTool = computed(() => route.params.tool || 'processes')
const observabilitySource = computed(() => ({ 'prometheus-query': 'prometheus', 'loki-log-query': 'loki' })[selectedTool.value] || '')
const isHarborBrowser = computed(() => selectedTool.value === 'harbor-browser')
const isDiagnosticTool = computed(() => ['service-http-check', 'service-certificate-check', 'config-diff'].includes(selectedTool.value))
const activeTool = computed(() => findOperationTool(selectedTool.value) || findOperationTool('processes'))
const toolValues = reactive({})
watch(activeTool, tool => {
  for (const key of Object.keys(toolValues)) delete toolValues[key]
  for (const parameter of tool.parameters || []) toolValues[parameter.id] = parameter.defaultValue || ''
}, { immediate: true })
const previewResult = computed(() => {
  try { return { commands: previewOperationToolCommands(activeTool.value, toolValues), error: '' } }
  catch (error) { return { commands: [], error: error.message || '参数不符合安全规则' } }
})
const commandPreview = computed(() => previewResult.value.commands)
const previewError = computed(() => previewResult.value.error)
const filteredRunCommands = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return runResult.value?.commands || []
  return (runResult.value?.commands || []).filter(item =>
    `${item.command} ${item.stdout} ${item.stderr}`.toLowerCase().includes(needle))
})
const isProcessTool = computed(() => selectedTool.value === 'processes')
const knowledgeContext = computed(() => route.query.knowledge || '')
const selectedScenarioId = ref('server-slow')
const selectedScenario = computed(() => getProcessDiagnosticScenario(selectedScenarioId.value))
let runRevision = 0
watch([() => route.query, selectedTool, toolValues, () => activeRuntime.value?.runtimeId], () => {
  cloudAcknowledged.value = false
  runRevision++
  runResult.value = null
  runError.value = ''
}, { deep: true })
async function runTool() {
  if (!activeRuntime.value?.runtimeId || running.value || previewError.value) return
  if (fromCloud.value && !cloudAcknowledged.value) {
    runError.value = '请先核对云原生目标提示与当前远程会话，再确认执行。'
    return
  }
  if (!activeTool.value.readOnly) {
    runError.value = '该变更工具需要独立审批流程，当前只读执行入口已阻止执行。'
    return
  }
  running.value = true
  runError.value = ''
  runResult.value = null
  const revision = runRevision
  try {
    const response = await executeOperationTool(activeRuntime.value.runtimeId, activeTool.value.id, { ...toolValues })
    if (revision === runRevision) runResult.value = response.data?.data || response.data || response
  } catch (error) {
    if (revision === runRevision) runError.value = error.message || '工具执行失败'
  } finally {
    running.value = false
  }
}
function formatTime(value) { return value ? new Date(value).toLocaleString('zh-CN') : '—' }
function openConnections() { router.push('/connections') }
</script>

<style scoped>
.cloud-context-notice{display:grid;gap:10px;margin:20px 0;padding:18px;border:1px solid var(--smart-border-strong);background:var(--smart-surface);color:var(--smart-text);overflow-wrap:anywhere}.cloud-context-notice p{margin:0;color:var(--smart-muted);line-height:1.7}.cloud-context-notice label{display:flex;align-items:center;gap:10px;min-height:44px}.cloud-context-notice a{color:var(--smart-primary-strong)}
.tools-page{color:var(--smart-text)}.tools-header{display:flex;justify-content:space-between;gap:40px;padding:44px 0 32px;border-bottom:1px solid var(--smart-border)}.editorial-label,.tool-nav p,.tool-toolbar span,.tool-footer{color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.13em}.tools-header h1{margin:20px 0 8px;font:400 clamp(2.4rem,5vw,5rem)/.9 var(--font-display);letter-spacing:-.04em}.tools-header p:not(.editorial-label){color:var(--smart-muted);font:var(--body-cn)}.bridge-state{display:grid;align-content:end;min-width:220px;padding-left:20px;border-left:1px solid var(--smart-border);color:var(--smart-muted);font:10px var(--font-mono);letter-spacing:.1em}.bridge-state strong{margin-top:12px;color:var(--smart-primary-strong);font-weight:400}.status-dot{width:7px;height:7px;margin-bottom:8px;border-radius:50%;background:#a37a82}.status-dot.online{background:var(--smart-primary-strong);box-shadow:0 0 12px var(--smart-primary-strong)}.tool-nav{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;padding:24px 0;border-bottom:1px solid var(--smart-border)}.tool-nav section{display:grid;align-content:start;gap:7px}.tool-nav p{margin:0 0 5px;color:var(--smart-muted)}.tool-nav a{padding:8px 0;border-bottom:1px solid rgba(130,160,180,.12);color:var(--smart-text);font:12px var(--font-cn);text-decoration:none}.tool-nav a.active,.tool-nav a:hover{color:var(--smart-primary-strong)}.tool-panel{min-height:430px;margin-top:24px;border:1px solid var(--smart-border);background:rgba(3,7,13,.35)}.tool-toolbar{display:flex;justify-content:space-between;gap:16px;padding:15px 18px;border-bottom:1px solid var(--smart-border)}.tool-toolbar div{display:flex;gap:12px}.tool-toolbar input{width:180px;border:0;border-bottom:1px solid var(--smart-border);background:transparent;color:var(--smart-text);outline:0;font:11px var(--font-mono)}button{padding:9px 12px;border:1px solid var(--smart-border-strong);background:transparent;color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.1em;cursor:pointer}button:disabled{opacity:.4;cursor:not-allowed}.tool-empty{display:grid;place-items:center;align-content:center;min-height:360px;padding:30px;text-align:center}.tool-empty strong{color:var(--smart-primary-strong);font:14px var(--font-mono);letter-spacing:.12em}.tool-empty p{max-width:450px;color:var(--smart-muted);font:var(--body-cn);line-height:1.7}.capability-chip{padding:8px 10px;border:1px solid var(--smart-border);color:var(--smart-muted);font:10px var(--font-mono)}.tool-footer{display:flex;gap:13px;padding:18px 0}.tool-footer i{color:var(--smart-primary-strong);font-style:normal}.tool-footer small{margin-left:auto;color:var(--smart-muted)}@media(max-width:800px){.tools-header{display:block}.bridge-state{margin-top:24px;padding:14px 0 0;border-top:1px solid var(--smart-border);border-left:0}.tool-nav{grid-template-columns:1fr}.tool-toolbar{display:block}.tool-toolbar div{margin-top:12px}.tool-footer{flex-wrap:wrap}.tool-footer small{width:100%;margin-left:0}}
 .process-workspace{padding:22px}.process-context{display:flex;flex-wrap:wrap;gap:12px;align-items:center;padding-bottom:18px;border-bottom:1px solid var(--smart-border)}.process-context strong{color:var(--smart-primary-strong);font:11px var(--font-mono);letter-spacing:.1em}.process-context span,.process-context small{color:var(--smart-muted);font:10px var(--font-mono)}.process-context small{flex-basis:100%;font-family:var(--font-cn);font-size:12px}.process-scenarios{display:flex;flex-wrap:wrap;gap:8px;padding:18px 0}.process-scenario{font-family:var(--font-cn)}.process-scenario.active{background:var(--smart-primary-strong);color:#071018}.process-detail{display:grid;grid-template-columns:1fr 1fr;gap:22px;padding-top:10px}.process-detail h2{margin:0 0 8px;font:400 24px var(--font-cn)}.process-detail h3{margin:0 0 10px;color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.1em}.process-detail p,.process-detail li{color:var(--smart-muted);font:13px/1.7 var(--font-cn)}.process-detail ul{margin:0;padding-left:18px}.command-preview{display:grid;gap:8px}.command-preview code{display:grid;gap:5px;padding:10px;border:1px solid var(--smart-border);background:rgba(5,17,25,.5);color:var(--smart-text);font:12px var(--font-mono)}.command-preview small{color:var(--smart-muted);font:11px var(--font-cn)}.process-risk{grid-column:1/-1;padding-top:16px;border-top:1px solid var(--smart-border)}@media(max-width:800px){.process-workspace{padding:16px}.process-detail{grid-template-columns:1fr}.process-risk{grid-column:auto}}
.operation-tool-workspace{padding:22px}.tool-definition-header{display:flex;justify-content:space-between;gap:20px;padding-bottom:18px;border-bottom:1px solid var(--smart-border)}.tool-definition-header strong{color:var(--smart-primary-strong);font:13px var(--font-mono);letter-spacing:.08em}.tool-definition-header p,.tool-note,.bridge-gate p,.tool-definition-grid li{color:var(--smart-muted);font:12px/1.7 var(--font-cn)}.tool-badges{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px}.tool-badges span{height:max-content;padding:6px 8px;border:1px solid var(--smart-border);color:var(--smart-muted);font:9px var(--font-mono)}.tool-badges .risk-high{border-color:#aa6670;color:#dc9aa3}.tool-definition-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;padding-top:22px}.tool-definition-grid section{min-width:0}.tool-definition-grid h2{margin:0 0 12px;color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.12em}.tool-parameters{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.tool-parameters label{display:grid;gap:6px;color:var(--smart-muted);font:11px var(--font-cn)}.tool-parameters input{min-width:0;padding:9px;border:1px solid var(--smart-border);background:rgba(5,17,25,.5);color:var(--smart-text);font:12px var(--font-mono);outline:0}.tool-parameters input:focus{border-color:var(--smart-primary-strong)}.tool-error{color:#dc9aa3;font:12px var(--font-cn)}.bridge-gate{display:grid;align-content:start;justify-items:start;gap:10px}.bridge-gate .capability-chip{margin-bottom:4px}@media(max-width:800px){.tool-definition-header{display:grid}.tool-badges{justify-content:flex-start}.tool-definition-grid{grid-template-columns:1fr}.tool-parameters{grid-template-columns:1fr}}
.tool-run-result{margin-top:24px;padding-top:20px;border-top:1px solid var(--smart-border)}.tool-run-result>header{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:14px;color:var(--smart-muted);font:10px var(--font-mono)}.tool-run-result>header strong{color:var(--smart-primary-strong)}.command-result{display:grid;gap:12px;padding:16px 0;border-top:1px solid rgba(130,160,180,.14)}.command-result>div{display:flex;justify-content:space-between;gap:16px}.command-result code{color:var(--smart-text);font:12px var(--font-mono)}.command-result h3{margin:0 0 6px;color:var(--smart-primary-strong);font:10px var(--font-mono)}.command-result pre{max-height:280px;margin:0;padding:12px;overflow:auto;border:1px solid var(--smart-border);background:#03070d;color:var(--smart-text);font:11px/1.6 var(--font-mono);white-space:pre-wrap}.exit-ok{color:#8fc7af}.exit-failed{color:#dc9aa3}
</style>
