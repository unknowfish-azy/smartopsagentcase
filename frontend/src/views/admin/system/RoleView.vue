<template>
  <section aria-labelledby="role-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">SYSTEM / 权限模型</p><h1 id="role-title">角色管理</h1></div><button class="admin-primary" @click="open('create')">新增角色</button></header>
    <p class="admin-muted">角色通过菜单/按钮权限控制可见范围；授权采用整树替换。写操作需输入管理员密码复核。</p>
    <p v-if="success" class="admin-notice" role="status">{{ success }}</p>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载角色…</p>
    <div v-if="data" class="admin-table-wrap" tabindex="0" aria-label="角色列表">
      <table><thead><tr><th scope="col">角色名称</th><th scope="col">编码</th><th scope="col">数据权限</th><th scope="col">用户数</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead>
        <tbody><tr v-for="role in data" :key="role.id"><td>{{ role.name }}</td><td><code>{{ role.code }}</code></td><td>{{ scopeLabel(role.data_scope) }}</td><td>{{ role.userCount }}</td><td><span class="admin-status-tag" :class="role.status === 1 ? 'admin-status-tag--on' : 'admin-status-tag--off'">{{ role.status === 1 ? '启用' : '停用' }}</span></td><td><div class="admin-actions"><button @click="open('grant', role)">授权</button><button @click="open('edit', role)">编辑</button><button @click="toggle(role)">{{ role.status === 1 ? '停用' : '启用' }}</button><button @click="remove(role)">删除</button></div></td></tr></tbody>
      </table><p v-if="!data.length" class="admin-empty">还没有角色，点击「新增角色」创建。</p>
    </div>

    <AdminDialog v-if="action === 'create' || action === 'edit'" :title="action === 'create' ? '新增角色' : '编辑角色'" :busy="saving" @close="close">
      <form class="admin-form" @submit.prevent="save">
        <label>角色名称<input v-model.trim="draft.name" required maxlength="64"></label>
        <label>角色编码<input v-model.trim="draft.code" required maxlength="64" placeholder="如 OPS"></label>
        <label>数据权限<select v-model.number="draft.dataScope"><option :value="1">全部数据</option><option :value="2">本部门数据</option><option :value="3">本人数据</option></select></label>
        <label>排序<input v-model.number="draft.sort" type="number" min="0"></label>
        <label>备注<input v-model.trim="draft.remark" maxlength="255"></label>
        <label>管理员复核密码<input v-model="adminPassword" type="password" autocomplete="current-password" required :disabled="saving"></label>
        <p v-if="saveError" class="admin-error" role="alert">{{ saveError }}</p>
        <footer><button type="button" :disabled="saving" @click="close">取消</button><button class="admin-primary" type="submit" :disabled="saving">{{ saving ? '提交中…' : '保存' }}</button></footer>
      </form>
    </AdminDialog>

    <AdminDialog v-if="action === 'grant'" :title="`授权「${target?.name}」`" :busy="saving" @close="close">
      <p class="admin-muted">勾选后保存即整树替换；取消勾选的旧权限会被清除。</p>
      <div class="admin-menu-tree" role="tree" aria-label="菜单权限树">
        <div v-for="node in menuTree" :key="node.id">
          <label class="admin-tree-node"><input type="checkbox" :value="node.id" v-model="checkedMenus" /> {{ node.name }}</label>
          <div v-for="child in node.children" :key="child.id" style="padding-left: 22px">
            <label class="admin-tree-node"><input type="checkbox" :value="child.id" v-model="checkedMenus" /> {{ child.name }}</label>
            <div v-for="btn in child.children" :key="btn.id" style="padding-left: 22px">
              <label class="admin-tree-node admin-tree-node--btn"><input type="checkbox" :value="btn.id" v-model="checkedMenus" /> {{ btn.name }} <code>{{ btn.perms }}</code></label>
            </div>
          </div>
        </div>
      </div>
      <label class="admin-form">管理员复核密码<input v-model="adminPassword" type="password" autocomplete="current-password" :disabled="saving"></label>
      <p v-if="saveError" class="admin-error" role="alert">{{ saveError }}</p>
      <footer><button type="button" :disabled="saving" @click="close">取消</button><button class="admin-primary" type="submit" :disabled="saving" @click="saveGrant">{{ saving ? '提交中…' : '保存授权' }}</button></footer>
    </AdminDialog>
  </section>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { systemApi } from '../../../api/adminSystem.js'
