<template>
  <div ref="dashboardShellRef" class="sentinel-shell" :data-theme="resolvedTheme">
    <CanvasAmbientField v-if="!isMobile" class="sentinel-ambient" :palette-root="dashboardShellRef" :star-multiplier="1.8" connect-particles :connect-max-dist="130" />
    <div v-if="!isMobile" class="sentinel-aurora" aria-hidden="true"></div>
    <MeteorShower v-if="!isMobile" class="sentinel-meteors" />
    <div class="sentinel-mask" aria-hidden="true"></div>

  <section class="sentinel-surface" aria-labelledby="sentinel-title">
    <header class="sentinel-page-header">
      <div>
        <h1 id="sentinel-title">哨兵监控台</h1>
      </div>
      <button type="button" :disabled="state.loading" @click="reload">刷新</button>
    </header>
    <p class="sentinel-lede">
      常驻哨兵持续采集系统与业务指标、监听日志关键字，命中阈值且持续时间达标后产生告警并送入告警中心。
      区别于定时巡检：哨兵是常驻监听，不是一次性任务。
    </p>

    <section class="sentinel-crawler-stage crawler-stage" aria-labelledby="sentinel-crawler-title">
      <div class="sentinel-crawler-copy">
        <p class="sentinel-eyebrow">CRAWLER / 拓扑巡网</p>
        <h2 id="sentinel-crawler-title">哨兵在网 · 节点在巡</h2>
        <p class="sentinel-crawler-desc">
          每个网节点对应一个真实哨兵任务：青=在线采集、红=离线、橙=采集异常、灰=缺运行连接；
          蜘蛛巡向最近一次采样的节点并高亮，反映真实采集活动。
        </p>
        <ul v-if="state.status === 'ready'" class="sentinel-crawler-legend">
          <li><i class="dot dot--online"></i>在线</li>
          <li><i class="dot dot--offline"></i>离线</li>
          <li><i class="dot dot--error"></i>异常</li>
          <li><i class="dot dot--none"></i>缺连接</li>
        </ul>
        <p v-else-if="state.status === 'unavailable'" class="sentinel-crawler-note">
          后端暂未接入，下方为示意网；接入后将显示真实任务节点。
        </p>
        <p v-else-if="state.status === 'unauthorized'" class="sentinel-crawler-note">
          请先登录后再查看哨兵监控数据。
        </p>
        <p v-else class="sentinel-crawler-note">哨兵数据加载中…</p>
      </div>
      <div class="sentinel-crawler-canvas">
        <SpiderCrawler
          :nodes="crawlerNodes"
          :status="state.status"
          :active-id="hoveredTaskId"
          :seed="42"
          :speed="1"
        />
      </div>
    </section>

    <SentinelNotice
      v-if="state.status === 'unavailable' || state.status === 'unauthorized'"
      :tone="state.status === 'unauthorized' ? 'info' : 'warn'"
      :title="state.status === 'unauthorized' ? '请先登录' : '后端未接入'"
      :detail="state.reason"
    />

    <p class="sentinel-statusbar">
      <span>哨兵 <b>{{ state.tasks.length }}</b></span>
      <span>在线 <b>{{ onlineCount }}</b></span>
      <span>已启用 <b>{{ enabledCount }}</b></span>
      <span :class="{ 'is-bad': offlineCount > 0 }">离线 / 异常 <b>{{ offlineCount }}</b></span>
      <span>最后更新 <b>{{ lastUpdatedText }}</b></span>
    </p>

    <SentinelEmpty
      v-if="state.loaded && state.tasks.length === 0"
      title="还没有哨兵任务"
      description="哨兵任务需要绑定一个已授权的运行连接（连接中心），再选择采集类别与阈值模板。后端 /api/sentinel/* 接入后，这里会列出真实任务与其采集状态。"
    >
      <p class="sentinel-empty__links">
        <RouterLink to="/connections">前往连接中心配置目标资产 →</RouterLink>
      </p>
    </SentinelEmpty>

    <div v-else-if="state.tasks.length" class="sentinel-table-wrap">
      <table>
        <caption class="sentinel-caption">哨兵任务与采集状态</caption>
        <thead>
          <tr>
            <th scope="col">名称</th>
            <th scope="col">类别</th>
            <th scope="col">采集目标</th>
            <th scope="col">状态</th>
            <th scope="col">采集节奏</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="task in state.tasks"
            :key="task.id"
            :class="{ 'is-linked': hoveredTaskId === task.id }"
            @mouseenter="hoveredTaskId = task.id"
            @mouseleave="hoveredTaskId = null"
            @focusin="hoveredTaskId = task.id"
            @focusout="hoveredTaskId = null"
          >
            <td>{{ task.name }}</td>
            <td>{{ kindLabel(task.kind) }}</td>
            <td class="sentinel-mono">{{ task.target }}</td>
            <td><span class="sentinel-tag" :class="`sentinel-tag--${task.lastStatus || 'unknown'}`">{{ statusLabel(task.lastStatus) }}</span></td>
            <td class="sentinel-muted">{{ collectionLine(task) }}</td>
            <td>
              <button type="button" :disabled="busyId === task.id" @click="toggle(task)">
                {{ task.enabled ? '停用' : '启用' }}
              </button>
              <button type="button" :disabled="rebindBusy" @click="openRebind(task)">重绑连接</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="runtimeNote" class="sentinel-hint sentinel-hint--table">{{ runtimeNote }}</p>
    </div>

    <section v-if="rebindTask" class="sentinel-panel" aria-labelledby="sentinel-rebind-title">
      <h2 id="sentinel-rebind-title">重绑运行连接</h2>
      <p class="sentinel-hint">
        任务「{{ rebindTask.name }}」绑定的采集通道是<strong>会话级</strong>资源：后端重启或终端关闭后
        runtimeId 就失效了，任务会显示「缺少运行连接」。重新连接会生成新的通道，
        在这里选一个已有连接绑定即可继续采集，不必删任务重建。
      </p>
      <div class="sentinel-editor">
        <label class="sentinel-field"><span>运行连接</span>
          <select v-model="rebindSessionId">
            <option :value="null">请选择连接…</option>
            <option v-for="session in rebindSessions" :key="session.id" :value="session.id">
              {{ session.name || session.host }} · {{ session.protocol }} {{ session.host }}:{{ session.port }}
            </option>
          </select></label>
      </div>
      <div class="sentinel-editor__actions">
        <button type="button" :disabled="rebindBusy || !rebindSessionId" @click="submitRebind">
          {{ rebindBusy ? '正在连接…' : '连接并绑定' }}</button>
        <button type="button" @click="closeRebind">取消</button>
      </div>
      <p v-if="!rebindSessions.length" class="sentinel-muted">
        连接中心还没有可用连接，请先到「远程运维 → 连接中心」建立 SSH 连接。
      </p>
      <p v-if="rebindMessage" class="sentinel-hint" role="status">{{ rebindMessage }}</p>
    </section>

    <section class="sentinel-panel" aria-labelledby="sentinel-templates-title">
      <h2 id="sentinel-templates-title">阈值模板</h2>
      <p class="sentinel-hint">
        模板可复用并批量下发到多台资产。支持单指标阈值与复合阈值（同一数组内全部满足才触发），
        <strong>持续时间防抖</strong>用于避免瞬时峰值误报。
      </p>
      <SentinelEmpty
        v-if="state.templates.length === 0"
        title="还没有阈值模板"
        description="新建模板后可批量应用到多个哨兵任务。"
      />
      <ul v-else class="sentinel-list">
        <li v-for="template in state.templates" :key="template.id">
          <strong>{{ template.name }}</strong>
          <span class="sentinel-muted">{{ describeRules(template.rules) }}</span>
          <span class="sentinel-tag">{{ template.severity || 'P2' }}</span>
          <span class="sentinel-muted">防抖 {{ template.debounceSec }} 秒</span>
        </li>
      </ul>
    </section>

    <details class="sentinel-details">
      <summary>资产分组批量启停</summary>
      <div class="sentinel-details__body">
        <p class="sentinel-hint">
          一台机器上可能挂着多个哨兵（CPU / 内存 / 日志），按分组一次启停比逐个点更不容易漏。
          分组是自由标签，只影响组织方式，不改变采集语义。
        </p>
        <ul v-if="state.taskGroups.length" class="sentinel-list">
          <li v-for="group in state.taskGroups" :key="group.label">
            <strong>{{ group.label }}</strong>
            <span class="sentinel-muted">{{ group.enabled }} / {{ group.total }} 启用</span>
            <button type="button" :disabled="groupBusy === group.label" @click="toggleGroupState(group, true)">全部启用</button>
            <button type="button" :disabled="groupBusy === group.label" @click="toggleGroupState(group, false)">全部停用</button>
          </li>
        </ul>
        <p v-else class="sentinel-muted">还没有分组。给哨兵任务填一个分组标签后，这里就能批量启停。</p>
        <p v-if="groupMessage" class="sentinel-hint" role="status">{{ groupMessage }}</p>
      </div>
    </details>

    <details class="sentinel-details">
      <summary>新建哨兵任务</summary>
      <div class="sentinel-details__body">
        <p class="sentinel-hint">
          目标格式由<strong>后端校验</strong>（指标白名单 / 端口范围 / 进程名），这里不重复写一份规则，
          避免两侧漂移。填写错误会直接返回可读原因。
        </p>
        <div class="sentinel-editor">
          <label class="sentinel-field"><span>名称</span>
            <input v-model.trim="taskForm.name" maxlength="128" placeholder="如 web-01 CPU" /></label>
          <label class="sentinel-field"><span>采集类别</span>
            <select v-model="taskForm.kind">
              <option v-for="kind in SENTINEL_KINDS" :key="kind.id" :value="kind.id">{{ kind.label }}</option>
            </select></label>
          <label class="sentinel-field"><span>目标</span>
            <input v-model.trim="taskForm.target" :placeholder="targetPlaceholder" /></label>
          <label v-if="taskForm.kind === 'log'" class="sentinel-field">
            <span>日志关键字</span>
            <input v-model.trim="taskForm.matchRule" placeholder="如 ERROR、OutOfMemory" /></label>
          <label class="sentinel-field"><span>采集间隔</span>
            <select v-model.number="taskForm.intervalSec">
              <option v-for="item in COLLECT_INTERVALS" :key="item.id" :value="item.id">{{ item.label }}</option>
            </select></label>
          <label class="sentinel-field"><span>阈值模板</span>
            <select v-model="taskForm.templateId">
              <option :value="null">不绑定（仅采集不告警）</option>
              <option v-for="tpl in state.templates" :key="tpl.id" :value="tpl.id">{{ tpl.name }}</option>
            </select></label>
          <label class="sentinel-field"><span>资产分组</span>
            <input v-model.trim="taskForm.groupLabel" maxlength="64" placeholder="可选，如 web-prod" /></label>
          <label class="sentinel-field sentinel-field--wide"><span>运行连接 ID</span>
            <input v-model.trim="taskForm.runtimeId" placeholder="在「远程运维」建立连接后获得" /></label>
        </div>
        <div class="sentinel-editor__actions">
          <button type="button" :disabled="creating || !taskReady" @click="submitTask">
            {{ creating ? '正在创建…' : '创建哨兵任务' }}</button>
          <span class="sentinel-muted">{{ taskReady ? targetPlaceholder : '请填写名称、目标与运行连接' }}</span>
        </div>
        <p v-if="createMessage" class="sentinel-hint" role="status">{{ createMessage }}</p>
        <p class="sentinel-hint">
          类别：{{ SENTINEL_KINDS.map(item => `${item.label}（${item.cn}）`).join('、') }}。
          系统指标：{{ SYSTEM_METRICS.map(item => item.label).join('、') }}；
          业务指标：{{ BUSINESS_METRICS.map(item => item.label).join('、') }}；
          日志关键字默认：{{ LOG_KEYWORDS.join('、') }}。
        </p>
      </div>
    </details>

    <details class="sentinel-details">
      <summary>新建阈值模板</summary>
      <div class="sentinel-details__body">
        <p class="sentinel-hint">
          一条规则是单指标阈值，多条即<strong>复合阈值</strong>（全部满足才算命中）。
          持续时间用于防抖：指标需连续满足该时长才产生告警，避免抖动误报。
        </p>
        <div class="sentinel-editor">
          <label class="sentinel-field"><span>模板名称</span>
            <input v-model.trim="tplForm.name" maxlength="128" placeholder="如 高负载告警" /></label>
          <label class="sentinel-field"><span>告警级别</span>
            <select v-model="tplForm.severity">
              <option v-for="item in ALERT_SEVERITIES" :key="item.id" :value="item.id">{{ item.label }}</option>
            </select></label>
          <label class="sentinel-field"><span>持续时间（秒）</span>
            <input v-model.number="tplForm.debounceSec" type="number" min="0" max="3600" /></label>
        </div>
        <div v-for="(rule, index) in tplForm.rules" :key="index" class="sentinel-editor">
          <label class="sentinel-field"><span>指标</span>
            <select v-model="rule.metric">
              <option v-for="m in allMetrics" :key="m.id" :value="m.id">{{ m.label }}</option>
            </select></label>
          <label class="sentinel-field"><span>运算</span>
            <select v-model="rule.operator">
              <option v-for="op in THRESHOLD_OPERATORS" :key="op.id" :value="op.id">{{ op.symbol }}</option>
            </select></label>
          <label class="sentinel-field"><span>阈值</span>
            <input v-model.number="rule.value" type="number" step="0.1" /></label>
          <div class="sentinel-editor__actions">
            <button type="button" :disabled="tplForm.rules.length <= 1" @click="tplForm.rules.splice(index, 1)">删除这条</button>
          </div>
        </div>
        <div class="sentinel-editor__actions">
          <button type="button" @click="addRule">再加一条（复合阈值）</button>
          <button type="button" :disabled="creating || !templateReady" @click="submitTemplate">
            {{ creating ? '正在创建…' : '创建阈值模板' }}</button>
        </div>
        <p v-if="templateMessage" class="sentinel-hint" role="status">{{ templateMessage }}</p>
      </div>
    </details>
  </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, defineAsyncComponent } from 'vue'
