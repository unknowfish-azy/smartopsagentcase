<template>
  <section aria-labelledby="menu-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">SYSTEM / 权限模型</p><h1 id="menu-title">菜单管理</h1></div><button class="admin-primary" @click="open('create')">新增菜单</button></header>
    <p class="admin-muted">菜单三级：目录/菜单/按钮；按钮权限标识用 system:module:action 三段式。写操作需输入管理员密码复核。</p>
    <p v-if="success" class="admin-notice" role="status">{{ success }}</p>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载菜单…</p>
    <div v-if="data" class="admin-table-wrap" tabindex="0" aria-label="菜单列表">
      <table><thead><tr><th scope="col">菜单名称</th><th scope="col">类型</th><th scope="col">路由</th><th scope="col">权限标识</th><th scope="col">排序</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead>
        <tbody><tr v-for="row in flattened" :key="row.id"><td><span :style="{ paddingLeft: (row.depth * 20) + 'px' }">{{ row.depth > 0 ? '└ ' : '' }}{{ row.name }}</span></td><td>{{ typeLabel(row.type) }}</td><td><code>{{ row.path || '—' }}</code></td><td><code>{{ row.perms || '—' }}</code></td><td>{{ row.sort }}</td><td><span class="admin-status-tag" :class="row.status === 1 ? 'admin-status-tag--on' : 'admin-status-tag--off'">{{ row.status === 1 ? '启用' : '停用' }}</span></td><td><div class="admin-actions"><button @click="open('create', row)">加子项</button><button @click="open('edit', row)">编辑</button><button @click="toggle(row)">{{ row.status === 1 ? '停用' : '启用' }}</button><button @click="remove(row)">删除</button></div></td></tr></tbody>
      </table><p v-if="!flattened.length" class="admin-empty">还没有菜单，点击「新增菜单」创建。</p>
    </div>
    <AdminDialog v-if="action" :title="dialogTitle" :busy="saving" @close="close">
      <form class="admin-form" @submit.prevent="save">
        <label>上级菜单<select v-model="draft.parentId"><option :value="0">（顶级）</option><option v-for="row in flattened" :key="row.id" :value="row.id" :disabled="row.id === target?.id">{{ '\u3000'.repeat(row.depth) }}{{ row.name }}</option></select></label>
        <label>类型<select v-model.number="draft.type"><option :value="1">目录</option><option :value="2">菜单</option><option :value="3">按钮</option></select></label>
        <label>菜单名称<input v-model.trim="draft.name" required maxlength="64"></label>
        <label>路由路径<input v-model.trim="draft.path" maxlength="200" placeholder="如 /system/dept"></label>
        <label v-if="draft.type !== 3">组件路径<input v-model.trim="draft.component" maxlength="200"></label>
        <label v-if="draft.type === 3">权限标识<input v-model.trim="draft.perms" maxlength="200" placeholder="如 system:dept:add"></label>
        <label>图标<input v-model.trim="draft.icon" maxlength="64"></label>
        <label>排序<input v-model.number="draft.sort" type="number" min="0"></label>
        <label class="admin-check"><input type="checkbox" v-model="draft.visible"> 显示</label>
        <label>管理员复核密码<input v-model="adminPassword" type="password" autocomplete="current-password" required :disabled="saving"></label>
        <p v-if="saveError" class="admin-error" role="alert">{{ saveError }}</p>
        <footer><button type="button" :disabled="saving" @click="close">取消</button><button class="admin-primary" type="submit" :disabled="saving">{{ saving ? '提交中…' : '保存' }}</button></footer>
      </form>
    </AdminDialog>
    <AdminConfirmAction :open="!!passwordRequest" :title="passwordRequest?.title || ''" :description="passwordRequest?.description || ''" :busy="confirmBusy" :error="confirmError" @confirm="confirmPassword" @cancel="cancelPassword" />
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { systemApi } from '../../../api/adminSystem.ts'
import { useAdminResource } from '../../../composables/useAdminResource.js'
import AdminDialog from '../../../components/admin/AdminDialog.vue'
import AdminConfirmAction from '../../../components/admin/AdminConfirmAction.vue'
const { data, loading, error, load } = useAdminResource(() => systemApi.menus())
onMounted(load)
const action = ref('')
const saving = ref(false)
const saveError = ref('')
const success = ref('')
const target = ref(null)
const adminPassword = ref('')
const draft = reactive({ parentId: 0, name: '', type: 2, path: '', component: '', perms: '', icon: '', sort: 0, visible: true })
const dialogTitle = computed(() => ({ create: '新增菜单', edit: '编辑菜单' })[action.value])
const typeLabel = type => ({ 1: '目录', 2: '菜单', 3: '按钮' })[type] || type

