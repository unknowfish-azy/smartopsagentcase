/**
 * 数字人真机验收（页面侧）。
 *
 * 直接挂载生产同款 createVrmStage，采集：首帧、稳态帧时、真实渲染帧率、自动降级、
 * 上下文丢失后的静态替身表现，最后把结论 POST 回本地 runner。
 *
 * 为什么绕开 AgentPersona：它对 pointer: coarse 默认退回静态替身（移动端设计如此），
 * 真机上永远看不到 3D。本页只验证渲染链路，不代表手机端的默认产品行为。
 *
 * 用法：由 test/persona-device-acceptance.mjs 启动 Vite 后在真机打开打印出的地址。
 * 调试可用查询参数缩短窗口：?warmup=1500&steady=2500&degrade=3000&after=1500
 */
import { createVrmStage } from '/src/components/persona/useVrmModel.js'
import { personaProfile } from '/src/components/persona/personaStates.js'
import { isDegraded as schedulerDegraded } from '/src/visual/motionScheduler.js'

const MODEL_URL = '/avatar/sendagaya-shino/model.vrm'
const BUDGET = {
  firstFrameMs: 1200,
  frameP90Ms: 14,
  drawCalls: 12,
  modelBytes: 6 * 1048576,
  heapMB: 180,
  minFps: 16
}

const params = new URLSearchParams(location.search)
/** 只接受正数，避免调试参数把窗口变成 0 或 NaN */
function timing(key, fallback) {
  const value = Number(params.get(key))
  return Number.isFinite(value) && value > 0 ? value : fallback
}

const timings = {
  warmupMs: timing('warmup', 8000),
  steadyMs: timing('steady', 6000),
  degradeWaitMs: timing('degrade', 20000),
  afterDegradeMs: timing('after', 4000)
}
const READY_TIMEOUT_MS = 60000
const CONTEXT_LOSS_WAIT_MS = 1500

const logElement = document.getElementById('log')
const summaryElement = document.getElementById('summary')
const rawElement = document.getElementById('raw')
const deviceLine = document.getElementById('device-line')
const staticPanel = document.getElementById('static-panel')
const stageElement = document.getElementById('stage')

const report = {
  kind: 'persona-device-acceptance',
  version: 1,
  startedAt: new Date().toISOString(),
  finishedAt: null,
  url: location.href,
  timings,
  device: null,
  fatal: null,
  firstFrameMs: null,
  pixelRatioAtReady: null,
  model: null,
  steady: null,
  degrade: null,
  contextLoss: null,
  errors: [],
  checks: []
}

addEventListener('error', (event) => {
  report.errors.push(`error: ${event.message}`)
})
addEventListener('unhandledrejection', (event) => {
  report.errors.push(`unhandledrejection: ${event.reason?.message ?? event.reason}`)
})

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const now = () => performance.now()

function step(label, detail) {
  const item = document.createElement('li')
  const text = document.createElement('span')
  text.textContent = label
  item.appendChild(text)
  if (detail) {
    const detailElement = document.createElement('em')
    detailElement.textContent = detail
    item.appendChild(detailElement)
  }
  logElement.appendChild(item)
  console.log('[acceptance]', label, detail ?? '')
}

/** 读一遍设备与 GPU 信息；探针上下文用完立刻释放，避免占用上下文名额 */
function readDevice() {
  const probe = document.createElement('canvas')
  let api = 'none'
  let gpu = 'unknown'
  try {
    const webgl2 = probe.getContext('webgl2')
    const gl = webgl2 || probe.getContext('webgl')
    api = webgl2 ? 'webgl2' : gl ? 'webgl1' : 'none'
    if (gl) {
      const extension = gl.getExtension('WEBGL_debug_renderer_info')
      gpu = String(extension ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER))
      gl.getExtension('WEBGL_lose_context')?.loseContext()
    }
  } catch (error) {
    gpu = `probe failed: ${error.message}`
  }
  return {
    userAgent: navigator.userAgent,
    dpr: Number(devicePixelRatio.toFixed(2)),
    viewport: `${innerWidth}x${innerHeight}`,
    screen: `${screen.width}x${screen.height}`,
    hardwareConcurrency: navigator.hardwareConcurrency ?? null,
    deviceMemoryGB: navigator.deviceMemory ?? null,
    api,
    gpu
  }
}

