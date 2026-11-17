<template>
  <article class="device-registry-page">

    <!-- 页面标题 -->
    <header class="page-head">
      <div>
        <h1>设备接入台账</h1>
        <p>多设备统一接入视图与本地视觉识别异常预警；全部数据来自真实接口，失败即如实标注。</p>
      </div>
    </header>

    <!-- A. 接入台账区：四类来源分别聚合，失败独立降级 -->
    <section class="section" aria-labelledby="ledger-heading">
      <h2 id="ledger-heading" class="section-title">接入台账</h2>

      <!-- 汇总条：由纯函数 summarizeLedger 基于真实返回计算 -->
      <div class="ledger-summary" role="status">
        <span>服务器 <strong>{{ ledger.serverTotal }}</strong> 台 · 在线 <strong>{{ ledger.serverOnline }}</strong></span>
        <span>模型连接 <strong>{{ ledger.connectionTotal }}</strong> 条 · 启用 <strong>{{ ledger.connectionEnabled }}</strong></span>
        <span>本地运行时 <strong>{{ miniRuntime.state === 'ok' ? (miniRuntime.data.available ? '在线' : '离线') : '—' }}</strong></span>
        <span>巡检机器人 <strong>{{ robotsTotal }}</strong> 台 · 启用 <strong>{{ robotsEnabled }}</strong></span>
      </div>

      <div class="ledger-grid">

        <!-- 来源 1：服务器（GET /api/servers） -->
        <div class="source-card">
          <div class="source-head">
            <h3>服务器</h3>
            <span class="pill" :class="sourcePillClass(serversSource.state)">
              {{ sourcePillText(serversSource.state) }}
            </span>
          </div>
          <p v-if="serversSource.state === 'loading'" class="source-note">正在加载真实服务器列表…</p>
          <p v-else-if="serversSource.state === 'error'" class="source-error" role="alert">
            不可用：{{ serversSource.error }}
          </p>
          <template v-else>
            <ul class="source-list">
              <li v-for="server in serversSource.data.slice(0, 5)" :key="server.id ?? server.name">
                <span class="item-name">{{ server.name || server.host || '未命名服务器' }}</span>
                <span class="pill" :class="serverStatusClass(server.status)">{{ server.status || '未知' }}</span>
              </li>
            </ul>
            <p v-if="!serversSource.data.length" class="source-note">暂无真实服务器记录</p>
            <p v-else-if="serversSource.data.length > 5" class="source-note">仅展示前 5 条，共 {{ serversSource.data.length }} 条</p>
          </template>
        </div>

        <!-- 来源 2：模型连接（GET /api/model-connections） -->
        <div class="source-card">
          <div class="source-head">
            <h3>模型连接</h3>
            <span class="pill" :class="sourcePillClass(connectionsSource.state)">
              {{ sourcePillText(connectionsSource.state) }}
            </span>
          </div>
          <p v-if="connectionsSource.state === 'loading'" class="source-note">正在加载模型连接…</p>
          <p v-else-if="connectionsSource.state === 'error'" class="source-error" role="alert">
            不可用：{{ connectionsSource.error }}
          </p>
          <template v-else>
            <ul class="source-list">
              <li v-for="connection in connectionsSource.data.slice(0, 5)" :key="connection.id">
                <span class="item-name">{{ connection.name || connection.modelName || '未命名连接' }}</span>
                <span class="pill" :class="connection.enabled ? 'pill-ok' : 'pill-neutral'">
                  {{ connection.enabled ? '已启用' : '停用' }}
                </span>
              </li>
            </ul>
            <p v-if="!connectionsSource.data.length" class="source-note">暂无模型连接记录</p>
            <p v-else-if="connectionsSource.data.length > 5" class="source-note">仅展示前 5 条，共 {{ connectionsSource.data.length }} 条</p>
          </template>
        </div>

        <!-- 来源 3：智维 Mini 本地运行时（GET /api/web-research/runtime） -->
        <div class="source-card">
          <div class="source-head">
            <h3>智维 Mini 本地运行时</h3>
            <span class="pill" :class="sourcePillClass(miniRuntime.state)">
              {{ sourcePillText(miniRuntime.state) }}
            </span>
          </div>
          <p v-if="miniRuntime.state === 'loading'" class="source-note">正在探测本地运行时…</p>
          <p v-else-if="miniRuntime.state === 'error'" class="source-error" role="alert">
            不可用：{{ miniRuntime.error }}
          </p>
          <template v-else>
            <p class="runtime-model">
              模型 <code>{{ miniRuntime.data.model || '未设置' }}</code>
            </p>
            <span class="pill" :class="miniRuntime.data.available ? 'pill-ok' : 'pill-danger'">
              {{ miniRuntime.data.available ? '在线' : '离线 / ' + (miniRuntime.data.status || '未知状态') }}
            </span>
            <p class="source-note">{{ miniRuntime.data.detail || '运行时未返回说明' }}</p>
          </template>
        </div>

        <!-- 来源 4：巡检机器人（GET /api/robot/devices，M0 台账） -->
        <div class="source-card">
          <div class="source-head">
            <h3>巡检机器人</h3>
            <span class="pill" :class="sourcePillClass(robotsSource.state)">
              {{ sourcePillText(robotsSource.state) }}
            </span>
          </div>
          <p v-if="robotsSource.state === 'loading'" class="source-note">正在加载巡检机器人台账…</p>
          <p v-else-if="robotsSource.state === 'error'" class="source-error" role="alert">
            不可用：{{ robotsSource.error }}
          </p>
          <template v-else>
            <ul class="source-list">
              <li
                v-for="robot in robotsSource.data.slice(0, 5)"
                :key="robot.deviceKey"
                class="robot-row"
                :class="{ 'robot-row-selected': robot.deviceKey === selectedRobotKey }"
                role="button"
                tabindex="0"
                :aria-pressed="robot.deviceKey === selectedRobotKey"
                :aria-label="`选择机器人 ${robot.name || robot.deviceKey} 查看 3D 态势`"
                @click="selectRobot(robot.deviceKey)"
                @keydown.enter.prevent="selectRobot(robot.deviceKey)"
                @keydown.space.prevent="selectRobot(robot.deviceKey)"
              >
                <span class="item-name">{{ robot.name || robot.deviceKey }}</span>
                <span class="pill pill-neutral">{{ formFactorLabel(robot.formFactor) }}</span>
                <span class="pill" :class="robot.enabled ? 'pill-ok' : 'pill-neutral'">
                  {{ robot.enabled ? '已启用' : '未启用' }}
                </span>
              </li>
            </ul>
            <p v-if="!robotsSource.data.length" class="source-note">暂无登记的巡检机器人（管理员可通过 POST /api/robot/devices 登记）</p>
            <p v-else-if="robotsSource.data.length > 5" class="source-note">仅展示前 5 条，共 {{ robotsSource.data.length }} 条；点击设备可查看 3D 态势</p>
            <p v-else class="source-note">点击设备可查看 3D 态势</p>
          </template>
        </div>

      </div>
    </section>

    <!-- A+. 机器人实时态势：复用控制台 RobotScene3D，数据经 REST 轮询（无 WebSocket 依赖） -->
    <section v-if="robotsSource.state === 'ok' && robotsSource.data.length" class="section" aria-labelledby="robot3d-heading">
      <h2 id="robot3d-heading" class="section-title">机器人实时态势</h2>
      <p v-if="!selectedRobotKey" class="source-note">点击上方「巡检机器人」列表中的设备，查看其 3D 态势（遥测经 GET /api/robot/live 轮询，路线来自真实任务数据）。</p>
      <template v-else>
        <div class="robot3d-head">
          <span class="item-name mono">{{ selectedRobot?.name || selectedRobotKey }}</span>
          <span class="pill" :class="robotStale ? 'pill-warning' : 'pill-ok'">
            {{ robotTelemetry ? (robotStale ? '遥测超时' : '遥测正常') : '等待遥测' }}
          </span>
          <span class="pill pill-neutral">{{ formFactorLabel(selectedRobot?.formFactor) }}</span>
        </div>
        <RobotScene3D
          :telemetry="robotTelemetry"
          :stale="robotStale"
          :device-key="selectedRobotKey"
          :form-factor="selectedRobot?.formFactor || 'CAR'"
          :mode="robotMode"
        />
      </template>
    </section>

    <!-- B. 视觉巡检区：本地多模态模型识别 + 纠察事件落库 -->
    <section class="section" aria-labelledby="vision-heading">
      <h2 id="vision-heading" class="section-title">视觉巡检</h2>

      <!-- 配置徽标：真实读取 /api/inspector/vision/status，fail-closed -->
      <div class="vision-status" role="status">
        <template v-if="visionStatus.state === 'ok'">
          <span v-if="visionStatus.data.configured" class="pill pill-ok">
            已配置视觉模型：{{ visionStatus.data.model }}
          </span>
          <span v-else class="pill pill-warning">
            未配置：请设置 smartops.vision.model 指向本地多模态模型（如 llava）
          </span>
        </template>
        <span v-else-if="visionStatus.state === 'loading'" class="pill pill-neutral">正在读取视觉巡检配置…</span>
        <span v-else class="pill pill-danger">配置状态不可用：{{ visionStatus.error }}</span>
      </div>

      <div class="vision-layout">

        <!-- 上传 + 预览 -->
        <div class="vision-upload-col">
          <div
            class="dropzone"
            :class="{ 'dropzone-over': dragging }"
            role="button"
            tabindex="0"
            aria-label="上传巡检图片"
            @click="pickFile"
            @keydown.enter.prevent="pickFile"
            @keydown.space.prevent="pickFile"
            @dragover.prevent="dragging = true"
            @dragleave.prevent="dragging = false"
            @drop.prevent="onDrop"
          >
            <input
              ref="fileInput"
              type="file"
              accept="image/*"
              class="visually-hidden"
              @change="onFileChange"
            >
            <template v-if="previewUrl">
              <img class="preview" :src="previewUrl" alt="巡检图片预览">
              <p class="source-note">{{ filename }}（{{ sizeLabel }}）</p>
            </template>
            <template v-else>
              <p class="dropzone-main">点击选择或拖拽图片到此处</p>
              <p class="source-note">支持 image/* 格式，不超过 5MB</p>
            </template>
          </div>

          <label class="target-row">
            <span>巡检目标（可选）</span>
            <input
              v-model="target"
              type="text"
              maxlength="120"
              placeholder="如：机房 A 交换机面板"
            >
          </label>

          <button
            type="button"
            class="submit-btn"
            :disabled="!imageBase64 || submitting || !visionReady"
            @click="submitVision"
          >
            {{ submitting ? '正在识别…' : '提交识别' }}
          </button>
          <p v-if="uploadError" class="source-error" role="alert">{{ uploadError }}</p>
        </div>

        <!-- 识别结果卡：纯文本渲染（Vue 插值自动转义），不做 v-html -->
        <div class="vision-result-col">
          <p v-if="submitError" class="source-error" role="alert">识别失败：{{ submitError }}</p>
          <div v-else-if="visionResult" class="result-card">
            <div class="result-head">
              <h3>识别结论</h3>
              <span class="pill" :class="verdictPillClass">
                {{ verdictText }}
              </span>
            </div>
            <p class="result-summary">{{ visionResult.analysis.summary }}</p>
            <ul v-if="visionResult.analysis.issues.length" class="result-issues">
              <li v-for="(issue, index) in visionResult.analysis.issues" :key="index">{{ issue }}</li>
            </ul>
            <p class="source-note">模型：{{ visionResult.analysis.model || '未知' }}</p>
            <p class="result-event">
              已写入纠察事件
              <RouterLink class="event-link" to="/inspector">
                {{ visionResult.eventId }}（前往纠察中心复核）
              </RouterLink>
            </p>
          </div>
          <p v-else class="source-note result-empty">尚未提交识别。结论只反映本地视觉模型对当前画面的判断。</p>
        </div>

      </div>

      <!-- 最近视觉事件：真实纠察事件过滤 category=VISION -->
      <div class="recent-events">
        <h3>最近视觉事件</h3>
        <p v-if="recentEvents.state === 'loading'" class="source-note">正在加载纠察事件…</p>
        <p v-else-if="recentEvents.state === 'error'" class="source-error" role="alert">
          不可用：{{ recentEvents.error }}
        </p>
        <ul v-else-if="recentEvents.data.length" class="event-list">
          <li v-for="event in recentEvents.data" :key="event.id">
            <span class="item-name mono">{{ event.taskId }}</span>
            <span class="pill" :class="event.severity === 'WARN' ? 'pill-warning' : 'pill-neutral'">
              {{ event.severity }}
            </span>
            <span class="pill pill-neutral">{{ event.status }}</span>
            <span class="event-reason">{{ event.reason }}</span>
            <span class="event-time">{{ event.createdAt }}</span>
          </li>
        </ul>
        <p v-else class="source-note">暂无 VISION 类纠察事件</p>
      </div>

      <!-- 诚实声明条 -->
      <p class="honesty-bar" role="note">
        识别结论来自本地视觉模型，均需人工复核后处置；模型解析失败时仅展示原文截断，不编造判断。
      </p>
    </section>

  </article>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'

import request from '../../utils/request'
import { getServers } from '../../api/server'
import { getModelConnections } from '../../api/model'
import { getInspectorEvents } from '../../api/inspector'
import { getRobotDevices, getRobotLive } from '../../api/robot'
import { summarizeLedger } from '../../utils/deviceRegistry'
import RobotScene3D from '../../components/robot/RobotScene3D.vue'

/* ============ 常量 ============ */

