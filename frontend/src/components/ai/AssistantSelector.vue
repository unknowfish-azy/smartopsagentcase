<template>
  <div class="assistant-selector" :aria-busy="optionsLoading || preferenceSaving">
    <div class="assistant-selector__controls">
      <label class="assistant-selector__field">
        <span>助手模型</span>
        <select aria-label="助手模型" :value="selectedKey" :disabled="!optionsLoaded || optionsLoading || preferenceSaving" @change="changeProvider">
          <option v-if="!options.some(option => option.key === selectedKey)" :value="selectedKey" disabled>{{ selectedOption.name }}</option>
          <option v-for="option in options" :key="option.key" :value="option.key" :disabled="!option.enabled">
            {{ option.name }}{{ option.kind === 'connection' ? (option.enabled ? ' · 已配置，未实测' : ' · 已停用') : '' }}
          </option>
        </select>
      </label>
      <button type="button" :disabled="optionsLoading || preferenceSaving" aria-label="刷新助手选项" @click="store.loadOptions(true)">{{ optionsLoading ? '加载中…' : '刷新' }}</button>
      <button v-if="allowCreate" class="assistant-selector__create" type="button" aria-label="接入大模型" :aria-expanded="formOpen" @click="formOpen = !formOpen">{{ formOpen ? '收起' : '＋ 接入模型' }}</button>
    </div>
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
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useAiChatStore } from '../../stores/aiChat.js'
import { createModelConnection } from '../../api/model.ts'

defineProps({ allowCreate: Boolean })

const store = useAiChatStore()
const { options, selectedKey, selectedOption, optionsLoaded, optionsLoading, optionsError, preferenceSaving,
  preferenceError, preferenceNotice, canSwitchToMini, accountEpoch } = storeToRefs(store)
const miniStatus = computed(() => {
  if (optionsLoading.value) return '正在检查运行时'
  if (!optionsLoaded.value) return '运行时状态未获取'
  const status = options.value.find(option => option.key === 'mini')?.status
  return { ready: '运行时就绪', offline: '运行时离线', model_missing: '本地模型未安装' }[status] || '运行时不可用'
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
.assistant-selector { flex: none; min-width: 0; padding: 10px; border: 1px solid var(--smart-border); border-radius: 10px; background: var(--smart-surface); color: var(--smart-text); font: 12px/1.5 var(--font-cn); overflow-wrap: anywhere; }
.assistant-selector__controls { display: flex; align-items: end; gap: 8px; min-width: 0; }
.assistant-selector__field { display: grid; flex: 1; gap: 4px; min-width: 0; }
.assistant-selector select { width: 100%; min-width: 0; max-width: 100%; min-height: 44px; padding: 6px; border: 1px solid var(--smart-border-strong); border-radius: 6px; background: var(--smart-card); color: var(--smart-text); font: inherit; text-overflow: ellipsis; }
.assistant-selector button { flex: none; min-height: 44px; padding: 6px 10px; border: 1px solid var(--smart-border-strong); border-radius: 6px; background: var(--smart-card); color: var(--smart-text); font: inherit; cursor: pointer; }
.assistant-selector :is(button, select):focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.assistant-selector :disabled { cursor: not-allowed; opacity: .65; }
.assistant-selector__status { display: flex; flex-wrap: wrap; gap: 2px 10px; margin-top: 6px; color: var(--smart-muted); }
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
