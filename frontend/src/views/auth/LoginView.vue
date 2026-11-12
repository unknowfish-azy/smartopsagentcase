<template>
  <StellarOceanProvider state="thinking">
  <main class="login-shell" :data-visual-mode="visualMode">
    <CanvasAmbientField class="login-ambient" />
    <MeteorShower v-if="visualMode === 'balanced'" class="login-meteors" />
    <header class="login-topbar">
      <div class="login-brand"><span class="login-brand__mark" aria-hidden="true">智</span><div><strong>智维 Agent</strong><span>SMARTOPS / PERSONAL WORKSPACE</span></div></div>
      <div class="login-appearance" aria-label="外观设置">
        <label><span>主题</span><select aria-label="选择主题模式" :value="themeMode" @change="setThemeMode($event.target.value)"><option value="light">浅色</option><option value="dark">深色</option><option value="system">跟随系统</option></select></label>
        <label><span>视觉</span><select aria-label="选择视觉模式" :value="visualMode" @change="setVisualMode($event.target.value)"><option value="balanced">平衡视觉</option><option value="lightweight">轻量视觉</option><option value="reduced-motion">减少动态</option></select></label>
      </div>
    </header>
    <div class="login-layout">
    <section class="login-showcase" aria-label="智维工作空间介绍">
      <div class="login-copy">
      <p class="editorial-label">个人运维知识空间</p>
      <h1>智驭系统<br><span>维系上下文</span></h1>
      <p class="login-copy__description">把知识、系统与运维记忆连接起来，<br class="desktop-break">让每一次操作都有清晰的上下文。</p>
      </div>
      <dl class="login-trust">
        <div><dt>身份认证</dt><dd>服务端验证</dd></div>
        <div><dt>访问权限</dt><dd>按账号授权</dd></div>
        <div><dt>会话保护</dt><dd>安全令牌校验</dd></div>
      </dl>
      <div class="login-organisms" aria-hidden="true">
        <div class="login-glyph"><span>OPS</span></div>
        <CanvasParticleWhale v-if="visualMode === 'balanced'" placement="knowledge" state="thinking" />
        <LivingJellyfish class="login-jellyfish" state="thinking" ecosystem="login" :motion-mode="visualMode" />
        <span class="login-scene-label">KNOWLEDGE · MEMORY · AGENT</span>
      </div>
    </section>
    <form ref="glassCard" class="login-form login-form--portal" aria-labelledby="login-title" @pointermove="moveGlassLight" @pointerleave="resetGlassLight" @submit.prevent="submit" novalidate>
      <header class="login-form__header">
        <div>
          <p class="editorial-label">你的工作空间 / SECURE ENTRY</p>
          <h2 id="login-title">{{ pendingMfa ? '二次认证' : registering ? '注册普通账号' : '欢迎回来' }}</h2>
          <p>{{ registering ? '注册账号固定为运维用户，管理员不开放注册。' : form.portal === 'admin' ? '仅限已授权管理员进入管理工作台。' : '继续你的知识与运维工作。' }}</p>
        </div>
        <span class="login-form__status"><span aria-hidden="true"></span>LOCAL</span>
      </header>

      <MfaChallenge v-if="pendingMfa" :challenge="pendingMfa" @verified="finishLogin" @cancel="pendingMfa = null; error = ''" />
      <template v-else>
      <div v-if="!registering" class="role-switcher" role="tablist" aria-label="登录入口">
        <button v-for="entry in portals" :id="`portal-${entry.id}`" :key="entry.id" type="button" role="tab" aria-controls="portal-fields" :aria-selected="form.portal === entry.id" :tabindex="form.portal === entry.id ? 0 : -1" :class="{ 'is-active': form.portal === entry.id }" :disabled="loading" @click="switchPortal(entry.id)" @keydown.left.prevent="selectPortal" @keydown.right.prevent="selectPortal"><span class="role-switcher__dot" aria-hidden="true"></span>{{ entry.label }}</button>
      </div>
      <!-- 两个入口各由独立服务提供，切换会改变地址；提前说明，避免被当成"页面乱跳"。 -->
      <p v-if="!registering && otherPortal" class="role-switcher__hint">
        切换{{ otherPortal.label }}：<code>{{ otherPortal.address }}</code>（独立服务，需重新登录）
      </p>
      <p v-if="route.query.reason === 'password-changed'" role="status">密码已更新，旧会话已退出，请重新登录。</p>
      <p v-if="route.query.reason === 'denied'" role="status">当前账号没有管理员入口。请使用管理员账号登录，或切换到用户门户。</p>
      <p v-if="success" class="login-form__notice" role="status">{{ success }}</p>
      <div id="portal-fields" class="login-form__fields" :role="registering ? 'group' : 'tabpanel'" :aria-label="registering ? '普通账号注册信息' : undefined" :aria-labelledby="registering ? undefined : `portal-${form.portal}`">
        <label class="login-field" :class="{ 'login-field--focused': focusedInput === 'username' }">
          <span class="login-field__label">账号</span>
          <span class="login-input-shell">
            <el-icon class="login-input-icon" aria-hidden="true"><User /></el-icon>
            <input v-model.trim="form.username" autocomplete="username" :disabled="loading" :aria-describedby="registering ? 'registration-guidance' : undefined" placeholder="输入运维账号" required @focus="focusedInput = 'username'" @blur="focusedInput = ''" @input="error = ''">
          </span>
        </label>

        <label class="login-field" :class="{ 'login-field--focused': focusedInput === 'password' }">
          <span class="login-field__label">密码</span>
          <span class="login-input-shell">
            <el-icon class="login-input-icon" aria-hidden="true"><Lock /></el-icon>
            <input v-model="form.password" :disabled="loading" :aria-describedby="registering ? 'registration-guidance' : undefined" :type="showPassword ? 'text' : 'password'" :autocomplete="registering ? 'new-password' : 'current-password'" :placeholder="registering ? '设置登录密码' : '输入访问密码'" required @focus="focusedInput = 'password'" @blur="focusedInput = ''" @input="error = ''">
            <button class="password-visibility-toggle" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" :aria-pressed="showPassword" @click="showPassword = !showPassword">
              <el-icon aria-hidden="true"><View v-if="!showPassword" /><Hide v-else /></el-icon>
            </button>
          </span>
        </label>
      </div>

      <label v-if="registering" class="login-field">
        <span class="login-field__label">确认密码</span>
        <span class="login-input-shell"><el-icon class="login-input-icon" aria-hidden="true"><Lock /></el-icon><input v-model="form.confirmPassword" :disabled="loading" aria-describedby="registration-guidance" type="password" autocomplete="new-password" placeholder="再次输入密码" required></span>
      </label>
      <p v-if="registering" id="registration-guidance" class="login-form__guidance">账号为 3–64 位字母、数字、点、下划线或短横线。普通密码至少 {{ policy?.userPasswordMinLength || 12 }} 字符，管理员新密码至少 {{ policy?.adminPasswordMinLength || 16 }} 字符，均不超过 {{ policy?.passwordMaxBytes || 72 }} UTF-8 字节。</p>

      <div v-if="!registering" class="login-form__options">
        <label class="remember-control"><input v-model="rememberMe" type="checkbox"><span>记住本机账号</span></label>
        <span class="login-form__policy">最小权限 · 全程留痕</span>
      </div>

      <HumanVerification ref="humanCheck" :action="registering ? 'register' : form.portal === 'admin' ? 'admin_login' : 'login'" :disabled="loading" @change="updateHumanState" />
      <p v-if="error" id="login-error" class="login-form__error" role="alert">{{ error }}</p>
      <button class="login-submit" type="submit" :disabled="loading || !humanState.ready || (registering && !policy?.enabled)">
        <span>{{ registering ? (loading ? '正在创建账号' : '创建普通账号') : (loading ? '正在建立安全会话' : '进入智维Agent') }}</span>
        <el-icon v-if="!loading" aria-hidden="true"><ArrowRight /></el-icon>
        <span v-else class="login-submit__spinner" aria-hidden="true"></span>
      </button>
      <div v-if="form.portal === 'user'" class="login-registration">
        <button v-if="registering" type="button" :disabled="loading" @click="setRegistration(false)">返回登录</button>
        <template v-else>
          <span v-if="policy?.enabled">首次使用？</span>
          <button type="button" :disabled="loading || !policy?.enabled" @click="setRegistration(true)">注册普通账号</button>
          <p v-if="policy && !policy.enabled" role="status">普通账号注册已关闭，请联系管理员。</p>
          <p v-else-if="policyError" role="alert">{{ policyError }} <button type="button" @click="loadPolicy">重试</button></p>
          <p v-else-if="!policy" role="status">正在读取注册状态…</p>
        </template>
      </div>
      <p v-else class="login-form__guidance">管理员不开放注册；新密码至少 16 字符且不超过 72 UTF-8 字节。已有账号仍可使用原密码登录。</p>
      <p class="login-form__footer">使用已创建的真实账号登录 · 会话空闲 {{ form.portal === 'admin' ? 10 : 30 }} 分钟后失效</p>
      </template>
    </form>
    </div>
    <footer class="login-page-footer"><span>SMARTOPS AGENT</span><span>知识 · 记忆 · 受控智能体</span></footer>
  </main>
  </StellarOceanProvider>