import SentinelNotice from './SentinelNotice.vue'
import SentinelEmpty from './SentinelEmpty.vue'
import SpiderCrawler from '../../components/effects/SpiderCrawler.vue'
import { resolvedTheme as _resolvedTheme } from '../../theme.js'
import { createTask, createTemplate, loadSentinel, rebindRuntime, sentinelState as state, startPolling, stopPolling, successRate, toggleGroup, toggleTask } from './sentinelStore.js'
import { getOperationSessions } from '../../api/operations.ts'
import { ALERT_SEVERITIES, BUSINESS_METRICS, COLLECT_INTERVALS, SENTINEL_KINDS, SYSTEM_METRICS, LOG_KEYWORDS, THRESHOLD_OPERATORS, describeRules } from './sentinelModel.js'
import './sentinel.css'

const CanvasAmbientField = defineAsyncComponent(() => import('../../components/common/CanvasAmbientField.vue'))
const MeteorShower = defineAsyncComponent(() => import('../../components/common/MeteorShower.vue'))

const dashboardShellRef = ref(null)
const resolvedTheme = computed(() => _resolvedTheme.value)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 1024)
function updateMobile() { isMobile.value = window.innerWidth < 1024 }

const busyId = ref(null)
const groupBusy = ref(null)
const groupMessage = ref('')
/** 表格当前 hover 的任务 id；传给巡网动画实现「表格 ↔ 网图」联动高亮。 */
const hoveredTaskId = ref(null)

