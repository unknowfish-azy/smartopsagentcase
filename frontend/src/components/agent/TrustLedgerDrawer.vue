<template>
  <Teleport to="body">
    <transition name="tld-fade">
      <section
        v-if="modelValue"
        class="tld"
        role="dialog"
        aria-modal="true"
        aria-label="信任账本"
      >
        <header class="tld-head">
          <div class="tld-head__text">
            <strong>信任账本 · Trust Ledger</strong>
            <small>审计哈希链验真 + Agent 运行回放</small>
          </div>
          <button type="button" class="tld-close" aria-label="关闭信任账本" @click="close">×</button>
        </header>

        <section class="tld-verify" aria-label="一键验链">
          <div class="tld-verify__row">
            <button
              type="button"
              class="tld-btn tld-btn--primary"
              :disabled="verifyLoading"
              @click="runVerify"
            >
              {{ verifyLoading ? '校验中…' : '一键验链' }}
            </button>
            <span class="tld-hint">校验审计哈希链、轮转分段与清单锚点</span>
          </div>
          <p v-if="verifyError" class="tld-error" role="alert">{{ verifyError }}</p>
          <p
            v-else-if="verifyResult"
            class="tld-verify__result"
            :class="verifyResult.ok ? 'is-ok' : 'is-bad'"
          >
            <template v-if="!verifyResult.available">
              不可用：{{ verifyResult.reason || '安全基线未启用' }}
            </template>
            <template v-else>
              ok={{ verifyResult.ok ? 'true' : 'false' }}
              · 事件 {{ verifyResult.total_events ?? '—' }}
              · 分段 {{ verifyResult.segments ?? '—' }}
              <span v-if="verifyResult.first_bad_file"> · 首个异常文件 {{ verifyResult.first_bad_file }}</span>
              <span v-else-if="verifyResult.reason"> · {{ verifyResult.reason }}</span>
              <span v-if="verifyResult.checkedAt"> · {{ formatTime(verifyResult.checkedAt) }}</span>
            </template>
          </p>
          <p v-else class="tld-muted">尚未验链：点击按钮执行真实验真，不用占位结论代替。</p>
        </section>

        <section class="tld-query">
          <label class="tld-query__field">
            <span>run_id</span>
            <input
              v-model="runIdInput"
              type="text"
              placeholder="run_..."
              autocomplete="off"
              @keyup.enter="loadRun(runIdInput)"
            />
          </label>
          <button
            type="button"
            class="tld-btn"
            :disabled="detailLoading || !runIdInput.trim()"
            @click="loadRun(runIdInput)"
          >
            查询
          </button>
        </section>

        <p v-if="listError" class="tld-error" role="alert">{{ listError }}</p>
        <p v-if="detailError" class="tld-error" role="alert">{{ detailError }}</p>

        <div class="tld-body">
          <aside class="tld-list" aria-label="最近运行">
            <h3>最近运行</h3>
            <p v-if="listLoading" class="tld-muted">加载中…</p>
            <p v-else-if="!runs.length" class="tld-muted">暂无运行记录（未运行/无数据）</p>
            <ul v-else>
              <li v-for="run in runs" :key="run.runId">
                <button
                  type="button"
                  class="tld-run"
                  :class="{ 'is-active': detail && detail.runId === run.runId }"
                  @click="loadRun(run.runId)"
                >
                  <span class="tld-run__id">{{ run.runId }}</span>
                  <span class="tld-run__meta">{{ run.risk }} · {{ run.status }} · {{ formatTime(run.createdAt) }}</span>
                </button>
              </li>
            </ul>
          </aside>

          <div class="tld-detail">
            <p v-if="!detail" class="tld-muted">选择一条运行记录，或输入 run_id 查看回放。</p>
            <template v-else>
              <div class="tld-summary">
                <span class="tld-chip" :class="`is-${String(detail.risk || 'low').toLowerCase()}`">{{ detail.risk }}</span>
                <span class="tld-chip">{{ detail.status }}</span>
                <span class="tld-chip">核验 {{ detail.verificationStatus }}</span>
                <span class="tld-chip">{{ detail.intent || '意图未识别' }}</span>
              </div>
              <p class="tld-goal">{{ detail.goal || '无输入记录' }}</p>

              <SecurityBriefCard :brief="detail.brief" />

              <div class="tld-replay">
                <div class="tld-replay__bar">
                  <div class="tld-replay__title">
                    <strong>只读回放</strong>
                    <span class="tld-hint">按记录逐步重建时间线，不重新执行工具</span>
                  </div>
                  <div class="tld-replay__actions">
                    <button type="button" class="tld-btn" :disabled="replayIndex < 0" @click="step(-1)">上一步</button>
                    <button type="button" class="tld-btn" :disabled="!timeline.length" @click="togglePlay">
                      {{ playing ? '暂停' : '自动播放' }}
                    </button>
                    <button type="button" class="tld-btn" :disabled="replayIndex >= timeline.length - 1" @click="step(1)">下一步</button>
                  </div>
                </div>

                <ol v-if="timeline.length" class="tld-timeline">
                  <li
                    v-for="(item, index) in timeline"
                    :key="index"
                    :class="{
                      'is-active': index === replayIndex,
                      'is-done': index < replayIndex,
                      'is-bad': item.ok === false,
                    }"
                  >
                    <span class="tld-timeline__kind">{{ KIND_LABELS[item.kind] }}</span>
                    <span class="tld-timeline__label">{{ item.label }}</span>
                    <span class="tld-timeline__text">{{ item.text }}</span>
                  </li>
                </ol>
                <p v-else class="tld-muted">该 run 没有可回放的步骤（未运行/无数据）。</p>
              </div>

              <div class="tld-evidence">
                <h3>证据与审计</h3>
                <p><b>证据引用：</b>{{ evidenceText }}</p>
                <p><b>审计事件：</b>{{ auditText }}</p>
              </div>
            </template>
          </div>
        </div>
      </section>
    </transition>
  </Teleport>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  getAgentRun,
  listAgentRuns,
  verifyAuditChain,
} from '../../api/trustLedger.ts'
import SecurityBriefCard from './SecurityBriefCard.vue'