const MAX_IMAGE_BYTES = 5 * 1024 * 1024

/* ============ 接入台账：三类来源独立加载、独立降级 ============ */

const serversSource = ref({ state: 'loading', data: [], error: '' })
const connectionsSource = ref({ state: 'loading', data: [], error: '' })
const miniRuntime = ref({ state: 'loading', data: {}, error: '' })

const ledger = computed(() =>
  summarizeLedger(serversSource.value.data, connectionsSource.value.data)
)

async function loadServers() {
  serversSource.value = { state: 'loading', data: [], error: '' }
  try {
    const result = await getServers()
    serversSource.value = { state: 'ok', data: Array.isArray(result?.data) ? result.data : [], error: '' }
  } catch (error) {
    serversSource.value = { state: 'error', data: [], error: error?.message || '接口请求失败' }
  }
}

async function loadConnections() {
  connectionsSource.value = { state: 'loading', data: [], error: '' }
  try {
    const result = await getModelConnections()
    // 该接口无统一包装，直接返回数组；数组缺失即按空处理，不造数
    connectionsSource.value = { state: 'ok', data: Array.isArray(result) ? result : [], error: '' }
  } catch (error) {
    connectionsSource.value = { state: 'error', data: [], error: error?.message || '接口请求失败' }
  }
}

