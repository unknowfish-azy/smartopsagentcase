<template>
  <section class="admin-registration" aria-labelledby="registration-title">
    <div><h2 id="registration-title">普通账号注册</h2><p v-if="policy" role="status">普通账号注册已{{ policy.enabled ? '开放' : '关闭' }}</p><p class="admin-muted">仅允许注册运维用户，管理员不开放注册。</p></div>
    <button v-if="policy" :disabled="loading" @click="open">{{ policy.enabled ? '关闭注册' : '开放注册' }}</button>
    <p v-if="loading" role="status">正在读取注册策略…</p>
    <p v-if="error" class="admin-error" role="alert">{{ error }} <button @click="load">重试</button></p>
    <AdminDialog v-if="confirming" title="确认注册策略变更" :busy="saving" @close="close">
      <form class="admin-form" @submit.prevent="save">
        <p>将{{ policy.enabled ? '关闭' : '开放' }}普通账号注册。已有账号仍可登录。</p>
        <label>当前管理员密码<input v-model="adminPassword" type="password" autocomplete="current-password" required :disabled="saving" aria-describedby="registration-verify-hint"></label>
        <small id="registration-verify-hint">仅用于本次身份复核，不会保存。</small>
        <p v-if="saveError" class="admin-error" role="alert">{{ saveError }}</p>
        <footer><button type="button" :disabled="saving" @click="close">取消</button><button type="submit" class="admin-primary" :disabled="saving">{{ saving ? '提交中…' : '确认变更' }}</button></footer>
      </form>
    </AdminDialog>
  </section>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { adminApi } from '../../api/admin.ts'
import { useAdminResource } from '../../composables/useAdminResource.js'
import AdminDialog from './AdminDialog.vue'

const { data: policy, loading, error, load } = useAdminResource(adminApi.registration)
const confirming = ref(false), saving = ref(false), saveError = ref(''), adminPassword = ref('')
function open() { adminPassword.value = ''; saveError.value = ''; confirming.value = true }
function close() { if (saving.value) return; adminPassword.value = ''; saveError.value = ''; confirming.value = false }
async function save() {
  if (saving.value || !adminPassword.value) return
  saving.value = true
  saveError.value = ''
  const password = adminPassword.value
  adminPassword.value = ''
  try {
    policy.value = await adminApi.updateRegistration(!policy.value.enabled, password)
    confirming.value = false
  } catch (failure) { saveError.value = failure.message || '策略保存失败，请重试' }
  finally { adminPassword.value = ''; saving.value = false }
}
onMounted(load)
</script>
<style scoped>
.admin-registration { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px 16px; margin: 18px 0; padding: 18px 20px; border: 1px solid var(--admin-border); border-left: 3px solid var(--admin-accent); border-radius: var(--admin-radius); background: var(--admin-panel); box-shadow: var(--admin-shadow); }
.admin-registration h2 { margin: 0; font-size: 15px; font-weight: 600; }
.admin-registration p { margin: 6px 0 0; }
.admin-registration > div:first-child { min-width: 0; }
.admin-registration button { flex: 0 0 auto; }
</style>