const flattened = computed(() => {
  const out = []
  const walk = (nodes, depth) => { for (const node of nodes || []) { out.push({ ...node, depth }); walk(node.children, depth + 1) } }
  walk(data.value, 0)
  return out
})

function open(kind, menu = null) {
  target.value = menu
  action.value = kind
  saveError.value = ''
  success.value = ''
  adminPassword.value = ''
  if (kind === 'create' && menu) Object.assign(draft, { parentId: menu.id, name: '', type: 2, path: '', component: '', perms: '', icon: '', sort: 0, visible: true })
  else if (menu) Object.assign(draft, { parentId: menu.parent_id, name: menu.name, type: menu.type, path: menu.path || '', component: menu.component || '', perms: menu.perms || '', icon: menu.icon || '', sort: menu.sort, visible: menu.visible === 1 })
  else Object.assign(draft, { parentId: 0, name: '', type: 2, path: '', component: '', perms: '', icon: '', sort: 0, visible: true })
}
function close() { if (saving.value) return; action.value = ''; saveError.value = '' }
async function save() {
  if (saving.value) return
  saveError.value = ''
  if (!adminPassword.value) { saveError.value = '请输入管理员复核密码'; return }
  const password = adminPassword.value; adminPassword.value = ''
  saving.value = true
  try {
    if (action.value === 'create') await systemApi.createMenu(draft, password)
    else await systemApi.updateMenu(target.value.id, draft, password)
    action.value = ''
    success.value = '菜单已保存。'
    await load()
  } catch (failure) { saveError.value = failure.message || '保存失败，请重试' }
  finally { saving.value = false }
}
const passwordRequest = ref(null)
const confirmBusy = ref(false)
const confirmError = ref('')
function askPassword(title, description, fallback, action) { confirmError.value = ''; passwordRequest.value = { title, description, fallback, action } }
function cancelPassword() { if (confirmBusy.value) return; passwordRequest.value = null; confirmError.value = '' }
async function confirmPassword(password) {
  if (confirmBusy.value || !passwordRequest.value) return
  const request = passwordRequest.value
  confirmError.value = ''
  confirmBusy.value = true
  try { await request.action(password); passwordRequest.value = null }
  catch (failure) { confirmError.value = failure.message || request.fallback }
  finally { confirmBusy.value = false }
}
function toggle(menu) {
  const label = menu.status === 1 ? '停用菜单' : '启用菜单'
  askPassword(label, `请输入当前管理员密码以${label}（仅用于本次身份复核）`, '操作失败', async password => {
    success.value = ''; error.value = ''
    await systemApi.menuStatus(menu.id, menu.status === 1 ? 0 : 1, password)
    success.value = '菜单状态已更新。'
    await load()
  })
}
function remove(menu) {
  if (!window.confirm(`确认删除菜单「${menu.name}」？`)) return
  askPassword('删除菜单', `请输入当前管理员密码以删除菜单「${menu.name}」（仅用于本次身份复核）`, '删除失败', async password => {
    success.value = ''; error.value = ''
    await systemApi.deleteMenu(menu.id, password)
    success.value = '菜单已删除。'
    await load()
  })
}
</script>
