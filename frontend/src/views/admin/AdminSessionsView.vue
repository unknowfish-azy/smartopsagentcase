<template>
  <section aria-labelledby="sessions-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">SESSIONS / 当前访问</p><h1 id="sessions-title">活动会话</h1></div><button :disabled="loading" @click="load">刷新会话</button></header>
    <p class="admin-muted">入口权限在登录时确定。列表仅展示管理标识，不包含 Cookie、CSRF 或认证秘密。</p>
    <p v-if="success" class="admin-notice" role="status">{{ success }}</p><p v-if="error" class="admin-error" role="alert">{{ error }}</p><p v-if="loading" role="status">正在加载会话…</p>
    <p v-if="data" id="sessions-scroll-hint" class="admin-table-hint">左右滑动查看完整列表及操作；键盘可聚焦列表后使用左右方向键。</p>
    <div v-if="data" class="admin-table-wrap" tabindex="0" aria-label="会话列表，可横向滚动" aria-describedby="sessions-scroll-hint"><table><thead><tr><th scope="col">账号</th><th scope="col">入口</th><th scope="col">创建时间</th><th scope="col">最近活动</th><th scope="col">操作</th></tr></thead><tbody><tr v-for="session in data.items" :key="session.id"><td>{{ session.username }}<span v-if="session.current" class="admin-badge">当前会话</span></td><td>{{ session.portal === 'admin' ? '管理层' : '用户层' }}</td><td>{{ formatAdminTime(session.createdAt) }}</td><td>{{ formatAdminTime(session.lastSeenAt) }}</td><td><button @click="open(session)">撤销会话</button></td></tr></tbody></table><p v-if="!data.items.length" class="admin-empty">当前没有活动会话。</p></div>
    <AdminDialog v-if="target" title="确认撤销会话" :busy="saving" @close="close"><form class="admin-form" @submit.prevent="revoke"><p>目标账户：<strong>{{ target.username }}</strong></p><p class="admin-notice">撤销后该会话及关联终端连接将失效，需要重新登录。{{ target.current ? '这是当前会话，确认后你将退出管理台。' : '' }}</p><label>当前管理员密码<input v-model="adminPassword" type="password" autocomplete="current-password" required :disabled="saving" aria-describedby="session-verify-hint"></label><small id="session-verify-hint">仅用于本次身份复核，不会保存。</small><p v-if="saveError" class="admin-error" role="alert">{{ saveError }}</p><footer><button type="button" :disabled="saving" @click="close">取消</button><button type="submit" class="admin-primary" :disabled="saving">{{ saving ? '撤销中…' : '确认撤销' }}</button></footer></form></AdminDialog>
  </section>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi } from '../../api/admin.js'
import { clearSession } from '../../security/session.js'
import { useAdminResource, formatAdminTime } from '../../composables/useAdminResource.js'
import AdminDialog from '../../components/admin/AdminDialog.vue'
const router = useRouter()
const { data, loading, error, load } = useAdminResource(adminApi.sessions)
const target = ref(null), saving = ref(false), saveError = ref(''), success = ref('')
const adminPassword = ref('')
function open(session) { target.value = session; saveError.value = ''; success.value = ''; adminPassword.value = '' }
function close() { if (saving.value) return; target.value = null; adminPassword.value = ''; saveError.value = '' }
async function revoke() {
  if (saving.value || !adminPassword.value) return
  saving.value = true
  saveError.value = ''
  const verificationPassword = adminPassword.value
  adminPassword.value = ''
  const session = target.value
  try {
    await adminApi.revokeSession(session.id, verificationPassword)
    target.value = null
    if (session.current) { clearSession(); await router.replace({ path: '/login', query: { portal: 'admin', reason: 'session-revoked' } }); return }
    success.value = '会话已撤销。'
    await load()
  } catch (failure) { saveError.value = failure.message || '撤销失败，请重试' }
  finally { adminPassword.value = ''; saving.value = false }
}
onMounted(load)
</script>
