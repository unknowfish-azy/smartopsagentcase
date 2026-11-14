<template>
  <div
    class="fable"
    :data-theme="theme"
    :data-state="compositionState"
    :data-reduced="reduced ? 'true' : 'false'"
  >
    <header class="fable-plate">
      <div>
        <div class="fable-index">
          <span>PLATE 07</span>
          <i aria-hidden="true"></i>
          <span>AGENT MODULE · 智能体模块</span>
          <i aria-hidden="true"></i>
          <span>REV 5.2</span>
        </div>
        <div class="fable-title">
          <h1>构成变换</h1>
          <p class="title-en">COMPOSITION<br />TRANSFORM</p>
        </div>
        <p class="fable-lead">
          智能体不是聊天框。它是持续注视基础设施的一具身体：五种构成状态对应五种注意力，
          几何、孔径与体积随之重排。所有数字都来自真实运行时；读不到时显示「—」，绝不补数。
        </p>
      </div>

      <div class="fable-seal">
        <span>COMPOSITION / 当前构成</span>
        <b>
          {{ profile.cn }}
          <em>{{ profile.en }}</em>
        </b>
        <span class="seal-time">RUNTIME {{ runtimeLabel }} · {{ clock }}</span>
        <span v-if="stale" class="seal-badge seal-badge--stale">STALE · 数据冻结</span>
        <span v-if="isRehearsal" class="seal-badge seal-badge--rehearsal">REHEARSAL · 演练锁定</span>
        <button
          v-if="drillState"
          type="button"
          class="seal-reset"
          @click="drillState = null"
        >
          跟随运行时 / FOLLOW RUNTIME
        </button>
      </div>
    </header>

    <div class="fable-grid">
      <section class="fable-stage" aria-labelledby="fable-state-title">
        <div class="stage-head">
          <span class="mono-label">α · COMPOSITION FIELD / 构成场</span>
          <button
            type="button"
            class="gaze-toggle"
            :aria-pressed="gazeFollow"
            @click="toggleFollow"
          >
            <span class="dot" aria-hidden="true"></span>
            注视指针 / GAZE
          </button>
        </div>

        <div
          ref="fieldRef"
          class="stage-field"
          :class="{ 'is-stale': stale, 'is-rehearsal': isRehearsal }"
          @pointermove="onPointerMove"
          @pointerleave="onPointerLeave"
        >
          <FableComposition :field="liveField" :attractor="compositionState" :stale="stale" :reduced="reduced" />

          <span class="crop crop--tl" aria-hidden="true"></span>
          <span class="crop crop--tr" aria-hidden="true"></span>
          <span class="crop crop--bl" aria-hidden="true"></span>
          <span class="crop crop--br" aria-hidden="true"></span>
          <span class="stage-meta" aria-hidden="true">SCALE 1:1 · SVG · REV 5.2</span>

          <div class="stage-gaze">
            <FableGaze :look-x="look.x" :look-y="look.y" :field="liveField" :stale="stale" :reduced="reduced" />
          </div>

          <span class="stage-body-line" aria-hidden="true"></span>
          <div class="stage-body">
            <span class="body-figure">
              <FatBlob
                :seed="7.2"
                tone="clay"
                :size="164"
                :breathe="!reduced && !stale"
                :volume="liveField.volume"
                :pulse="liveField.pulse"
                label="肥波：智能体的体积"
              />
            </span>
            <p class="body-label">祂 · THE WATCHER</p>
          </div>

          <div class="stage-caption">
            <p class="cap-index">{{ profile.num }} / 05</p>
            <h2 id="fable-state-title">{{ profile.cn }}</h2>
            <p class="cap-en">{{ profile.en }}</p>
            <p class="cap-desc">{{ profile.desc }}</p>
            <dl class="cap-params" aria-label="构成参数">
              <div><dt>APERTURE</dt><dd>{{ formatAperture(liveField.aperture) }}</dd></div>
              <div><dt>TILT</dt><dd>{{ formatTilt(liveField.tilt) }}</dd></div>
              <div><dt>VOLUME</dt><dd>{{ formatVolume(liveField.volume) }}</dd></div>
            </dl>
          </div>
        </div>

        <div class="state-strip" role="group" aria-label="构成演练：选择状态">
          <button
            v-for="item in STATES"
            :key="item.key"
            type="button"
            :aria-pressed="compositionState === item.key"
            @click="selectState(item.key)"
          >
            <span class="num">{{ item.num }}</span>
            <span class="cn">{{ item.cn }}</span>
            <span class="en">{{ item.en }}</span>
          </button>
        </div>
        <p class="state-reason" aria-live="polite">{{ stateReason }}</p>
        <p class="state-shortcut">快捷键 1–5 切换状态 · 0 恢复自动</p>
      </section>

      <div class="fable-instruments">
        <section class="fable-panel" aria-labelledby="fable-panel-weights">
          <div class="fable-panel-head">
            <div>
              <h3 id="fable-panel-weights">构成权重</h3>
              <span class="en">ATTENTION WEIGHTS</span>
            </div>
            <span class="tag">STRUCTURAL</span>
          </div>
          <ul class="weights">
            <li v-for="(weight, index) in profile.weights" :key="WEIGHT_LABELS[index].en">
              <span class="w-label">{{ WEIGHT_LABELS[index].cn }}</span>
              <span class="w-en">{{ WEIGHT_LABELS[index].en }}</span>
              <span class="w-track">
                <span class="w-fill" :style="{ '--w': weight }"></span>
              </span>
            </li>
          </ul>
        </section>

        <section class="fable-panel" aria-labelledby="fable-panel-field">
          <div class="fable-panel-head">
            <div>
              <h3 id="fable-panel-field">构成场手动调节</h3>
              <span class="en">MANUAL FIELD TUNE</span>
            </div>
            <button
              v-if="manualOverride"
              type="button"
              class="field-reset"
              @click="resetManualField"
            >
              重置 / RESET
            </button>
            <span v-else class="tag">DATA-DRIVEN</span>
          </div>
          <div class="field-sliders">
            <label v-for="s in FIELD_SLIDERS" :key="s.key" class="slider-row">
              <span class="s-label">{{ s.label }}</span>
              <input
                type="range"
                :min="s.min"
                :max="s.max"
                :step="s.step"
                :value="sliderVals[s.key]"
                @input="onSliderInput(s.key, Number($event.target.value))"
              />
              <span class="s-val">{{ Number(sliderVals[s.key]).toFixed(2) }}</span>
            </label>
          </div>
        </section>

        <section class="fable-panel" aria-labelledby="fable-panel-loop">
          <div class="fable-panel-head">
            <div>
              <h3 id="fable-panel-loop">回路</h3>
              <span class="en">AGENT LOOP</span>
            </div>
            <span class="tag" :class="loopsStatus === 'live' ? 'tag--live' : 'tag--off'">
              {{ loopsStatus === 'live' ? 'LIVE' : 'OFFLINE' }}
            </span>
          </div>
          <ol class="loop">
            <li
              v-for="(step, index) in LOOP_STEPS"
              :key="step.en"
              :class="{ 'is-active': profile.loop === index }"
            >
              <span class="l-index">{{ String(index + 1).padStart(2, '0') }}</span>
              <span class="l-copy">
                <span class="l-cn">{{ step.cn }}</span>
                <span class="l-en">{{ step.en }}</span>
              </span>
              <span class="l-dot" aria-hidden="true"></span>
            </li>
          </ol>
          <div class="runtime-rows">
            <div><span>AGENT 运行态</span><b>{{ runtimeLabel }}</b></div>
            <div><span>巡检健康</span><b>{{ health === null ? '—' : `${health}/100` }}</b></div>
            <div><span>活跃告警</span><b>{{ alerts === null ? '—' : alerts }}</b></div>
            <div><span>闭环记录</span><b>{{ loopsStatus === 'live' ? loops.length : '—' }}</b></div>
          </div>
        </section>

        <section class="fable-panel fable-panel--gate" aria-labelledby="fable-panel-gate">
          <div class="fable-panel-head">
            <div>
              <h3 id="fable-panel-gate">人工门</h3>
              <span class="en">HUMAN GATE</span>
            </div>
            <span class="tag">REHEARSAL</span>
          </div>
          <div class="gate-risk">
            <div>
              <span class="r-label">当前风险刻度</span>
              <span class="r-en">RISK · {{ profile.risk }}/5</span>
            </div>
            <div class="risk-scale" aria-hidden="true">
              <i v-for="n in 5" :key="n" :class="riskClass(n)"></i>
            </div>
          </div>
          <p class="gate-note">
            决策后默认暂停：动作不会自动落地，必须由人按下批准。此处两个按钮只演示构成反馈，
            不写入运行时，也不产生任何运维动作。
          </p>
          <div class="gate-actions">
            <button
              type="button"
              class="btn btn--primary"
              :disabled="gate === 'approved'"
              @click="gate = 'approved'"
            >
              模拟批准
            </button>
            <button
              type="button"
              class="btn"
              :disabled="gate === 'rejected'"
              @click="gate = 'rejected'"
            >
              模拟驳回
            </button>
          </div>
          <p class="gate-result" aria-live="polite">{{ gateMessage }}</p>
        </section>

        <section class="fable-panel fable-panel--trail" aria-labelledby="fable-panel-trail">
          <div class="fable-panel-head">
            <div>
              <h3 id="fable-panel-trail">记忆尾迹</h3>
              <span class="en">MEMORY TRAIL</span>
            </div>
            <span class="tag" :class="trailIsSample ? 'tag--sample' : 'tag--live'">
              {{ trailIsSample ? 'SAMPLE' : 'LIVE' }}
            </span>
          </div>
          <ol v-if="trail.length" class="trail">
            <li v-for="(memory, index) in trail" :key="`${memory.title}-${index}`">
              <span class="m-title">{{ memory.title }}</span>
              <span class="m-meta">{{ memory.meta }}</span>
            </li>
          </ol>
          <p v-else class="trail-empty">运行时未连接，也没有样例尾迹。</p>
        </section>

        <section class="fable-panel fable-panel--tools" aria-labelledby="fable-panel-tools">
          <div class="fable-panel-head">
            <div>
              <h3 id="fable-panel-tools">工具面</h3>
              <span class="en">TOOL PLANE</span>
            </div>
            <span class="tag">SUBSYSTEMS</span>
          </div>
          <div class="tool-plane">
            <div v-for="tool in TOOLS" :key="tool.en" class="tool">
              <FatBlob :seed="tool.seed" :tone="tool.tone" :size="34" :breathe="false" />
              <div class="t-copy">
                <span class="t-cn">{{ tool.cn }}</span>
                <span class="t-en">{{ tool.en }}</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <footer class="fable-foot">
      <span><b>FABLE 5.2</b> · 构成变换</span>
      <span>呼吸 7.4s · 变换 900–1200ms · 注视 30fps</span>
      <span>REDUCED MOTION → 静态单帧</span>
      <span>证据规则：本页只呈现运行时事实或标注为 SAMPLE / REHEARSAL 的构成</span>
    </footer>

    <p class="fable-sr" aria-live="polite">{{ announcement }}</p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import FableComposition from '../../components/agent/fable/FableComposition.vue'
