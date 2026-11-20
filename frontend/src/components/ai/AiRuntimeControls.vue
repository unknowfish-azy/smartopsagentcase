<template>
  <div v-if="controllable" class="ai-runtime" role="group" aria-label="AI 服务启停">
    <span class="ai-runtime__dot" :class="`is-${state}`" :title="dotTitle"></span>
    <button type="button" class="ai-runtime__btn" :disabled="!canStart" :title="startTitle"
            aria-label="启动 AI 服务" @click="start">
      <VideoPlay :size="13" />
    </button>
    <button type="button" class="ai-runtime__btn" :disabled="!canStop" :title="stopTitle"
            aria-label="停止 AI 服务" @click="stop">
      <VideoPause :size="13" />
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { VideoPlay, VideoPause } from '@element-plus/icons-vue'
import { useAiRuntime } from '../../composables/useAiRuntime'

const { state, error, controllable, canStart, canStop, start, stop } = useAiRuntime()

const LABELS = {
  running: '运行中', partial: '部分可用', stopped: '已停止',
  starting: '启动中', stopping: '停止中', error: '异常', disabled: '未开启控制', unknown: '检查中',
}
const label = computed(() => LABELS[state.value] || '检查中')
const detail = computed(() => {
  if (error.value) return `（${error.value}）`
  return ''
})
const dotTitle = computed(() => `AI 服务：${label.value}（Ollama + ai-service）${detail.value}`)
const startTitle = computed(() => (canStart.value
  ? '启动 Ollama 运行时与 ai-service'
  : `当前${label.value}，无法启动`))
const stopTitle = computed(() => (canStop.value
  ? '停止 Ollama 运行时与 ai-service（外部安装的 Ollama 不会被停止）'
  : `当前${label.value}，无法停止`))
</script>

<style scoped>
.ai-runtime { display: inline-flex; align-items: center; gap: 3px; flex: none; }
.ai-runtime__dot { width: 7px; height: 7px; margin-right: 2px; border-radius: 50%; background: var(--smart-muted); }
.ai-runtime__dot.is-running { background: var(--ds-semantic-success); box-shadow: 0 0 0 3px color-mix(in srgb, var(--ds-semantic-success) 22%, transparent); }
.ai-runtime__dot.is-partial { background: var(--ds-semantic-warning, #e6a23c); }
.ai-runtime__dot.is-stopped, .ai-runtime__dot.is-error { background: var(--smart-danger); }
.ai-runtime__dot.is-starting, .ai-runtime__dot.is-stopping { background: var(--ds-semantic-warning, #e6a23c); animation: ai-runtime-pulse 1s ease-in-out infinite; }
.ai-runtime__btn { display: grid; place-items: center; width: 26px; height: 26px; padding: 0; border: 1px solid var(--smart-border-strong); border-radius: 6px; background: var(--smart-card); color: var(--smart-text); cursor: pointer; transition: color var(--duration-fast), border-color var(--duration-fast); }
.ai-runtime__btn:hover:not(:disabled) { color: var(--smart-primary-strong); border-color: var(--smart-primary-strong); }
.ai-runtime__btn:disabled { opacity: .42; cursor: not-allowed; }
.ai-runtime__btn:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }

@keyframes ai-runtime-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
</style>