async function loadMiniRuntime() {
  miniRuntime.value = { state: 'loading', data: {}, error: '' }
  try {
    const result = await request.get('/api/web-research/runtime')
    miniRuntime.value = { state: 'ok', data: result?.data || {}, error: '' }
  } catch (error) {
    miniRuntime.value = { state: 'error', data: {}, error: error?.message || '接口请求失败' }
  }
}

/* ============ 巡检机器人台账（M0） ============ */

const robotsSource = ref({ state: 'loading', data: [], error: '' })

const robotsTotal = computed(() =>
  robotsSource.value.state === 'ok' ? robotsSource.value.data.length : 0
)

const robotsEnabled = computed(() =>
  robotsSource.value.state === 'ok'
    ? robotsSource.value.data.filter((robot) => robot?.enabled).length
    : 0
)

const FORM_FACTOR_LABELS = {
  CAR: '巡检车',
  SPIDER: '巡检蜘蛛',
  DOG: '机器狗',
  ROBOT: '巡检机器人'
}

function formFactorLabel(formFactor) {
  return FORM_FACTOR_LABELS[formFactor] || (formFactor || '未知形态')
}

async function loadRobots() {
  robotsSource.value = { state: 'loading', data: [], error: '' }
  try {
    const result = await getRobotDevices()
    robotsSource.value = { state: 'ok', data: Array.isArray(result?.data) ? result.data : [], error: '' }
  } catch (error) {
    robotsSource.value = { state: 'error', data: [], error: error?.message || '接口请求失败' }
  }
}

