<template>
  <section class="orchestration" aria-label="多子智能体协同">
    <div class="orchestration__bar">
      <label class="orchestration__goal">
        <span>目标</span>
        <input
          v-model="goal"
          :disabled="running"
          placeholder="例如：巡检 A 区并诊断 robot-car-01，再做合规审计"
          @keyup.enter="start"
        >
      </label>
      <label class="orchestration__conc">
        <span>并发</span>
        <select v-model.number="concurrency" :disabled="running">
          <option v-for="n in [1, 2, 3, 4]" :key="n" :value="n">{{ n }}</option>
        </select>
      </label>
      <button type="button" class="orchestration__run" :disabled="!canRun" @click="start">
        {{ running ? '协同中…' : '开始协同' }}
      </button>
    </div>

    <div class="orchestration__meta">
      <span v-if="traceId" class="orchestration__trace">trace {{ traceId }}</span>
      <span v-if="running" class="orchestration__elapsed">{{ (elapsedMs / 1000).toFixed(1) }}s</span>
      <span class="orchestration__count">{{ doneCount }}/{{ total }}</span>
      <span v-if="overall" class="orchestration__status" :data-status="overall">{{ overallText }}</span>
    </div>

    <div
      class="orchestration__progress"
      role="progressbar"
      :aria-valuenow="progress"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-label="`协同进度 ${progress}%`"
    >
      <span class="orchestration__progress-fill" :style="{ '--progress': `${progress}%` }" />
    </div>

    <p v-if="errorText" class="orchestration__error" role="alert">{{ errorText }}</p>
    <p v-if="noticeText" class="orchestration__notice">{{ noticeText }}</p>

    <ol v-if="cards.length" class="orchestration__flow">
      <template v-for="(card, index) in cards" :key="card.key">
        <li
          class="agent-card"
          :data-state="card.state"
          :style="{ '--card-delay': `${index * 0.14}s` }"
        >
          <span class="agent-card__sweep" aria-hidden="true" />
          <span class="agent-card__ring" aria-hidden="true" />
          <span class="agent-card__pulse" aria-hidden="true" />
          <span class="agent-card__icon" aria-hidden="true">{{ card.icon }}</span>
          <span class="agent-card__name">{{ card.label }}</span>
          <span class="agent-card__state">{{ stateText(card) }}</span>
          <span v-if="durationOf(card)" class="agent-card__time">
            {{ durationOf(card) }}ms<template v-if="card.attempts > 1"> · 重试 {{ card.attempts - 1 }}</template>
          </span>
          <span v-if="card.summary" class="agent-card__summary" :title="card.summary">{{ card.summary }}</span>
        </li>
        <li
          v-if="index < cards.length - 1"
          class="agent-card__link"
          :style="{ '--spark-delay': `${index * 0.3}s` }"
          aria-hidden="true"
        >
          <i class="agent-card__spark" />
        </li>
      </template>
    </ol>

    <p v-if="conflicts.length" class="orchestration__conflict">
      冲突提示：{{ conflicts.join('；') }}
    </p>
    <p v-if="finalSynthesis" class="orchestration__synthesis">{{ finalSynthesis }}</p>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { streamOrchestration } from '../../api/orchestrate'

const props = defineProps({
  deviceKey: { type: String, default: '' },
  deviceKeys: { type: Array, default: () => [] }
})

/** task_id 前缀 → 展示名与图标；未知专长按通用处理。 */
const SPECIALTIES = {
  patrol_planner: { label: '巡检调度官', icon: '巡' },
  device_diagnostician: { label: '设备诊断师', icon: '诊' },
  compliance_auditor: { label: '安全合规审计员', icon: '审' },
  anomaly_sleuth: { label: '异常发现', icon: '异' },
  rootcause_hunter: { label: '根因分析', icon: '因' },
  log_interpreter: { label: '日志解读', icon: '志' },
  case_retriever: { label: '案例检索', icon: '案' },
  action_advisor: { label: '处置建议', icon: '处' }
}

const STATE_TEXT = {
  pending: '等待',
  running: '执行中',
  success: '完成',
  failed: '失败',
  skipped: '跳过'
}

const OVERALL_TEXT = {
  completed: '协同完成',
  partial: '部分完成',
  failed: '协同失败'
}

