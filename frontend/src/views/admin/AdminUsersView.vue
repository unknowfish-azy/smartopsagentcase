<template>
  <section aria-labelledby="users-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">IDENTITY / 账户生命周期</p><h1 id="users-title">账户管理</h1></div><button class="admin-primary" @click="open('create')">新增账号</button></header>
    <p class="admin-muted">角色属于账号，入口属于会话。部门/岗位/RBAC 角色可从「组织」动作绑定，写操作需管理员密码复核。</p>
    <AdminRegistrationPolicy />
    <form class="admin-filters" @submit.prevent="search">
      <label>搜索账号<input v-model.trim="filters.q" type="search" placeholder="按账号子串搜索" maxlength="64"></label>
      <label>账号角色<select v-model="filters.role"><option value="">全部角色</option><option value="operator">运维用户</option><option value="admin">管理员</option></select></label>
      <label>账号状态<select v-model="filters.enabled"><option value="">全部状态</option><option value="true">启用</option><option value="false">禁用</option></select></label>
      <button type="submit" :disabled="loading">查询</button>
    </form>
    <p v-if="success" class="admin-notice" role="status">{{ success }}</p>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载账户…</p>
    <p v-if="data" id="users-scroll-hint" class="admin-table-hint">左右滑动查看完整列表及操作；键盘可聚焦列表后使用左右方向键。</p>
    <div v-if="data" class="admin-table-wrap" tabindex="0" aria-label="账户列表，可横向滚动" aria-describedby="users-scroll-hint">
      <table><thead><tr><th scope="col">账号</th><th scope="col">角色</th><th scope="col">部门</th><th scope="col">岗位</th><th scope="col">状态</th><th scope="col">密码状态</th><th scope="col">创建时间</th><th scope="col">操作</th></tr></thead>
        <tbody><tr v-for="account in data.items" :key="account.id"><td>{{ account.username }}<span v-if="account.id === currentSession?.id" class="admin-badge">本人</span></td><td>{{ account.role === 'admin' ? '管理员' : '运维用户' }}</td><td>{{ deptName(account.deptId) }}</td><td>{{ postName(account.postId) }}</td><td>{{ account.enabled ? '启用' : '禁用' }}</td><td>{{ account.mustChangePassword ? '待首次改密' : '正常' }}</td><td>{{ formatAdminTime(account.createdAt) }}</td><td><div class="admin-actions"><button @click="open('status', account)">{{ account.enabled ? '禁用' : '启用' }}</button><button @click="open('role', account)">变更角色</button><button @click="open('org', account)">组织</button><button @click="open('reset', account)">重置密码</button></div></td></tr></tbody>
      </table><p v-if="!data.items.length" class="admin-empty">没有匹配的账户，请调整查询条件。</p>
    </div>
    <AdminPagination :total="data?.total || 0" :page="query.page" :page-size="query.pageSize" :loading="loading || !!error" @page="changePage" @resize="resize" />
    <AdminDialog v-if="action" :title="dialogTitle" :busy="saving" @close="close">
      <form class="admin-form" @submit.prevent="save">
        <template v-if="action === 'create'">
          <label>账号<input v-model.trim="draft.username" autocomplete="off" required maxlength="100"></label>
          <label>初始密码<input v-model="draft.password" type="password" autocomplete="new-password" required></label>
          <label>账号角色<select v-model="draft.role"><option value="operator">运维用户</option><option value="admin">管理员</option></select></label>
          <label>所属部门<select v-model="draft.deptId"><option :value="null">（不绑定）</option><option v-for="d in deptOptions" :key="d.id" :value="d.id">{{ d.indent }}{{ d.name }}</option></select></label>
          <label>岗位<select v-model="draft.postId"><option :value="null">（不绑定）</option><option v-for="p in posts" :key="p.id" :value="p.id">{{ p.name }}</option></select></label>
          <fieldset class="admin-check-group"><legend>RBAC 角色</legend><label v-for="r in roles" :key="r.id" class="admin-check"><input type="checkbox" :value="r.id" v-model="draft.roleIds">{{ r.name }}</label></fieldset>
          <p class="admin-notice">创建后必须首次改密，初始密码不会回显或保存在浏览器中。</p>
        </template>
        <template v-else-if="action === 'org'">
          <p>目标账户：<strong>{{ target.username }}</strong></p>
          <label>所属部门<select v-model="draft.deptId"><option :value="null">（不绑定）</option><option v-for="d in deptOptions" :key="d.id" :value="d.id">{{ d.indent }}{{ d.name }}</option></select></label>
          <label>岗位<select v-model="draft.postId"><option :value="null">（不绑定）</option><option v-for="p in posts" :key="p.id" :value="p.id">{{ p.name }}</option></select></label>
          <fieldset class="admin-check-group"><legend>RBAC 角色</legend><label v-for="r in roles" :key="r.id" class="admin-check"><input type="checkbox" :value="r.id" v-model="draft.roleIds">{{ r.name }}</label></fieldset>
        </template>
        <template v-else>
          <p>目标账户：<strong>{{ target.username }}</strong></p>
          <label v-if="action === 'role'">新角色<select v-model="draft.role"><option value="operator">运维用户</option><option value="admin">管理员</option></select></label>
          <label v-if="action === 'reset'">临时密码<input v-model="draft.password" type="password" autocomplete="new-password" aria-describedby="reset-password-guidance" required></label>
          <small v-if="action === 'reset'" id="reset-password-guidance">临时密码不能与目标账户的旧密码相同；服务端校验失败时不会完成重置。</small>
          <p v-if="action === 'status'">将{{ target.enabled ? '禁用' : '启用' }}此账号。</p>
          <p class="admin-notice">此操作会撤销目标账户的旧会话及终端连接，要求重新登录。{{ action === 'reset' ? '重置后必须首次改密。' : '最后一个启用管理员不能被禁用或降权。' }}{{ target.id === currentSession?.id ? '这是你当前使用的账号，操作成功后将退出。' : '' }}</p>
        </template>
        <small v-if="action === 'create' || action === 'reset'">{{ passwordRole === 'admin' ? '管理员密码至少 16 字符' : '普通密码至少 12 字符' }}，不超过 72 UTF-8 字节。</small>
        <p v-if="action === 'role' && draft.role === 'admin'" class="admin-notice">提升为管理员后将强制修改密码，满足管理员密码策略。</p>
        <label>当前管理员密码<input v-model="adminPassword" type="password" autocomplete="current-password" required :disabled="saving" aria-describedby="admin-verify-guidance"></label>
        <small id="admin-verify-guidance">输入你当前登录的管理员密码，仅用于本次身份复核；不是目标账户的新密码，不会保存。</small>
        <p v-if="saveError" class="admin-error" role="alert">{{ saveError }}</p>
        <footer><button type="button" :disabled="saving" @click="close">取消</button><button class="admin-primary" type="submit" :disabled="saving">{{ saving ? '提交中…' : action === 'create' ? '创建账号' : action === 'reset' ? '确认重置' : '确认变更' }}</button></footer>
      </form>
    </AdminDialog>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi } from '../../api/admin.ts'