import FableGaze from '../../components/agent/fable/FableGaze.vue'
import FatBlob from '../../components/agent/fable/FatBlob.vue'
import { resolvedTheme } from '../../theme.js'
import { visualMode } from '../../visual/visualMode.js'
import { subscribe } from '../../visual/motionScheduler.js'
import { getDecisionLoops, getDecisionLoopStats } from '../../api/decisionLoop'
import { getInspectorSummary } from '../../api/inspector'
import { useCompanionStore } from '../../stores/companion.js'
import { computeField } from './fable/useCompositionField.js'
import { useCompositionFieldClock } from './fable/useCompositionFieldClock.js'
import '../../assets/styles/fable-agent.css'

const companion = useCompanionStore()

const STATES = Object.freeze([
  {
    key: 'idle',
    num: '01',
    cn: '静观',
    en: 'IDLE / WATCHING',
    desc: '构成收拢成一条水平线。瞳孔散开，孔径最宽 —— 它在看，但什么都不抓。',
    risk: 1,
    loop: 0,
    weights: [0.18, 0.3, 0.42, 0.24, 0.1]
  },
  {
    key: 'analyze',
    num: '02',
    cn: '解析',
    en: 'PARSING',
    desc: '环裂成弧，径向刻线展开。目光开始切片，把现象分成几块可以证伪的东西。',
    risk: 2,
    loop: 0,
    weights: [0.52, 0.78, 0.6, 0.38, 0.16]
  },
  {
    key: 'decide',
    num: '03',
    cn: '决断',
    en: 'DECIDING',
    desc: '楔形升起，孔径收窄。构图只剩下两个选项，风险刻度被迫显形。',
    risk: 4,
    loop: 1,
    weights: [0.58, 0.46, 0.72, 0.44, 0.9]
  },
  {
    key: 'execute',
    num: '04',
    cn: '执行',
    en: 'EXECUTING',
    desc: '横杆加速，弧线沉入重力。动作被切成节拍，每一步都要留下可回看的痕迹。',
    risk: 5,
    loop: 2,
    weights: [0.66, 0.4, 0.34, 0.88, 0.5]
  },
  {
    key: 'reflect',
    num: '05',
    cn: '复盘',
    en: 'REFLECTING',
    desc: '圆重新合拢，内侧长出螺旋。把这一轮折回自身，写进下一次的注视。',
    risk: 2,
    loop: 3,
    weights: [0.4, 0.36, 0.66, 0.3, 0.34]
  }
])