const goal = ref('巡检当前区域并诊断设备，最后做合规审计')
const concurrency = ref(3)
const running = ref(false)
const errorText = ref('')
const noticeText = ref('')
const traceId = ref('')
const overall = ref('')
const cards = ref([])
const conflicts = ref([])
const finalSynthesis = ref('')
const elapsedMs = ref(0)

let controller = null
let timer = 0
let startedAt = 0

/* 耗时数字滚动：卡片完成时从 0 计数到真实毫秒数 */
const displayDurations = ref({})
const durationFrames = new Map()

function durationOf(card) {
  return displayDurations.value[card.key] ?? card.durationMs
}

function animateDuration(key, target) {
  const value = Number(target) || 0
  if (durationFrames.has(key)) {
    cancelAnimationFrame(durationFrames.get(key))
    durationFrames.delete(key)
  }
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (reduced || !value) {
    displayDurations.value = { ...displayDurations.value, [key]: value }
    return
  }
  const started = performance.now()
  const step = (now) => {
    const progressRate = Math.min((now - started) / 280, 1)
    const eased = 1 - (1 - progressRate) ** 3
    displayDurations.value = { ...displayDurations.value, [key]: Math.round(value * eased) }
    if (progressRate < 1) durationFrames.set(key, requestAnimationFrame(step))
    else durationFrames.delete(key)
  }
  durationFrames.set(key, requestAnimationFrame(step))
}

function stopDurationAnimations() {
  durationFrames.forEach(frame => cancelAnimationFrame(frame))
  durationFrames.clear()
}

const total = computed(() => cards.value.length)
const doneCount = computed(() => cards.value.filter(card => ['success', 'failed', 'skipped'].includes(card.state)).length)
const progress = computed(() => (total.value ? Math.round((doneCount.value / total.value) * 100) : 0))
const overallText = computed(() => OVERALL_TEXT[overall.value] || overall.value)
const canRun = computed(() => Boolean(goal.value.trim()) && !running.value)

function stateText(card) {
  return STATE_TEXT[card.state] || card.state
}

function specialtyMeta(taskId) {
  const key = String(taskId).replace(/^t_/, '')
  return { key, ...(SPECIALTIES[key] || { label: key, icon: '协' }) }
}

function buildContext() {
  const context = {}
  if (props.deviceKey) context.device_key = props.deviceKey
  const keys = (props.deviceKeys || []).filter(Boolean)
  if (keys.length) context.device_keys = keys.slice(0, 10)
  return context
}

function reset() {
  stopDurationAnimations()
  displayDurations.value = {}
  errorText.value = ''
  noticeText.value = ''
  traceId.value = ''
  overall.value = ''
  cards.value = []
  conflicts.value = []
  finalSynthesis.value = ''
  elapsedMs.value = 0
}

function ensureCard(taskId, index) {
  let card = cards.value.find(item => item.key === taskId)
  if (!card) {
    const meta = specialtyMeta(taskId)
    card = {
      key: taskId,
      label: meta.label,
      icon: meta.icon,
      state: 'pending',
      durationMs: 0,
      attempts: 1,
      summary: ''
    }
    cards.value.splice(index ?? cards.value.length, 0, card)
  }
  return card
}

function applyEvent(event) {
  const payload = event.payload || {}
  switch (event.event) {
    case 'orchestration.started': {
      traceId.value = payload.trace_id || event.trace_id || ''
      const ids = Array.isArray(payload.task_ids) ? payload.task_ids : []
      cards.value = ids.map((taskId) => {
        const meta = specialtyMeta(taskId)
        return {
          key: taskId,
          label: meta.label,
          icon: meta.icon,
          state: 'pending',
          durationMs: 0,
          attempts: 1,
          summary: ''
        }
      })
      break
    }
    case 'orchestration.subtask_started': {
      const card = ensureCard(payload.task_id)
      card.state = 'running'
      break
    }
    case 'orchestration.subtask_finished': {
      const card = ensureCard(payload.task_id)
      card.state = payload.skipped ? 'skipped' : (payload.success ? 'success' : 'failed')
      card.durationMs = Number(payload.duration_ms) || 0
      card.attempts = Number(payload.attempts) || 1
      animateDuration(payload.task_id, card.durationMs)
      break
    }
    case 'orchestration.finished':
      overall.value = payload.status || ''
      break
    case 'result': {
      overall.value = payload.overall_status || overall.value
      traceId.value = payload.trace_id || traceId.value
      conflicts.value = Array.isArray(payload.conflict_notes) ? payload.conflict_notes : []
      finalSynthesis.value = payload.final_synthesis || ''
      for (const result of payload.results || []) {
        const card = ensureCard(result.task_id)
        card.summary = result.summary || ''
        if (Number.isFinite(result.duration_ms)) card.durationMs = result.duration_ms
        if (Number.isFinite(result.attempts)) card.attempts = result.attempts
        if (displayDurations.value[result.task_id] == null && card.durationMs) {
          animateDuration(result.task_id, card.durationMs)
        }
      }
      break
    }
    case 'error':
      errorText.value = payload.message || '编排执行失败'
      break
    default:
      break
  }
}

