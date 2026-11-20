<template>
  <div class="assistant-selector" :class="{ 'is-collapsed': collapsed && !manuallyExpanded }" :aria-busy="optionsLoading || preferenceSaving">
    <div class="assistant-selector__bar">
    <!-- 折叠态：只显示一行胶囊条，点击展开 -->
    <button
      v-if="collapsed && !manuallyExpanded"
      type="button"
      class="assistant-selector__pill"
      :title="`点击展开模型设置 · ${miniStatus}`"
      @click="manuallyExpanded = true"
    >
      <span class="pill-label">助手模型</span>
      <span class="pill-model">{{ selectedOption.name || selectedKey }}</span>
      <span v-if="selectedOption.kind === 'connection'" class="pill-tag pill-tag--conn">自定义接入</span>
      <span v-else class="pill-tag pill-tag--mini">智维</span>
      <span class="pill-status" :class="{ 'is-ready': miniReady }">
        <span class="pill-dot"></span>{{ miniStatusShort }}
      </span>
      <span class="pill-caret" aria-hidden="true">▾</span>
    </button>

    <!-- 展开态：完整模型选择表单 -->
    <div v-else class="assistant-selector__controls">
        <label class="assistant-selector__field">
          <span>助手模型</span>
          <select aria-label="助手模型" :value="selectedKey" :disabled="!optionsLoaded || optionsLoading || preferenceSaving" @change="changeProvider">
            <option v-if="!options.some(option => option.key === selectedKey)" :value="selectedKey" disabled>{{ selectedOption.name }}</option>
            <option v-for="option in options" :key="option.key" :value="option.key" :disabled="!option.enabled">
              {{ option.name }}{{ option.kind === 'connection' ? (option.enabled ? ' · 已配置，未实测' : ' · 已停用') : '' }}
            </option>
          </select>
        </label>
        <button type="button" class="assistant-selector__icon-btn" :disabled="optionsLoading || preferenceSaving" :aria-label="optionsLoading ? '正在加载助手选项' : '刷新助手选项'" :title="optionsLoading ? '正在加载…' : '刷新模型列表'" @click="store.loadOptions(true)"><Refresh :size="14" /></button>
        <button v-if="allowCreate" class="assistant-selector__create" type="button" aria-label="接入大模型" :aria-expanded="formOpen" :title="formOpen ? '收起接入表单' : '接入自己的大模型'" @click="formOpen = !formOpen"><Plus :size="13" /> {{ formOpen ? '收起' : '接入模型' }}</button>
        <!-- 折叠按钮：收起回胶囊态 -->
        <button v-if="collapsible" type="button" class="assistant-selector__collapse" title="收起模型设置" @click="manuallyExpanded = false">收起</button>
      </div>
      <AiRuntimeControls />
    </div>
    <template v-if="!collapsed || manuallyExpanded">
      <form v-if="allowCreate && formOpen" class="assistant-selector__form" @submit.prevent="saveConnection">
        <label>名称<input v-model.trim="form.name" required placeholder="如 DeepSeek"></label>
        <label>接口地址<input v-model.trim="form.baseUrl" required placeholder="https://api.deepseek.com/v1"></label>
        <label>模型名<input v-model.trim="form.modelName" required placeholder="deepseek-chat"></label>
        <label>API 密钥<input v-model.trim="form.apiKey" type="password" required autocomplete="off" placeholder="sk-…"></label>
        <p class="assistant-selector__hint">密钥由服务端 AES 加密保存，不会回显；保存后自动切换到该模型。</p>
        <button type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存并切换' }}</button>
        <p v-if="formError" role="alert">{{ formError }}</p>
      </form>
      <RouterLink v-if="allowCreate" to="/model-settings" class="assistant-selector__link">去「模型接入」填写 API 密钥 ↗</RouterLink>
      <div class="assistant-selector__status" role="status">
        <span>智维 Mini · {{ miniStatus }}</span>
        <span v-if="optionsLoaded && selectedOption.kind === 'connection'">{{ selectedOption.enabled ? '已配置，未实测（未实时验证）' : '已保存的连接不可用，不会自动切换' }}</span>
        <span v-if="optionsLoaded && selectedOption.model">{{ selectedOption.model }}</span>
        <span v-if="optionsLoaded && selectedOption.detail">{{ selectedOption.detail }}</span>
        <span v-if="preferenceSaving">正在保存偏好…</span>
        <span v-if="preferenceNotice">{{ preferenceNotice }}</span>
      </div>
      <p v-if="optionsError" role="alert">选项加载失败：{{ optionsError }} 请点击刷新重试。</p>
      <p v-if="preferenceError" role="alert">偏好保存失败：{{ preferenceError }} 原选择已保留。</p>
      <button v-if="canSwitchToMini" class="assistant-selector__fallback" type="button" :disabled="preferenceSaving || optionsLoading || !optionsLoaded" @click="store.selectProvider('mini')">改用智维 Mini</button>
    </template>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { Refresh, Plus } from '@element-plus/icons-vue'
