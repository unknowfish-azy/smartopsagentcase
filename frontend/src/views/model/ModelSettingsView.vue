<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import { getModelConnections, createModelConnection, updateModelConnection, deleteModelConnection, invokeModelConnection } from '../../api/model'
import { createEmptyModelConnection, normalizeModelConnection } from '../../types/model'
import { connectionPayload, filterConnections, validateConnection } from '../../components/model/modelConnectionForm.js'
import ModelConnectionCard from '../../components/model/ModelConnectionCard.vue'
import IntegrationCard from '../../components/ui/integration-card.vue'
import { useSkillsStore } from '../../stores/skills.js'
const skillsStore = useSkillsStore(); skillsStore.load()
const applySkills = ref(false)

const connections = ref([]), loading = ref(false), loadError = ref(''), actionError = ref(''), notice = ref('')
const query = ref(''), statusFilter = ref('all'), busyIds = ref(new Set())
const dialogVisible = ref(false), editingId = ref(null), form = ref(createEmptyModelConnection()), formErrors = ref({}), saveError = ref(''), saving = ref(false)
const testVisible = ref(false), testing = ref(false), testConnection = ref(null), prompt = ref('请用一句话说明你可以如何帮助排查系统故障。'), testError = ref(''), testResult = ref(null)
const results = ref({})
let disposed = false, loadGeneration = 0
const visibleConnections = computed(() => filterConnections(connections.value, query.value, statusFilter.value))
const enabledCount = computed(() => connections.value.filter(item => item.enabled).length)
const fields = [
  { key: 'name', label: '连接名称', placeholder: '例如：运维推理模型' },
  { key: 'provider', label: '服务商标识', placeholder: '自定义服务商名称' },
  { key: 'baseUrl', label: 'Base URL', placeholder: 'https://your-gateway.example/v1', type: 'url' },
  { key: 'modelName', label: '模型 ID', placeholder: '填写服务商提供的准确模型 ID' },
]
const unwrap = response => response?.data ?? response
const errorMessage = error => error?.message || '操作失败，请稍后重试'
async function loadConnections() {
  const generation = ++loadGeneration
  loading.value = true; loadError.value = ''
  try {
    const response = unwrap(await getModelConnections())
    const items = response?.items ?? response
    if (!Array.isArray(items)) throw new Error('模型列表返回格式异常')
    if (!disposed && generation === loadGeneration) connections.value = items.map(normalizeModelConnection)
  } catch (error) {
    if (!disposed && generation === loadGeneration) loadError.value = errorMessage(error)
  } finally { if (!disposed && generation === loadGeneration) loading.value = false }
}
function openCreate() {
  editingId.value = null; form.value = { ...createEmptyModelConnection(), provider: 'custom' }
  formErrors.value = {}; saveError.value = ''; dialogVisible.value = true
}
function openEdit(connection) {
  if (busyIds.value.has(connection.id) || testing.value) return
  editingId.value = connection.id; form.value = { ...connection, apiKey: '' }
  formErrors.value = {}; saveError.value = ''; dialogVisible.value = true
}
function clearSecret() { form.value.apiKey = '' }
function beforeFormClose(done) { if (!saving.value) done() }
function applySaved(response) {
  const saved = normalizeModelConnection(unwrap(response))
  if (saved.id === null) throw new Error('服务未返回已保存的模型，请刷新列表确认')
  if (disposed) return
  const index = connections.value.findIndex(item => item.id === saved.id)
  if (index < 0) connections.value.push(saved)
  else connections.value.splice(index, 1, saved)
  delete results.value[saved.id]
}
async function save() {
  if (saving.value) return
  formErrors.value = validateConnection(form.value, editingId.value !== null)
  if (Object.keys(formErrors.value).length) return
  saving.value = true; saveError.value = ''; notice.value = ''
  try {
    const payload = connectionPayload(form.value)
    applySaved(editingId.value !== null ? await updateModelConnection(editingId.value, payload) : await createModelConnection(payload))
    dialogVisible.value = false; clearSecret()
    notice.value = '模型配置已保存，可通过“测试模型”验证调用。'
  } catch (error) { if (!disposed) saveError.value = errorMessage(error) }
  finally { saving.value = false }
}
async function toggle(connection) {
  if (busyIds.value.has(connection.id)) return
  busyIds.value.add(connection.id); actionError.value = ''
  try { applySaved(await updateModelConnection(connection.id, { enabled: !connection.enabled })) }
  catch (error) { if (!disposed) actionError.value = errorMessage(error) }
  finally { busyIds.value.delete(connection.id) }
}
async function remove(connection) {
  if (busyIds.value.has(connection.id)) return
  busyIds.value.add(connection.id)
  try {
    await ElMessageBox.confirm(`删除“${connection.name}”后需要重新填写凭据才能接入。`, '删除模型连接', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
    actionError.value = ''
    await deleteModelConnection(connection.id)
    if (!disposed) { connections.value = connections.value.filter(item => item.id !== connection.id); delete results.value[connection.id] }
  } catch (error) { if (error !== 'cancel' && error !== 'close' && !disposed) actionError.value = errorMessage(error) }
  finally { busyIds.value.delete(connection.id) }
}
function openTest(connection) {
  if (!connection.enabled || testing.value || busyIds.value.has(connection.id)) return
  testConnection.value = connection; testResult.value = results.value[connection.id] || null
  testError.value = ''; testVisible.value = true
}
async function runTest() {
  if (testing.value || !testConnection.value?.enabled) return
  if (!prompt.value.trim()) { testError.value = '请输入测试内容'; return }
  const connection = testConnection.value
  testing.value = true; busyIds.value.add(connection.id); testError.value = ''; testResult.value = null
  const started = performance.now()
  try {
    const systemPrompt = applySkills.value ? skillsStore.prompt() : ''
    const value = unwrap(await invokeModelConnection(connection.id, { prompt: prompt.value.trim(), temperature: .2, ...(systemPrompt ? { systemPrompt } : {}) }, connection.timeoutSeconds))
    if (typeof value?.content !== 'string' || !value.content.trim()) throw new Error('模型接口已响应，但未返回文本，请检查模型 ID 与接口兼容性')
    if (!disposed) {
      const result = { status: 'success', content: value.content, usage: value.usage || {}, durationMs: Math.round(performance.now() - started) }
      testResult.value = result; results.value[connection.id] = result
    }
  } catch (error) {
    if (!disposed) { testError.value = errorMessage(error); results.value[connection.id] = { status: 'error' } }
  } finally { testing.value = false; busyIds.value.delete(connection.id) }
}
function beforeTestClose(done) { if (!testing.value) done() }
onMounted(loadConnections)
onBeforeUnmount(() => { disposed = true; clearSecret() })
</script>

<template>
  <div class="model-settings">
    <header class="page-header"><div><p class="eyebrow">CONNECT / CONFIGURE / VERIFY</p><h1>模型接入中心</h1><p>把模型能力连接到你的运维工作空间。</p></div><RouterLink to="/model-strength">模型强度与用量 ↗</RouterLink></header>
    <IntegrationCard :connections="connections" :loading="loading" :unavailable="Boolean(loadError)" @create="openCreate" @select="openEdit" />
    <section id="model-connections" class="connections-section" aria-labelledby="connections-title">
      <div class="connections-heading"><div><h2 id="connections-title">已接入模型 <span>{{ connections.length }}</span></h2><p>{{ enabledCount }} 个已启用 · 测试结果仅保留在当前页面</p></div><button type="button" class="secondary" :disabled="loading || saving || busyIds.size > 0" @click="loadConnections">{{ loading ? '刷新中…' : '刷新列表' }}</button></div>
      <div class="filters"><label class="search"><span class="sr-only">搜索模型</span><input v-model="query" type="search" placeholder="搜索名称、服务商或模型 ID" aria-label="搜索模型"></label><label><span class="sr-only">筛选状态</span><select v-model="statusFilter" aria-label="筛选状态"><option value="all">全部状态</option><option value="enabled">已启用</option><option value="disabled">已停用</option></select></label></div>
      <p v-if="notice" class="notice" role="status">{{ notice }}</p>
      <p v-if="actionError" class="error" role="alert">{{ actionError }}</p>
      <div v-if="loadError" class="error-panel" role="alert"><strong>暂时无法读取模型连接</strong><p>{{ loadError }}</p><button type="button" class="secondary" :disabled="loading" @click="loadConnections">重试</button></div>
      <div v-if="loading && !connections.length" class="empty" role="status">正在读取模型连接…</div>
      <div v-else-if="visibleConnections.length" class="model-grid"><ModelConnectionCard v-for="connection in visibleConnections" :key="connection.id" :connection="connection" :busy="loading || busyIds.has(connection.id)" :result="results[connection.id]" @edit="openEdit" @delete="remove" @toggle="toggle" @test="openTest" /></div>
      <div v-else-if="!loadError" class="empty"><h3>{{ connections.length ? '没有匹配的模型' : '连接你的第一个模型' }}</h3><p>{{ connections.length ? '尝试其他关键词或筛选条件。' : '填写服务地址、模型 ID 和密钥，保存后即可发起测试。' }}</p><button v-if="!connections.length" type="button" class="primary" @click="openCreate">添加模型</button></div>
    </section>

    <el-dialog v-model="dialogVisible" :title="editingId !== null ? '编辑模型连接' : '添加模型连接'" width="min(560px, calc(100vw - 32px))" append-to-body destroy-on-close :close-on-click-modal="false" :before-close="beforeFormClose" @closed="clearSecret">
      <form class="model-form" @submit.prevent="save" novalidate>
        <p class="form-help">使用兼容 Chat Completions 的服务地址，系统会自动追加 /chat/completions。其他原生协议需要通过兼容网关接入。</p>
        <label v-for="field in fields" :key="field.key">{{ field.label }}<input v-model="form[field.key]" :aria-label="field.label" :type="field.type || 'text'" :disabled="saving" :aria-invalid="!!formErrors[field.key]" :aria-describedby="`model-${field.key}-error`" :placeholder="field.placeholder"><small :id="`model-${field.key}-error`" class="error">{{ formErrors[field.key] }}</small></label>
        <label>API Key<input v-model="form.apiKey" aria-label="API Key" type="password" autocomplete="new-password" :disabled="saving" :aria-invalid="!!formErrors.apiKey" aria-describedby="model-key-error" :placeholder="editingId !== null ? '留空保留原密钥' : '输入服务商的 API Key'"><small id="model-key-error" class="error">{{ formErrors.apiKey }}</small></label>
        <label>请求超时（秒）<input v-model.number="form.timeoutSeconds" aria-label="请求超时（秒）" type="number" min="5" max="300" step="1" :disabled="saving" :aria-invalid="!!formErrors.timeoutSeconds" aria-describedby="model-timeout-error"><small id="model-timeout-error" class="error">{{ formErrors.timeoutSeconds }}</small></label>
        <label class="checkbox"><input v-model="form.enabled" type="checkbox" :disabled="saving">启用此模型连接</label>
        <p v-if="saveError" role="alert" class="error">{{ saveError }}</p>
        <div class="form-actions"><button type="button" class="secondary" :disabled="saving" @click="dialogVisible = false">取消</button><button type="submit" class="primary" :disabled="saving">{{ saving ? '保存中…' : '保存连接' }}</button></div>
      </form>
    </el-dialog>

    <el-dialog v-model="testVisible" :title="`测试模型 · ${testConnection?.name || ''}`" width="min(640px, calc(100vw - 32px))" append-to-body :close-on-click-modal="false" :before-close="beforeTestClose">
      <form class="model-form" @submit.prevent="runTest">
        <p class="form-help">将向此连接发送一次真实文本请求，可能产生服务商用量费用。测试耗时包含后端和网络往返。</p>
        <label>测试内容<textarea v-model="prompt" rows="4" maxlength="12000" :disabled="testing" /></label>
        <label class="checkbox"><input v-model="applySkills" type="checkbox" :disabled="testing || !!skillsStore.error">应用已启用 Skill 和任务目标（{{ skillsStore.enabled.length }} 项）</label>
        <p v-if="applySkills" class="form-help">本次请求将附加技能中心保存的目标和指令。Skill 不授予工具执行权限。<RouterLink to="/skills">管理技能</RouterLink></p>
        <p v-if="testError" role="alert" class="error">{{ testError }}</p>
        <div class="form-actions"><button type="submit" class="primary" :disabled="testing">{{ testing ? '等待模型响应…' : '发送测试' }}</button></div>
        <section v-if="testResult?.status === 'success'" class="test-output" aria-live="polite"><h3>模型回复</h3><div class="test-metrics"><span>{{ testResult.durationMs }} ms</span><span v-if="testResult.usage.total_tokens != null">{{ testResult.usage.total_tokens }} tokens</span><span v-else>服务商未返回 Token 用量</span></div><pre>{{ testResult.content }}</pre></section>
      </form>
    </el-dialog>
  </div>
</template>

<style scoped>
.model-settings{padding:32px 0 0;display:grid;gap:30px}.page-header{padding:0 0 22px;display:flex;justify-content:space-between;align-items:center;gap:20px}.eyebrow{font:10px var(--font-mono);letter-spacing:.15em;color:var(--smart-primary-strong)}h1{margin:10px 0;font-size:30px;font-weight:500}.page-header p:not(.eyebrow),.connections-heading p{color:var(--smart-muted);font-size:13px}.page-header a{color:var(--smart-primary-strong);font-size:13px;white-space:nowrap}.connections-section{display:grid;gap:18px;scroll-margin-top:80px}.connections-heading{display:flex;justify-content:space-between;align-items:center;gap:16px}.connections-heading h2{font-size:19px;margin:0}.connections-heading h2 span{font-size:13px;color:var(--smart-muted);margin-left:8px}.connections-heading p{margin:8px 0 0}.filters{display:flex;gap:12px}.search{flex:1}.filters input,.filters select{height:42px;width:100%;border:1px solid var(--smart-border);border-radius:9px;padding:0 12px;background:var(--smart-surface);color:var(--smart-text)}.model-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));gap:16px}.empty{padding:40px 20px;border:1px dashed var(--smart-border);border-radius:12px;text-align:center;color:var(--smart-muted)}.empty h3{color:var(--smart-text)}.empty p{font-size:13px}.notice{color:var(--smart-primary-strong);font-size:13px}.error,.error-panel{color:var(--smart-danger,#f08d9c)}.error-panel{padding:18px;border:1px solid currentColor;border-radius:10px}.error-panel p{font-size:13px}
.primary,.secondary{min-height:40px;padding:10px 16px;border:1px solid var(--smart-border);border-radius:9px;cursor:pointer;font-size:13px}.primary{background:var(--smart-primary);color:var(--smart-accent-foreground);border-color:transparent}.secondary{background:var(--smart-surface);color:var(--smart-text)}button:disabled{opacity:.5;cursor:wait}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid var(--smart-primary-strong);outline-offset:3px}.sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
.model-form{display:grid;gap:16px;color:var(--smart-text)}.model-form label{display:grid;gap:7px;font-size:13px}.model-form input:not([type=checkbox]),.model-form textarea{width:100%;box-sizing:border-box;min-width:0;padding:10px 12px;border:1px solid var(--smart-border);border-radius:8px;background:var(--smart-surface);color:var(--smart-text);font:inherit}.model-form textarea{resize:vertical;line-height:1.65}.model-form input[aria-invalid=true]{border-color:var(--smart-danger)}.model-form small:empty{display:none}.model-form .checkbox{display:flex;align-items:center;gap:9px}.model-form .checkbox input{width:16px;height:16px}.form-help{margin:0;color:var(--smart-muted);font-size:12px;line-height:1.7}.form-actions{display:flex;justify-content:flex-end;gap:10px}.test-output{padding:16px;border:1px solid var(--smart-border);border-radius:10px}.test-output h3{margin:0;font-size:15px}.test-metrics{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;color:var(--smart-primary-strong);font-size:12px}.test-output pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.8 var(--font-cn);max-height:320px;overflow:auto}.error{font-size:12px;line-height:1.6}@media(max-width:600px){.page-header{align-items:flex-start}.page-header h1{font-size:25px}.page-header a{margin-top:16px}.model-settings{padding-top:24px}.filters{flex-wrap:wrap}.search{min-width:180px}}
</style>
