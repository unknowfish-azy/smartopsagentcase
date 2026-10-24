<template>
  <section class="sentinel-surface" aria-labelledby="sentinel-title">
    <header class="sentinel-page-header sentinel-page-header--hud">
      <div>
        <p class="sentinel-eyebrow">SENTINEL / 哨兵监控</p>
        <h1 id="sentinel-title">哨兵监控台</h1>
      </div>
      <button type="button" :disabled="state.loading" @click="reload">刷新</button>
    </header>
    <p class="sentinel-lede">
      常驻哨兵持续采集系统与业务指标、监听日志关键字，命中阈值且持续时间达标后产生告警并送入告警中心。
      区别于定时巡检：哨兵是常驻监听，不是一次性任务。
    </p>

    <SentinelNotice v-if="state.status === 'unavailable'" tone="warn" title="后端未接入" :detail="state.reason" />

    <dl class="sentinel-stats">
      <div class="sentinel-stat sentinel-stat--hud"><dt><b>TOTAL</b>哨兵总数</dt><dd>{{ state.tasks.length }}</dd></div>
      <div class="sentinel-stat sentinel-stat--hud"><dt><b>ONLINE</b>在线哨兵</dt><dd>{{ onlineCount }}</dd></div>
      <div class="sentinel-stat sentinel-stat--hud"><dt><b>OFFLINE</b>离线 / 异常</dt><dd>{{ offlineCount }}</dd></div>
      <div class="sentinel-stat sentinel-stat--hud"><dt><b>ENABLED</b>已启用</dt><dd>{{ enabledCount }}</dd></div>
    </dl>

    <!-- CRAWLER / 拓扑巡网：蜘蛛沿拓扑网持续爬检的氛围动效（哨兵巡检的视觉隐喻）。
         画布不承载实时采集数据，真实哨兵状态见上方统计与任务表；后端未接入时照常显示。 -->
    <section class="sentinel-panel sentinel-crawler" aria-labelledby="sentinel-crawler-title">
      <h2 id="sentinel-crawler-title">CRAWLER / 拓扑巡网</h2>
      <div class="crawler-stage">
        <SpiderCrawler :seed="42" />
      </div>
      <p class="sentinel-hint">
        巡网意象：蜘蛛沿服务拓扑持续爬检，路过节点即视为一次巡查。此为氛围动效，不承载实时采集数据——
        哨兵在线率、采集成功率等真实状态以上方统计与任务表为准。
      </p>
    </section>

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
            <th scope="col">周期</th>
            <th scope="col">状态</th>
            <th scope="col">最近采集</th>
            <th scope="col">采集成功率</th>
            <th scope="col">采样历史</th>
            <th scope="col">启停</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in state.tasks" :key="task.id">
            <td>{{ task.name }}</td>
            <td>{{ kindLabel(task.kind) }}</td>
            <td class="sentinel-mono">{{ task.target }}</td>
            <td>{{ intervalLabel(task.intervalSec) }}</td>
            <td><span class="sentinel-tag" :class="`sentinel-tag--${task.lastStatus || 'unknown'}`">{{ statusLabel(task.lastStatus) }}</span></td>
            <td>{{ task.lastSeenAt || '—' }}</td>
            <td>{{ rateLabel(task) }}</td>
            <td><SentinelHeartbeat :samples="Array.isArray(task.heartbeats) ? task.heartbeats : Array.isArray(task.checks) ? task.checks : []" /></td>
            <td>
              <button type="button" :disabled="busyId === task.id" @click="toggle(task)">
                {{ task.enabled ? '停用' : '启用' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="runtimeNote" class="sentinel-hint sentinel-hint--table">{{ runtimeNote }}</p>
    </div>

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

    <section class="sentinel-panel" aria-labelledby="sentinel-groups-title">
      <h2 id="sentinel-groups-title">资产分组批量启停</h2>
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
    </section>

    <section class="sentinel-panel" aria-labelledby="sentinel-create-title">
      <h2 id="sentinel-create-title">新建哨兵任务</h2>
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
    </section>

    <section class="sentinel-panel" aria-labelledby="sentinel-template-title">
      <h2 id="sentinel-template-title">新建阈值模板</h2>
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
    </section>

    <section class="sentinel-panel" aria-labelledby="sentinel-kinds-title">
      <h2 id="sentinel-kinds-title">支持的采集类别</h2>
      <ul class="sentinel-list">
        <li v-for="kind in SENTINEL_KINDS" :key="kind.id">
          <strong>{{ kind.label }}</strong><span class="sentinel-muted">{{ kind.cn }}</span>
        </li>
      </ul>
      <p class="sentinel-hint">
        系统指标：{{ SYSTEM_METRICS.map(item => item.label).join('、') }}。
        业务指标：{{ BUSINESS_METRICS.map(item => item.label).join('、') }}。
        日志关键字默认：{{ LOG_KEYWORDS.join('、') }}。
      </p>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import SentinelNotice from './SentinelNotice.vue'
import SentinelEmpty from './SentinelEmpty.vue'
import SentinelHeartbeat from './SentinelHeartbeat.vue'
import SpiderCrawler from '../../components/effects/SpiderCrawler.vue'
import { createTask, createTemplate, loadSentinel, sentinelState as state, successRate, toggleGroup, toggleTask } from './sentinelStore.js'
import { ALERT_SEVERITIES, BUSINESS_METRICS, COLLECT_INTERVALS, SENTINEL_KINDS, SYSTEM_METRICS, LOG_KEYWORDS, THRESHOLD_OPERATORS, describeRules } from './sentinelModel.js'
import './sentinel.css'

const busyId = ref(null)
const groupBusy = ref(null)
const groupMessage = ref('')

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
  ? '「缺少运行连接」表示该任务的会话级连接已关闭。哨兵采集发生在已授权的运行连接内，连接关闭后无法采集；要实现 7×24 常驻采集需要独立部署轻量采集器。'
  : '')

const onlineCount = computed(() => state.tasks.filter(task => task.lastStatus === 'online').length)
const offlineCount = computed(() => state.tasks.filter(task => task.lastStatus && task.lastStatus !== 'online').length)
const enabledCount = computed(() => state.tasks.filter(task => task.enabled).length)

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
const rateLabel = task => {
  const rate = successRate(task)
  return rate === null ? '—' : `${(rate * 100).toFixed(1)}%`
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

onMounted(loadSentinel)
</script>