async function start() {
  if (!canRun.value) return
  reset()
  running.value = true
  startedAt = Date.now()
  timer = window.setInterval(() => {
    elapsedMs.value = Date.now() - startedAt
  }, 100)
  controller = new AbortController()

  try {
    await streamOrchestration(
      {
        goal: goal.value.trim(),
        context: buildContext(),
        maxConcurrency: concurrency.value,
        signal: controller.signal
      },
      applyEvent
    )
    if (!errorText.value && !cards.value.length) {
      noticeText.value = '该目标未命中任何专长，试试包含「巡检 / 诊断 / 合规」等关键词'
    }
  } catch (error) {
    if (error?.name !== 'AbortError') {
      errorText.value = error?.message || '编排请求失败'
    }
  } finally {
    window.clearInterval(timer)
    timer = 0
    running.value = false
    controller = null
  }
}

onBeforeUnmount(() => {
  window.clearInterval(timer)
  stopDurationAnimations()
  if (controller) controller.abort()
})
</script>

<style scoped>
.orchestration {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 24%, transparent);
  border-radius: 12px;
  background:
    radial-gradient(120% 140% at 0% 0%, color-mix(in srgb, var(--smart-primary-strong) 10%, transparent), transparent 60%),
    var(--smart-panel, transparent);
}

/* 背景：漂浮粒子 + 弱网格，让面板在静止时也有轻微呼吸感 */
.orchestration::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 0;
  border-radius: inherit;
  pointer-events: none;
  opacity: 0.5;
  background-image:
    radial-gradient(circle, color-mix(in srgb, var(--smart-primary-strong) 45%, transparent) 0 1px, transparent 1.5px),
    radial-gradient(circle, color-mix(in srgb, var(--smart-primary-strong) 30%, transparent) 0 1px, transparent 1.5px),
    linear-gradient(color-mix(in srgb, var(--smart-primary-strong) 10%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--smart-primary-strong) 10%, transparent) 1px, transparent 1px);
  background-size: 54px 54px, 83px 83px, 27px 27px, 27px 27px;
  animation: orchestration-drift 22s linear infinite;
}

.orchestration > * {
  position: relative;
  z-index: 1;
}

.orchestration__bar {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.orchestration__goal {
  flex: 1 1 320px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--smart-muted);
}

.orchestration__goal input,
.orchestration__conc select {
  height: 30px;
  padding: 0 9px;
  border-radius: 7px;
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 22%, transparent);
  background: color-mix(in srgb, var(--smart-primary-strong) 6%, transparent);
  color: var(--smart-text, inherit);
  font-size: 12px;
}

.orchestration__goal input:focus-visible,
.orchestration__conc select:focus-visible,
.orchestration__run:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--smart-primary-strong) 60%, transparent);
  outline-offset: 1px;
}

.orchestration__conc {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--smart-muted);
}

.orchestration__run {
  height: 30px;
  padding: 0 14px;
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 45%, transparent);
  border-radius: 7px;
  background: color-mix(in srgb, var(--smart-primary-strong) 16%, transparent);
  color: var(--smart-primary-strong);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease;
}

.orchestration__run:hover:not(:disabled) {
  background: color-mix(in srgb, var(--smart-primary-strong) 26%, transparent);
  transform: translateY(-1px);
}

.orchestration__run:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.orchestration__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 10px;
  color: var(--smart-muted);
}

.orchestration__trace { font-family: var(--font-mono); opacity: 0.8; }
.orchestration__elapsed,
.orchestration__count { font-family: var(--font-mono); color: var(--smart-primary-strong); }

.orchestration__status {
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid currentColor;
  font-weight: 600;
}

