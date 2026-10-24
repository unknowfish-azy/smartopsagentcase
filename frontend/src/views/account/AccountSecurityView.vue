<template>
  <main class="admin-surface account-shell">
    <header class="account-toolbar"><strong>智维Agent / 账户安全</strong><label class="admin-theme">主题<select aria-label="选择主题模式" :value="themeMode" @change="setThemeMode($event.target.value)"><option value="light">浅色</option><option value="dark">深色</option><option value="system">跟随系统</option></select></label><button type="button" :disabled="busy" @click="logout">退出登录</button></header>
    <section class="account-panel" aria-labelledby="security-title">
      <p class="admin-eyebrow">ACCOUNT SECURITY</p><h1 id="security-title">账户安全</h1>
      <p class="admin-muted">当前账号：{{ currentSession?.username }}</p>
      <p v-if="currentSession?.mustChangePassword" class="admin-notice" role="status">首次登录、密码已重置或已提升为管理员，请先修改密码。完成前仅可修改密码或退出登录。</p>
      <p v-else class="admin-notice">修改密码将撤销此账号的全部旧会话及终端连接，包括当前会话，成功后必须重新登录。</p>
      <form class="admin-form" @submit.prevent="submit">
        <label>当前密码<input v-model="form.currentPassword" type="password" autocomplete="current-password" required></label>
        <label>新密码<input v-model="form.newPassword" type="password" autocomplete="new-password" aria-describedby="password-guidance" required></label>
        <small id="password-guidance">请使用与当前密码不同的安全密码；{{ currentSession?.role === 'admin' ? '管理员至少 16 字符' : '普通用户至少 12 字符' }}，不超过 72 UTF-8 字节。</small>
        <label>确认新密码<input v-model="form.confirmPassword" type="password" autocomplete="new-password" required></label>
        <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
        <button class="admin-primary" type="submit" :disabled="busy">{{ busy ? '处理中…' : '更新密码并退出' }}</button>
        <RouterLink v-if="!currentSession?.mustChangePassword" :to="isAdminSession(currentSession) ? '/admin' : '/'">返回工作台</RouterLink>
      </form>
    </section>
    <section class="account-panel" aria-labelledby="profile-title">
      <p class="admin-eyebrow">PERSONAL PROFILE</p><h1 id="profile-title">个人资料</h1>
      <p class="admin-muted">姓名、电话、邮箱仅用于联系与识别，不参与登录鉴权。</p>
      <form class="admin-form" @submit.prevent="saveProfile">
        <label>姓名<input v-model.trim="profile.realName" maxlength="64" autocomplete="name"></label>
        <label>电话<input v-model.trim="profile.phone" maxlength="32" autocomplete="tel"></label>
        <label>邮箱<input v-model.trim="profile.email" type="email" maxlength="128" autocomplete="email"></label>
        <p v-if="profileError" class="admin-error" role="alert">{{ profileError }}</p>
        <p v-if="profileSaved" class="admin-notice" role="status">个人资料已保存。</p>
        <button class="admin-primary" type="submit" :disabled="busy">{{ busy ? '保存中…' : '保存资料' }}</button>
      </form>
    </section>
  </main>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { currentSession, changePassword, logoutSession } from '../../security/session.js'
import request from '../../utils/request.js'
import { passwordError } from '../../security/passwordPolicy.js'
import { isAdminSession } from '../../security/portalPolicy.js'
import { themeMode, setThemeMode } from '../../theme.js'
import '../../assets/styles/admin.css'
const router = useRouter()
const form = reactive({ currentPassword: '', newPassword: '', confirmPassword: '' })
const busy = ref(false), error = ref('')
const profile = reactive({ realName: '', phone: '', email: '' })
const profileError = ref(''), profileSaved = ref(false)
async function loadProfile() {
  try { const data = (await request.get('/api/auth/profile')).data; Object.assign(profile, { realName: data.realName || '', phone: data.phone || '', email: data.email || '' }) } catch { /* 资料加载失败不阻断安全页 */ }
}
async function saveProfile() {
  if (busy.value) return
  profileError.value = ''; profileSaved.value = false
  busy.value = true
  try { await request.put('/api/auth/profile', { ...profile }); profileSaved.value = true }
  catch (failure) { profileError.value = failure.message || '保存失败，请重试' }
  finally { busy.value = false }
}
onMounted(loadProfile)
async function submit() {
  if (busy.value) return
  error.value = ''
  if (form.newPassword !== form.confirmPassword) { error.value = '两次输入的新密码不一致'; return }
  if (form.currentPassword === form.newPassword) { error.value = '新密码不能与当前密码相同'; return }
  error.value = passwordError(form.newPassword, currentSession.value?.role)
  if (error.value) return
  busy.value = true
  const portal = currentSession.value?.portal || 'user'
  try {
    await changePassword(form.currentPassword, form.newPassword)
    Object.assign(form, { currentPassword: '', newPassword: '', confirmPassword: '' })
    await router.replace({ path: '/login', query: { reason: 'password-changed', portal } })
  } catch (failure) { error.value = failure.message || '修改失败，请重试' }
  finally { busy.value = false }
}
async function logout() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try { await logoutSession(); await router.replace('/login') }
  catch (failure) { error.value = failure.message || '退出失败，请重试' }
  finally { busy.value = false }
}
</script>
