<template>
  <section class="voice-bar" aria-labelledby="robot-voice-title">
    <label for="robot-voice-input" id="robot-voice-title" class="sr-only">语音指令</label>
    <div class="voice-row">
      <input
        id="robot-voice-input"
        ref="inputEl"
        v-model="input"
        type="text"
        class="voice-input"
        placeholder="输入语音指令：停止 / 拍照 / 开始巡检 / 暂停任务 / 取消任务"
        :disabled="busy"
        @keydown.enter="send"
      />
      <button type="button" class="btn btn-primary" :disabled="busy || !input.trim()" @click="send">发送</button>
    </div>
    <p class="hint-text">
      指令文本会过注入检测后再执行；注入话术（例如「忽略之前所有指令」）会被拦截。
    </p>
    <p v-if="lastResult" class="hint-text" :class="resultClass">
      {{ formatResult(lastResult) }}
    </p>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { sendRobotVoice } from '../../api/robot'

const props = defineProps({ deviceKey: { type: String, required: true } })

const input = ref('')
const busy = ref(false)
const lastResult = ref(null)

const KNOWN = [
  { op: 'STOP', label: '停止' },
  { op: 'CAPTURE', label: '拍照' },
  { op: 'PATROL', label: '开始巡检' },
  { op: 'PAUSE_LATEST', label: '暂停最新任务' },
  { op: 'CANCEL_LATEST', label: '取消最新任务' }
]

async function send() {
  const text = input.value.trim()
  if (!text || busy.value) return
  busy.value = true
  try {
    const response = await sendRobotVoice(props.deviceKey, text)
    lastResult.value = response?.data || response
    input.value = ''
  } catch (e) {
    lastResult.value = {
      matched: false,
      blocked: false,
      message: e?.message || '语音指令发送失败'
    }
  } finally {
    busy.value = false
  }
}

function formatResult(r) {
  if (!r) return ''
  if (r.blocked) return `⚠ 注入拦截：${r.message || '检测到高危话术'}`
  if (!r.matched) return `✗ ${r.message || '未识别指令'}`
  const op = KNOWN.find(k => k.op === r.op)
  const label = op ? op.label : (r.op || '已执行')
  const error = r.executionError ? `｜${r.executionError}` : ''
  return `✓ ${label}${error}`
}

import { computed } from 'vue'
const resultClass = computed(() => {
  const r = lastResult.value
  if (!r) return ''
  if (r.blocked) return 'result-danger'
  if (r.matched && !r.executionError) return 'result-ok'
  return 'result-warn'
})
</script>

<style scoped>
.voice-bar {
  padding: var(--ds-space-3) 0;
}

.voice-row {
  display: flex;
  gap: var(--ds-space-2);
}

.voice-input {
  flex: 1;
  height: var(--ds-control-height, 36px);
  padding: 0 var(--ds-space-3);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-text);
  font-size: var(--ds-font-sm);
  outline: none;
  transition: border-color var(--ds-duration-fast) ease;
}
.voice-input:focus { border-color: var(--ds-color-primary); }
.voice-input:disabled { opacity: 0.5; cursor: not-allowed; }

.btn {
  height: var(--ds-control-height, 36px);
  padding: 0 var(--ds-space-4);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-text);
  font-size: var(--ds-font-sm);
  cursor: pointer;
}
.btn:hover:not(:disabled) { border-color: var(--ds-color-primary); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-primary { border-color: var(--ds-color-primary); background: rgba(36, 150, 237, 0.14); }

.hint-text {
  margin: var(--ds-space-2) 0 0;
  font-size: var(--ds-font-xs);
  line-height: var(--ds-line-base);
}

.result-ok { color: var(--ds-color-success); }
.result-warn { color: var(--ds-color-warning); }
.result-danger { color: var(--ds-color-danger); }

.sr-only {
  position: absolute;
  width: 1px; height: 1px;
  padding: 0; margin: -1px; overflow: hidden;
  clip: rect(0, 0, 0, 0); border: 0;
}
</style>
