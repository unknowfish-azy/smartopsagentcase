<template>
  <section aria-labelledby="dept-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">SYSTEM / 组织架构</p><h1 id="dept-title">部门管理</h1></div><button class="admin-primary" @click="open('create')">新增部门</button></header>
    <p class="admin-muted">部门为树形结构；删除有子部门或有用户的部门会被拒绝。写操作需输入管理员密码复核。</p>
    <p v-if="success" class="admin-notice" role="status">{{ success }}</p>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载部门…</p>
    <div v-if="data" class="admin-table-wrap" tabindex="0" aria-label="部门列表">
      <table><thead><tr><th scope="col">部门名称</th><th scope="col">负责人</th><th scope="col">电话</th><th scope="col">排序</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead>
        <tbody><tr v-for="row in flattened" :key="row.id"><td><span :style="{ paddingLeft: (row.depth * 20) + 'px' }">{{ row.depth > 0 ? '└ ' : '' }}{{ row.name }}</span></td><td>{{ row.leader || '—' }}</td><td>{{ row.phone || '—' }}</td><td>{{ row.sort }}</td><td><span class="admin-status-tag" :class="row.status === 1 ? 'admin-status-tag--on' : 'admin-status-tag--off'">{{ row.status === 1 ? '启用' : '停用' }}</span></td><td><div class="admin-actions"><button @click="open('create', row)">加子部门</button><button @click="open('edit', row)">编辑</button><button @click="toggle(row)">{{ row.status === 1 ? '停用' : '启用' }}</button><button @click="remove(row)">删除</button></div></td></tr></tbody>
      </table><p v-if="!flattened.length" class="admin-empty">还没有部门，点击「新增部门」创建。</p>
    </div>
    <AdminDialog v-if="action" :title="dialogTitle" :busy="saving" @close="close">
      <form class="admin-form" @submit.prevent="save">
        <label>上级部门<select v-model="draft.parentId"><option :value="0">（顶级部门）</option><option v-for="row in flattened" :key="row.id" :value="row.id" :disabled="row.id === target?.id">{{ '　'.repeat(row.depth) }}{{ row.name }}</option></select></label>
        <label>部门名称<input v-model.trim="draft.name" required maxlength="64"></label>
        <label>负责人<input v-model.trim="draft.leader" maxlength="32"></label>
        <label>联系电话<input v-model.trim="draft.phone" maxlength="32"></label>
        <label>排序<input v-model.number="draft.sort" type="number" min="0"></label>
        <label>管理员复核密码<input v-model="adminPassword" type="password" autocomplete="current-password" required :disabled="saving"></label>
        <small>输入你当前登录的管理员密码，仅用于本次身份复核。</small>
        <p v-if="saveError" class="admin-error" role="alert">{{ saveError }}</p>
        <footer><button type="button" :disabled="saving" @click="close">取消</button><button class="admin-primary" type="submit" :disabled="saving">{{ saving ? '提交中…' : '保存' }}</button></footer>
      </form>
    </AdminDialog>
  </section>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { systemApi } from '../../../api/adminSystem.js'
import { useAdminResource } from '../../../composables/useAdminResource.js'
import AdminDialog from '../../../components/admin/AdminDialog.vue'
const { data, loading, error, load } = useAdminResource(() => systemApi.depts())
const action = ref('')
const saving = ref(false)
const saveError = ref('')
const success = ref('')
const target = ref(null)
const adminPassword = ref('')
const draft = reactive({ parentId: 0, name: '', leader: '', phone: '', sort: 0 })
const dialogTitle = computed(() => ({ create: '新增部门', edit: '编辑部门' })[action.value])

const flattened = computed(() => {
  const out = []
  const walk = (nodes, depth) => { for (const node of nodes || []) { out.push({ ...node, depth }); walk(node.children, depth + 1) } }
  walk(data.value, 0)
  return out
})

function open(kind, dept = null) {
  target.value = dept
  action.value = kind
  saveError.value = ''
  success.value = ''
  adminPassword.value = ''
  if (kind === 'create' && dept) Object.assign(draft, { parentId: dept.id, name: '', leader: '', phone: '', sort: 0 })
  else if (dept) Object.assign(draft, { parentId: dept.parent_id, name: dept.name, leader: dept.leader || '', phone: dept.phone || '', sort: dept.sort })
  else Object.assign(draft, { parentId: 0, name: '', leader: '', phone: '', sort: 0 })
}
function close() { if (saving.value) return; action.value = ''; saveError.value = '' }
async function save() {
  if (saving.value) return
  saveError.value = ''
  if (!adminPassword.value) { saveError.value = '请输入管理员复核密码'; return }
  const password = adminPassword.value; adminPassword.value = ''
  saving.value = true
  try {
    if (action.value === 'create') await systemApi.createDept(draft, password)
    else await systemApi.updateDept(target.value.id, draft, password)
    action.value = ''
    success.value = '部门已保存。'
    await load()
  } catch (failure) { saveError.value = failure.message || '保存失败，请重试' }
  finally { saving.value = false }
}
function askPassword(label) { return window.prompt(`请输入当前管理员密码以${label}（仅用于本次身份复核）`) }
async function toggle(dept) {
  const password = askPassword(dept.status === 1 ? '停用部门' : '启用部门')
  if (!password) return
  success.value = ''; error.value = ''
  try { await systemApi.deptStatus(dept.id, dept.status === 1 ? 0 : 1, password); success.value = '部门状态已更新。'; await load() }
  catch (failure) { error.value = failure.message || '操作失败' }
}
async function remove(dept) {
  if (!window.confirm(`确认删除部门「${dept.name}」？`)) return
  const password = askPassword('删除部门')
  if (!password) return
  success.value = ''; error.value = ''
  try { await systemApi.deleteDept(dept.id, password); success.value = '部门已删除。'; await load() }
  catch (failure) { error.value = failure.message || '删除失败' }
}
</script>