import { systemApi } from '../../api/adminSystem.ts'
import { currentSession, clearSession } from '../../security/session.js'
import { useAdminResource, formatAdminTime } from '../../composables/useAdminResource.js'
import AdminDialog from '../../components/admin/AdminDialog.vue'
import AdminRegistrationPolicy from '../../components/admin/AdminRegistrationPolicy.vue'
import { passwordError } from '../../security/passwordPolicy.js'
import AdminPagination from '../../components/admin/AdminPagination.vue'
const router = useRouter()
const filters = reactive({ q: '', role: '', enabled: '' })
const query = reactive({ q: '', role: '', enabled: '', page: 1, pageSize: 20 })
const { data, loading, error, load } = useAdminResource(() => adminApi.users({ ...query }))
const action = ref('')
const target = ref(null)
const saving = ref(false)
const saveError = ref('')
const success = ref('')
const adminPassword = ref('')
const passwordRole = computed(() => action.value === 'create' ? draft.role : target.value?.role)
const draft = reactive({ username: '', password: '', role: 'operator', deptId: null, postId: null, roleIds: [] })
const dialogTitle = computed(() => ({ create: '新增账号', status: '确认账户状态变更', role: '确认角色变更', org: '组织与 RBAC 角色', reset: '确认密码重置' })[action.value])