/* ============ 机器人 3D 态势（复用控制台组件，REST 轮询驱动） ============ */

const selectedRobotKey = ref('')
const robotTelemetry = ref(null)
const robotTelemetryAt = ref(0)
const robotMode = ref('OFFLINE')
const robotNowTick = ref(Date.now())
let robotPollTimer = null

const selectedRobot = computed(() =>
  robotsSource.value.data.find((robot) => robot?.deviceKey === selectedRobotKey.value) || null
)

/* REST 轮询 2s 一次，超过 3s 未更新即视为超时（比控制台 WS 的 1.5s 宽松一档） */
const robotStale = computed(() => {
  if (!robotTelemetry.value) return true
  return robotNowTick.value - robotTelemetryAt.value > 3000
})

function selectRobot(key) {
  if (selectedRobotKey.value === key) return
  selectedRobotKey.value = key
  robotTelemetry.value = null
  robotTelemetryAt.value = 0
  robotMode.value = 'OFFLINE'
  startRobotPoll()
}

async function pollRobotLive() {
  if (!selectedRobotKey.value) return
  try {
    const response = await getRobotLive(selectedRobotKey.value)
    const data = response?.data || {}
    robotMode.value = data.mode || 'OFFLINE'
    if (data.telemetry) {
      robotTelemetry.value = data.telemetry
      robotTelemetryAt.value = Date.now()
    }
  } catch {
    /* 轮询失败保持上次值，由 stale 判定如实展示超时 */
  }
}