</template>

<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, Hide, Lock, User, View } from '@element-plus/icons-vue'
import LivingJellyfish from '../../components/common/LivingJellyfish.vue'
import StellarOceanProvider from '../../components/common/StellarOceanProvider.vue'
import MeteorShower from '../../components/common/MeteorShower.vue'
import HumanVerification from '../../components/auth/HumanVerification.vue'
import MfaChallenge from '../../components/auth/MfaChallenge.vue'
import { loginSession, registrationPolicy, registerAccount } from '../../security/session.js'
import { sessionLanding } from '../../security/portalPolicy.js'
import { resolvePortalSwitch } from '../../security/portalSwitch.js'
import { registrationError } from '../../security/passwordPolicy.js'
import { themeMode, setThemeMode } from '../../theme.js'
import { visualMode, setVisualMode } from '../../visual/visualMode.js'

const CanvasParticleWhale = defineAsyncComponent(() => import('../../components/common/CanvasParticleWhale.vue'))
const CanvasAmbientField = defineAsyncComponent(() => import('../../components/common/CanvasAmbientField.vue'))

const router = useRouter()
const route = useRoute()
const form = reactive({ username: '', password: '', confirmPassword: '', portal: route.query.portal === 'admin' ? 'admin' : 'user' })
const portals = [{ id: 'user', label: '用户层' }, { id: 'admin', label: '管理员层' }]
const registering = ref(false)
const pendingMfa = ref(null)
const policy = ref(null)
const policyError = ref('')
const success = ref('')
const loading = ref(false)
const error = ref('')
const showPassword = ref(false)
const rememberMe = ref(false)
const focusedInput = ref('')
const glassCard = ref(null)
const humanCheck = ref(null)
const humanState = reactive({ token: '', ready: false })
function updateHumanState(state) { Object.assign(humanState, state) }

