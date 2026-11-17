<template>
  <div class="fv-panel">
    <!-- 人工复测表单 -->
    <div class="fv-form">
      <label class="fv-field">
        <span>复测读数</span>
        <input v-model="form.reading" type="number" step="any" placeholder="—" aria-label="复测读数" />
      </label>
      <label class="fv-field">
        <span>结论等级</span>
        <select v-model="form.status" aria-label="结论等级">
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label class="fv-field fv-field--wide">
        <span>观察记录</span>
        <textarea v-model="form.note" rows="2" maxlength="500" placeholder="现场观察记录（人工复核口径，非传感器读数）" aria-label="观察记录"></textarea>
      </label>
      <div class="fv-actions">
        <button type="button" class="fv-submit" :disabled="submitting" @click="submit">
          {{ submitting ? '提交中…' : `提交核查结果（${nextVer}）` }}
        </button>
        <span v-if="hasLocalOnly" class="fv-local-flag">SESSION-LOCAL · 存在未同步后端的本地记录</span>
      </div>
      <p v-if="formError" class="fv-error">{{ formError }}</p>
      <p v-if="submitError" class="fv-error">提交失败：{{ submitError }}（已保留本地记录）</p>
    </div>

    <!-- 版本化核查结果 -->
    <div class="fv-versions">
      <h3>核查结果版本</h3>
      <p v-if="!versions.length" class="fv-empty">—</p>
      <div v-for="v in versions" :key="v.version + v.at" class="fv-version" :class="{ 'fv-version--local': !v.synced }">
        <span class="fv-version__tag" :class="{ 'fv-version__tag--local': !v.synced }">{{ v.version }}<i v-if="!v.synced">LOCAL</i></span>
        <span class="fv-version__meta">
          <b :class="`fv-status--${v.status.toLowerCase()}`">{{ v.status }}</b>
          <small>读数 {{ v.reading == null ? '—' : v.reading }} · {{ formatAt(v.at) }}</small>
        </span>
        <p v-if="v.note" class="fv-version__note">{{ v.note }}</p>
      </div>
    </div>

    <!-- 会话事件流 -->
    <div class="fv-stream">
      <h3>核查事件流</h3>
      <p v-if="!sessionEvents.length" class="fv-empty">本会话暂无核查事件</p>
      <ol v-else class="fv-stream-list">
        <li v-for="e in sessionEvents" :key="e.id" class="fv-stream-item">
          <i class="fv-stream__dot" :class="`fv-stream__dot--${e.synced ? 'ok' : 'local'}`"></i>
          <span class="fv-stream__body">
            <b>{{ eventLabel(e.kind) }}<small v-if="e.version"> · {{ e.version }}</small></b>
            <small>{{ formatAt(e.at) }}{{ e.synced ? ' · 已同步后端' : ' · 仅本地会话' }}</small>
          </span>
        </li>
      </ol>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { verifyInspection } from '../../api/inspector'
import {
  VERIFY_STATUSES,
  buildVerifyPayload,
  nextVersion,
  appendSessionEvent,
  makeVersionEntry
} from '../../domain/inspector/fieldVerification.js'

const props = defineProps({
  event: { type: Object, default: () => ({}) }
})

const statuses = VERIFY_STATUSES
const form = reactive({ reading: '', status: 'PENDING', note: '' })
const submitting = ref(false)
const submitError = ref('')
const formError = ref('')

const sessionEvents = ref([])
const sessionVersions = ref([])

const hasLocalOnly = computed(() =>
  sessionVersions.value.some(v => !v.synced) || sessionEvents.value.some(e => !e.synced)
)

const nextVer = computed(() => nextVersion(props.event?.verification, sessionVersions.value.length))

const versions = computed(() => sessionVersions.value)

function formatAt(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', { hour12: false })
}

function eventLabel(kind) {
  return { submitted: '提交核查', resubmitted: '重新提交', comment_created: '追加观察记录' }[kind] || kind
}

async function submit() {
  submitError.value = ''
  formError.value = ''
  const payload = buildVerifyPayload(props.event, form)
  if (!payload.inspectionId) {
    formError.value = '事件 ID 缺失，无法提交'
    return
  }
  const version = nextVer.value
  submitting.value = true
  try {
    await verifyInspection(payload)
    sessionVersions.value = [...sessionVersions.value, makeVersionEntry(version, payload, true)]
    sessionEvents.value = appendSessionEvent(
      sessionEvents.value,
      sessionVersions.value.length > 1 ? 'resubmitted' : 'submitted',
      { version, status: payload.status, reading: payload.details.reading, synced: true }
    )
    submitError.value = ''
    form.note = ''
    form.reading = ''
  } catch (err) {
    submitError.value = err?.message || '网络错误'
    sessionVersions.value = [...sessionVersions.value, makeVersionEntry(version, payload, false)]
    sessionEvents.value = appendSessionEvent(
      sessionEvents.value,
      'submitted',
      { version, status: payload.status, reading: payload.details.reading, synced: false }
    )
  } finally {
    submitting.value = false
  }
}

