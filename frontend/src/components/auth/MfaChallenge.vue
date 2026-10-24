<template>
  <section class="mfa-challenge" aria-labelledby="mfa-title">
    <h3 id="mfa-title">验证管理员身份</h3>
    <p>密码已通过，完成二次认证后才能建立登录会话。</p>
    <label>动态码或恢复码<input ref="input" v-model.trim="code" :disabled="busy || expired" :inputmode="recovery ? 'text' : 'numeric'" :autocomplete="recovery ? 'off' : 'one-time-code'" :maxlength="recovery ? 64 : 6" :placeholder="recovery ? '输入一枚未使用的恢复码' : '输入认证器中的 6 位动态码'" @keydown.enter.stop.prevent="submit"></label>
    <label class="mfa-challenge__choice"><input v-model="recovery" type="checkbox" :disabled="busy" @change="code = ''">使用恢复码</label>
    <p v-if="!expired">验证有效期剩余 {{ remaining }} 秒。刚使用过的动态码不能重复提交。</p>
    <p v-else role="status">验证已失效，请返回密码登录。</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <button type="button" :disabled="busy || expired || !code" @click="submit">{{ busy ? '正在验证…' : '验证并登录' }}</button>
    <button type="button" :disabled="busy" @click="cancel">返回密码登录</button>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { completeMfa, cancelMfa } from '../../security/session.js'
const props = defineProps({ challenge: { type: Object, required: true } })
const emit = defineEmits(['verified', 'cancel'])
const code = ref(''), error = ref(''), busy = ref(false), recovery = ref(false), input = ref(null)
const remaining = ref(Math.max(0, Number(props.challenge.expiresIn) || 0))
const rejected = ref(false)
const expired = computed(() => rejected.value || remaining.value <= 0)
const deadline = Date.now() + remaining.value * 1000
let timer
onMounted(async () => {
  timer = setInterval(() => { remaining.value = Math.max(0, Math.ceil((deadline - Date.now()) / 1000)); if (expired.value) code.value = '' }, 1000)
  await nextTick()
  input.value?.focus()
})
onBeforeUnmount(() => { clearInterval(timer); code.value = '' })
async function submit() {
  if (busy.value || expired.value || !code.value) return
  if (!recovery.value && !/^[0-9]{6}$/.test(code.value)) { error.value = '请输入 6 位数字动态码'; return }
  busy.value = true
  error.value = ''
  try { emit('verified', await completeMfa(props.challenge.challenge, code.value)) }
  catch (failure) { error.value = failure.message || '二次认证失败'; if ([401, 429].includes(failure.status)) rejected.value = true }
  finally { code.value = ''; busy.value = false }
}
async function cancel() {
  busy.value = true
  try { await cancelMfa(); emit('cancel') }
  catch (failure) { error.value = failure.message || '暂时无法取消，请稍后重试' }
  finally { code.value = ''; busy.value = false }
}
</script>

<style scoped>
.mfa-challenge { display: grid; gap: 16px; color: var(--smart-text); min-width: 0; }
.mfa-challenge h3 { margin: 0; font-size: 20px; }
.mfa-challenge p { margin: 0; font-size: 13px; line-height: 1.7; color: var(--smart-muted); }
.mfa-challenge label { display: grid; gap: 8px; font-size: 13px; }
.mfa-challenge input:not([type=checkbox]) { width: 100%; min-width: 0; padding: 14px; border: 1px solid var(--smart-border); border-radius: 9px; background: var(--smart-surface); color: var(--smart-text); }
.mfa-challenge input::placeholder { color: var(--smart-muted); opacity: 1; }
.mfa-challenge .mfa-challenge__choice { display: flex; align-items: center; gap: 8px; }
.mfa-challenge button { min-height: 44px; border: 1px solid var(--smart-border); border-radius: 9px; background: var(--smart-surface); color: var(--smart-text); cursor: pointer; }
.mfa-challenge button:disabled { cursor: not-allowed; opacity: .65; }
.mfa-challenge :focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 3px; }
</style>