/**
 * 当前入口之外的另一个入口，以及它真实的地址。
 *
 * 端口是可配置的（VITE_SMARTOPS_ADMIN_PORT / VITE_SMARTOPS_USER_PORT），
 * 因此这里显示的是 resolvePortalSwitch 实际算出来的地址，而不是写死的字符串。
 */
const otherPortal = computed(() => {
  const target = form.portal === 'admin' ? 'user' : 'admin'
  const decision = resolvePortalSwitch(target, { query: { ...route.query } })
  if (!decision) return null
  return { id: target, label: target === 'admin' ? '管理员层' : '用户层', address: decision.url.replace(/^https?:\/\//, '').split('?')[0] }
})
let glassFrame = 0
let glassMotionQuery
let glassPointerX = 64
let glassPointerY = 8
let lastGlassWriteAt = 0
const GLASS_LIGHT_THROTTLE_MS = 30

function syncPortalUrl(portal) {
  if (!['user', 'admin'].includes(portal) || route.query.portal === portal) return
  router.replace({ path: '/login', query: { ...route.query, portal } })
}

/**
 * 切换入口。
 *
 * 用户层（:5173）与管理员层（:5174）是两个独立的前端服务，
 * 切换时不是"改一个变量"，而是要整页跳到目标服务，让目标服务加载自己的
 * HTML 入口与路由表。同源时才走 SPA 替换。
 */
function switchPortal(target) {
  if (!['user', 'admin'].includes(target)) return
  const decision = resolvePortalSwitch(target, { query: { ...route.query } })
  if (!decision) return
  error.value = ''
  if (!decision.crossOrigin) {
    form.portal = target
    syncPortalUrl(target)
    return
  }
  // 跨源：整页跳转。目标服务会用 ?portal= 决定默认选中的入口。
  window.location.assign(decision.url)
}

function resetGlassLight() {
  cancelAnimationFrame(glassFrame)
  glassFrame = 0
  glassCard.value?.style.setProperty('--login-light-x', '64%')
  glassCard.value?.style.setProperty('--login-light-y', '8%')
}

function moveGlassLight(event) {
  if (event.pointerType === 'touch' || visualMode.value !== 'balanced' || glassMotionQuery?.matches) return
  // P1：保留 --login-light-x/y 的写入契约（浏览器测试依赖），但降频到约 33Hz，
  // 且 ::before 已改为静态高光、不再引用这两个变量，因此写入不再触发渐变重绘。
  const now = performance.now()
  if (now - lastGlassWriteAt < GLASS_LIGHT_THROTTLE_MS) return
  const bounds = event.currentTarget.getBoundingClientRect()
  glassPointerX = Math.max(0, Math.min(100, (event.clientX - bounds.left) / bounds.width * 100))
  glassPointerY = Math.max(0, Math.min(100, (event.clientY - bounds.top) / bounds.height * 100))
  if (glassFrame) return
  glassFrame = requestAnimationFrame(() => {
    glassFrame = 0
    lastGlassWriteAt = now
    glassCard.value?.style.setProperty('--login-light-x', `${glassPointerX.toFixed(1)}%`)
    glassCard.value?.style.setProperty('--login-light-y', `${glassPointerY.toFixed(1)}%`)
  })
}

watch(visualMode, resetGlassLight)

function selectPortal(event) {
  const next = form.portal === 'user' ? 'admin' : 'user'
  switchPortal(next)
  error.value = ''
  // 跨源时页面即将跳转，聚焦目标元素没有意义；同源时才移动焦点。
  if (resolvePortalSwitch(next)?.crossOrigin !== true) {
    event.currentTarget.parentElement.querySelector(`#portal-${next}`)?.focus()
  }
}

watch(() => route.query.portal, (portal) => {
  const next = portal === 'admin' ? 'admin' : 'user'
  if (form.portal !== next) form.portal = next
})

onMounted(() => {
  glassMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  glassMotionQuery.addEventListener('change', resetGlassLight)
  loadPolicy()
  const hint = localStorage.getItem('smartops_login_hint')
  if (hint) {
    form.username = hint
    rememberMe.value = true
  }
})

onBeforeUnmount(() => {
  cancelAnimationFrame(glassFrame)
  glassMotionQuery?.removeEventListener('change', resetGlassLight)
})

async function loadPolicy() {
  policyError.value = ''
  try { policy.value = await registrationPolicy() }
  catch (failure) { policy.value = null; policyError.value = failure.message || '无法读取注册状态，请重试' }
}

function setRegistration(enabled) {
  if (loading.value || (enabled && (form.portal !== 'user' || !policy.value?.enabled))) return
  registering.value = enabled
  form.password = ''
  form.confirmPassword = ''
  showPassword.value = false
  error.value = ''
  success.value = ''
}

async function register() {
  if (form.portal !== 'user' || !policy.value?.enabled) { error.value = '注册已关闭'; return }
  error.value = registrationError(form, policy.value)
  if (error.value) return
  loading.value = true
  try {
    await registerAccount({ ...form, humanToken: humanState.token })
    registering.value = false
    form.portal = 'user'
    await router.replace({ path: '/login', query: { portal: 'user' } })
    success.value = '注册成功，请使用新账号登录。'
  } catch (failure) {
    error.value = failure.message || '注册失败，请稍后重试'
    if (failure.status === 403) await loadPolicy()
    await humanCheck.value?.refresh(failure.status === 428)
  } finally {
    form.password = ''
    form.confirmPassword = ''
    showPassword.value = false
    loading.value = false
  }
}

async function submit() {
  if (loading.value || pendingMfa.value) return
  error.value = ''
  if (!humanState.ready) { error.value = '请先完成安全验证'; return }
  if (registering.value) return register()
  if (!form.username || !form.password) {
    error.value = '请输入账号和密码'
    return
  }
  loading.value = true
  try {
    const user = await loginSession(form.username, form.password, form.portal, humanState.token)
    form.password = ''
    showPassword.value = false
    if (user?.mfaRequired) { pendingMfa.value = user; return }
    await finishLogin(user)
  } catch (failure) {
    error.value = failure.message || '登录失败，请稍后重试'
    await humanCheck.value?.refresh(failure.status === 428)
  } finally { loading.value = false }
}

async function finishLogin(user) {
  try {
    if (rememberMe.value) localStorage.setItem('smartops_login_hint', form.username)
    else localStorage.removeItem('smartops_login_hint')
  } catch {}
  form.password = ''
  await router.replace(sessionLanding(user, route.query.redirect))
}
</script>

<style scoped>
.login-shell { --login-glass-bg: rgba(9, 22, 32, .76); --login-glass-edge: rgba(173, 222, 239, .32); --login-glass-highlight: rgba(222, 248, 255, .16); --login-glass-luster: rgba(146, 224, 249, .1); --login-glass-shadow: 0 24px 64px rgba(0, 0, 0, .24), inset 0 1px 0 rgba(222, 248, 255, .32), inset 1px 0 0 rgba(222, 248, 255, .12), inset 0 -1px 0 rgba(122, 215, 245, .12); --login-glass-blur: 10px; --login-glyph-edge: rgba(181, 237, 250, .25); position: relative; isolation: isolate; display: flex; flex-direction: column; min-height: 100dvh; gap: 28px; padding: 24px clamp(20px, 4.4vw, 72px); color: var(--smart-text); background: var(--smart-bg); }
.login-shell > .login-ambient { opacity: .42; pointer-events: none; }
.login-shell > .login-meteors { opacity: .3; pointer-events: none; }
.login-topbar, .login-layout, .login-page-footer { position: relative; z-index: 1; width: min(100%, 1240px); margin-inline: auto; }
.login-topbar { display: flex; justify-content: space-between; align-items: center; gap: 24px; }
.login-brand { display: flex; align-items: center; gap: 12px; }
.login-brand__mark { display: grid; place-items: center; width: 40px; height: 40px; border: 1px solid var(--smart-border-strong); border-radius: 12px; color: var(--smart-primary-strong); background: var(--smart-surface); font-size: 20px; }
.login-brand > div { display: grid; gap: 5px; }
.login-brand strong { font-size: 17px; font-weight: 600; }
.login-brand > div > span { font: 9px var(--font-mono); letter-spacing: .1em; color: var(--smart-muted); }
.login-appearance { display: flex; gap: 16px; }
.login-appearance label { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--smart-muted); }
.login-appearance select { min-height: 44px; max-width: 128px; padding: 0 10px; border: 1px solid var(--smart-border); border-radius: 8px; background: var(--smart-surface); color: var(--smart-text); font-size: 12px; cursor: pointer; }
.login-layout { flex: 1; display: grid; grid-template-columns: minmax(0, 1fr) minmax(380px, 440px); align-items: center; gap: clamp(40px, 5.5vw, 88px); }
.login-showcase { min-width: 0; }
.login-copy { position: relative; z-index: 1; }
.editorial-label { margin: 0 0 16px; color: var(--smart-primary-strong); font: 11px var(--font-mono); letter-spacing: .12em; }
.login-copy h1 { margin: 0; font: 500 clamp(36px, 3.7vw, 56px)/1.22 var(--font-cn); letter-spacing: -.025em; text-shadow: none; }
.login-copy h1 span { color: var(--smart-primary-strong); }
.login-copy__description { margin: 20px 0 0; max-width: 440px; color: var(--smart-muted); font-size: 15px; line-height: 1.8; }
.login-organisms { position: relative; isolation: isolate; width: 100%; height: clamp(290px, 35vh, 350px); margin-top: 24px; pointer-events: none; }
.login-organisms::before { content: ''; position: absolute; inset: 10% 0 2%; border-radius: 50%; background: radial-gradient(ellipse at 60% 42%, var(--smart-primary-soft), transparent 65%); }
.login-organisms :deep(.canvas-whale) { position: absolute; top: 5%; left: 0; right: auto; width: 51%; height: 55%; transform: none; opacity: .32; pointer-events: none; }
.login-organisms .login-jellyfish { position: absolute; z-index: 1; top: 8%; right: 7%; width: min(64%, 360px); height: 88%; opacity: .95; pointer-events: none; filter: none; }
.login-glyph { position: absolute; left: 2%; bottom: 12%; opacity: .7; font: 800 clamp(80px, 10vw, 156px)/1 var(--font-display); letter-spacing: -.07em; pointer-events: none; }
.login-glyph span { color: transparent; background: linear-gradient(125deg, var(--login-glass-highlight), var(--login-glass-luster) 30%, var(--login-glass-highlight) 45%, transparent 68%); background-size: 220% 100%; background-clip: text; -webkit-background-clip: text; -webkit-text-stroke: 1px var(--login-glyph-edge); animation: login-glass-flow 22s ease-in-out infinite; }
.login-scene-label { position: absolute; bottom: 0; left: 0; font: 10px var(--font-mono); color: var(--smart-muted); letter-spacing: .12em; }
.login-trust { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 24px 0 0; padding-top: 18px; border-top: 1px solid var(--smart-border); }
.login-trust > div { display: grid; gap: 6px; }
.login-trust dt { color: var(--smart-muted); font-size: 12px; }
.login-trust dd { margin: 0; color: var(--smart-text); font-size: 13px; }
.login-form { position: relative; isolation: isolate; overflow: hidden; display: grid; gap: 13px; width: 100%; min-width: 0; padding: 26px; border: 1px solid var(--login-glass-edge); border-radius: 14px 14px 14px 14px / 13px 13px 15px 15px; background: var(--login-glass-bg); box-shadow: var(--login-glass-shadow); backdrop-filter: blur(var(--login-glass-blur)) saturate(120%); -webkit-backdrop-filter: blur(var(--login-glass-blur)) saturate(120%); }
.login-form::before, .login-form::after { content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none; z-index: 0; }
.login-form::before { background: radial-gradient(ellipse 70% 55% at 50% -10%, var(--login-glass-highlight), transparent 72%), linear-gradient(145deg, var(--login-glass-luster), transparent 36%); opacity: .55; }
.login-form::after { background: linear-gradient(180deg, var(--login-glass-highlight), transparent 18%, transparent 82%, var(--login-glass-luster)); opacity: .16; animation: none; }
.login-form > * { position: relative; z-index: 1; }
.login-form__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.login-form__header .editorial-label { margin-bottom: 12px; font-size: 10px; letter-spacing: .06em; }
.login-form__header h2 { margin: 0 0 6px; font-size: 27px; font-weight: 550; line-height: 1.2; color: var(--smart-text); }
.login-form__header p:not(.editorial-label) { margin: 0; color: var(--smart-muted); font-size: 13px; line-height: 1.6; }
.login-form__status { display: inline-flex; align-items: center; gap: 6px; margin-top: 2px; color: var(--smart-primary-strong); font: 9px var(--font-mono); letter-spacing: .06em; }
.login-form__status > span { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.role-switcher { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; padding: 4px; border: 1px solid var(--smart-border); border-radius: 11px; background: var(--smart-bg); }
.role-switcher button { display: flex; justify-content: center; align-items: center; gap: 8px; min-height: 40px; padding: 8px; border: 1px solid transparent; border-radius: 7px; background: var(--smart-surface); color: var(--smart-muted); font-size: 13px; }
.role-switcher button.is-active { border-color: var(--smart-primary-strong); color: var(--smart-primary-strong); font-weight: 600; }
.role-switcher__dot { width: 6px; height: 6px; border: 1px solid currentColor; border-radius: 50%; }
.role-switcher button.is-active .role-switcher__dot { background: currentColor; }
.role-switcher__hint { margin: 8px 0 0; color: var(--smart-muted); font-size: 11.5px; line-height: 1.6; }
.role-switcher__hint code { padding: 1px 5px; border-radius: 4px; background: var(--smart-primary-soft); color: var(--smart-primary-strong); font-family: var(--font-mono); font-size: 11px; }
.login-form__fields { display: grid; gap: 16px; }
.login-field { display: grid; gap: 8px; min-width: 0; }
.login-field__label { color: var(--smart-text); font-size: 13px; font-weight: 500; }
.login-input-shell { display: flex; align-items: center; position: relative; min-width: 0; border: 1px solid var(--smart-border-strong); border-radius: 9px; background: var(--smart-surface); }
.login-input-shell:focus-within { border-color: var(--smart-primary-strong); box-shadow: 0 0 0 3px var(--smart-primary-soft); }
.login-input-icon { position: absolute; left: 13px; color: var(--smart-muted); font-size: 16px; pointer-events: none; }
.login-input-shell input { width: 100%; min-width: 0; min-height: 44px; padding: 0 44px 0 40px; border: 0; outline: none; background: transparent; color: var(--smart-text); border-radius: inherit; font: 14px var(--font-cn); }
.login-input-shell input::placeholder { color: var(--smart-muted); opacity: 1; }
.password-visibility-toggle { position: absolute; right: 2px; top: 2px; display: grid; place-items: center; width: 44px; height: 44px; padding: 0; border: 0; border-radius: 7px; background: transparent; color: var(--smart-muted); }
.password-visibility-toggle:hover { color: var(--smart-primary-strong); }
.login-form__options { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.remember-control { position: relative; display: flex; align-items: center; gap: 8px; min-height: 32px; color: var(--smart-muted); font-size: 12px; cursor: pointer; }
.remember-control input { width: 16px; height: 16px; margin: 0; accent-color: var(--smart-primary); cursor: pointer; }
.login-form__policy { color: var(--smart-muted); font-size: 11px; line-height: 1.6; }
.login-form__error, .login-form__notice { margin: 0; padding: 10px 12px; border: 1px solid var(--smart-border-strong); border-radius: 8px; background: var(--smart-bg); color: var(--smart-text); font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
.login-form__error { border-color: var(--smart-danger); color: var(--smart-danger); }
.login-submit { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; min-height: 46px; padding: 12px 16px; border: 1px solid transparent; border-radius: 9px; background: var(--smart-primary); color: var(--smart-accent-foreground); font: 600 14px var(--font-cn); }
.login-submit:hover:not(:disabled) { background: var(--smart-primary-strong); }
.login-submit__spinner { width: 16px; height: 16px; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: login-spin .8s linear infinite; }
.login-registration { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 0 6px; color: var(--smart-muted); font-size: 13px; }
.login-registration button { min-height: 36px; padding: 4px; border: 0; border-radius: 4px; background: var(--smart-surface); color: var(--smart-primary-strong); font-size: 13px; text-decoration: underline; text-underline-offset: 4px; }
.login-registration p { flex-basis: 100%; margin: 6px 0 0; line-height: 1.6; text-align: center; overflow-wrap: anywhere; }
.login-form__guidance { margin: 0; color: var(--smart-muted); font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
.login-form__footer { margin: 0; padding-top: 12px; border-top: 1px solid var(--smart-border); color: var(--smart-muted); font-size: 11px; line-height: 1.7; text-align: center; }
.login-form button:disabled { cursor: not-allowed; opacity: .65; }
.login-form :is(button, input):focus-visible, .login-appearance select:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 3px; }
.login-form .login-input-shell input:focus-visible { outline: none; }
.login-page-footer { display: flex; justify-content: space-between; gap: 16px; color: var(--smart-muted); font: 10px var(--font-mono); letter-spacing: .06em; }
:global([data-theme='light'] .login-shell) { --login-glass-bg: rgba(255, 255, 255, .74); --login-glass-edge: rgba(80, 125, 146, .27); --login-glass-highlight: rgba(255, 255, 255, .8); --login-glass-luster: rgba(145, 201, 218, .18); --login-glass-shadow: 0 20px 56px rgba(16, 53, 70, .09), inset 0 1px 0 rgba(255, 255, 255, .98), inset 1px 0 0 rgba(255, 255, 255, .72), inset 0 -1px 0 rgba(80, 125, 146, .12); --login-glyph-edge: rgba(80, 125, 146, .2); }
:global([data-theme='light'] .login-organisms .login-jellyfish) { opacity: .92; }
:global([data-theme='light'] .login-glyph) { opacity: .55; }
@keyframes login-glass-flow { 0%, 100% { background-position: 100% 50%; } 50% { background-position: 0% 50%; } }
@keyframes login-spin { to { transform: rotate(360deg); } }
@media (max-width: 1100px) {
  .login-shell { gap: 24px; }
  .login-layout { flex: none; grid-template-columns: minmax(0, 1fr); width: min(100%, 540px); gap: 24px; }
  .login-showcase { display: grid; grid-template-columns: minmax(0, 1fr) 170px; align-items: center; gap: 12px; }
  .login-copy .editorial-label { margin-bottom: 12px; font-size: 10px; }
  .login-copy h1 { font-size: 30px; }
  .login-copy__description, .login-trust, .login-scene-label, .login-glyph, .login-organisms :deep(.canvas-whale) { display: none; }
  .login-organisms { width: 100%; height: 170px; margin: 0; }
  .login-organisms .login-jellyfish { top: 8%; right: 5%; width: 90%; height: 84%; }
  .login-form { width: min(100%, 480px); margin-inline: auto; }
  .login-page-footer { margin-top: auto; }
}
@media (max-width: 600px) {
  .login-shell { --login-glass-blur: 8px; gap: 20px; padding: 20px 16px; }
  .login-topbar { flex-wrap: wrap; gap: 16px; }
  .login-brand > div > span { font-size: 8px; }
  .login-appearance { width: 100%; gap: 12px; }
  .login-appearance label { flex: 1; }
  .login-appearance select { flex: 1; max-width: none; min-width: 0; }
  .login-showcase { grid-template-columns: minmax(0, 1fr) 112px; gap: 8px; }
  .login-copy h1 { font-size: clamp(21px, 6vw, 26px); }
  .login-copy .editorial-label { font-size: 9px; margin-bottom: 8px; }
  .login-organisms { height: 128px; }
  .login-layout { gap: 16px; }
  .login-form { gap: 16px; padding: 24px 20px; border-radius: 12px; }
  .login-form__header h2 { font-size: 27px; }
  .login-form__status { font-size: 8px; }
  .login-page-footer { font-size: 9px; flex-wrap: wrap; }
}
.login-shell[data-visual-mode='lightweight'], .login-shell[data-visual-mode='reduced-motion'] { --login-glass-blur: 6px; }
.login-shell:not([data-visual-mode='balanced']) .login-form::after,
.login-shell:not([data-visual-mode='balanced']) .login-glyph span { animation: none; }
@media (pointer: coarse) { .login-form::after, .login-glyph span { animation: none; } }
@media (prefers-reduced-motion: reduce) { .login-submit__spinner, .login-form::after, .login-glyph span { animation: none; } .login-form, .login-submit { transition: none; } }
.login-shell[data-visual-mode='reduced-motion'] .login-submit__spinner { animation: none; }
/* P1 简约化：画面只保留「一句价值主张 + 宇宙星空 + 一个果冻卡」。
   装饰性元素只做视觉隐藏、不删 DOM，避免破坏既有的布局/几何回归契约。 */
.login-glyph, .login-scene-label { display: none; }
.login-trust { grid-template-columns: 1fr; gap: 8px; margin-top: 18px; padding-top: 14px; }
.login-trust > div:not(:first-child) { display: none; }
.login-trust > div { display: flex; align-items: baseline; gap: 10px; }
.login-copy__description { max-width: 380px; font-size: 14px; line-height: 1.7; }
/* 卡片聚焦反馈统一由 global.css 的 .login-form 规则负责（含 reduced-motion 关闭）；
   这里只保留按钮的按压缩放，卡片几何恒为 transform: none。 */
.login-submit { transition: transform 180ms cubic-bezier(.22, 1.3, .36, 1), background-color 160ms ease; }
.login-submit:active { transform: scale(.985); }
.login-organisms::before { opacity: .55; }
.login-form { gap: 12px; }
.login-form__header h2 { font-size: 24px; }
@supports not (backdrop-filter: blur(1px)) { .login-form { background: var(--smart-surface); } }
</style>