function startRobotPoll() {
  stopRobotPoll()
  if (!selectedRobotKey.value) return
  pollRobotLive()
  robotPollTimer = window.setInterval(() => {
    robotNowTick.value = Date.now()
    pollRobotLive()
  }, 2000)
}

function stopRobotPoll() {
  if (robotPollTimer) {
    window.clearInterval(robotPollTimer)
    robotPollTimer = null
  }
}

/* ============ 视觉巡检 ============ */

const visionStatus = ref({ state: 'loading', data: {}, error: '' })
const submitting = ref(false)
const submitError = ref('')
const visionResult = ref(null)
const recentEvents = ref({ state: 'loading', data: [], error: '' })

const visionReady = computed(() =>
  visionStatus.value.state === 'ok' && visionStatus.value.data.configured === true
)

const verdictText = computed(() => {
  const abnormal = visionResult.value?.analysis?.abnormal
  if (abnormal === true) return '疑似异常（待人工复核）'
  if (abnormal === false) return '未发现异常（待人工复核）'
  return '结论未结构化，请人工复核原文'
})

const verdictPillClass = computed(() => {
  const abnormal = visionResult.value?.analysis?.abnormal
  if (abnormal === true) return 'pill-danger'
  if (abnormal === false) return 'pill-ok'
  return 'pill-warning'
})