const WEIGHT_LABELS = Object.freeze([
  { cn: '指标', en: 'METRICS' },
  { cn: '日志', en: 'LOGS' },
  { cn: '知识', en: 'KNOWLEDGE' },
  { cn: '工具', en: 'TOOLS' },
  { cn: '审批', en: 'APPROVAL' }
])

const LOOP_STEPS = Object.freeze([
  { cn: '感知', en: 'PERCEIVE' },
  { cn: '规划', en: 'PLAN' },
  { cn: '执行', en: 'ACT' },
  { cn: '核查', en: 'VERIFY' }
])

const TOOLS = Object.freeze([
  { cn: '混合检索', en: 'HYBRID RETRIEVAL', tone: 'sage', seed: 2.4 },
  { cn: '风险策略', en: 'RISK POLICY', tone: 'clay', seed: 5.1 },
  { cn: '人工审批', en: 'HUMAN GATE', tone: 'butter', seed: 3.8 },
  { cn: '安全执行', en: 'EXECUTOR', tone: 'apricot', seed: 8.6 },
  { cn: '结果核查', en: 'INSPECTOR', tone: 'gaze', seed: 4.3 },
  { cn: '审计留痕', en: 'AUDIT TRAIL', tone: 'plum', seed: 9.7 }
])

const SAMPLE_MEMORIES = Object.freeze([
  { title: 'MySQL 连接数打满 → 提升 max_connections 并回收空闲连接', meta: 'SAMPLE · 记忆样例' },
  { title: 'Nginx 502 → upstream keepalive 超时，调大空闲连接数', meta: 'SAMPLE · 记忆样例' },
  { title: '磁盘 inode 耗尽 → 清理 journal 与旧镜像层', meta: 'SAMPLE · 记忆样例' },
  { title: 'Redis 主从延迟 → 拆大 key、限制全量扫描', meta: 'SAMPLE · 记忆样例' }
])

