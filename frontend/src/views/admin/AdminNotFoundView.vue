<template>
  <section class="admin-not-found" aria-labelledby="admin-not-found-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">NOT FOUND / 访问边界</p><h1 id="admin-not-found-title">页面不存在或不可访问</h1></div></header>
    <p class="admin-notice">请求地址 <code>{{ route.fullPath }}</code> 不在管理端注册的路由表中，可能已更名、尚未上线，或属于用户门户。</p>
    <p class="admin-muted">管理端只注册平台治理页面：账户、团队、系统配置、安全审计与服务接入检查。模型接入、连接中心、指标查询与仓库浏览属于用户门户，需要切换到用户门户并重新登录后访问。</p>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <div class="admin-not-found-actions">
      <button type="button" class="admin-primary" @click="back">返回管理总览</button>
      <button type="button" :disabled="leaving" @click="switchPortal">{{ leaving ? '切换中…' : '前往用户门户（重新登录）' }}</button>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { logoutSession } from '../../security/session.js'
import { resolvePortalSwitch } from '../../security/portalSwitch.js'
const route = useRoute()
const router = useRouter()
const leaving = ref(false)
const error = ref('')
function back() { router.replace('/admin') }
// 跨门户沿用既有切换机制：先退出当前入口，再整页跳到用户入口重新登录。
async function switchPortal() {
  if (leaving.value) return
  leaving.value = true
  error.value = ''
  try {
    await logoutSession()
    const decision = resolvePortalSwitch('user')
    if (decision?.crossOrigin) { window.location.assign(decision.url); return }
    await router.replace({ path: '/login', query: { portal: 'user' } })
  } catch (failure) { error.value = failure.message || '切换失败，请重试' }
  finally { leaving.value = false }
}
</script>

<style scoped>
.admin-not-found { max-width: 720px; }
.admin-not-found-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
</style>