import { useAiChatStore } from '../../stores/aiChat.js'
import { createModelConnection } from '../../api/model.ts'
import AiRuntimeControls from './AiRuntimeControls.vue'

const props = defineProps({ allowCreate: Boolean, collapsed: { type: Boolean, default: false } })
const collapsible = computed(() => props.collapsed)

const store = useAiChatStore()
const { options, selectedKey, selectedOption, optionsLoaded, optionsLoading, optionsError, preferenceSaving,
  preferenceError, preferenceNotice, canSwitchToMini, accountEpoch } = storeToRefs(store)

// 折叠态：用户点击展开后保持展开，直到手动收起
const manuallyExpanded = ref(false)

const miniStatus = computed(() => {
  if (optionsLoading.value) return '正在检查运行时'
  if (!optionsLoaded.value) return '运行时状态未获取'
  const status = options.value.find(option => option.key === 'mini')?.status
  return { ready: '运行时就绪', offline: '运行时离线', model_missing: '本地模型未安装' }[status] || '运行时不可用'
})
const miniReady = computed(() => miniStatus.value === '运行时就绪')
const miniStatusShort = computed(() => {
  if (miniStatus.value === '运行时就绪') return '就绪'
  if (miniStatus.value === '运行时离线') return '离线'
  if (miniStatus.value === '本地模型未安装') return '未安装'
  return '检查中'
})
watch(accountEpoch, () => store.loadOptions(), { immediate: true })
async function changeProvider(event) {
  const target = event.target
  const providerKey = target.value
  target.value = selectedKey.value
  await store.selectProvider(providerKey)
  target.value = selectedKey.value
}

const formOpen = ref(false)
const saving = ref(false)
const formError = ref('')
const form = reactive({ name: '', baseUrl: '', modelName: '', apiKey: '' })
const unwrap = value => value?.data ?? value