import { useAdminResource } from '../../../composables/useAdminResource.js'
import AdminDialog from '../../../components/admin/AdminDialog.vue'
const { data, loading, error, load } = useAdminResource(() => systemApi.roles())
const action = ref('')
const saving = ref(false)
const saveError = ref('')
const success = ref('')
const target = ref(null)
const adminPassword = ref('')
const draft = reactive({ name: '', code: '', dataScope: 1, sort: 0, remark: '' })
const menuTree = ref([])
const checkedMenus = ref([])
const scopeLabel = scope => ({ 1: '全部数据', 2: '本部门数据', 3: '本人数据' })[scope] || scope

function open(kind, role = null) {
  target.value = role
  action.value = kind
  saveError.value = ''
  success.value = ''
  adminPassword.value = ''
  if (kind === 'edit') Object.assign(draft, { name: role.name, code: role.code, dataScope: role.data_scope, sort: role.sort, remark: role.remark || '' })
  else Object.assign(draft, { name: '', code: '', dataScope: 1, sort: 0, remark: '' })
  if (kind === 'grant') loadGrant(role)
}
async function loadGrant(role) {
  try {
    const [menus, granted] = await Promise.all([systemApi.menus(), systemApi.roleMenus(role.id)])
    menuTree.value = menus
    checkedMenus.value = granted.menuIds || []
  } catch (failure) { saveError.value = failure.message || '加载菜单失败' }
}
function close() { if (saving.value) return; action.value = ''; saveError.value = '' }
async function save() {
  if (saving.value) return
  saveError.value = ''
  if (!adminPassword.value) { saveError.value = '请输入管理员复核密码'; return }
  const password = adminPassword.value; adminPassword.value = ''
  saving.value = true
  try {
    if (action.value === 'create') await systemApi.createRole(draft, password)
    else await systemApi.updateRole(target.value.id, draft, password)
    action.value = ''
    success.value = '角色已保存。'
    await load()
  } catch (failure) { saveError.value = failure.message || '保存失败，请重试' }
  finally { saving.value = false }
}
async function saveGrant() {
  if (saving.value) return
  saveError.value = ''
  if (!adminPassword.value) { saveError.value = '请输入管理员复核密码'; return }
  const password = adminPassword.value; adminPassword.value = ''
  saving.value = true
  try { await systemApi.grantMenus(target.value.id, checkedMenus.value, password); action.value = ''; success.value = '权限已更新。' }
  catch (failure) { saveError.value = failure.message || '授权失败，请重试' }
  finally { saving.value = false }
}
function askPassword(label) { return window.prompt(`请输入当前管理员密码以${label}（仅用于本次身份复核）`) }
async function toggle(role) {
  const password = askPassword(role.status === 1 ? '停用角色' : '启用角色')
  if (!password) return
  success.value = ''; error.value = ''
  try { await systemApi.roleStatus(role.id, role.status === 1 ? 0 : 1, password); success.value = '角色状态已更新。'; await load() }
  catch (failure) { error.value = failure.message || '操作失败' }
}
async function remove(role) {
  if (!window.confirm(`确认删除角色「${role.name}」？`)) return
  const password = askPassword('删除角色')
  if (!password) return
  success.value = ''; error.value = ''
  try { await systemApi.deleteRole(role.id, password); success.value = '角色已删除。'; await load() }
  catch (failure) { error.value = failure.message || '删除失败' }
}
</script>
