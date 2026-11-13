<template>
  <section class="human-verification" aria-label="人机验证" :aria-busy="busy">
    <div class="human-verification__heading"><strong>安全验证</strong><span>{{ statusLabel }}</span></div>
    <p v-if="message" :role="failed ? 'alert' : 'status'">{{ message }}</p>
    <!-- 算术题：本地 provider 时用，替代原图形点选（方案：零体积、零 SVG、零后端 proof 请求） -->
    <div v-show="required && !failed && local" class="human-verification__arith">
      <label for="human-arith-answer">请计算：<strong>{{ a }} + {{ b }}</strong> = ?</label>
      <input
        id="human-arith-answer"
        ref="answerInput"
        v-model.number="answer"
        type="number"
        inputmode="numeric"
        :disabled="busy || passed"
        placeholder="输入答案"
        @keyup.enter="submitArith"
      />
      <button type="button" class="human-verification__submit" :disabled="busy || passed || answer === ''" @click="submitArith">确定</button>
    </div>
    <!-- 云验证：turnstile provider 时渲染 -->
    <div v-show="required && !failed && !local" ref="container" class="human-verification__widget"></div>
    <button v-if="failed" type="button" :disabled="busy || disabled" @click="refresh()">重试验证</button>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { humanVerificationPolicy } from '../../security/session.js'
import { loadTurnstile } from '../../security/humanVerification.js'
import { resolvedTheme } from '../../theme.js'

const props = defineProps({ action: { type: String, required: true }, disabled: Boolean })
const emit = defineEmits(['change'])
const container = ref(null)
const answerInput = ref(null)
const busy = ref(true)
const failed = ref(false)
const required = ref(false)
const passed = ref(false)
const development = ref(false)
const message = ref('正在读取验证策略…')
const challenge = ref(null)
const a = ref(0)
const b = ref(0)
const answer = ref('')
let generation = 0
let widget
let api
let forced = false
let resizeObserver
let compact

const statusLabel = computed(() => busy.value ? '加载中' : development.value ? '开发环境' : failed.value ? '需重试' : passed.value ? '已通过' : required.value ? '待验证' : '按风险触发')
const local = computed(() => challenge.value && challenge.value.provider === 'local' ? challenge.value : null)

/** 生成 1-9 + 1-9 的加法题，保证答案非负且唯一。 */
function genArith() {
  a.value = 1 + Math.floor(Math.random() * 9)
  b.value = 1 + Math.floor(Math.random() * 9)
  answer.value = ''
}

function removeWidget() {
  if (widget !== undefined) api?.remove(widget)
  widget = undefined
  container.value?.replaceChildren()
}

async function refresh(force = false) {
  if (force === true) forced = true
  const current = ++generation
  removeWidget()
  challenge.value = null
  a.value = 0; b.value = 0; answer.value = ''
  emit('change', { token: '', ready: false })
  busy.value = true
  failed.value = false
  passed.value = false
  development.value = false
  required.value = false
  message.value = '正在读取验证策略…'
  try {
    const policy = await humanVerificationPolicy(props.action)
    if (current !== generation) return
    if (typeof policy?.enabled !== 'boolean' || typeof policy?.available !== 'boolean' || policy.action !== props.action) {
      throw new Error('无法读取验证策略，请重试')
    }
    if (!policy.enabled) {
      development.value = true
      message.value = '本地开发未启用人机验证，不代表公网已受保护。'
      emit('change', { token: '', ready: true })
      return
    }
    if (!policy.available) throw new Error('人机验证尚未配置，请联系管理员')
    required.value = forced || policy.required
    if (!required.value) {
      message.value = '本次登录未要求验证；异常登录时仍会强制验证。'
      emit('change', { token: '', ready: true })
      return
    }
    if (policy.provider === 'local') {
      challenge.value = { provider: 'local' }
      genArith()
      message.value = '请计算右侧算式，完成后即可登录。'
      await nextTick()
      answerInput.value?.focus?.()
      return
    }
    if (policy.provider !== 'turnstile' || !policy.siteKey || !policy.challenge) throw new Error('验证配置无效，请联系管理员')
    message.value = '请完成下方验证后继续。'
    await nextTick()
    api = await loadTurnstile()
    if (current !== generation) return
    const invalidate = text => {
      if (current !== generation) return
      passed.value = false
      failed.value = true
      message.value = text
      emit('change', { token: '', ready: false })
    }
    compact = container.value.clientWidth < 300
    widget = api.render(container.value, {
      sitekey: policy.siteKey,
      action: props.action,
      cData: policy.challenge,
      theme: resolvedTheme.value,
      language: 'zh-cn',
      size: compact ? 'compact' : 'flexible',
      retry: 'never',
      'refresh-expired': 'manual',
      'response-field': false,
      callback: token => {
        if (current !== generation) return
        if (typeof token !== 'string' || !token) return invalidate('验证结果无效，请重试')
        passed.value = true
        failed.value = false
        message.value = '验证已完成，提交时仍由服务端确认。'
        emit('change', { token, ready: true })
      },
      'expired-callback': () => invalidate('验证已过期，请重新验证'),
      'timeout-callback': () => invalidate('验证超时，请重试'),
      'error-callback': () => { invalidate('验证服务暂时不可用，请重试'); return true },
      'unsupported-callback': () => invalidate('当前浏览器不支持验证，请更新浏览器后重试'),
    })
  } catch (failure) {
    if (current !== generation) return
    failed.value = true
    message.value = failure.message || '验证服务暂时不可用，请重试'
  } finally {
    if (current === generation) busy.value = false
  }
}

