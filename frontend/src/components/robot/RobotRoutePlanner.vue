<template>
  <section class="planner" aria-labelledby="planner-title">
    <header class="planner-head">
      <div>
        <p class="planner-eyebrow">ROUTE PLANNER · 点选式编排</p>
        <h3 id="planner-title">巡检路线规划</h3>
      </div>
      <button
        type="button"
        class="mode-btn"
        :class="{ active: editable }"
        @click="emit('update:editable', !editable)"
      >{{ editable ? '退出规划' : '进入规划' }}</button>
    </header>

    <p class="planner-hint">
      {{ editable ? '在地图上依次点击生成路点；点击编号可删除，列表可调整顺序与动作。' : '开启规划后，点击左侧孪生地图即可落点。' }}
    </p>

    <div class="planner-tools">
      <button type="button" class="tool-btn" :disabled="!editable" @click="applyRingTemplate">环形模板</button>
      <button type="button" class="tool-btn" :disabled="!points.length" @click="clearPoints">清空</button>
      <button type="button" class="tool-btn" :disabled="!points.length" @click="saveTemplate">保存模板</button>
      <select v-model="selectedTemplate" class="tool-select" :disabled="!templates.length" @change="loadTemplate">
        <option value="">载入模板…</option>
        <option v-for="item in templates" :key="item.name" :value="item.name">{{ item.name }}</option>
      </select>
      <button v-if="selectedTemplate" type="button" class="tool-btn danger" @click="removeTemplate">删除模板</button>
    </div>

    <div v-if="!points.length" class="planner-empty">
      还没有路点。{{ editable ? '点击地图开始规划。' : '进入规划模式后点击地图落点。' }}
    </div>

    <ol v-else class="waypoint-list">
      <li v-for="(point, index) in points" :key="index" class="waypoint">
        <div class="waypoint-order">{{ index + 1 }}</div>
        <div class="waypoint-main">
          <div class="waypoint-row">
            <input v-model="point.label" class="label-input" type="text" maxlength="16" :aria-label="`第 ${index + 1} 个路点名称`" />
            <span class="coord">{{ Number(point.targetX).toFixed(1) }}, {{ Number(point.targetY).toFixed(1) }} m</span>
          </div>
          <div class="waypoint-row actions">
            <label class="action-chip" :class="{ active: point.actions.includes('CAPTURE') }">
              <input v-model="point.actions" type="checkbox" value="CAPTURE" />拍照识别
            </label>
            <label class="action-chip" :class="{ active: point.actions.includes('SPEAK') }">
              <input v-model="point.actions" type="checkbox" value="SPEAK" />语音喊话
            </label>
            <input
              v-if="point.actions.includes('SPEAK')"
              v-model="point.speech"
              class="speech-input"
              type="text"
              maxlength="40"
              placeholder="播报内容"
            />
          </div>
        </div>
        <div class="waypoint-ops">
          <button type="button" class="icon-btn" :disabled="index === 0" title="上移" @click="move(index, -1)">↑</button>
          <button type="button" class="icon-btn" :disabled="index === points.length - 1" title="下移" @click="move(index, 1)">↓</button>
          <button type="button" class="icon-btn danger" title="删除" @click="removePoint(index)">×</button>
        </div>
      </li>
    </ol>

    <div class="planner-submit">
      <div class="submit-meta">
        <span>{{ points.length }} 个路点</span>
        <span>·</span>
        <span>预计里程 {{ estimatedDistance }} m</span>
      </div>
      <button type="button" class="submit-btn" :disabled="!canSubmit || submitting" @click="submit">
        {{ submitting ? '下发中…' : '下发巡检任务' }}
      </button>
    </div>
    <p v-if="!canSubmit" class="submit-block">{{ submitBlockReason }}</p>
    <p v-if="feedback" class="submit-feedback" :class="feedbackType">{{ feedback }}</p>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { submitRobotTask } from '../../api/robot'

const props = defineProps({
  deviceKey: { type: String, default: '' },
  mode: { type: String, default: 'OFFLINE' },
  bridgeConnected: { type: Boolean, default: false },
  points: { type: Array, default: () => [] },
  editable: { type: Boolean, default: false }
})

const emit = defineEmits(['update:points', 'update:editable', 'submitted'])