/**
 * 重绑运行连接。
 *
 * 不自动挑连接：采集发生在哪个通道上是有安全含义的决定，必须由人选。
 * 后端若该连接已有存活通道会复用，不会重复建立 SSH。
 */
const rebindTask = ref(null)
const rebindSessions = ref([])
const rebindSessionId = ref(null)
const rebindBusy = ref(false)
const rebindMessage = ref('')

async function openRebind(task) {
  rebindTask.value = task
  rebindSessionId.value = null
  rebindMessage.value = ''
  try {
    const response = await getOperationSessions()
    rebindSessions.value = Array.isArray(response?.data) ? response.data : []
  } catch {
    rebindSessions.value = []
  }
}

function closeRebind() {
  rebindTask.value = null
  rebindMessage.value = ''
}

async function submitRebind() {
  if (!rebindTask.value || !rebindSessionId.value) return
  rebindBusy.value = true
  rebindMessage.value = ''
  try {
    const result = await rebindRuntime(rebindTask.value.id, rebindSessionId.value)
    rebindMessage.value = result.ok
      ? `已绑定新通道，下一轮采集（最长 30 秒）会用该通道取数。`
      : result.message
    if (result.ok) await loadSentinel()
  } finally {
    rebindBusy.value = false
  }
}

/** 批量启停：后端返回实际改动数，用它告诉用户"改了几条"而不是笼统成功。 */
async function toggleGroupState(group, enabled) {
  groupBusy.value = group.label
  groupMessage.value = ''
  try {
    const result = await toggleGroup(group.label, enabled)
    groupMessage.value = result.ok
      ? `分组「${group.label}」已${enabled ? '启用' : '停用'} ${result.changed} 个任务。`
      : result.message
    if (result.ok) await loadSentinel()
  } finally { groupBusy.value = null }
}
/**
 * 采集边界说明：显示"缺少运行连接"时要讲清为什么，否则会被当成采集器坏了。
 * 文案与服务端 /api/sentinel/runtime-boundary 保持一致。
 */