function summarizeGaps(gaps) {
  if (!gaps.length) return { samples: 0, fps: 0, p50: 0, p90: 0 }
  const sorted = [...gaps].sort((a, b) => a - b)
  const at = (percent) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil((percent / 100) * sorted.length) - 1))]
  const mean = gaps.reduce((sum, gap) => sum + gap, 0) / gaps.length
  return {
    samples: gaps.length,
    fps: Number((1000 / mean).toFixed(1)),
    p50: Number(at(50).toFixed(1)),
    p90: Number(at(90).toFixed(1))
  }
}

/** rAF 间隔：反映主线程与合成器是否被拖慢（不等于渲染帧率） */
function sampleGaps(ms) {
  return new Promise((resolve) => {
    const gaps = []
    let last = now()
    let stopped = false
    const tick = (current) => {
      const gap = current - last
      last = current
      if (gap > 0 && gap < 2000) gaps.push(gap)
      if (!stopped) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
    setTimeout(() => {
      stopped = true
      resolve(summarizeGaps(gaps))
    }, ms)
  })
}

/** 真实渲染帧率：用 stage 的累计渲染帧数算，GPU 慢也能被看见 */
async function sampleRender(stage, ms) {
  const startFrames = stage.stats().frames ?? 0
  const startedAt = now()
  const gaps = await sampleGaps(ms)
  const seconds = (now() - startedAt) / 1000
  const frames = stage.stats().frames ?? 0
  return {
    renderFps: Number(((frames - startFrames) / seconds).toFixed(1)),
    gapFps: gaps.fps,
    gapP50Ms: gaps.p50,
    gapP90Ms: gaps.p90
  }
}

function waitFor(predicate, timeout) {
  return new Promise((resolve) => {
    const startedAt = now()
    const timer = setInterval(() => {
      const matched = predicate()
      if (matched || now() - startedAt >= timeout) {
        clearInterval(timer)
        resolve(matched)
      }
    }, 200)
  })
}

/** 页面切后台会停掉共享 rAF，采样失去意义，直接中止 */
function ensureForeground() {
  if (document.hidden) throw new Error('页面在测试过程中进入后台，采样无效；请保持屏幕点亮、页面在前台后重试')
}

function buildChecks() {
  if (report.fatal) {
    return [{ id: 'load', label: '加载', actual: report.fatal, budget: '模型可加载并出首帧', verdict: 'fail' }]
  }
  const checks = []
  const push = (id, label, actual, budget, verdict) => checks.push({ id, label, actual, budget, verdict })
  const steady = report.steady
  // 占位模型 15 MB / 17 材质，首帧、体积、draw call 三项按 PERF.md §3.1 记为例外
  const placeholder = !report.model?.bytes || report.model.bytes > BUDGET.modelBytes

  push(
    'first-frame',
    '首帧',
    `${report.firstFrameMs} ms`,
    `≤ ${BUDGET.firstFrameMs} ms`,
    report.firstFrameMs <= BUDGET.firstFrameMs ? 'pass' : placeholder ? 'exempt' : 'fail'
  )
  push(
    'model-bytes',
    '模型体积',
    report.model?.bytes ? `${(report.model.bytes / 1048576).toFixed(1)} MB` : '未知',
    '≤ 6 MB（KTX2）',
    report.model?.bytes && report.model.bytes <= BUDGET.modelBytes ? 'pass' : 'exempt'
  )
  push(
    'frame-p90',
    '稳态帧时 P90',
    `${steady.frameP90Ms} ms`,
    `≤ ${BUDGET.frameP90Ms} ms`,
    steady.frameP90Ms <= BUDGET.frameP90Ms ? 'pass' : 'fail'
  )
  const effectiveFps = report.degrade?.renderFpsAfter ?? steady.renderFps
  push(
    'render-fps',
    '真实渲染帧率',
    steady.schedulerDegraded
      ? `${steady.renderFps} fps（共享调度器已限到 15fps，数值被钳制）`
      : report.degrade?.renderFpsAfter
        ? `${steady.renderFps} → ${report.degrade.renderFpsAfter} fps`
        : `${steady.renderFps} fps`,
    `≥ ${BUDGET.minFps} fps`,
    steady.schedulerDegraded ? 'exempt' : effectiveFps >= BUDGET.minFps ? 'pass' : 'fail'
  )
  push(
    'draw-calls',
    'draw call',
    `${steady.drawCalls}`,
    `≤ ${BUDGET.drawCalls}`,
    steady.drawCalls <= BUDGET.drawCalls ? 'pass' : placeholder ? 'exempt' : 'fail'
  )
  push(
    'heap',
    'JS 堆',
    steady.heapMB === null ? '设备不可读' : `${steady.heapMB} MB`,
    `≤ ${BUDGET.heapMB} MB`,
    steady.heapMB === null ? 'exempt' : steady.heapMB <= BUDGET.heapMB ? 'pass' : 'fail'
  )
  push(
    'auto-degrade',
    '自动降级',
    report.degrade?.needed
      ? report.degrade.triggered
        ? `${report.degrade.waitMs} ms 触发`
        : `${timings.degradeWaitMs} ms 内未触发`
      : '帧率达标，无需降级',
    `低帧率须 ${Math.round(timings.degradeWaitMs / 1000)} s 内触发`,
    !report.degrade?.needed || report.degrade.triggered ? 'pass' : 'fail'
  )
  push(
    'context-loss',
    '上下文丢失',
    !report.contextLoss?.supported
      ? '浏览器不支持 WEBGL_lose_context'
      : report.contextLoss.fired && report.contextLoss.pageVisible
        ? '静态替身可见，未白屏'
        : '未降级或出现白屏',
    '事件触发且页面仍可见',
    !report.contextLoss?.supported ? 'exempt' : report.contextLoss.fired && report.contextLoss.pageVisible ? 'pass' : 'fail'
  )
  push('errors', '运行时错误', report.errors.length ? `${report.errors.length} 条` : '无', '0 条', report.errors.length ? 'fail' : 'pass')
  return checks
}

function renderSummary() {
  const failures = report.checks.filter((check) => check.verdict === 'fail').length
  summaryElement.textContent = ''
  const headline = document.createElement('p')
  headline.textContent = failures ? `未通过：${failures} 项` : '验收通过（例外项已标注）'
  summaryElement.appendChild(headline)

  const table = document.createElement('table')
  const head = document.createElement('tr')
  for (const text of ['项目', '实测', '预算', '结论']) {
    const cell = document.createElement('th')
    cell.textContent = text
    head.appendChild(cell)
  }
  table.appendChild(head)
  for (const check of report.checks) {
    const row = document.createElement('tr')
    row.dataset.verdict = check.verdict
    for (const text of [check.label, String(check.actual), check.budget, check.verdict.toUpperCase()]) {
      const cell = document.createElement('td')
      cell.textContent = text
      row.appendChild(cell)
    }
    table.appendChild(row)
  }
  summaryElement.appendChild(table)
  summaryElement.hidden = false
}

async function publish() {
  try {
    await fetch('/__acceptance/report', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(report),
      keepalive: true
    })
    step('回传结果', '已发送到验收服务')
  } catch (error) {
    step('回传结果', `发送失败：${error.message}；本页可截图留证`)
  }
}