const FIELD_SLIDERS = Object.freeze([
  { key: 'aperture', label: 'APERTURE 孔径', min: 0, max: 1, step: 0.01 },
  { key: 'tilt', label: 'TILT 倾角', min: -90, max: 90, step: 1 },
  { key: 'volume', label: 'VOLUME 体积', min: 0, max: 1, step: 0.01 },
  { key: 'gaze', label: 'GAZE 注视', min: 0, max: 1, step: 0.01 },
  { key: 'spin', label: 'SPIN 环速', min: 0, max: 1, step: 0.01 }
])

const theme = computed(() => resolvedTheme.value)
const reduced = computed(
  () =>
    visualMode.value === 'reduced-motion' ||
    (typeof globalThis.matchMedia === 'function' &&
      globalThis.matchMedia('(prefers-reduced-motion: reduce)').matches)
)

/* ---------------------------- 运行时事实 ---------------------------- */

const runtimeState = computed(() =>
  companion.states.whale === 'DEGRADED' ? 'warning' : 'idle'
)
const runtimeLabel = computed(() => (runtimeState.value === 'warning' ? 'WARNING' : 'IDLE'))

const summary = ref(null)
const loops = ref([])
const loopsStatus = ref('loading')
const stats = ref(null)

/* ---------------------------- 吸引子判定辅助（DESIGN §3） ---------------------------- */