const TEMPLATE_KEY = 'smartops_robot_route_templates'
const submitting = ref(false)
const feedback = ref('')
const feedbackType = ref('ok')
const selectedTemplate = ref('')
const templates = ref(loadTemplates())

function loadTemplates() {
  try {
    const raw = window.localStorage.getItem(TEMPLATE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function persistTemplates() {
  try {
    window.localStorage.setItem(TEMPLATE_KEY, JSON.stringify(templates.value))
  } catch {
    /* 存储不可用时仅本次生效 */
  }
}

function normalizePoint(x, y, index) {
  return {
    label: `路点 ${index + 1}`,
    x: 0,
    y: 0,
    theta: 0,
    targetX: Number(x),
    targetY: Number(y),
    actions: ['CAPTURE'],
    speech: ''
  }
}

function applyRingTemplate() {
  const radius = 5
  const generated = Array.from({ length: 8 }, (_, index) => {
    const angle = (Math.PI * 2 * index) / 8
    return normalizePoint(
      Math.round(Math.cos(angle) * radius * 10) / 10,
      Math.round(Math.sin(angle) * radius * 10) / 10,
      index
    )
  })
  emit('update:points', generated)
  feedback.value = '已生成 8 个环形路点，可继续在地图上微调'
  feedbackType.value = 'ok'
}

function clearPoints() {
  emit('update:points', [])
  feedback.value = ''
}

function move(index, delta) {
  const next = [...props.points]
  const target = index + delta
  if (target < 0 || target >= next.length) return
  const [item] = next.splice(index, 1)
  next.splice(target, 0, item)
  emit('update:points', next)
}

function removePoint(index) {
  const next = props.points.filter((_, itemIndex) => itemIndex !== index)
  emit('update:points', next)
}

function saveTemplate() {
  const name = window.prompt('模板名称（例如：教学楼夜巡）', `路线 ${templates.value.length + 1}`)
  if (!name) return
  const snapshot = props.points.map(point => ({ ...point }))
  const existing = templates.value.find(item => item.name === name)
  if (existing) {
    existing.points = snapshot
  } else {
    templates.value = [...templates.value, { name, points: snapshot }]
  }
  persistTemplates()
  selectedTemplate.value = name
  feedback.value = `模板「${name}」已保存到本机`
  feedbackType.value = 'ok'
}

function loadTemplate() {
  const item = templates.value.find(template => template.name === selectedTemplate.value)
  if (!item) return
  emit('update:points', item.points.map(point => ({
    ...normalizePoint(point.targetX, point.targetY, 0),
    ...point,
    actions: Array.isArray(point.actions) && point.actions.length ? [...point.actions] : ['CAPTURE']
  })))
  feedback.value = `已载入模板「${item.name}」`
  feedbackType.value = 'ok'
}

function removeTemplate() {
  if (!selectedTemplate.value) return
  templates.value = templates.value.filter(item => item.name !== selectedTemplate.value)
  persistTemplates()
  selectedTemplate.value = ''
  feedback.value = '模板已删除'
  feedbackType.value = 'ok'
}

const estimatedDistance = computed(() => {
  let total = 0
  let previous = null
  props.points.forEach((point) => {
    const current = { x: Number(point.targetX), y: Number(point.targetY) }
    if (previous) total += Math.hypot(current.x - previous.x, current.y - previous.y)
    previous = current
  })
  return total.toFixed(1)
})

const canSubmit = computed(() => Boolean(
  props.deviceKey && props.points.length && props.points.length <= 50 && props.bridgeConnected && props.mode === 'IDLE'
))

const submitBlockReason = computed(() => {
  if (!props.deviceKey) return '请先选择设备'
  if (!props.points.length) return '至少需要一个路点'
  if (props.points.length > 50) return '单个任务最多 50 个路点'
  if (!props.bridgeConnected) return '控制桥未连接，任务无法下发'
  if (props.mode !== 'IDLE') return `设备当前为 ${props.mode}，仅空闲态可受理新任务`
  return ''
})

async function submit() {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  feedback.value = ''
  try {
    const route = props.points.map((point, index) => ({
      x: 0,
      y: 0,
      theta: 0,
      targetX: Number(point.targetX),
      targetY: Number(point.targetY),
      label: point.label || `路点 ${index + 1}`,
      actions: point.actions.length ? [...point.actions] : ['CAPTURE'],
      speech: point.speech || ''
    }))
    await submitRobotTask(props.deviceKey, route, null)
    feedback.value = '任务已受理，可在下方任务面板跟踪执行进度'
    feedbackType.value = 'ok'
    emit('submitted')
  } catch (error) {
    feedback.value = error?.message || '任务下发失败'
    feedbackType.value = 'error'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.planner {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-3);
  padding: var(--ds-card-padding, var(--ds-space-4));
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-color-surface);
  min-width: 0;
}

.planner-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ds-space-2);
}

.planner-eyebrow {
  margin: 0 0 2px;
  color: var(--ds-color-muted);
  font-size: 10px;
  letter-spacing: 0.12em;
}

.planner-head h3 {
  margin: 0;
  font-size: var(--ds-font-md);
}

.mode-btn {
  padding: 5px 12px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-pill);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  cursor: pointer;
}