async function run() {
  report.device = readDevice()
  deviceLine.textContent = `${report.device.api} · ${report.device.viewport} @${report.device.dpr}x · ${report.device.hardwareConcurrency ?? '?'} 核`
  step('设备', report.device.gpu)

  const canvas = document.createElement('canvas')
  stageElement.appendChild(canvas)
  const events = { lost: 0 }
  let stage = null
  stage = createVrmStage({
    canvas,
    container: stageElement,
    modelUrl: MODEL_URL,
    id: 'device-acceptance',
    onContextLost: () => {
      events.lost += 1
      canvas.hidden = true
      staticPanel.hidden = false
      stage?.dispose()
    }
  })
  stage.setState(personaProfile('idle'), { fade: 0 })
  step('加载模型', '占位模型 15 MB')

  const ready = await Promise.race([
    stage.ready.then(() => true).catch((error) => {
      report.fatal = error?.message ?? String(error)
      return false
    }),
    sleep(READY_TIMEOUT_MS).then(() => false)
  ])
  if (!ready) {
    report.fatal = report.fatal ?? `首帧超时（>${READY_TIMEOUT_MS} ms）`
    return
  }

  const first = stage.stats()
  report.firstFrameMs = first.firstFrameMs
  report.pixelRatioAtReady = first.pixelRatio
  report.model = { url: MODEL_URL, bytes: first.modelBytes }
  step('首帧', `${first.firstFrameMs} ms · 像素比 ${first.pixelRatio}`)

  step('预热', `${(timings.warmupMs / 1000).toFixed(1)} s`)
  await sleep(timings.warmupMs)
  ensureForeground()

  step('稳态采样', `${(timings.steadyMs / 1000).toFixed(1)} s`)
  const sample = await sampleRender(stage, timings.steadyMs)
  const steady = stage.stats()
  ensureForeground()
  report.steady = {
    renderFps: sample.renderFps,
    gapFps: sample.gapFps,
    gapP50Ms: sample.gapP50Ms,
    gapP90Ms: sample.gapP90Ms,
    frameP50Ms: steady.frameP50Ms,
    frameP90Ms: steady.frameP90Ms,
    drawCalls: steady.drawCalls,
    geometries: steady.geometries,
    textures: steady.textures,
    pixelRatio: steady.pixelRatio,
    heapMB: steady.heapMB,
    degraded: steady.degraded,
    schedulerDegraded: schedulerDegraded()
  }
  step('稳态', `${sample.renderFps} fps · 帧时 P50 ${steady.frameP50Ms} / P90 ${steady.frameP90Ms} ms`)

  const needsDegrade = sample.renderFps < BUDGET.minFps
  const degrade = {
    needed: needsDegrade,
    triggered: steady.degraded,
    waitMs: 0,
    pixelRatioBefore: report.pixelRatioAtReady,
    pixelRatioAfter: steady.pixelRatio
  }
  if (!steady.degraded && needsDegrade) {
    const startedAt = now()
    degrade.triggered = await waitFor(() => stage.stats().degraded, timings.degradeWaitMs)
    degrade.waitMs = Math.round(now() - startedAt)
    if (degrade.triggered) {
      const after = await sampleRender(stage, timings.afterDegradeMs)
      const current = stage.stats()
      degrade.pixelRatioAfter = current.pixelRatio
      degrade.renderFpsAfter = after.renderFps
      degrade.frameP90After = current.frameP90Ms
      step('自动降级', `${degrade.waitMs} ms 触发 · ${sample.renderFps} → ${after.renderFps} fps · 像素比 ${degrade.pixelRatioBefore} → ${degrade.pixelRatioAfter}`)
    } else {
      step('自动降级', `${timings.degradeWaitMs} ms 内未触发`)
    }
  } else {
    step('自动降级', steady.degraded ? '预热阶段已触发' : '帧率达标，未触发')
  }
  report.degrade = degrade

  ensureForeground()
  const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')
  const extension = gl?.getExtension('WEBGL_lose_context')
  const contextLoss = { supported: Boolean(extension), fired: false, pageVisible: false, canvasHidden: false }
  if (extension) {
    extension.loseContext()
    await sleep(CONTEXT_LOSS_WAIT_MS)
    contextLoss.fired = events.lost > 0
    contextLoss.pageVisible = document.body.innerText.trim().length > 0 && !staticPanel.hidden
    contextLoss.canvasHidden = canvas.hidden
    step('上下文丢失', contextLoss.fired ? '静态替身可见，页面未白屏' : '未触发降级')
  } else {
    step('上下文丢失', '浏览器不支持 WEBGL_lose_context')
  }
  report.contextLoss = contextLoss
}

run()
  .catch((error) => {
    report.fatal = error?.message ?? String(error)
    step('中止', report.fatal)
  })
  .finally(async () => {
    report.finishedAt = new Date().toISOString()
    report.checks = buildChecks()
    renderSummary()
    rawElement.textContent = JSON.stringify(report, null, 2)
    await publish()
  })