/**
 * 取 byStage 中 count 最大的阶段（大写）。无有效数据返回 null。
 * 真实后端 stage：ANALYZE → MEMORIZE → DECIDE → REVIEW → LEARNED
 */
function dominantStage(byStage) {
  if (!Array.isArray(byStage) || byStage.length === 0) return null
  let best = null
  for (const entry of byStage) {
    const count = Number(entry && entry.count ? entry.count : 0)
    if (count <= 0) continue
    if (!best || count > best.count) {
      best = { stage: String(entry.stage || 'ANALYZE').toUpperCase(), count }
    }
  }
  return best ? best.stage : null
}

/**
 * reflect 吸引子需要 learnedCount 增长中。
 * 每次 stats 到达时与上一次比较，记录是否增长。
 */
const learnedCountGrowing = ref(false)
let lastLearnedCount = null
watch(
  stats,
  next => {
    const lc = next?.learnedCount
    if (lc == null) return
    if (lastLearnedCount != null) {
      learnedCountGrowing.value = lc > lastLearnedCount
    }
    lastLearnedCount = lc
  },
  { flush: 'sync' }
)

/* ---------------------------- 数据新鲜度（DESIGN §5） ---------------------------- */

/** 最近一次成功获取数据的时间戳（ms）。请求失败时不更新，保持旧值。 */
const fetchedAt = ref(0)
/** 当前时间戳，每秒刷新一次，用于 stale 判定。 */
const now = ref(Date.now())
/** stale：距上次成功获取 ≥ 30s。此时冻结形状、停 pulse、读数显示「—」。 */
const stale = computed(() => fetchedAt.value > 0 && now.value - fetchedAt.value > 30_000)
/** 演练模式：drillState 不为 null。视觉上加 REHEARSAL 角标 + 锁定环。 */
const isRehearsal = computed(() => drillState.value !== null)

const health = computed(() => {
  const data = summary.value
  const total = Number(data?.total ?? 0)
  if (!data || !Number.isFinite(total) || total <= 0) return null
  const pass = Number(data.pass ?? 0)
  const warning = Number(data.warning ?? 0)
  return Math.max(0, Math.min(100, Math.round(((pass + warning * 0.5) / total) * 100)))
})
const alerts = computed(() => {
  if (!summary.value) return null
  return Number(summary.value.high ?? 0) + Number(summary.value.critical ?? 0)
})

/* ---------------------------- 构成场参数（数据驱动） ---------------------------- */

/** 由后端数据算出的 target field（每帧 spring 插值前的值）。 */
const targetField = computed(() =>
  computeField(loops.value, stats.value || {}, summary.value || {}, companion)
)

/** spring 插值后的当前 field（传给组件渲染的就是这个）。 */
const { current: liveField, setTarget: setFieldTarget, setReduced: setFieldReduced, dispose: disposeFieldClock } =
  useCompositionFieldClock(targetField.value, reduced.value)

/* A1：手动参数覆盖 —— 必须在 watch(targetField) 之前定义，否则 immediate 回调引用未初始化变量 */
const manualOverride = ref(false)
const sliderVals = reactive({ aperture: 0.5, tilt: 0, volume: 0.5, gaze: 0, spin: 0 })

watch(targetField, next => {
  if (manualOverride.value) return // 手动覆盖期间跳过后端数据驱动
  setFieldTarget(next)
}, { immediate: true })
// reduced 变化时同步给 clock：开启时立即落位，关闭时恢复 spring
watch(reduced, setFieldReduced)

/* ---------------------------- 构成状态 ---------------------------- */

const drillState = ref(null)
/**
 * 五吸引子判定（DESIGN §3）。
 * 不再是 warning ? decide : idle 两分支，而是按数据条件判定：
 *   idle    — high+critical=0 且无 requiresHuman
 *   decide  — 存在 requiresHuman=true 的 loop（最高优先级，需人工介入）
 *   reflect — byStage 主导 LEARNED 且 learnedCount 增长中
 *   execute — byStage 主导 DECIDE / REVIEW
 *   analyze — byStage 主导 ANALYZE / MEMORIZE，或有告警待分析
 * 判定结果只作为「主导吸引子」提示，视觉位置仍由 liveField 参数决定。
 */
