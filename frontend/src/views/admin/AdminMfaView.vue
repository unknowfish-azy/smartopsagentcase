<template>
  <section class="mfa-page">
    <header class="admin-heading"><div><p class="admin-eyebrow">ADMINISTRATOR SECURITY</p><h1>管理员二次认证</h1><p class="admin-muted">使用认证器离线生成动态码，不需要公网。仅管理当前账号，不会替其他管理员重置认证器。</p></div><button type="button" :disabled="busy" @click="load">刷新状态</button></header>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <p v-if="message" class="admin-notice" role="status">{{ message }}</p>
    <section v-if="status" class="mfa-panel" aria-labelledby="mfa-state-title">
      <h2 id="mfa-state-title">{{ status.enabled ? '二次认证已启用' : '尚未绑定认证器' }}</h2>
      <p class="admin-muted">{{ status.enabled ? `剩余恢复码：${status.recoveryCodesRemaining} 枚。管理员账号在用户入口登录时也需要二次认证。` : '现有账号不会被强制锁定。完成绑定后，密码通过仍需动态码或恢复码才能登录。' }}</p>
      <form v-if="!recoveryCodes.length" class="admin-form" @submit.prevent="perform(draft ? 'enable' : 'setup')">
        <label>当前密码<input v-model="password" type="password" autocomplete="current-password" :disabled="busy" placeholder="每次安全操作都需要重新确认密码"></label>
        <template v-if="draft">
          <p class="admin-notice">在认证器中选择“手动添加密钥”：服务名称 SmartOpsAgent，账号 {{ draft.account }}，类型 TOTP，6 位数字，每 30 秒更新。剩余 {{ remaining }} 秒。</p>
          <label>绑定密钥（仅本次显示）<input :value="draft.secret" readonly autocomplete="off" spellcheck="false" aria-label="绑定密钥（仅本次显示）"></label>
          <label>认证器动态码<input v-model.trim="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" :disabled="busy" placeholder="输入认证器中的 6 位动态码"></label>
          <div class="mfa-actions"><button class="admin-primary" type="submit" :disabled="busy || !password || !code">确认绑定</button><button type="button" :disabled="busy" @click="clearDraft">取消绑定</button></div>
        </template>
        <button v-else-if="!status.enabled" class="admin-primary" type="submit" :disabled="busy || !password">开始绑定认证器</button>
        <template v-else>
          <label>动态码或恢复码<input v-model.trim="code" autocomplete="off" maxlength="64" :disabled="busy" placeholder="输入当前动态码或一枚恢复码"></label>
          <p class="admin-muted">重生成将立即废弃全部旧恢复码；安全变更会撤销其他会话。刚使用过的动态码需等待下一组。</p>
          <button type="button" :disabled="busy || !password || !code" @click="perform('recovery')">重生成恢复码</button>
          <label class="mfa-checkbox"><input v-model="confirmDisable" type="checkbox" :disabled="busy">我确认关闭二次认证会降低账号安全性</label>
          <button type="button" :disabled="busy || !password || !code || !confirmDisable" @click="perform('disable')">关闭二次认证</button>
        </template>
      </form>
      <section v-else class="mfa-recovery" aria-labelledby="recovery-title">
        <h3 id="recovery-title">请立即离线保存恢复码</h3>
        <p class="admin-notice">每枚只能使用一次，关闭或离开页面后无法再次查看。不要将恢复码和密码保存在同一位置。</p>
        <textarea :value="recoveryCodes.join('\n')" rows="10" readonly autocomplete="off" spellcheck="false" aria-label="一次性恢复码"></textarea>
        <label class="mfa-checkbox"><input v-model="saved" type="checkbox">我已离线保存全部恢复码</label>
        <button type="button" :disabled="!saved" @click="recoveryCodes = []; saved = false">完成并隐藏恢复码</button>
      </section>
    </section>
    <section class="mfa-panel" aria-labelledby="security-notices-title">
      <h2 id="security-notices-title">我的安全提醒</h2><p class="admin-muted">展示最近 50 条站内提醒，不代表已发送邮件、短信或浏览器推送。</p>
      <p v-if="!notices.length" class="admin-muted">暂无安全提醒。</p>
      <ul v-else class="mfa-notices"><li v-for="notice in notices" :key="notice.id"><p>{{ notice.message }}</p><div><time>{{ formatTime(notice.createdAt) }}</time><span v-if="notice.read">已读</span><button v-else type="button" :disabled="busy" @click="readNotice(notice.id)">标记已读</button></div></li></ul>
    </section>
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { mfaApi } from '../../api/mfa.ts'
const status = ref(null), notices = ref([]), password = ref(''), code = ref(''), draft = ref(null)
const recoveryCodes = ref([]), saved = ref(false), confirmDisable = ref(false), busy = ref(false), error = ref(''), message = ref(''), remaining = ref(0)
let timer, deadline = 0, disposed = false
function clearDraft() { draft.value = null; password.value = ''; code.value = ''; clearInterval(timer) }
function formatTime(value) { return new Date(value).toLocaleString() }
async function load() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try { [status.value, notices.value] = await Promise.all([mfaApi.status(), mfaApi.notices()]) }
  catch (failure) { error.value = failure.message || '安全设置读取失败，请重试' }
  finally { busy.value = false }
}
async function perform(action) {
  if (busy.value || !password.value || (action !== 'setup' && !code.value) || (action === 'disable' && !confirmDisable.value)) return
  if (status.value?.enabled && action === 'setup') return
  busy.value = true
  error.value = ''; message.value = ''
  try {
    if (action === 'setup') {
      const enrollment = await mfaApi.setup(password.value)
      if (disposed) return
      draft.value = enrollment
      remaining.value = draft.value.expiresIn
      deadline = Date.now() + remaining.value * 1000
      clearInterval(timer)
      timer = setInterval(() => {
        remaining.value = Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
        if (!remaining.value) { clearDraft(); error.value = '绑定请求已过期，请重新开始' }
      }, 1000)
    } else {
      const result = action === 'enable' ? await mfaApi.enable(draft.value.challenge, code.value, password.value) : await mfaApi[action](code.value, password.value)
      if (disposed) return
      clearDraft()
      recoveryCodes.value = result.recoveryCodes || []
      saved.value = false; confirmDisable.value = false
      message.value = action === 'disable' ? '二次认证已关闭，其他会话已撤销。' : '安全设置已更新，其他会话已撤销。请保存本次恢复码。'
      ;[status.value, notices.value] = await Promise.all([mfaApi.status(), mfaApi.notices()])
    }
  } catch (failure) { error.value = failure.message || '安全设置更新失败'; if (failure.status === 409) clearDraft() }
  finally { password.value = ''; code.value = ''; busy.value = false }
}
async function readNotice(id) {
  if (busy.value) return
  busy.value = true
  try { await mfaApi.readNotice(id); notices.value = await mfaApi.notices() }
  catch (failure) { error.value = failure.message || '标记失败' }
  finally { busy.value = false }
}
function preventSecretLoss(event) {
  if (busy.value || recoveryCodes.value.length) { event.preventDefault(); event.returnValue = '' }
}
onBeforeRouteLeave(() => !(busy.value || recoveryCodes.value.length) || window.confirm('安全操作尚未结束或恢复码尚未关闭。离开后无法再次查看本次恢复码，确认离开？'))
onMounted(() => { load(); window.addEventListener('beforeunload', preventSecretLoss) })
onBeforeUnmount(() => { disposed = true; clearDraft(); recoveryCodes.value = []; window.removeEventListener('beforeunload', preventSecretLoss) })
</script>