const runtimeNote = computed(() => state.tasks.some(task => task.lastStatus === 'no_runtime')
  ? '「缺少运行连接」表示该任务的会话级连接已关闭。哨兵采集发生在已授权的运行连接内，连接关闭后无法采集；在任务行点「重绑连接」可重新接上，要实现 7×24 常驻采集则需独立部署轻量采集器。'
  : '')

const onlineCount = computed(() => state.tasks.filter(task => task.lastStatus === 'online').length)
const offlineCount = computed(() => state.tasks.filter(task => task.lastStatus && task.lastStatus !== 'online').length)
const enabledCount = computed(() => state.tasks.filter(task => task.enabled).length)

/** 把真实哨兵任务投影成巡网动画的节点：id + 采集状态 + 最近采样时间，驱动网节点着色与蜘蛛巡访目标。 */
const crawlerNodes = computed(() => state.tasks.map(task => ({
  id: task.id,
  status: task.lastStatus || 'unknown',
  lastSeenAt: task.lastSeenAt || null,
  enabled: task.enabled
})))

/** 最后更新文案：轮询会在 lastPolledAt 后刷新，这里做相对时间显示（每秒 tick 一次）。 */
const nowTs = ref(Date.now())
const lastUpdatedText = computed(() => {
  if (!state.lastPolledAt) return '尚未更新'
  const sec = Math.max(0, Math.round((nowTs.value - state.lastPolledAt) / 1000))
  if (sec < 60) return `${sec} 秒前`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} 分钟前`
  return `${Math.floor(min / 60)} 小时前`
})

const kindLabel = id => SENTINEL_KINDS.find(item => item.id === id)?.label ?? id ?? '—'
const intervalLabel = value => COLLECT_INTERVALS.find(item => item.id === value)?.label ?? (value ? `${value} 秒` : '—')
const STATUS_LABELS = {
  online: '在线',
  offline: '离线',
  error: '采集异常',
  // 运行连接是会话级资源：连接关闭后取不到采集通道，这是正常状态而不是"未知"。
  no_runtime: '缺少运行连接'
}
const statusLabel = value => STATUS_LABELS[value] ?? '未知'

/** 一行讲完采集节奏：间隔 · 最近采集 · 成功率。没有样本就只说间隔，不编造 0%。 */
const collectionLine = task => {
  const parts = [intervalLabel(task.intervalSec), task.lastSeenAt || '未采集']
  const rate = successRate(task)
  if (rate !== null) parts.push(`${(rate * 100).toFixed(0)}% 成功`)
  return parts.join(' · ')
}

async function toggle(task) {
  busyId.value = task.id
  try {
    const ok = await toggleTask(task.id, !task.enabled)
    if (!ok) state.reason = '启停失败：后端未接入或权限不足。'
  } finally {
    busyId.value = null
  }
}

const reload = () => loadSentinel()
/* ── 新建哨兵 / 阈值模板 ───────────────────────────────────────────── */

const creating = ref(false)
const createMessage = ref('')
const templateMessage = ref('')

const taskForm = reactive({
  name: '', kind: 'system', target: 'cpu', matchRule: '', intervalSec: 60,
  templateId: null, runtimeId: '', groupLabel: ''
})
const tplForm = reactive({
  name: '', severity: 'P2', debounceSec: 0,
  rules: [{ metric: 'cpu', operator: 'gt', value: 90 }]
})

/** 指标下拉：系统 + 业务一起给出，避免用户在两处找。 */
const allMetrics = computed(() => [...SYSTEM_METRICS, ...BUSINESS_METRICS])

/** 目标格式随类别变化：后端仍会二次校验，这里只是提示怎么填。 */
const targetPlaceholder = computed(() => {
  if (taskForm.kind === 'system') return SYSTEM_METRICS.map(m => m.id).join(' / ')
  if (taskForm.kind === 'business') return 'port:443 / process:nginx / http:https://example.test/health'
  return '/var/log/app/error.log'
})

const taskReady = computed(() => taskForm.name.length > 0
  && taskForm.target.length > 0 && taskForm.runtimeId.length > 0)

const templateReady = computed(() => tplForm.name.length > 0
  && tplForm.rules.length > 0
  && tplForm.rules.every(rule => rule.metric && rule.operator && Number.isFinite(Number(rule.value))))

function addRule() {
  tplForm.rules.push({ metric: 'memory', operator: 'gt', value: 90 })
}

async function submitTask() {
  creating.value = true
  createMessage.value = ''
  try {
    const result = await createTask({ ...taskForm })
    createMessage.value = result.ok
      ? `已创建哨兵「${result.task.name}」，等待下一次轮询开始采集。`
      : result.message
    if (result.ok) {
      createMessage.value += ' 若未绑定模板，它只采集不告警。'
      await loadSentinel()
    }
  } finally { creating.value = false }
}

async function submitTemplate() {
  creating.value = true
  templateMessage.value = ''
  try {
    const rules = tplForm.rules.map(rule => ({
      metric: rule.metric, operator: rule.operator, value: Number(rule.value)
    }))
    const result = await createTemplate({
      name: tplForm.name, description: '', rules,
      severity: tplForm.severity, debounceSec: Number(tplForm.debounceSec) || 0
    })
    templateMessage.value = result.ok
      ? `已创建模板「${result.template.name}」（${rules.length} 条规则，${describeRules(rules)}）`
      : result.message
    if (result.ok) await loadSentinel()
  } finally { creating.value = false }
}

let tickTimer = null

onMounted(() => {
  updateMobile(); window.addEventListener('resize', updateMobile)
  loadSentinel()
  startPolling(30000) // 真实轮询：每 30 秒刷新一次哨兵数据（后端未接入时静默失败，不伪造数据）
  tickTimer = setInterval(() => { nowTs.value = Date.now() }, 5000) // P3：1s 改 5s，避免每秒触发整组件响应式重渲染
})

onUnmounted(() => {
  window.removeEventListener('resize', updateMobile)
  stopPolling()
  if (tickTimer) { clearInterval(tickTimer); tickTimer = null }
})
</script>

<style scoped>
/* === 启佑风格背景层 === */
.sentinel-shell{position:relative;min-height:calc(100vh - 64px);overflow:hidden;background:radial-gradient(ellipse at 80% 10%,rgba(122,215,245,.10) 0%,transparent 50%),radial-gradient(ellipse at 20% 90%,rgba(63,185,80,.07) 0%,transparent 50%),#040B16}
.sentinel-shell[data-theme='light']{background:radial-gradient(ellipse at 80% 10%,rgba(26,110,154,.07) 0%,transparent 50%),radial-gradient(ellipse at 20% 90%,rgba(26,127,55,.04) 0%,transparent 50%),#EAF3FA}
.sentinel-ambient{position:absolute;inset:0;z-index:0;opacity:.48;pointer-events:none}
.sentinel-meteors{position:absolute;inset:0;z-index:0;opacity:.35;pointer-events:none}
.sentinel-aurora{position:absolute;inset:0;z-index:0;pointer-events:none;background:radial-gradient(ellipse at 75% 15%,rgba(122,215,245,.22) 0%,transparent 45%),radial-gradient(ellipse at 30% 85%,rgba(63,185,80,.16) 0%,transparent 45%);filter:blur(24px);background-size:240% 240%;animation:sentinel-drift 22s ease-in-out infinite alternate}
.sentinel-aurora::after{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 30% 20% at 15% 50%,rgba(122,215,245,.35),transparent 70%);filter:blur(18px);animation:sentinel-sweep 32s ease-in-out infinite}
.sentinel-shell[data-theme='light'] .sentinel-aurora{background:radial-gradient(ellipse at 75% 15%,rgba(26,110,154,.14) 0%,transparent 45%),radial-gradient(ellipse at 30% 85%,rgba(26,127,55,.10) 0%,transparent 45%)}
.sentinel-shell[data-theme='light'] .sentinel-aurora::after{background:radial-gradient(ellipse 30% 20% at 15% 50%,rgba(26,110,154,.22),transparent 70%)}
@keyframes sentinel-drift{0%{background-position:0% 0%,100% 100%;transform:translate3d(0,0,0)}100%{background-position:30% 10%,70% 90%;transform:translate3d(-2%,2%,0)}}
@keyframes sentinel-sweep{0%,100%{opacity:.55;transform:translate3d(0,0,0)}50%{opacity:1;transform:translate3d(-8%,4%,0)}}
@media(prefers-reduced-motion:reduce){.sentinel-aurora,.sentinel-aurora::after{animation:none}}
.sentinel-mask{position:absolute;inset:0;z-index:0;pointer-events:none;background:radial-gradient(ellipse at center,transparent 40%,rgba(4,11,22,.42) 100%)}
.sentinel-shell[data-theme='light'] .sentinel-mask{background:radial-gradient(ellipse at center,transparent 40%,rgba(234,243,250,.42) 100%)}
.sentinel-shell>.sentinel-surface{position:relative;z-index:1}
</style>
