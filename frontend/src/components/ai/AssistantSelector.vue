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
    </div>
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
import { computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useAiChatStore } from '../../stores/aiChat.js'

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
</style>