async function loadVisionStatus() {
  visionStatus.value = { state: 'loading', data: {}, error: '' }
  try {
    const result = await request.get('/api/inspector/vision/status')
    visionStatus.value = { state: 'ok', data: result?.data || {}, error: '' }
  } catch (error) {
    visionStatus.value = { state: 'error', data: {}, error: error?.message || '接口请求失败' }
  }
}

async function loadRecentEvents() {
  recentEvents.value = { state: 'loading', data: [], error: '' }
  try {
    const result = await getInspectorEvents(100)
    const events = Array.isArray(result?.data) ? result.data : []
    recentEvents.value = {
      state: 'ok',
      data: events.filter((event) => event && event.category === 'VISION').slice(0, 5),
      error: ''
    }
  } catch (error) {
    recentEvents.value = { state: 'error', data: [], error: error?.message || '接口请求失败' }
  }
}

/* ---- 图片上传（input + 拖拽，image/*，≤5MB） ---- */

const fileInput = ref(null)
const dragging = ref(false)
const previewUrl = ref('')
const imageBase64 = ref('')
const filename = ref('')
const sizeLabel = ref('')
const target = ref('')
const uploadError = ref('')

function pickFile() {
  fileInput.value?.click()
}

function onDrop(event) {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) acceptFile(file)
}

function onFileChange(event) {
  const file = event.target?.files?.[0]
  if (file) acceptFile(file)
}

function acceptFile(file) {
  uploadError.value = ''
  previewUrl.value = ''
  imageBase64.value = ''
  filename.value = ''
  sizeLabel.value = ''
  if (!file.type || !file.type.startsWith('image/')) {
    uploadError.value = '仅支持 image/* 格式的图片'
    return
  }
  if (file.size > MAX_IMAGE_BYTES) {
    uploadError.value = '图片过大：不能超过 5MB'
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    const dataUrl = String(reader.result || '')
    const comma = dataUrl.indexOf(',')
    if (comma < 0) {
      uploadError.value = '图片读取失败，请重试'
      return
    }
    previewUrl.value = dataUrl
    imageBase64.value = dataUrl.slice(comma + 1)
    filename.value = file.name.slice(0, 200)
    sizeLabel.value = `${(file.size / 1024).toFixed(0)} KB`
  }
  reader.onerror = () => {
    uploadError.value = '图片读取失败，请重试'
  }
  reader.readAsDataURL(file)
}

async function submitVision() {
  if (!imageBase64.value || submitting.value) return
  submitting.value = true
  submitError.value = ''
  visionResult.value = null
  try {
    const result = await request.post('/api/inspector/vision', {
      imageBase64: imageBase64.value,
      target: target.value ? target.value.slice(0, 120) : undefined,
      filename: filename.value || undefined
    }, { timeout: 125000 })
    visionResult.value = result?.data || null
    ElMessage.success('识别完成，已写入纠察事件，请人工复核')
    // 事件已落库，刷新最近视觉事件列表
    loadRecentEvents()
  } catch (error) {
    submitError.value = error?.message || '识别请求失败'
    ElMessage.error(submitError.value)
  } finally {
    submitting.value = false
  }
}

/* ============ 徽标样式映射 ============ */

function sourcePillClass(state) {
  if (state === 'ok') return 'pill-ok'
  if (state === 'error') return 'pill-danger'
  return 'pill-neutral'
}

function sourcePillText(state) {
  if (state === 'ok') return '正常'
  if (state === 'error') return '不可用'
  return '加载中'
}

function serverStatusClass(status) {
  if (status === 'ONLINE') return 'pill-ok'
  if (status === 'WARNING') return 'pill-warning'
  if (status === 'OFFLINE' || status === 'UNKNOWN') return 'pill-danger'
  return 'pill-neutral'
}

/* ============ 初始化：并行加载，互不影响 ============ */

onMounted(() => {
  loadServers()
  loadConnections()
  loadMiniRuntime()
  loadRobots()
  loadVisionStatus()
  loadRecentEvents()
})