const derivedState = computed(() => {
  const data = summary.value || {}
  const high = Number(data.high ?? 0)
  const critical = Number(data.critical ?? 0)
  const highCritical = high + critical

  const hasRequiresHuman = loops.value.some(l => Boolean(l && l.requiresHuman))

  // idle：无告警且无人工审批
  if (highCritical === 0 && !hasRequiresHuman) return 'idle'

  // decide：存在需要人工审批的闭环（最高优先级）
  if (hasRequiresHuman) return 'decide'

  // 按主导阶段判定 analyze / execute / reflect
  const stage = dominantStage(stats.value?.byStage)

  if (stage === 'LEARNED' && learnedCountGrowing.value) return 'reflect'
  if (stage === 'DECIDE' || stage === 'REVIEW') return 'execute'

  // ANALYZE / MEMORIZE 主导，或有告警需要分析
  return 'analyze'
})
const compositionState = computed(() => drillState.value ?? derivedState.value)
const profile = computed(
  () => STATES.find(item => item.key === compositionState.value) || STATES[0]
)

/** A2：当前状态的驱动原因文案 */
const stateReason = computed(() => {
  if (drillState.value) return '手动演练中 · 已脱离运行时数据'
  const data = summary.value || {}
  const highCritical = Number(data.high ?? 0) + Number(data.critical ?? 0)
  const requiresHumanCount = loops.value.filter(l => Boolean(l && l.requiresHuman)).length
  const stage = dominantStage(stats.value?.byStage)
  switch (derivedState.value) {
    case 'idle':
      return highCritical === 0 && requiresHumanCount === 0 ? '无告警 · 无待审批闭环' : '运行时空闲'
    case 'decide':
      return `${requiresHumanCount} 个闭环等待人工审批`
    case 'reflect':
      return stage === 'LEARNED' ? '知识沉淀中 · 复盘闭环' : '复盘进行中'
    case 'execute':
      return stage ? `执行阶段 · ${stage}` : '决策/核查执行中'
    case 'analyze':
      return highCritical > 0 ? `${highCritical} 条告警待分析` : '现象解析中'
    default:
      return '—'
  }
})

function selectState(key) {
  drillState.value = compositionState.value === key ? null : key
  // 切换状态时清除手动参数覆盖，恢复数据驱动
  if (manualOverride.value) resetManualField()
}

/** A3：键盘快捷键 1-5 切状态，0 恢复自动 */
function onKeydown(e) {
  if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return
  if (e.ctrlKey || e.metaKey || e.altKey) return
  const map = { '1': 'idle', '2': 'analyze', '3': 'decide', '4': 'execute', '5': 'reflect' }
  if (e.key in map) {
    e.preventDefault()
    selectState(map[e.key])
  } else if (e.key === '0') {
    e.preventDefault()
    drillState.value = null
    resetManualField()
  }
}

/* ---------------------------- A1：手动参数覆盖（ref 已在上方 watch 前定义） ---------------------------- */

function applyManualField() {
  const base = targetField.value
  setFieldTarget({
    ...base,
    aperture: sliderVals.aperture,
    tilt: sliderVals.tilt,
    volume: sliderVals.volume,
    gaze: sliderVals.gaze,
    spin: sliderVals.spin
  })
}

function onSliderInput(key, value) {
  sliderVals[key] = value
  manualOverride.value = true
  applyManualField()
}

function resetManualField() {
  manualOverride.value = false
  setFieldTarget(targetField.value)
}

/* ---------------------------- 人工门演练 ---------------------------- */

const gate = ref('pending')
watch(compositionState, () => {
  gate.value = 'pending'
})
const gateMessage = computed(() => {
  if (gate.value === 'approved') return '已批准 · 仅本页构成演练，不写入运行时'
  if (gate.value === 'rejected') return '已驳回 · 仅本页构成演练，不写入运行时'
  return '待批准 · 决策后默认暂停，动作不会自动落地'
})
function riskClass(index) {
  if (index > profile.value.risk) return ''
  return profile.value.risk >= 4 ? 'on' : 'on on--mid'
}