defineExpose({ form, sessionEvents, sessionVersions, submit })
</script>

<style scoped>
.fv-panel {
  display: grid;
  gap: 16px;
  padding: 16px;
  border: 1px solid var(--smart-border);
  border-radius: 12px;
  font-size: 13px;
}

.fv-form { display: grid; gap: 10px; }

.fv-field { display: grid; gap: 5px; }
.fv-field span {
  color: var(--smart-muted);
  font: 10px Consolas, 'Cascadia Mono', ui-monospace, monospace;
  letter-spacing: .1em;
}

.fv-field input,
.fv-field select,
.fv-field textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--smart-border);
  border-radius: 6px;
  background: var(--smart-surface);
  color: var(--smart-text);
  font: 13px Consolas, 'Cascadia Mono', ui-monospace, monospace;
  box-sizing: border-box;
}

.fv-field textarea { resize: vertical; }

.fv-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.fv-submit {
  padding: 8px 16px;
  border: 1px solid var(--smart-primary, #2496ED);
  border-radius: 999px;
  background: color-mix(in srgb, var(--smart-primary, #2496ED) 14%, transparent);
  color: var(--smart-text);
  font-size: 12px;
  cursor: pointer;
  transition: background-color 120ms ease, border-color 120ms ease;
}

.fv-submit:hover:not(:disabled) {
  background: color-mix(in srgb, var(--smart-primary, #2496ED) 24%, transparent);
}

.fv-submit:disabled {
  opacity: .55;
  cursor: not-allowed;
}

.fv-local-flag {
  color: var(--smart-warning, #D29922);
  font: 10px Consolas, 'Cascadia Mono', ui-monospace, monospace;
  letter-spacing: .06em;
}

.fv-error {
  margin: 0;
  color: var(--smart-danger, #F85149);
  font-size: 12px;
}

.fv-versions h3,
.fv-stream h3 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--smart-text);
}

.fv-empty {
  margin: 0;
  color: var(--smart-muted);
  font: 11px Consolas, 'Cascadia Mono', ui-monospace, monospace;
}

.fv-version {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  margin-bottom: 8px;
  border: 1px solid var(--smart-border);
  border-radius: 8px;
}

.fv-version--local {
  border-style: dashed;
  border-color: color-mix(in srgb, var(--smart-warning, #D29922) 55%, transparent);
}

.fv-version__tag {
  font: 11px Consolas, 'Cascadia Mono', ui-monospace, monospace;
  color: var(--smart-primary-strong, #7AD7F5);
}

.fv-version__tag--local i {
  margin-left: 6px;
  padding: 1px 5px;
  border: 1px solid color-mix(in srgb, var(--smart-warning, #D29922) 55%, transparent);
  border-radius: 3px;
  color: var(--smart-warning, #D29922);
  font-style: normal;
  font-size: 9px;
  letter-spacing: .1em;
}

.fv-version__meta {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.fv-version__meta b { font-size: 12px; }
.fv-version__meta small { color: var(--smart-muted); font-size: 11px; }

.fv-status--pass { color: var(--smart-success, #3FB68B); }
.fv-status--fail { color: var(--smart-danger, #F85149); }
.fv-status--pending { color: var(--smart-warning, #D29922); }

.fv-version__note {
  margin: 0;
  color: var(--smart-muted);
  font-size: 12px;
  line-height: 1.6;
}

.fv-stream-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}

.fv-stream-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding-left: 4px;
  border-left: 2px solid var(--smart-border);
  padding-bottom: 4px;
}

.fv-stream__dot {
  width: 8px;
  height: 8px;
  margin-top: 5px;
  border-radius: 50%;
  flex: none;
}

.fv-stream__dot--ok { background: var(--smart-success, #3FB68B); }
.fv-stream__dot--local { background: var(--smart-warning, #D29922); }

.fv-stream__body { display: grid; line-height: 1.4; }
.fv-stream__body b { font-size: 12px; }
.fv-stream__body small { color: var(--smart-muted); font-size: 11px; }

@media (prefers-reduced-motion: reduce) {
  .fv-panel * { transition: none !important; animation: none !important; }
}
</style>