.mode-btn.active {
  border-color: var(--ds-color-primary);
  background: rgba(36, 150, 237, 0.16);
  color: var(--ds-color-text);
}

.planner-hint {
  margin: 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  line-height: 1.6;
}

.planner-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tool-btn,
.tool-select {
  padding: 4px 10px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-sm);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  cursor: pointer;
}

.tool-btn:hover:not(:disabled),
.tool-select:hover:not(:disabled) {
  border-color: var(--ds-color-primary);
  color: var(--ds-color-text);
}

.tool-btn:disabled,
.tool-select:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.tool-btn.danger {
  border-color: rgba(224, 100, 110, 0.4);
  color: #ff9aa4;
}

.planner-empty {
  padding: var(--ds-space-4);
  border: 1px dashed var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  color: var(--ds-color-muted);
  font-size: var(--ds-font-sm);
  text-align: center;
}

.waypoint-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 320px;
  overflow-y: auto;
}

.waypoint {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
}

.waypoint-order {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(36, 150, 237, 0.16);
  color: var(--ds-color-primary);
  font-family: var(--ds-font-mono);
  font-size: 10px;
  flex-shrink: 0;
}

.waypoint-main {
  display: flex;
  flex-direction: column;
  gap: 5px;
  flex: 1;
  min-width: 0;
}

.waypoint-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.label-input,
.speech-input {
  min-width: 0;
  padding: 3px 6px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-sm);
  background: var(--ds-color-surface);
  color: var(--ds-color-text);
  font-size: var(--ds-font-xs);
}

.label-input {
  width: 110px;
}

.speech-input {
  flex: 1;
}

.coord {
  color: var(--ds-color-muted);
  font-family: var(--ds-font-mono);
  font-size: 10px;
}

.action-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-pill);
  color: var(--ds-color-muted);
  font-size: 10px;
  cursor: pointer;
}

.action-chip.active {
  border-color: rgba(67, 209, 160, 0.5);
  background: rgba(67, 209, 160, 0.12);
  color: #7fe7c1;
}

.action-chip input {
  display: none;
}

.waypoint-ops {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.icon-btn {
  width: 22px;
  height: 20px;
  border: 1px solid var(--ds-color-border);
  border-radius: 4px;
  background: transparent;
  color: var(--ds-color-muted);
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
}

.icon-btn:hover:not(:disabled) {
  border-color: var(--ds-color-primary);
  color: var(--ds-color-text);
}

.icon-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.icon-btn.danger:hover {
  border-color: rgba(224, 100, 110, 0.5);
  color: #ff9aa4;
}

.planner-submit {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-3);
  padding-top: var(--ds-space-2);
  border-top: 1px solid var(--ds-color-border);
}

.submit-meta {
  display: flex;
  gap: 6px;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  font-variant-numeric: tabular-nums;
}

.submit-btn {
  padding: 7px 16px;
  border: 1px solid transparent;
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-primary);
  color: #04121e;
  font-size: var(--ds-font-xs);
  font-weight: 600;
  cursor: pointer;
}

.submit-btn:disabled {
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-muted);
  cursor: not-allowed;
}

.submit-block {
  margin: 0;
  color: var(--ds-color-warning);
  font-size: var(--ds-font-xs);
}

.submit-feedback {
  margin: 0;
  font-size: var(--ds-font-xs);
}

.submit-feedback.ok { color: #6ddcab; }
.submit-feedback.error { color: #ff9aa4; }
</style>