/* ---------------------------- 记忆尾迹 ---------------------------- */

const trailIsSample = computed(() => !(loopsStatus.value === 'live' && loops.value.length > 0))
const trail = computed(() => {
  if (!trailIsSample.value) {
    return loops.value.slice(0, 4).map(loop => ({
      title: loop.title || loop.incidentKey || '未命名闭环',
      meta: `${loop.stage || 'ANALYZE'} · ${formatDate(loop.updatedAt)}`
    }))
  }
  return loopsStatus.value === 'loading' ? [] : SAMPLE_MEMORIES
})

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

/* ---------------------------- 构成参数格式化 ---------------------------- */

const formatAperture = v => (stale.value || v == null ? '—' : Number(v).toFixed(2))
const formatTilt = v => (stale.value || v == null ? '—' : `${Number(v).toFixed(0)}°`)
const formatVolume = v => (stale.value || v == null ? '—' : Number(v).toFixed(2))

/* ---------------------------- 注视指针 ---------------------------- */

const fieldRef = ref(null)
const gazeFollow = ref(!reduced.value)
const look = reactive({ x: 0, y: 0 })
const target = reactive({ x: 0, y: 0 })
let stopTracking = null

function startTracking() {
  if (stopTracking) return
  stopTracking = subscribe(
    dt => {
      const ease = Math.min(1, dt / 200)
      look.x += (target.x - look.x) * ease
      look.y += (target.y - look.y) * ease
      const settled = Math.abs(look.x - target.x) < 0.002 && Math.abs(look.y - target.y) < 0.002
      if (settled && target.x === 0 && target.y === 0) stopTrackingNow()
    },
    { fps: 30, id: 'fable-gaze' }
  )
}

function stopTrackingNow() {
  if (!stopTracking) return
  stopTracking()
  stopTracking = null
  look.x = 0
  look.y = 0
}

function onPointerMove(event) {
  if (!gazeFollow.value || reduced.value || !fieldRef.value) return
  const rect = fieldRef.value.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  target.x = Math.max(-1, Math.min(1, ((event.clientX - rect.left) / rect.width) * 2 - 1))
  target.y = Math.max(-1, Math.min(1, ((event.clientY - rect.top) / rect.height) * 2 - 1))
  startTracking()
}

function onPointerLeave() {
  target.x = 0
  target.y = 0
  if (!stopTracking) {
    look.x = 0
    look.y = 0
  }
}

function toggleFollow() {
  gazeFollow.value = !gazeFollow.value
  if (!gazeFollow.value) {
    target.x = 0
    target.y = 0
    stopTrackingNow()
  }
}

/* ---------------------------- 时钟 ---------------------------- */

const clock = ref('')

function syncClock() {
  const now = new Date()
  const date = now.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
  const time = now.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })
  clock.value = `${date} ${time}`
}

const announcement = computed(
  () => `当前构成：${profile.value.cn}。运行时状态 ${runtimeLabel.value}。`
)

/* ---------------------------- 生命周期 ---------------------------- */

let clockTimer = 0
let pollTimer = 0
let nowTimer = 0

async function loadRuntime() {
  const [inspectorResult, loopsResult, statsResult] = await Promise.allSettled([
    getInspectorSummary(),
    getDecisionLoops(8),
    getDecisionLoopStats()
  ])

  summary.value = inspectorResult.status === 'fulfilled' ? inspectorResult.value?.data || null : null

  if (loopsResult.status === 'fulfilled') {
    loops.value = Array.isArray(loopsResult.value?.data) ? loopsResult.value.data : []
    loopsStatus.value = 'live'
  } else {
    // 请求失败：保留上一帧形状（不清空 loops），只标记状态
    loopsStatus.value = 'offline'
  }

  stats.value = statsResult.status === 'fulfilled' ? statsResult.value?.data || null : null

  // 只有全部成功才更新 fetchedAt；任一失败则保持旧值，stale 会在 30s 后触发
  if (
    inspectorResult.status === 'fulfilled' &&
    loopsResult.status === 'fulfilled' &&
    statsResult.status === 'fulfilled'
  ) {
    fetchedAt.value = Date.now()
  }
}