<style scoped>
.mfa-page { display: grid; gap: 18px; max-width: 1000px; padding: clamp(20px, 2.6vw, 32px); }
.mfa-page h1 { padding-bottom: 12px; }
.mfa-page h2, .mfa-page h3 { margin: 0 0 10px; }
.mfa-page > header.admin-heading, .mfa-page > .admin-heading { margin-bottom: 0; }
.mfa-page > .admin-error, .mfa-page > .admin-notice { margin: 0; }
.mfa-panel { min-width: 0; padding: 22px 24px; background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); box-shadow: var(--admin-shadow); }
.mfa-panel h2 { padding-bottom: 10px; border-bottom: 1px solid var(--admin-border); }
.mfa-panel .admin-form { max-width: 660px; margin-top: 18px; }
.mfa-actions { display: flex; flex-wrap: wrap; gap: 12px; }
.mfa-panel .mfa-checkbox { display: flex; align-items: center; gap: 10px; color: var(--admin-text); }
.mfa-checkbox input { width: auto; }
.mfa-recovery { display: grid; gap: 16px; }
.mfa-recovery textarea { width: 100%; min-width: 0; padding: 12px 14px; color: var(--admin-text); background: var(--admin-surface-2); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-sm); font: 12px/1.8 var(--font-mono); white-space: pre; }
.mfa-notices { padding: 0; margin: 0; list-style: none; display: grid; gap: 0; }
.mfa-notices li { padding: 14px 0; border-bottom: 1px solid var(--admin-border); }
.mfa-notices li:last-child { border-bottom: 0; padding-bottom: 0; }
.mfa-notices li p { margin: 0 0 8px; line-height: 1.7; overflow-wrap: anywhere; }
.mfa-notices li div { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; color: var(--admin-muted); font-size: 12px; }
.mfa-notices li button { min-height: 32px; padding: 5px 10px; font-size: 12px; }
@media (max-width: 767px) { .mfa-page { padding: 20px 16px; } .mfa-panel { padding: 18px; } .mfa-page .admin-heading { flex-wrap: wrap; } }
@media (prefers-reduced-motion: reduce) { .mfa-panel, .mfa-recovery textarea { transition: none; } }
</style>