.orchestration__status[data-status='completed'] { color: var(--smart-success, #2f9e6f); }
.orchestration__status[data-status='partial'] { color: var(--smart-warning, #c98a12); }
.orchestration__status[data-status='failed'] { color: var(--smart-danger, #d94a4a); }

.orchestration__progress {
  position: relative;
  height: 5px;
  border-radius: 3px;
  overflow: hidden;
  background: color-mix(in srgb, var(--smart-primary-strong) 14%, transparent);
}

.orchestration__progress-fill {
  display: block;
  height: 100%;
  width: var(--progress, 0%);
  border-radius: 3px;
  background-image: linear-gradient(90deg,
    color-mix(in srgb, var(--smart-primary-strong) 65%, transparent),
    var(--smart-primary-strong));
  background-size: 200% 100%;
  transition: width 0.45s cubic-bezier(0.22, 1, 0.36, 1);
  animation: orchestration-shine 2.4s linear infinite;
}

/* 进度条刻度：每个子任务一格，完成度更易读 */
.orchestration__progress::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image: repeating-linear-gradient(
    90deg,
    transparent 0 9px,
    rgba(4, 10, 20, 0.38) 9px 10px
  );
  mix-blend-mode: multiply;
}

.orchestration__error {
  margin: 0;
  font-size: 11px;
  color: var(--smart-danger, #d94a4a);
}

.orchestration__notice { margin: 0; font-size: 11px; color: var(--smart-muted); }

.orchestration__flow {
  display: flex;
  align-items: stretch;
  gap: 0;
  margin: 4px 0 0;
  padding: 2px 0 6px;
  list-style: none;
  overflow-x: auto;
  scrollbar-width: thin;
}

.agent-card {
  position: relative;
  flex: 1 0 132px;
  max-width: 210px;
  min-height: 92px;
  padding: 8px 9px;
  border-radius: 9px;
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 22%, transparent);
  background: color-mix(in srgb, var(--smart-primary-strong) 7%, transparent);
  overflow: hidden;
  animation: card-rise 0.45s ease-out backwards;
  animation-delay: var(--card-delay, 0s);
  transition: border-color 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease;
}

/* 悬停：上浮 + 聚光，便于逐卡查看 */
.agent-card::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.3s ease;
  background: radial-gradient(120% 95% at 50% -15%,
    color-mix(in srgb, var(--smart-primary-strong) 26%, transparent),
    transparent 68%);
}

.agent-card:hover {
  transform: translateY(-3px);
  border-color: color-mix(in srgb, var(--smart-primary-strong) 55%, transparent);
  box-shadow: 0 8px 18px color-mix(in srgb, var(--smart-primary-strong) 18%, transparent);
}

.agent-card:hover::after { opacity: 1; }

/* 运行中描边：流动虚线圈（mask 只保留边框，不影响内容） */
.agent-card__ring {
  position: absolute;
  inset: 0;
  padding: 1px;
  border-radius: inherit;
  pointer-events: none;
  opacity: 0;
  background-image: repeating-linear-gradient(
    115deg,
    color-mix(in srgb, var(--smart-primary-strong) 85%, transparent) 0 5px,
    transparent 5px 11px
  );
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
}

.agent-card[data-state='running'] .agent-card__ring {
  opacity: 1;
  animation: card-ring-flow 1.1s linear infinite;
}

/* 完成瞬间：一次性能量环扩散 */
.agent-card__pulse {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  border: 1px solid var(--smart-success, #2f9e6f);
  opacity: 0;
}

.agent-card[data-state='success'] .agent-card__pulse {
  animation: card-burst 0.75s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.agent-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin-bottom: 5px;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 35%, transparent);
  background: color-mix(in srgb, var(--smart-primary-strong) 14%, transparent);
  color: var(--smart-primary-strong);
  font-size: 11px;
  font-weight: 700;
}

.agent-card__name {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--smart-text, inherit);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-card__state {
  display: inline-block;
  margin-top: 3px;
  font-size: 10px;
  letter-spacing: 0.04em;
  color: var(--smart-muted);
}

.agent-card__time {
  display: block;
  margin-top: 2px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--smart-muted);
}

.agent-card__summary {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-top: 4px;
  font-size: 10px;
  line-height: 1.45;
  color: var(--smart-muted);
}

/* 运行中：呼吸描边 + 内部扫光 */
.agent-card[data-state='running'] {
  border-color: color-mix(in srgb, var(--smart-primary-strong) 65%, transparent);
  animation: card-rise 0.45s ease-out backwards, card-pulse 1.6s ease-in-out infinite;
  animation-delay: var(--card-delay, 0s), 0s;
}

.agent-card[data-state='running'] .agent-card__state { color: var(--smart-primary-strong); }
.agent-card[data-state='success'] .agent-card__state { color: var(--smart-success, #2f9e6f); }
.agent-card[data-state='failed'] .agent-card__state { color: var(--smart-danger, #d94a4a); }
.agent-card[data-state='skipped'] { opacity: 0.6; }

.agent-card[data-state='running'] .agent-card__sweep,
.agent-card[data-state='success'] .agent-card__sweep {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(100deg, transparent 20%, color-mix(in srgb, var(--smart-primary-strong) 18%, transparent) 50%, transparent 80%);
  transform: translateX(-100%);
  animation: card-sweep 2.2s ease-in-out infinite;
}

.agent-card[data-state='success'] .agent-card__sweep { animation-iteration-count: 1; }

/* 连接线：流光 + 穿梭光点 */
.agent-card__link {
  position: relative;
  flex: 0 0 20px;
  align-self: center;
  height: 2px;
  margin: 0 2px;
  border-radius: 1px;
  background-image: linear-gradient(90deg,
    color-mix(in srgb, var(--smart-primary-strong) 15%, transparent) 0%,
    var(--smart-primary-strong) 50%,
    color-mix(in srgb, var(--smart-primary-strong) 15%, transparent) 100%);
  background-size: 220% 100%;
  animation: card-link-flow 1.7s linear infinite;
}

.agent-card__spark {
  position: absolute;
  top: 50%;
  left: 0;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--smart-primary-strong);
  box-shadow: 0 0 6px color-mix(in srgb, var(--smart-primary-strong) 75%, transparent);
  transform: translate(0, -50%);
  opacity: 0;
  animation: card-spark 1.9s linear infinite;
  animation-delay: var(--spark-delay, 0s);
}

.orchestration__conflict {
  margin: 0;
  font-size: 11px;
  color: var(--smart-warning, #c98a12);
}

.orchestration__synthesis {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px dashed color-mix(in srgb, var(--smart-primary-strong) 30%, transparent);
  font-size: 11px;
  line-height: 1.6;
  color: var(--smart-text, inherit);
  white-space: pre-wrap;
}

@keyframes card-rise {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes card-pulse {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--smart-primary-strong) 30%, transparent); }
  50% { box-shadow: 0 0 0 3px color-mix(in srgb, var(--smart-primary-strong) 12%, transparent); }
}

@keyframes card-sweep {
  from { transform: translateX(-100%); }
  to { transform: translateX(100%); }
}

@keyframes card-link-flow {
  from { background-position: 180% 0; }
  to { background-position: -80% 0; }
}

@keyframes card-spark {
  0% { opacity: 0; transform: translate(0, -50%); }
  18% { opacity: 1; }
  82% { opacity: 1; }
  100% { opacity: 0; transform: translate(17px, -50%); }
}

@keyframes orchestration-shine {
  from { background-position: 200% 0; }
  to { background-position: -100% 0; }
}

@keyframes orchestration-drift {
  from { background-position: 0 0, 0 0, 0 0, 0 0; }
  to { background-position: 54px 54px, -83px 41px, 27px 27px, 27px 27px; }
}

@keyframes card-ring-flow {
  from { background-position: 0 0; }
  to { background-position: 22px 0; }
}

@keyframes card-burst {
  0% { opacity: 0.9; transform: scale(0.9); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--smart-success, #2f9e6f) 70%, transparent); }
  60% { opacity: 0.55; transform: scale(0.99); box-shadow: inset 0 0 14px color-mix(in srgb, var(--smart-success, #2f9e6f) 26%, transparent); }
  100% { opacity: 0; transform: scale(1); box-shadow: inset 0 0 0 0 transparent; }
}

@media (prefers-reduced-motion: reduce) {
  .agent-card,
  .agent-card[data-state='running'],
  .agent-card__sweep,
  .agent-card__ring,
  .agent-card__pulse,
  .agent-card__link,
  .agent-card__spark,
  .orchestration::before,
  .orchestration__progress-fill { animation: none; }
  .orchestration__progress-fill { transition: none; }
  .orchestration__run:hover:not(:disabled) { transform: none; }
  .agent-card:hover { transform: none; }
  .agent-card__ring { opacity: 0; }
  .agent-card__pulse { opacity: 0; }
}
</style>
