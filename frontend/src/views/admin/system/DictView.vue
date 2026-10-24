<template>
  <section aria-labelledby="dict-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">SYSTEM / 数据字典</p><h1 id="dict-title">字典管理</h1></div><button class="admin-primary" @click="openType('create')">新增字典类型</button></header>
    <p class="admin-muted">先建类型，再在类型下维护数据项；写操作需输入管理员密码复核。</p>
    <p v-if="success" class="admin-notice" role="status">{{ success }}</p>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <div class="admin-split">
      <div class="admin-split__pane">
        <h2 class="admin-subhead">字典类型</h2>
        <p v-if="loading" role="status">正在加载…</p>
        <ul v-if="data" class="admin-list">
          <li v-for="type in data" :key="type.id" :class="{ 'is-current': currentType === type.type }">
            <button @click="select(type)"><strong>{{ type.name }}</strong> <code>{{ type.type }}</code> <span class="admin-status-tag" :class="type.status === 1 ? 'admin-status-tag--on' : 'admin-status-tag--off'">{{ type.status === 1 ? '启用' : '停用' }}</span></button>
            <div class="admin-actions"><button @click="openType('edit', type)">编辑</button><button @click="removeType(type)">删除</button></div>
          </li>
        </ul>
        <p v-if="data && !data.length" class="admin-empty">还没有字典类型。</p>
      </div>
      <div class="admin-split__pane">
        <h2 class="admin-subhead">字典数据{{ currentType ? ` · ${currentType}` : '' }}</h2>
        <button class="admin-secondary" :disabled="!currentType" @click="openData('create')">新增数据项</button>
        <p v-if="!currentType" class="admin-muted">先在左侧选择字典类型。</p>
        <table v-else class="admin-table"><thead><tr><th scope="col">标签</th><th scope="col">键值</th><th scope="col">排序</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead>
          <tbody><tr v-for="item in dictData" :key="item.id"><td>{{ item.label }}</td><td><code>{{ item.dict_value }}</code></td><td>{{ item.sort }}</td><td><span class="admin-status-tag" :class="item.status === 1 ? 'admin-status-tag--on' : 'admin-status-tag--off'">{{ item.status === 1 ? '启用' : '停用' }}</span></td><td><div class="admin-actions"><button @click="openData('edit', item)">编辑</button><button @click="toggleData(item)">{{ item.status === 1 ? '停用' : '启用' }}</button><button @click="removeData(item)">删除</button></div></td></tr></tbody>
        </table>
      </div>
    </div>

    <AdminDialog v-if="typeAction" :title="typeAction === 'create' ? '新增字典类型' : '编辑字典类型'" :busy="saving" @close="closeType">
      <form class="admin-form" @submit.prevent="saveType">
        <label>字典名称<input v-model.trim="typeDraft.name" required maxlength="64" placeholder="如 性别"></label>
        <label>字典类型（唯一标识）<input v-model.trim="typeDraft.type" required maxlength="100" placeholder="如 sys_gender"></label>
        <label>备注<input v-model.trim="typeDraft.remark" maxlength="255"></label>
        <label>管理员复核密码<input v-model="adminPassword" type="password" autocomplete="current-password" required :disabled="saving"></label>
        <p v-if="saveError" class="admin-error" role="alert">{{ saveError }}</p>
        <footer><button type="button" :disabled="saving" @click="closeType">取消</button><button class="admin-primary" type="submit" :disabled="saving">{{ saving ? '提交中…' : '保存' }}</button></footer>
      </form>
    </AdminDialog>

    <AdminDialog v-if="dataAction" :title="dataAction === 'create' ? '新增数据项' : '编辑数据项'" :busy="saving" @close="closeData">
      <form class="admin-form" @submit.prevent="saveData">
        <label>标签<input v-model.trim="dataDraft.label" required maxlength="100" placeholder="如 男"></label>
        <label>键值<input v-model.trim="dataDraft.value" required maxlength="100" placeholder="如 M"></label>
        <label>排序<input v-model.number="dataDraft.sort" type="number" min="0"></label>
        <label>备注<input v-model.trim="dataDraft.remark" maxlength="255"></label>
        <label>管理员复核密码<input v-model="adminPassword" type="password" autocomplete="current-password" required :disabled="saving"></label>
        <p v-if="saveError" class="admin-error" role="alert">{{ saveError }}</p>
        <footer><button type="button" :disabled="saving" @click="closeData">取消</button><button class="admin-primary" type="submit" :disabled="saving">{{ saving ? '提交中…' : '保存' }}</button></footer>
      </form>
    </AdminDialog>
  </section>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { systemApi } from '../../../api/adminSystem.ts'
