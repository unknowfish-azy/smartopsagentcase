<template>
  <section class="admin-governance" aria-labelledby="governance-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">GOVERNANCE / PLATFORM ADMINS</p><h1 id="governance-title">管理员与授权</h1><p class="admin-muted">平台身份与团队职务分离；当前页面只展示授权，不显示密钥或私人资源。能力目录与可转授范围由服务端下发。</p></div><button type="button" :disabled="loading" @click="load">{{ loading ? '读取中…' : '刷新' }}</button></header>
    <AdminErrorState :message="error" :busy="loading" @retry="load()" />
    <p v-if="catalogError" class="admin-error" role="alert">{{ catalogError }} <button type="button" @click="loadCatalog">重试</button></p>
    <p v-if="loading && !items.length" role="status">正在加载管理员授权…</p>
    <form class="admin-filters" @submit.prevent="appoint">
      <label>目标管理员账号
        <select v-model="form.id" required :disabled="loading || saving">
          <option value="" disabled>选择管理员账号</option>
          <option v-for="account in candidates" :key="account.id" :value="account.id">{{ account.username }}（ID {{ account.id }}{{ account.enabled ? '' : '，已禁用' }}）</option>
        </select>
      </label>
      <label>级别<select v-model="form.level" :disabled="loading || saving || !catalog.manageableLevels.length"><option v-for="level in catalog.manageableLevels" :key="level" :value="level">{{ labels[level] || level }}</option></select></label>
      <fieldset class="admin-check-group"><legend>平台能力（仅列出可转授项）</legend>
        <label v-for="capability in catalog.items" :key="capability.value" class="admin-check" :class="{ 'is-locked': !capability.grantable }">
          <input type="checkbox" :value="capability.value" v-model="form.capabilities" :disabled="!capability.grantable || loading || saving">
          {{ capability.label }}<span class="admin-muted">{{ capability.value }}</span>
        </label>
        <small v-if="!catalog.items.some(item => item.grantable)">当前级别没有可转授能力。</small>
      </fieldset>
      <label>当前管理员密码<input v-model="form.password" type="password" required autocomplete="current-password" :disabled="loading || saving" aria-describedby="governance-password-guidance"></label>
      <small id="governance-password-guidance">仅用于本次身份复核，不会保存；任命会提升目标账号并使其旧会话重新登录。</small>
      <button type="submit" :disabled="loading || saving || !form.id">任命或更新</button>
    </form>
    <div v-if="items.length" class="admin-table-wrap"><table><thead><tr><th scope="col">账号</th><th scope="col">级别</th><th scope="col">入口状态</th><th scope="col">平台能力</th><th scope="col">操作</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td>{{ item.username }}<span class="admin-muted"> · ID {{ item.id }}</span></td><td><span class="admin-status admin-status--muted">{{ labels[item.level] || item.level }}</span></td><td><span class="admin-status" :class="item.enabled ? 'admin-status--success' : 'admin-status--muted'">{{ item.enabled ? '启用' : '禁用' }}</span></td><td><span v-if="!item.capabilities.length" class="admin-muted">未授予专项能力</span><span v-else>{{ capabilityText(item.capabilities) }}</span></td><td><div class="admin-actions"><button v-if="item.level !== 'root'" type="button" :disabled="loading || saving" @click="selected = item">撤销管理员</button></div></td></tr></tbody></table></div>
    <p v-else-if="!loading" class="admin-empty">暂无管理员授权资料。</p>
    <form v-if="selected" class="admin-filters" @submit.prevent="revoke">
      <strong>撤销 {{ selected.username }}（ID {{ selected.id }}）</strong>
      <p class="admin-notice">撤销后保留档案与撤销时间，能力立即清空且不能再次任命为同级；目标账号的旧会话会失效。</p>
      <label>当前管理员密码<input v-model="revokePassword" type="password" required autocomplete="current-password" :disabled="loading || saving"></label>
      <button type="submit" :disabled="loading || saving">确认撤销</button>
      <button type="button" :disabled="loading || saving" @click="cancelRevoke">取消</button>
    </form>
  </section>
</template>
<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { adminApi } from '../../api/admin.ts'
import AdminErrorState from '../../components/admin/AdminErrorState.vue'
import { useAdminResource } from '../../composables/useAdminResource.js'
const labels = { root: '最高管理员', deputy: '副管理员', specialist: '专项管理员' }
const { data, loading, error, load } = useAdminResource(() => adminApi.governance())
const items = computed(() => data.value || [])
const candidates = ref([])
const catalog = reactive({ level: '', manageableLevels: [], items: [] })
const catalogError = ref('')
const form = reactive({ id: '', level: '', capabilities: [], password: '' })
const selected = ref(null)
const revokePassword = ref('')
// 普通刷新不会置 loading，这里用独立 busy 防止复核密码被重复提交。
const saving = ref(false)
const capabilityText = values => values.map(value => catalog.items.find(item => item.value === value)?.label || value).join(' · ')

async function loadCatalog() {
  catalogError.value = ''
  try {
    const result = await adminApi.capabilities()
    Object.assign(catalog, result)
    if (!catalog.manageableLevels.includes(form.level)) form.level = catalog.manageableLevels[0] || ''
    form.capabilities = form.capabilities.filter(value => catalog.items.some(item => item.value === value && item.grantable))
  } catch (failure) { catalogError.value = failure.message || '能力目录加载失败' }
}
async function loadCandidates() {
  try { candidates.value = (await adminApi.users({ role: 'admin', page: 1, pageSize: 100 })).items } catch { candidates.value = [] }
}
// 级别切换后丢弃该级别不可转授的能力，避免提交被服务端拒绝的越权组合。
watch(() => form.level, () => {
  form.capabilities = form.capabilities.filter(value => catalog.items.some(item => item.value === value && item.grantable))
})
onMounted(() => { load(); loadCatalog(); loadCandidates() })
async function appoint() {
  if (saving.value) return
  saving.value = true
  const value = { ...form, capabilities: [...form.capabilities] }
  const password = form.password
  form.password = ''
  error.value = ''
  try {
    await adminApi.appointAdmin(value.id, { level: value.level, capabilities: value.capabilities }, password)
    form.capabilities = []
    await Promise.all([load({ preserve: true }), loadCandidates()])
  } catch (failure) { error.value = failure.message || '管理员任命失败' } finally { saving.value = false; form.password = '' }
}
async function revoke() {
  if (!selected.value || saving.value) return
  saving.value = true
  const password = revokePassword.value
  revokePassword.value = ''
  error.value = ''
  try {
    await adminApi.revokeAdmin(selected.value.id, password)
    selected.value = null
    await Promise.all([load({ preserve: true }), loadCandidates()])
  } catch (failure) { error.value = failure.message || '管理员撤销失败' } finally { saving.value = false; revokePassword.value = '' }
}
function cancelRevoke() { selected.value = null; revokePassword.value = '' }
</script>
<style scoped>
.admin-check-group .admin-check { display: flex; align-items: center; gap: 6px; }
.admin-check.is-locked { opacity: .55; }
.admin-check .admin-muted { font-size: 12px; }
</style>