onBeforeUnmount(() => {
  stopRobotPoll()
})
</script>

<style scoped>
/* 颜色全部来自项目设计令牌，深浅色随 data-theme 自动切换；动效 ≤200ms */

.device-registry-page {
  display: grid;
  gap: var(--ds-section-gap);
  padding-bottom: 28px;
  color: var(--ds-color-text);
  font-size: var(--ds-font-md);
  line-height: var(--ds-line-base);
}

.page-head h1 {
  margin: 0 0 6px;
  font-size: var(--ds-font-2xl);
  font-weight: 600;
}

.page-head p {
  margin: 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-sm);
}

.section {
  display: grid;
  gap: 14px;
}

.section-title {
  margin: 0;
  font-size: var(--ds-font-lg);
  font-weight: 600;
}

/* 汇总条 */
.ledger-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  padding: 10px 14px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-muted);
  font-size: var(--ds-font-sm);
}

.ledger-summary strong {
  color: var(--ds-color-text);
  font-variant-numeric: tabular-nums;
}

/* 三来源卡片 */
.ledger-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}

.source-card {
  display: grid;
  align-content: start;
  gap: 10px;
  padding: var(--ds-card-padding);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-color-surface);
}

.source-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.source-head h3 {
  margin: 0;
  font-size: var(--ds-font-md);
  font-weight: 600;
}

.source-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.source-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: var(--ds-row-height, 40px);
  padding: 4px 0;
  border-bottom: 1px solid var(--ds-color-border);
}

.source-list li:last-child {
  border-bottom: 0;
}

/* 机器人列表行可点击选中（3D 态势联动） */
.robot-row {
  cursor: pointer;
  transition: background var(--ds-duration-fast) var(--ds-ease-out);
}

.robot-row:hover,
.robot-row:focus-visible {
  background: var(--ds-pill-neutral-bg);
  outline: var(--ds-focus-ring-width) solid var(--ds-focus-ring-color);
  outline-offset: -2px;
}

.robot-row-selected {
  background: var(--ds-pill-neutral-bg);
  box-shadow: inset 2px 0 0 var(--ds-color-primary);
}

/* 3D 态势区头部 */
.robot3d-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mono {
  font-family: var(--ds-font-mono);
}

.runtime-model {
  margin: 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-sm);
}

.runtime-model code {
  padding: 2px 6px;
  border-radius: var(--ds-radius-sm);
  background: var(--ds-pill-neutral-bg);
  color: var(--ds-color-text);
  font-family: var(--ds-font-mono);
  font-size: var(--ds-font-xs);
}

.source-note {
  margin: 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
}

.source-error {
  margin: 0;
  color: var(--ds-semantic-danger);
  font-size: var(--ds-font-sm);
}

/* 徽标 */
.pill {
  display: inline-flex;
  align-items: center;
  padding: 1px 10px;
  border-radius: var(--ds-radius-pill);
  font-size: var(--ds-font-xs);
  white-space: nowrap;
}

.pill-ok {
  background: var(--ds-pill-success-bg);
  color: var(--ds-pill-success-fg);
}

.pill-warning {
  background: var(--ds-pill-warning-bg);
  color: var(--ds-pill-warning-fg);
}

.pill-danger {
  background: var(--ds-pill-danger-bg);
  color: var(--ds-pill-danger-fg);
}

.pill-neutral {
  background: var(--ds-pill-neutral-bg);
  color: var(--ds-semantic-neutral);
}

/* 视觉巡检 */
.vision-status {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.vision-layout {
  display: grid;
  gap: 14px;
  grid-template-columns: minmax(260px, 420px) minmax(0, 1fr);
  align-items: start;
}

@media (max-width: 860px) {
  .vision-layout {
    grid-template-columns: 1fr;
  }
}

.vision-upload-col {
  display: grid;
  gap: 12px;
}

.dropzone {
  display: grid;
  justify-items: center;
  gap: 8px;
  padding: var(--ds-card-padding);
  border: 1px dashed var(--ds-color-border-strong);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-color-surface);
  cursor: pointer;
  text-align: center;
  transition: border-color var(--ds-duration-fast) var(--ds-ease-out),
              background var(--ds-duration-fast) var(--ds-ease-out);
}