async function saveConnection() {
  if (saving.value) return
  saving.value = true
  formError.value = ''
  try {
    const saved = unwrap(await createModelConnection({
      name: form.name.trim(), provider: 'custom', baseUrl: form.baseUrl.trim().replace(/\/+$/, ''),
      modelName: form.modelName.trim(), apiKey: form.apiKey.trim(), enabled: true, timeoutSeconds: 60,
    }))
    await store.loadOptions(true)
    if (saved?.id) await store.selectProvider(`connection:${saved.id}`)
    formOpen.value = false
    Object.assign(form, { name: '', baseUrl: '', modelName: '', apiKey: '' })
  } catch (error) {
    formError.value = error?.response?.data?.message || error.message || '接入失败'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.assistant-selector { flex: none; min-width: 0; padding: 8px 10px; border: 1px solid var(--smart-border); border-radius: 9px; background: var(--smart-surface); color: var(--smart-text); font: 12px/1.5 var(--font-cn); overflow-wrap: anywhere; transition: height .15s ease, padding .15s ease; }
.assistant-selector.is-collapsed { padding: 2px 6px 2px 0; border: 1px solid var(--smart-border); border-radius: 999px; background: color-mix(in srgb, var(--smart-surface) 80%, transparent); overflow: hidden; }
.assistant-selector__bar { display: flex; align-items: center; gap: 6px; min-width: 0; }

/* ===== 折叠胶囊条 ===== */
.assistant-selector__pill {
  display: inline-flex; align-items: center; gap: 8px; flex: 1 1 auto; width: auto; min-width: 0;
  min-height: 32px; padding: 0 12px; border: 0; border-radius: 999px; background: transparent;
  color: var(--smart-text); font: inherit; font-size: 11px; cursor: pointer;
  transition: background-color .15s;
}
.assistant-selector__pill:hover { background: color-mix(in srgb, var(--smart-primary) 8%, transparent); }
.assistant-selector__pill:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.pill-label { color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .12em; text-transform: uppercase; }
.pill-model { font-weight: 500; color: var(--smart-text); }
.pill-tag { padding: 1px 7px; border-radius: 999px; font: 9px var(--font-mono); letter-spacing: .04em; }
.pill-tag--mini { color: var(--smart-primary-strong); background: color-mix(in srgb, var(--smart-primary) 12%, transparent); }
.pill-tag--conn { color: var(--ds-semantic-info); background: color-mix(in srgb, var(--ds-semantic-info) 14%, transparent); }
.pill-status { display: inline-flex; align-items: center; gap: 4px; margin-left: auto; color: var(--smart-muted); font-size: 10px; }
.pill-status.is-ready { color: var(--ds-semantic-success); }
.pill-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--ds-semantic-success); }
.pill-caret { color: var(--smart-muted); font-size: 10px; margin-left: 2px; }
/* 收起按钮 */
.assistant-selector__collapse { flex: none; min-height: 28px; padding: 0 8px; border: 1px solid var(--smart-border); border-radius: 6px; background: var(--smart-surface); color: var(--smart-muted); font: 10px var(--font-mono); cursor: pointer; }
.assistant-selector__collapse:hover { color: var(--smart-text); border-color: var(--smart-border-strong); }

/* ===== 展开态原有样式 ===== */
.assistant-selector__controls { display: flex; align-items: center; gap: 6px; min-width: 0; flex: 1 1 auto; }
.assistant-selector__field { display: grid; flex: 1; gap: 3px; min-width: 0; }
.assistant-selector__field > span { color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .1em; }
.assistant-selector select { width: 100%; min-width: 0; max-width: 100%; min-height: 34px; padding: 4px 8px; border: 1px solid var(--smart-border-strong); border-radius: 6px; background: var(--smart-card); color: var(--smart-text); font: inherit; text-overflow: ellipsis; }
.assistant-selector button { flex: none; min-height: 34px; padding: 5px 10px; border: 1px solid var(--smart-border-strong); border-radius: 6px; background: var(--smart-card); color: var(--smart-text); font: inherit; font-size: 11px; cursor: pointer; }
.assistant-selector__icon-btn { display: grid; place-items: center; width: 34px; height: 34px; padding: 0; }
.assistant-selector__create { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.assistant-selector :is(button, select):focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.assistant-selector :disabled { cursor: not-allowed; opacity: .65; }
.assistant-selector__status { display: flex; flex-wrap: wrap; gap: 2px 10px; margin-top: 5px; color: var(--smart-muted); font-size: 11px; }
.assistant-selector p { margin: 6px 0 0; color: var(--smart-danger); }
.assistant-selector__fallback { margin-top: 8px; }
.assistant-selector__form { display: grid; gap: 8px; margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--smart-border); }
.assistant-selector__form label { display: grid; gap: 4px; color: var(--smart-muted); }
.assistant-selector__form input { min-height: 32px; padding: 4px 8px; border: 1px solid var(--smart-border-strong); border-radius: 6px; background: var(--smart-card); color: var(--smart-text); font: inherit; }
.assistant-selector__hint { margin: 0; color: var(--smart-muted); }
.assistant-selector__form button { justify-self: start; min-height: 32px; }
.assistant-selector__link { display: none; margin-top: 6px; color: var(--smart-primary-strong); font-size: 12px; }

/* 手机端：填密钥是长文本粘贴场景，不适合窄屏手输，只保留切换与跳转。 */
@media (max-width: 600px) {
  .assistant-selector__create, .assistant-selector__form { display: none; }
  .assistant-selector__link { display: inline-flex; }
}
</style>
