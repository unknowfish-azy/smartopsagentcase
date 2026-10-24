<template>
  <section aria-labelledby="post-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">SYSTEM / 组织架构</p><h1 id="post-title">岗位管理</h1></div><button class="admin-primary" @click="open('create')">新增岗位</button></header>
    <p class="admin-muted">岗位是扁平字典，可被多个部门复用；写操作需输入当前管理员密码复核身份。</p>
    <p v-if="success" class="admin-notice" role="status">{{ success }}</p>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载岗位…</p>
    <div v-if="data" class="admin-table-wrap" tabindex="0" aria-label="岗位列表">
      <table><thead><tr><th scope="col">编码</th><th scope="col">名称</th><th scope="col">排序</th><th scope="col">状态</th><th scope="col">备注</th><th scope="col">操作</th></tr></thead>
        <tbody><tr v-for="post in data" :key="post.id"><td><code>{{ post.code }}</code></td><td>{{ post.name }}</td><td>{{ post.sort }}</td><td><span class="admin-status-tag" :class="post.status === 1 ? 'admin-status-tag--on' : 'admin-status-tag--off'">{{ post.status === 1 ? '启用' : '停用' }}</span></td><td>{{ post.remark || '—' }}</td><td><div class="admin-actions"><button @click="open('edit', post)">编辑</button><button @click="toggle(post)">{{ post.status === 1 ? '停用' : '启用' }}</button><button @click="remove(post)">删除</button></div></td></tr></tbody>
      </table><p v-if="!data.length" class="admin-empty">还没有岗位，点击「新增岗位」创建。</p>
    </div>
    <AdminDialog v-if="action" :title="action === 'create' ? '新增岗位' : '编辑岗位'" :busy="saving" @close="close">
      <form class="admin-form" @submit.prevent="save">
        <label>岗位编码<input v-model.trim="draft.code" required maxlength="64" placeholder="如 ENGINEER"></label>
        <label>岗位名称<input v-model.trim="draft.name" required maxlength="64" placeholder="如 运维工程师"></label>
        <label>排序<input v-model.number="draft.sort" type="number" min="0"></label>
        <label>备注<input v-model.trim="draft.remark" maxlength="255"></label>
        <label>管理员复核密码<input v-model="adminPassword" type="password" autocomplete="current-password" required :disabled="saving"></label>
        <small>输入你当前登录的管理员密码，仅用于本次身份复核。</small>
        <p v-if="saveError" class="admin-error" role="alert">{{ saveError }}</p>
        <footer><button type="button" :disabled="saving" @click="close">取消</button><button class="admin-primary" type="submit" :disabled="saving">{{ saving ? '提交中…' : '保存' }}</button></footer>
      </form>
    </AdminDialog>
  </section>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { systemApi } from '../../../api/adminSystem.ts'
import { useAdminResource } from '../../../composables/useAdminResource.js'
import AdminDialog from '../../../components/admin/AdminDialog.vue'
const { data, loading, error, load } = useAdminResource(() => systemApi.posts())
const action = ref('')
const saving = ref(false)
const saveError = ref('')
const success = ref('')
const target = ref(null)
const adminPassword = ref('')
const draft = reactive({ code: '', name: '', sort: 0, remark: '' })
function open(kind, post = null) { target.value = post; action.value = kind; saveError.value = ''; success.value = ''; adminPassword.value = ''; Object.assign(draft, post ? { code: post.code, name: post.name, sort: post.sort, remark: post.remark || '' } : { code: '', name: '', sort: 0, remark: '' }) }
function close() { if (saving.value) return; action.value = ''; saveError.value = '' }
async function save() {
  if (saving.value) return
  saveError.value = ''
  if (!adminPassword.value) { saveError.value = '请输入管理员复核密码'; return }
  const password = adminPassword.value; adminPassword.value = ''
  saving.value = true
  try {
    if (action.value === 'create') await systemApi.createPost(draft, password)
    else await systemApi.updatePost(target.value.id, draft, password)
    action.value = ''
    success.value = '岗位已保存。'
    await load()
  } catch (failure) { saveError.value = failure.message || '保存失败，请重试' }
  finally { saving.value = false }
}
function askPassword(label) { return window.prompt(`请输入当前管理员密码以${label}（仅用于本次身份复核）`) }
async function toggle(post) {
  const password = askPassword(post.status === 1 ? '停用岗位' : '启用岗位')
  if (!password) return
  success.value = ''; error.value = ''
  try { await systemApi.postStatus(post.id, post.status === 1 ? 0 : 1, password); success.value = '岗位状态已更新。'; await load() }
  catch (failure) { error.value = failure.message || '操作失败' }
}
async function remove(post) {
  if (!window.confirm(`确认删除岗位「${post.name}」？`)) return
  const password = askPassword('删除岗位')
  if (!password) return
  success.value = ''; error.value = ''
  try { await systemApi.deletePost(post.id, password); success.value = '岗位已删除。'; await load() }
  catch (failure) { error.value = failure.message || '删除失败' }
}
</script>