const props = defineProps({
  /** 抽屉开关（v-model）。 */
  modelValue: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const KIND_LABELS = { start: '输入', tool: '工具', approval: '审批', verify: '核验' }

const verifyLoading = ref(false)
const verifyResult = ref(null)
const verifyError = ref('')

const runs = ref([])
const listLoading = ref(false)
const listError = ref('')

const runIdInput = ref('')
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')

const replayIndex = ref(-1)
const playing = ref(false)
let playTimer = null

const timeline = computed(() => {
  const record = detail.value
  if (!record) return []
  const items = [
    {
      kind: 'start',
      label: '接收请求',
      text: record.goal || '无输入记录',
      ok: true,
    },
  ]
  for (const call of record.toolCalls || []) {
    const meta = [call.action, call.risk ? `风险 ${call.risk}` : '', call.attempts ? `尝试 ${call.attempts} 次` : '']
      .filter(Boolean)
      .join(' · ')
    items.push({
      kind: 'tool',
      label: call.toolName || '工具调用',
      text: meta || '无附加信息',
      ok: call.success !== false,
    })
  }
  for (const approval of record.approvals || []) {
    items.push({
      kind: 'approval',
      label: '审批',
      text: `${approval.toolName || '工具'} · ${approval.approvalId ? `关联审批单 ${approval.approvalId}` : '未关联审批单'}`,
      ok: Boolean(approval.approvalId),
    })
  }
  if (record.result) {
    items.push({
      kind: 'verify',
      label: '结果核验',
      text: `执行 ${record.status || '未知'} · 核验 ${record.verificationStatus || '未知'}`,
      ok: record.result.verified === true,
    })
  }
  return items
})

const evidenceText = computed(() => joinList(detail.value?.brief?.evidence_refs))
const auditText = computed(() => joinList(detail.value?.auditEventIds))

function joinList(value) {
  const list = Array.isArray(value) ? value.filter(Boolean) : []
  return list.length ? list.join('、') : '无数据'
}

function formatTime(value) {
  if (!value) return '时间未知'
  const text = String(value).replace('T', ' ')
  return text.length > 19 ? text.slice(0, 19) : text
}

function close() {
  stopPlay()
  emit('update:modelValue', false)
}

function unwrap(response) {
  return response && typeof response === 'object' && 'data' in response ? response.data : response
}

async function runVerify() {
  verifyLoading.value = true
  verifyError.value = ''
  try {
    verifyResult.value = await verifyAuditChain()
  } catch (err) {
    verifyResult.value = null
    verifyError.value = err?.message || '验链失败，请确认 ai-service 已启动。'
  } finally {
    verifyLoading.value = false
  }
}

async function loadRuns() {
  listLoading.value = true
  listError.value = ''
  try {
    const payload = unwrap(await listAgentRuns(30))
    runs.value = Array.isArray(payload) ? payload : []
  } catch (err) {
    runs.value = []
    listError.value = err?.message || '运行记录加载失败'
  } finally {
    listLoading.value = false
  }
}

async function loadRun(runId) {
  const target = String(runId || '').trim()
  if (!target) return
  stopPlay()
  runIdInput.value = target
  detailLoading.value = true
  detailError.value = ''
  try {
    const payload = unwrap(await getAgentRun(target))
    if (!payload || !payload.runId) throw new Error('未找到该 run 的账本记录')
    detail.value = payload
    replayIndex.value = -1
  } catch (err) {
    detail.value = null
    detailError.value = err?.message || '运行详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function step(delta) {
  const last = timeline.value.length - 1
  replayIndex.value = Math.max(-1, Math.min(last, replayIndex.value + delta))
  if (replayIndex.value >= last) stopPlay()
}

function togglePlay() {
  if (playing.value) {
    stopPlay()
    return
  }
  if (!timeline.value.length) return
  if (replayIndex.value >= timeline.value.length - 1) replayIndex.value = -1
  playing.value = true
  playTimer = setInterval(() => step(1), 900)
}

function stopPlay() {
  playing.value = false
  if (playTimer) {
    clearInterval(playTimer)
    playTimer = null
  }
}

watch(
  () => props.modelValue,
  open => {
    if (open) {
      loadRuns()
    } else {
      stopPlay()
    }
  },
)

onBeforeUnmount(stopPlay)
</script>

<style scoped>
.tld {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 1700;
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: min(720px, 96vw);
  padding: 16px;
  overflow: hidden;
  border-left: 1px solid var(--ds-hairline, rgba(255, 255, 255, .08));
  background: var(--ds-surface, #0d1117);
  color: var(--ds-color-text, #e8f2f7);
  box-shadow: var(--ds-shadow-lg, -8px 0 32px rgba(0, 0, 0, .4));
  font-size: var(--ds-font-sm, 13px);
}

.tld-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.tld-head__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tld-head__text small,
.tld-hint,
.tld-muted {
  color: var(--ds-color-muted, #92a6b5);
  font-size: var(--ds-font-xs, 12px);
}

.tld-close {
  border: none;
  background: transparent;
  color: var(--ds-color-muted, #92a6b5);
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.tld-verify,
.tld-query,
.tld-replay,
.tld-evidence {
  padding: 10px 12px;
  border: 1px solid var(--ds-hairline, rgba(255, 255, 255, .08));
  border-radius: var(--ds-radius-md, 8px);
  background: var(--ds-surface-raised, #151a21);
}

.tld-verify__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.tld-verify__result {
  margin: 8px 0 0;
  font-variant-numeric: tabular-nums;
  word-break: break-word;
}

.tld-verify__result.is-ok { color: var(--ds-semantic-success, #3fb950); }
.tld-verify__result.is-bad { color: var(--ds-semantic-danger, #f85149); }

.tld-query {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.tld-query__field {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 4px;
  font-size: var(--ds-font-xs, 12px);
  color: var(--ds-color-muted, #92a6b5);
}

.tld-query__field input {
  padding: 6px 8px;
  border: 1px solid var(--ds-hairline, rgba(255, 255, 255, .12));
  border-radius: var(--ds-radius-sm, 6px);
  background: var(--ds-surface, #0d1117);
  color: var(--ds-color-text, #e8f2f7);
  font-family: var(--ds-font-mono, ui-monospace, monospace);
}

.tld-btn {
  padding: 5px 10px;
  border: 1px solid var(--ds-hairline, rgba(255, 255, 255, .16));
  border-radius: var(--ds-radius-sm, 6px);
  background: transparent;
  color: var(--ds-color-text, #e8f2f7);
  cursor: pointer;
}

.tld-btn:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.tld-btn--primary {
  border-color: var(--ds-semantic-info, #58a6ff);
  color: var(--ds-semantic-info, #58a6ff);
}

.tld-error {
  margin: 6px 0 0;
  color: var(--ds-semantic-danger, #f85149);
}

.tld-body {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 12px;
  min-height: 0;
  flex: 1;
  overflow: hidden;
}

.tld-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
  overflow-y: auto;
  border-right: 1px solid var(--ds-hairline, rgba(255, 255, 255, .08));
  padding-right: 8px;
}

.tld-list h3,
.tld-evidence h3 {
  margin: 0;
  font-size: var(--ds-font-xs, 12px);
  color: var(--ds-color-muted, #92a6b5);
  font-weight: 600;
}

.tld-list ul {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.tld-run {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: var(--ds-radius-sm, 6px);
  background: transparent;
  color: var(--ds-color-text, #e8f2f7);
  text-align: left;
  cursor: pointer;
}

.tld-run.is-active {
  border-color: var(--ds-semantic-info, #58a6ff);
  background: rgba(88, 166, 255, .08);
}

.tld-run__id {
  font-family: var(--ds-font-mono, ui-monospace, monospace);
  font-size: var(--ds-font-xs, 12px);
  word-break: break-all;
}

.tld-run__meta {
  color: var(--ds-color-muted, #92a6b5);
  font-size: 11px;
}

.tld-detail {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.tld-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tld-chip {
  padding: 1px 8px;
  border: 1px solid var(--ds-hairline, rgba(255, 255, 255, .16));
  border-radius: var(--ds-radius-pill, 999px);
  font-size: var(--ds-font-xs, 12px);
}

.tld-chip.is-high,
.tld-chip.is-critical {
  border-color: var(--ds-semantic-danger, #f85149);
  color: var(--ds-semantic-danger, #f85149);
}

.tld-chip.is-medium {
  border-color: var(--ds-semantic-warning, #d29922);
  color: var(--ds-semantic-warning, #d29922);
}

.tld-goal {
  margin: 0;
  word-break: break-word;
}

.tld-replay__bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.tld-replay__title {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tld-replay__actions {
  display: flex;
  gap: 6px;
}

.tld-timeline {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.tld-timeline li {
  display: grid;
  grid-template-columns: 52px 150px minmax(0, 1fr);
  gap: 8px;
  align-items: baseline;
  padding: 6px 8px;
  border-left: 2px solid var(--ds-hairline, rgba(255, 255, 255, .12));
  opacity: .55;
  transition: opacity .2s ease, border-color .2s ease;
}

.tld-timeline li.is-done {
  opacity: .85;
}

.tld-timeline li.is-active {
  opacity: 1;
  border-left-color: var(--ds-semantic-info, #58a6ff);
  background: rgba(88, 166, 255, .08);
}

.tld-timeline li.is-bad {
  border-left-color: var(--ds-semantic-danger, #f85149);
}

.tld-timeline__kind {
  color: var(--ds-color-muted, #92a6b5);
  font-size: 11px;
}

.tld-timeline__label {
  font-weight: 600;
  word-break: break-all;
}

.tld-timeline__text {
  color: var(--ds-color-muted, #92a6b5);
  word-break: break-word;
}

.tld-evidence p {
  margin: 6px 0 0;
  color: var(--ds-color-muted, #92a6b5);
  word-break: break-word;
}

.tld-fade-enter-active,
.tld-fade-leave-active {
  transition: opacity .18s ease, transform .18s ease;
}

.tld-fade-enter-from,
.tld-fade-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
</style>