// 部门/岗位/RBAC 角色选项
const depts = ref([])
const posts = ref([])
const roles = ref([])
const deptOptions = computed(() => {
  const out = []
  const walk = (nodes, depth) => { for (const n of nodes || []) { out.push({ ...n, indent: '　'.repeat(depth) }); walk(n.children, depth + 1) } }
  walk(depts.value, 0)
  return out
})
const deptName = id => id ? deptOptions.value.find(d => d.id === id)?.name || `#${id}` : '—'
const postName = id => id ? posts.value.find(p => p.id === id)?.name || `#${id}` : '—'
async function loadOrg() {
  try { [depts.value, posts.value, roles.value] = await Promise.all([systemApi.depts(), systemApi.posts(), systemApi.roles()]) } catch { /* 组织选项加载失败不阻断账户页 */ }
}

function search() { Object.assign(query, filters, { page: 1 }); success.value = ''; load() }
function changePage(page) { query.page = page; load() }
function resize(pageSize) { query.pageSize = pageSize; changePage(1) }
function open(kind, account = null) {
  adminPassword.value = ''
  target.value = account
  action.value = kind
  saveError.value = ''
  success.value = ''
  Object.assign(draft, { username: '', password: '', role: kind === 'role' && account?.role === 'operator' ? 'admin' : account?.role || 'operator', deptId: account?.deptId ?? null, postId: account?.postId ?? null, roleIds: account?.roleIds ? [...account.roleIds] : [] })
}
function close() { if (saving.value) return; action.value = ''; draft.password = ''; adminPassword.value = ''; saveError.value = '' }
async function save() {
  if (saving.value) return
  saveError.value = ''
  const verificationPassword = adminPassword.value
  adminPassword.value = ''
  if (!verificationPassword) { saveError.value = '请输入当前管理员密码'; return }
  if (action.value === 'create' || action.value === 'reset') {
    saveError.value = passwordError(draft.password, passwordRole.value)
    if (saveError.value) return
  }
  saving.value = true
  const kind = action.value
  const account = target.value
  try {
    if (kind === 'create') await adminApi.createUser({ username: draft.username, password: draft.password, role: draft.role, deptId: draft.deptId, postId: draft.postId, roleIds: draft.roleIds }, verificationPassword)
    else if (kind === 'reset') await adminApi.resetPassword(account.id, draft.password, verificationPassword)
    else if (kind === 'org') await adminApi.updateUser(account.id, { role: account.role, enabled: account.enabled, deptId: draft.deptId, postId: draft.postId, roleIds: draft.roleIds }, verificationPassword)
    else {
      if (kind === 'role' && draft.role === account.role) { saveError.value = '请选择不同的新角色'; return }
      await adminApi.updateUser(account.id, { role: kind === 'role' ? draft.role : account.role, enabled: kind === 'status' ? !account.enabled : account.enabled, deptId: account.deptId, postId: account.postId, roleIds: account.roleIds }, verificationPassword)
    }
    draft.password = ''
    action.value = ''
    if (kind !== 'create' && account.id === currentSession.value?.id) {
      clearSession()
      await router.replace({ path: '/login', query: { reason: 'account-changed', portal: 'admin' } })
      return
    }
    success.value = kind === 'create' ? '账户已创建，首次登录必须修改密码。' : '变更已完成，目标账户旧会话已撤销。'
    await load()
  } catch (failure) { saveError.value = failure.message || '操作失败，请重试' }
  finally { adminPassword.value = ''; draft.password = ''; saving.value = false }
}
onMounted(() => { load(); loadOrg() })
</script>