import { useAdminResource } from '../../../composables/useAdminResource.js'
import AdminDialog from '../../../components/admin/AdminDialog.vue'
const { data, loading, error, load } = useAdminResource(() => systemApi.dictTypes())
const currentType = ref('')
const dictData = ref([])
const typeAction = ref('')
const dataAction = ref('')
const typeTarget = ref(null)
const dataTarget = ref(null)
const saving = ref(false)
const saveError = ref('')
const success = ref('')
const adminPassword = ref('')
const typeDraft = reactive({ name: '', type: '', remark: '' })
const dataDraft = reactive({ value: '', label: '', sort: 0, remark: '' })

async function select(type) { currentType.value = type.type; success.value = ''; error.value = ''; await refreshData() }
async function refreshData() { try { dictData.value = await systemApi.dictData(currentType.value) } catch (failure) { error.value = failure.message || '加载字典数据失败' } }
function openType(kind, type = null) { typeTarget.value = type; typeAction.value = kind; saveError.value = ''; adminPassword.value = ''; Object.assign(typeDraft, type ? { name: type.name, type: type.type, remark: type.remark || '' } : { name: '', type: '', remark: '' }) }
function closeType() { if (saving.value) return; typeAction.value = ''; saveError.value = '' }
async function saveType() {
  if (saving.value) return
  saveError.value = ''
  if (!adminPassword.value) { saveError.value = '请输入管理员复核密码'; return }
  const password = adminPassword.value; adminPassword.value = ''
  saving.value = true
  try {
    if (typeAction.value === 'create') await systemApi.createDictType(typeDraft, password)
    else await systemApi.updateDictType(typeTarget.value.id, typeDraft, password)
    typeAction.value = ''
    success.value = '字典类型已保存。'
    await load()
  } catch (failure) { saveError.value = failure.message || '保存失败，请重试' }
  finally { saving.value = false }
}
function openData(kind, item = null) { dataTarget.value = item; dataAction.value = kind; saveError.value = ''; adminPassword.value = ''; Object.assign(dataDraft, item ? { value: item.dict_value, label: item.label, sort: item.sort, remark: item.remark || '' } : { value: '', label: '', sort: 0, remark: '' }) }
function closeData() { if (saving.value) return; dataAction.value = ''; saveError.value = '' }
async function saveData() {
  if (saving.value) return
  saveError.value = ''
  if (!adminPassword.value) { saveError.value = '请输入管理员复核密码'; return }
  const password = adminPassword.value; adminPassword.value = ''
  saving.value = true
  try {
    const body = { type: currentType.value, label: dataDraft.label, value: dataDraft.value, sort: dataDraft.sort, remark: dataDraft.remark }
    if (dataAction.value === 'create') await systemApi.createDictData(body, password)
    else await systemApi.updateDictData(dataTarget.value.id, body, password)
    dataAction.value = ''
    success.value = '数据项已保存。'
    await refreshData()
  } catch (failure) { saveError.value = failure.message || '保存失败，请重试' }
  finally { saving.value = false }
}
function askPassword(label) { return window.prompt(`请输入当前管理员密码以${label}（仅用于本次身份复核）`) }
async function removeType(type) {
  if (!window.confirm(`确认删除字典类型「${type.name}」？其下所有数据项将一并删除。`)) return
  const password = askPassword('删除字典类型')
  if (!password) return
  success.value = ''; error.value = ''
  try { await systemApi.deleteDictType(type.id, password); success.value = '字典类型已删除。'; await load() }
  catch (failure) { error.value = failure.message || '删除失败' }
}
async function toggleData(item) {
  const password = askPassword(item.status === 1 ? '停用数据项' : '启用数据项')
  if (!password) return
  success.value = ''; error.value = ''
  try { await systemApi.dictDataStatus(item.id, item.status === 1 ? 0 : 1, password); await refreshData() }
  catch (failure) { error.value = failure.message || '操作失败' }
}
async function removeData(item) {
  if (!window.confirm(`确认删除数据项「${item.label}」？`)) return
  const password = askPassword('删除数据项')
  if (!password) return
  success.value = ''; error.value = ''
  try { await systemApi.deleteDictData(item.id, password); await refreshData() }
  catch (failure) { error.value = failure.message || '删除失败' }
}
</script>
