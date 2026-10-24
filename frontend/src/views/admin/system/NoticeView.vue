<template>
  <section aria-labelledby="notice-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">SYSTEM / 内容发布</p><h1 id="notice-title">通知公告</h1></div><button class="admin-primary" @click="open('create')">新建公告</button></header>
    <p class="admin-muted">公告先保存为草稿，发布后才在用户层展示；写操作需输入管理员密码复核。</p>
    <p v-if="success" class="admin-notice" role="status">{{ success }}</p>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载公告…</p>
    <div v-if="data" class="admin-table-wrap" tabindex="0" aria-label="公告列表">
      <table><thead><tr><th scope="col">标题</th><th scope="col">类型</th><th scope="col">状态</th><th scope="col">发布人</th><th scope="col">发布时间</th><th scope="col">操作</th></tr></thead>
        <tbody><tr v-for="notice in data" :key="notice.id"><td>{{ notice.title }}</td><td>{{ notice.type === 1 ? '通知' : '公告' }}</td><td>{{ notice.published_at ? '已发布' : '草稿' }}</td><td>{{ notice.publisher_name || '—' }}</td><td>{{ formatAdminTime(notice.published_at) }}</td><td><div class="admin-actions"><button v-if="!notice.published_at" @click="publish(notice)">发布</button><button @click="open('edit', notice)">编辑</button><button @click="remove(notice)">删除</button></div></td></tr></tbody>
      </table><p v-if="!data.length" class="admin-empty">还没有公告，点击「新建公告」创建。</p>
    </div>
    <AdminDialog v-if="action" :title="action === 'create' ? '新建公告' : '编辑公告'" :busy="saving" @close="close">
      <form class="admin-form" @submit.prevent="save">
        <label>标题<input v-model.trim="draft.title" required maxlength="200"></label>
        <label>类型<select v-model.number="draft.type"><option :value="1">通知</option><option :value="2">公告</option></select></label>
        <label>内容<textarea v-model.trim="draft.content" required rows="6"></textarea></label>
        <label>管理员复核密码<input v-model="adminPassword" type="password" autocomplete="current-password" required :disabled="saving"></label>
        <p v-if="saveError" class="admin-error" role="alert">{{ saveError }}</p>
        <footer><button type="button" :disabled="saving" @click="close">取消</button><button class="admin-primary" type="submit" :disabled="saving">{{ saving ? '提交中…' : '保存草稿' }}</button></footer>
      </form>
    </AdminDialog>
  </section>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { systemApi } from '../../../api/adminSystem.ts'
import { useAdminResource, formatAdminTime } from '../../../composables/useAdminResource.js'
import AdminDialog from '../../../components/admin/AdminDialog.vue'
const { data, loading, error, load } = useAdminResource(() => systemApi.notices(true))
const action = ref('')
const saving = ref(false)
const saveError = ref('')
const success = ref('')
const target = ref(null)
const adminPassword = ref('')
const draft = reactive({ title: '', content: '', type: 1 })
function open(kind, notice = null) {
  target.value = notice
  action.value = kind
  saveError.value = ''
  success.value = ''
  adminPassword.value = ''
  Object.assign(draft, notice ? { title: notice.title, content: notice.content || '', type: notice.type } : { title: '', content: '', type: 1 })
}
function close() { if (saving.value) return; action.value = ''; saveError.value = '' }
async function save() {
  if (saving.value) return
  saveError.value = ''
  if (!adminPassword.value) { saveError.value = '请输入管理员复核密码'; return }
  const password = adminPassword.value; adminPassword.value = ''
  saving.value = true
  try {
    if (action.value === 'create') await systemApi.createNotice(draft, password)
    else await systemApi.updateNotice(target.value.id, draft, password)
    action.value = ''
    success.value = '公告已保存为草稿。'
    await load()
  } catch (failure) { saveError.value = failure.message || '保存失败，请重试' }
  finally { saving.value = false }
}
function askPassword(label) { return window.prompt(`请输入当前管理员密码以${label}（仅用于本次身份复核）`) }
async function publish(notice) {
  const password = askPassword('发布公告')
  if (!password) return
  success.value = ''; error.value = ''
  try { await systemApi.publishNotice(notice.id, password); success.value = '公告已发布。'; await load() }
  catch (failure) { error.value = failure.message || '发布失败' }
}
async function remove(notice) {
  if (!window.confirm(`确认删除公告「${notice.title}」？`)) return
  const password = askPassword('删除公告')
  if (!password) return
  success.value = ''; error.value = ''
  try { await systemApi.deleteNotice(notice.id, password); success.value = '公告已删除。'; await load() }
  catch (failure) { error.value = failure.message || '删除失败' }
}
</script>