onMounted(() => {
  syncClock()
  clockTimer = window.setInterval(syncClock, 30000)
  nowTimer = window.setInterval(() => {
    now.value = Date.now()
  }, 1000)
  pollTimer = window.setInterval(loadRuntime, 10000) // 10s 轮询
  loadRuntime()
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  if (clockTimer) window.clearInterval(clockTimer)
  if (pollTimer) window.clearInterval(pollTimer)
  if (nowTimer) window.clearInterval(nowTimer)
  stopTrackingNow()
  disposeFieldClock()
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
/* stale：整场降饱和 40%（DESIGN §5：数据陈旧时冻结并标注） */
.stage-field.is-stale {
  filter: saturate(0.6);
}

/* rehearsal：锁定虚线环（DESIGN §3.1：演练必须可见） */
.stage-field.is-rehearsal::after {
  content: '';
  position: absolute;
  inset: 8px;
  border: 1px dashed var(--fab-plum, #a383a6);
  border-radius: var(--ds-radius-sm, 4px);
  pointer-events: none;
  opacity: 0.6;
}

/* STALE / REHEARSAL 角标 */
.seal-badge {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 7px;
  border-radius: 2px;
  font: 9px/1 var(--fab-mono);
  letter-spacing: 0.1em;
}

.seal-badge--stale {
  color: var(--fab-clay, #c76a48);
  border: 1px solid color-mix(in srgb, var(--fab-clay) 50%, transparent);
  background: color-mix(in srgb, var(--fab-clay) 12%, transparent);
}

.seal-badge--rehearsal {
  color: var(--fab-plum, #a383a6);
  border: 1px solid color-mix(in srgb, var(--fab-plum) 50%, transparent);
  background: color-mix(in srgb, var(--fab-plum) 12%, transparent);
}

.seal-reset {
  justify-self: start;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--fab-gaze);
  font: 8.5px/1.5 var(--fab-mono);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  cursor: pointer;
  border-bottom: 1px solid currentColor;
}

.fable-seal b em {
  color: var(--fab-paper-46);
  font: 9px/1 var(--fab-mono);
  font-style: normal;
  letter-spacing: 0.2em;
  text-transform: uppercase;
}

.body-label {
  margin: 2px 0 0;
  color: var(--fab-paper-46);
  font: 8px/1 var(--fab-mono);
  letter-spacing: 0.24em;
  text-transform: uppercase;
  white-space: nowrap;
}

.fable-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}

/* A2：状态原因文案 */
.state-reason {
  margin: 8px 0 2px;
  color: var(--fab-gaze, #7ad7f5);
  font: 11px/1.5 var(--fab-mono);
  letter-spacing: 0.04em;
  opacity: 0.85;
}
.state-shortcut {
  margin: 0;
  color: var(--fab-paper-46, rgba(232, 242, 247, 0.46));
  font: 9px/1.4 var(--fab-mono);
  letter-spacing: 0.12em;
  opacity: 0.6;
}

/* A1：构成场手动调节滑杆 */
.field-sliders {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.slider-row {
  display: grid;
  grid-template-columns: 86px 1fr 42px;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.slider-row .s-label {
  color: var(--fab-paper, #e8f2f7);
  font: 9px/1 var(--fab-mono);
  letter-spacing: 0.08em;
  opacity: 0.8;
}
.slider-row input[type='range'] {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background: color-mix(in srgb, var(--fab-gaze) 22%, transparent);
  outline: none;
}
.slider-row input[type='range']::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--fab-gaze, #7ad7f5);
  cursor: pointer;
  box-shadow: 0 0 6px color-mix(in srgb, var(--fab-gaze) 60%, transparent);
}
.slider-row input[type='range']::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border: 0;
  border-radius: 50%;
  background: var(--fab-gaze, #7ad7f5);
  cursor: pointer;
  box-shadow: 0 0 6px color-mix(in srgb, var(--fab-gaze) 60%, transparent);
}
.slider-row .s-val {
  text-align: right;
  color: var(--fab-gaze, #7ad7f5);
  font: 9px/1 var(--fab-mono);
  letter-spacing: 0.04em;
}
.field-reset {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--fab-gaze, #7ad7f5);
  font: 8.5px/1.5 var(--fab-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  cursor: pointer;
  border-bottom: 1px solid currentColor;
}
</style>