.dropzone:hover,
.dropzone:focus-visible {
  border-color: var(--ds-color-primary);
  outline: var(--ds-focus-ring-width) solid var(--ds-focus-ring-color);
  outline-offset: var(--ds-focus-ring-offset);
}

.dropzone-over {
  border-color: var(--ds-color-primary);
  background: var(--ds-surface-raised, var(--ds-color-surface-raised));
}

.dropzone-main {
  margin: 0;
  font-size: var(--ds-font-sm);
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.preview {
  max-width: 100%;
  max-height: 220px;
  border-radius: var(--ds-radius-md);
  border: 1px solid var(--ds-color-border);
}

.target-row {
  display: grid;
  gap: 6px;
  font-size: var(--ds-font-sm);
  color: var(--ds-color-muted);
}

.target-row input {
  height: var(--ds-control-height);
  padding: 0 10px;
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-text);
  font-size: var(--ds-font-sm);
}

.target-row input:focus-visible {
  outline: var(--ds-focus-ring-width) solid var(--ds-focus-ring-color);
  outline-offset: var(--ds-focus-ring-offset);
  border-color: var(--ds-color-primary);
}

.submit-btn {
  height: var(--ds-control-height);
  padding: 0 18px;
  border: 1px solid var(--ds-color-primary);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-primary);
  color: var(--ds-color-surface-raised);
  font-size: var(--ds-font-md);
  cursor: pointer;
  transition: filter var(--ds-duration-fast) var(--ds-ease-out);
}

.submit-btn:hover:not(:disabled) {
  filter: brightness(1.08);
}

.submit-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.submit-btn:focus-visible {
  outline: var(--ds-focus-ring-width) solid var(--ds-focus-ring-color);
  outline-offset: var(--ds-focus-ring-offset);
}

.vision-result-col {
  display: grid;
  gap: 12px;
  align-content: start;
}

.result-card {
  display: grid;
  gap: 10px;
  padding: var(--ds-card-padding);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-color-surface);
}

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.result-head h3 {
  margin: 0;
  font-size: var(--ds-font-md);
  font-weight: 600;
}

.result-summary {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.result-issues {
  display: grid;
  gap: 6px;
  margin: 0;
  padding-left: 18px;
  color: var(--ds-color-warning);
}

.result-event {
  margin: 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-sm);
}

.event-link {
  color: var(--ds-color-primary);
  text-decoration: none;
}

.event-link:hover {
  text-decoration: underline;
}

.result-empty {
  padding: var(--ds-card-padding);
  border: 1px dashed var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
}

/* 最近视觉事件 */
.recent-events {
  display: grid;
  gap: 10px;
}

.recent-events h3 {
  margin: 0;
  font-size: var(--ds-font-md);
  font-weight: 600;
}

.event-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.event-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 8px 12px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface);
  font-size: var(--ds-font-sm);
}

.event-reason {
  flex: 1 1 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  overflow-wrap: anywhere;
}

.event-time {
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
}

/* 诚实声明条 */
.honesty-bar {
  margin: 0;
  padding: 10px 14px;
  border: 1px solid var(--ds-color-border);
  border-left: 3px solid var(--ds-semantic-info);
  border-radius: var(--ds-radius-md);
  background: var(--ds-pill-info-bg);
  color: var(--ds-color-text);
  font-size: var(--ds-font-sm);
}

/* 动效偏好：全关 */
@media (prefers-reduced-motion: reduce) {
  .device-registry-page *,
  .device-registry-page *::before,
  .device-registry-page *::after {
    transition: none !important;
    animation: none !important;
  }
}
</style>