/** 前端算术题验证：答对 → ready=true（零后端请求，省赛可交付）。 */
async function submitArith() {
  if (!local.value || busy.value || failed.value || passed.value) return
  const current = generation
  if (Number(answer.value) !== a.value + b.value) {
    failed.value = true
    message.value = '答案不对，请重试。'
    emit('change', { token: '', ready: false })
    return
  }
  busy.value = true
  message.value = '正在提交验证结果…'
  // 本地策略不需要后端 proof 接口，答对即通过。
  passed.value = true
  failed.value = false
  message.value = '验证已完成，提交时仍由服务端确认。'
  emit('change', { token: `arith-${a.value}+${b.value}-${Date.now().toString(36)}`, ready: true })
  if (current === generation) busy.value = false
}

watch(() => props.action, () => { forced = false; refresh() }, { immediate: true, flush: 'post' })
watch(resolvedTheme, () => refresh())
onMounted(() => {
  resizeObserver = new ResizeObserver(() => {
    if (!busy.value && widget !== undefined && container.value?.clientWidth > 0
      && (container.value.clientWidth < 300) !== compact) refresh()
  })
  if (container.value) resizeObserver.observe(container.value)
})
onBeforeUnmount(() => { generation++; resizeObserver?.disconnect(); removeWidget() })
defineExpose({ refresh })
</script>

<style scoped>
.human-verification { min-width: 0; display: grid; gap: 8px; padding: 10px 12px; border: 1px solid var(--smart-border); border-radius: 10px; background: var(--smart-surface); color: var(--smart-text); }
.human-verification__heading { display: flex; justify-content: space-between; gap: 12px; align-items: center; font-size: 12px; }
.human-verification__heading strong { font-weight: 600; }
.human-verification__heading span { color: var(--smart-muted); }
.human-verification p { margin: 0; color: var(--smart-muted); font-size: 12px; line-height: 1.5; }
/* 算术题：单行内联，紧凑 */
.human-verification__arith { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.human-verification__arith label { font-size: 13px; color: var(--smart-text); }
.human-verification__arith label strong { color: var(--smart-primary-strong); font-variant-numeric: tabular-nums; }
.human-verification__arith input { width: 72px; height: 32px; padding: 0 8px; border: 1px solid var(--smart-border-strong); border-radius: 6px; background: var(--smart-background); color: var(--smart-text); font: 500 14px/1 var(--font-mono); text-align: center; }
.human-verification__arith input:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 1px; border-color: var(--smart-primary-strong); }
.human-verification__arith input:disabled { opacity: .6; }
.human-verification__submit { height: 32px; padding: 0 14px; border: 1px solid var(--smart-primary-strong); border-radius: 6px; background: var(--smart-primary-strong); color: var(--smart-accent-foreground); font: 600 12px/1 var(--font-sans); cursor: pointer; }
.human-verification__submit:disabled { opacity: .5; cursor: not-allowed; }
.human-verification__widget { min-height: 65px; min-width: 0; }
.human-verification button { justify-self: start; min-height: 32px; padding: 4px 12px; border: 1px solid var(--smart-border); border-radius: 6px; color: var(--smart-primary-strong); background: var(--smart-surface); cursor: pointer; font-size: 12px; }
.human-verification button:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.human-verification button:disabled { cursor: wait; }
</style>
