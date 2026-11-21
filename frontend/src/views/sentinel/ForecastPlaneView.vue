<template>
  <div class="forecast-plane" :data-state="dataState">
    <!-- 页头 -->
    <header class="forecast-page-head">
      <div>
        <p class="forecast-eyebrow">PREDICTIVE SENTINEL · {{ eyebrowModel }} · {{ eyebrowSensor }}</p>
        <h1>预测面</h1>
        <p class="forecast-lede">
          用 12 步传感器窗口预测未来 15–120 秒的读数与越界概率。图上同时给出历史、中位数预测与 p10–p90 区间；右侧说明模型、门控权重与"还有多久会越线"。预测只是证据，越界仍需人工确认后才进入告警与工单链路。
        </p>
      </div>
      <div class="forecast-state-chips">
        <span class="forecast-chip">
          <i class="forecast-chip__dot" :class="stateDotClass"></i>
          数据流 <b>{{ stateLabel }}</b>
        </span>
        <span class="forecast-chip" :title="payload?.note || ''">
          模型 <b>{{ modelLabel }}</b>
        </span>
        <span v-if="dataState === 'demo'" class="forecast-chip forecast-chip--demo">
          DEMO · 虚构示例，非真实读数
        </span>
        <span v-else-if="dataState === 'offline'" class="forecast-chip forecast-chip--warn">
          离线 · {{ errorReason || '接口不可用' }}
        </span>
        <span v-else class="forecast-chip" :title="`${payload?.sampleCount ?? 0} 点 / 间隔 ${payload?.sampleIntervalSec ?? '—'}s`">
          LIVE · {{ payload?.mode || payload?.modelStatus || '—' }} · {{ payload?.sampleIntervalSec ?? '—' }}s/点
        </span>
      </div>
    </header>

    <!-- 工具栏 -->
    <section
      class="forecast-toolbar"
      role="toolbar"
      aria-label="预测面工具栏"
    >
      <div class="forecast-tool" role="group" aria-label="视野">
        <span>视野</span>
        <div class="forecast-seg" role="group">
          <button
            v-for="h in [15, 30, 60, 120]"
            :key="h"
            type="button"
            class="forecast-seg__btn"
            :aria-pressed="horizon === h"
            @click="horizon = h"
          >{{ h }}s</button>
        </div>
      </div>
      <div class="forecast-tool" role="group" aria-label="传感器">
        <span>指标</span>
        <div class="forecast-sensors">
          <button
            v-for="s in sensors"
            :key="s.key"
            type="button"
            class="forecast-sensor"
            :aria-pressed="primarySensor === s.key"
            :title="dataState === 'demo' ? `${s.cn}（演示）` : liveTitle(s)"
            @click="primarySensor = s.key"
          >{{ dataState === 'demo' ? s.en : sensorButtonLabel(s) }}</button>
        </div>
      </div>
      <div class="forecast-tool" role="group" aria-label="对比模型">
        <span>对比</span>
        <button
          type="button"
          class="forecast-btn"
          :class="{ 'forecast-btn--on': shadowEnabled }"
          :aria-pressed="shadowEnabled"
          :disabled="dataState === 'live'"
          :title="dataState === 'live' ? '真实链路只有一个在跑的模型，无影子模型可对比' : '叠加演示影子序列'"
          @click="shadowEnabled = !shadowEnabled"
        >影子 v3.3</button>
      </div>
      <div class="forecast-tool" role="group" aria-label="回放">
        <button
          type="button"
          class="forecast-btn"
          :class="{ 'forecast-btn--on': playing }"
          :aria-pressed="playing"
          :disabled="dataState === 'live'"
          :title="dataState === 'live' ? '真实数据没有可回放的过去，回放会把读数推成虚构未来' : '按虚拟时间推进'"
          @click="togglePlayback"
        >{{ playing ? '暂停' : '回放' }}</button>
      </div>
    </section>

    <!-- 主体网格 -->
    <div class="forecast-grid">
      <!-- 左：主图 + 残差 -->
      <div class="forecast-left-stack">
        <section class="forecast-card forecast-chart-card" aria-labelledby="forecast-chart-title">
          <header class="forecast-card-head">
            <div>
              <h2 id="forecast-chart-title">预测面 · {{ sensorTitle }}</h2>
              <span class="forecast-card-en">
                FORECAST PLANE · {{ dataState === 'live' ? payload?.metricName || 'REAL SERIES' : 'SYNTHETIC DEMO' }}
              </span>
            </div>
            <span class="forecast-card-aside">窗口 −120s → +{{ horizon }}s</span>
          </header>
          <div class="forecast-chart-wrap">
            <ForecastChart
              v-if="currentSensor"
              :sensor="currentSensor"
              :horizon="horizon"
              :shadow-enabled="shadowEnabled"
              :generated-at="generatedAt"
              :now="playOffset"
              :crossings="crossings"
              :history="payload?.series || []"
              :forecast="payload?.forecast || []"
              :live="dataState === 'live'"
            />
            <div v-else class="forecast-chart-placeholder">无传感器</div>
            <div v-if="dataState === 'offline'" class="forecast-chart-empty">
              <p>{{ errorReason || '后端接口未就绪，无法获取实时数据。' }}</p>
              <button type="button" class="forecast-btn" @click="retry">重试</button>
              <button type="button" class="forecast-btn" @click="useDemo">
                查看演示数据集
              </button>
            </div>
          </div>
        </section>

        <!-- 残差 -->
        <section class="forecast-card forecast-residual-card" aria-label="残差条">
            <ForecastResidual
              :sensor="currentSensor"
              :generated-at="generatedAt"
              :now="playOffset"
              :demo="dataState === 'demo'"
              :series="payload?.series || []"
              :live="dataState === 'live'"
            />
        </section>
      </div>

      <!-- 右：三卡 -->
      <div class="forecast-side">
        <!-- 模型卡 -->
        <section class="forecast-card forecast-side-card" aria-labelledby="forecast-model-title">
          <header class="forecast-card-head">
            <div>
              <h2 id="forecast-model-title">模型</h2>
              <span class="forecast-card-en">{{ modelCardEn }}</span>
            </div>
            <span v-if="dataState === 'demo'" class="forecast-tag forecast-tag--demo">DEMO</span>
          </header>
          <!-- P2 ForecastModelCard -->
          <ForecastModelCard
            :metrics="payload?.model?.metrics"
            :unit="currentSensor.unit"
            :params="payload?.model?.params"
            :trained-at="payload?.model?.trainedAt"
            :epochs="payload?.model?.epochs"
            :live="dataState === 'live'"
            :kind="payload?.kind || ''"
            :mode="payload?.mode || ''"
            :model-status-detail="payload?.modelStatusDetail || ''"
            :model-note="payload?.model?.note || payload?.note || ''"
          />
        </section>

        <!-- 门控权重 -->
        <section class="forecast-card forecast-side-card" aria-labelledby="forecast-gates-title">
          <header class="forecast-card-head">
            <div>
              <h2 id="forecast-gates-title">门控权重</h2>
              <span class="forecast-card-en">{{ gatesCardEn }}</span>
            </div>
            <span class="forecast-tag">{{ gatesTag }}</span>
          </header>
          <ForecastGates :primary-key="primarySensor" :live="dataState === 'live'" :mode="payload?.mode || ''" />
        </section>

        <!-- 越界预测 -->
        <section class="forecast-card forecast-side-card" aria-labelledby="forecast-crossings-title">
          <header class="forecast-card-head">
            <div>
              <h2 id="forecast-crossings-title">越界预测</h2>
              <span class="forecast-card-en">PREDICTED CROSSINGS</span>
            </div>
            <span class="forecast-card-aside">{{ payload?.crossings?.length || 0 }} 条</span>
          </header>
          <ForecastCrossings
            :primary-key="primarySensor"
            :generated-at="generatedAt"
            :now="playOffset"
            :horizon="horizon"
            :crossings="payload?.crossings"
            :live="dataState === 'live'"
            :sensor-cn="payload?.sensorCn || currentSensor.cn"
            :sensor-en="payload?.sensorEn || currentSensor.en"
            :sensor-digits="currentSensor.digits ?? 1"
            :metric-name="payload?.metricName || currentSensor.metric || ''"
            :unit="payload?.unit || currentSensor.unit"
            @switch-sensor="primarySensor = $event"
          />
        </section>

        <!-- 预防动作建议（P1-4）：置信度达阈值 → 建议提前准备的动作 + 一键契约草案 -->
        <section class="forecast-card forecast-side-card" aria-labelledby="forecast-preventive-title">
          <header class="forecast-card-head">
            <div>
              <h2 id="forecast-preventive-title">预防动作建议</h2>
              <span class="forecast-card-en">PREVENTIVE ACTIONS</span>
            </div>
            <span class="forecast-card-aside">人在环上</span>
          </header>
          <ForecastPreventive
            :primary-key="primarySensor"
            :generated-at="generatedAt"
            :now="playOffset"
            :horizon="horizon"
            :crossings="payload?.crossings"
            :live="dataState === 'live'"
            :sensor-cn="payload?.sensorCn || currentSensor.cn"
            :sensor-en="payload?.sensorEn || currentSensor.en"
            :metric-name="payload?.metricName || currentSensor.metric || ''"
          />
        </section>
      </div>
    </div>

    <!-- 底部两栏 -->
    <div class="forecast-bottom-row">
      <!-- 训练与评估 -->
      <section class="forecast-card forecast-bottom-card" aria-labelledby="forecast-train-title">
        <header class="forecast-card-head">
          <div>
            <h2 id="forecast-train-title">训练与评估</h2>
            <span class="forecast-card-en">TRAINING · EVALUATION</span>
          </div>
        </header>
        <!-- ForecastTraining 全宽嵌入 -->
        <ForecastTraining
          :gate="payload?.model?.gate || (dataState === 'demo' ? 'PASS' : 'FALLBACK')"
          :best-epoch="trainingBestEpoch"
          :retrain-at="payload?.model?.trainedAt || ''"
          :live="dataState === 'live'"
          :kind="payload?.kind || ''"
          :mode="payload?.mode || ''"
          :model-status-detail="payload?.modelStatusDetail || ''"
          :sample-count="payload?.sampleCount ?? null"
          :inference-ms="payload?.inferenceMs ?? null"
          :demo="dataState === 'demo'"
        />
      </section>

      <!-- 数据源 -->
      <section class="forecast-card forecast-bottom-card" aria-labelledby="forecast-sources-title">
        <header class="forecast-card-head">
          <div>
            <h2 id="forecast-sources-title">数据源</h2>
            <span class="forecast-card-en">SOURCES · QUALITY</span>
          </div>
          <span v-if="dataState === 'demo'" class="forecast-tag forecast-tag--demo">DEMO</span>
        </header>
        <ForecastSources :source-data="sourceRows" :label-header="dataState === 'live' ? '指标' : '传感器'" />
      </section>
    </div>

    <!-- 页脚 -->
    <footer class="forecast-page-foot">
      <span>FORECAST · SENTINEL</span>
      <span>{{ sourceFootnote }}</span>
      <span>预测 · 事实：越界人工确认后才进入告警</span>
      <span>REDUCED MOTION · <b>{{ reducedMotion ? '关闭自动回放' : '自动回放可用' }}</b></span>
    </footer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { subscribe, isDegraded } from '../../visual/motionScheduler.js'
import { isReducedMotionMode, isLightweightVisualMode } from '../../visual/visualMode.js'
import { SENSORS, crossingEvents } from '../../domain/forecast/syntheticSeries.js'
import { normalizeCatalogEntry } from '../../domain/forecast/liveSensors.js'
import { useForecastSeries } from '../../composables/useForecastSeries.js'
import ForecastChart from '../../components/forecast/ForecastChart.vue'
import ForecastResidual from '../../components/forecast/ForecastResidual.vue'
import ForecastModelCard from '../../components/forecast/ForecastModelCard.vue'
import ForecastGates from '../../components/forecast/ForecastGates.vue'
import ForecastCrossings from '../../components/forecast/ForecastCrossings.vue'
import ForecastPreventive from '../../components/forecast/ForecastPreventive.vue'
import ForecastTraining from '../../components/forecast/ForecastTraining.vue'
import ForecastSources from '../../components/forecast/ForecastSources.vue'

// ---------- 三态取数 ----------
const {
  state: dataState,
  payload,
  catalog,
  metric,
  horizon,
  errorReason,
  useDemo: composableUseDemo,
  retry,
  boot
} = useForecastSeries({ metric: 'ect', horizon: 30 })

// demo 态仍用设计稿的六传感器；live 态用后端返回的真实槽位（可能少于六个）。
const sensors = computed(() => {
  if (dataState.value === 'demo') return SENSORS
  const slots = Array.isArray(catalog.value) ? catalog.value : []
  const normalized = new Map(slots.map(normalizeCatalogEntry).map(slot => [slot.key, slot]))
  // 按六槽位顺序过滤：保持 UI 位置稳定，未采样的槽位剔除而不是错位填充。
  return SENSORS.map(demo => normalized.get(demo.key) || null).filter(Boolean)
})

function liveTitle(slot) {
  const count = slot.sampleCount ?? 0
  const interval = slot.sampleIntervalSec ?? '—'
  return `${slot.metric} · ${count} 点 · 间隔 ${interval}s`
}

/**
 * 槽位按钮文案：live 态显示真实指标名（cpu/memory/…），不显示引擎别名。
 * 别名保留在 title 里，避免"ECT"被误读成发动机冷却液温度。
 */
function sensorButtonLabel(slot) {
  return slot.metric || slot.en || slot.key
}

/** 主图标题：live 用真实指标名，并把 UI 槽位别名作为括注。 */
const sensorTitle = computed(() => {
  const slot = currentSensor.value
  if (dataState.value === 'demo') return `${slot.cn} ${slot.en}`
  const metric = slot.metric || slot.en || slot.key
  const alias = slot.en && String(slot.en).toLowerCase() !== String(metric).toLowerCase()
    ? `（UI 别名 ${slot.en}）`
    : ''
  return `${metric}${alias}`
})

const primarySensor = computed({
  get: () => metric.value,
  set: v => { metric.value = v }
})

// 目录到达后，若当前选中的槽位不在可用列表里，自动切到第一个可用槽位。
watch(sensors, list => {
  if (dataState.value === 'live' && list.length && !list.some(s => s.key === metric.value)) {
    metric.value = list[0].key
  }
})

// ---------- 本地 UI 状态 ----------
const shadowEnabled = ref(false)
const playing = ref(false)
const playOffset = ref(0)
const reducedMotion = ref(false)
let stopLoop = null
const playSpeed = 3

const currentSensor = computed(
  () => sensors.value.find(s => s.key === primarySensor.value) || sensors.value[0] || SENSORS[0]
)
const generatedAt = computed(() => payload.value?.generatedAtSec || Math.floor(Date.now() / 1000))
const nowSec = computed(() => generatedAt.value + playOffset.value)

// ---------- 页头状态文案（如实反映 kind，不把统计降级写成神经模型） ----------
const stateLabel = computed(() => {
  if (dataState.value === 'live') return '正常'
  if (dataState.value === 'demo') return '演示'
  if (dataState.value === 'loading') return '加载中'
  return '离线'
})
const stateDotClass = computed(() => ({
  'forecast-chip__dot--live': dataState.value === 'live',
  'forecast-chip__dot--warn': dataState.value === 'offline' || dataState.value === 'demo'
}))
const modelLabel = computed(() => {
  const p = payload.value
  if (!p) return '—'
  if (p.kind === 'neural') return `${p.model?.arch || 'PatchTST'} · 已启用`
  if (p.kind === 'statistical') return `${p.mode || 'statistical'} · 权重未加载`
  return '不可用'
})
/** 模型卡的英文副标：live 如实写统计降级，不沿用设计稿的 MLP+GRU。 */
const modelCardEn = computed(() => {
  if (dataState.value === 'live') {
    return payload.value?.kind === 'neural' ? 'MODEL · PatchTST' : 'MODEL · STATISTICAL FALLBACK'
  }
  return 'MODEL · MLP + GRU'
})
/** 门控卡副标：统计降级没有 GRU 门控权重可导出。 */
const gatesCardEn = computed(() => {
  if (dataState.value === 'live') return payload.value?.kind === 'neural' ? 'GRU UPDATE GATE' : 'GATE · NOT EXPORTABLE'
  return 'GRU UPDATE GATE'
})
/** 页眉 eyebrow：live 如实写统计降级与哨兵指标，不沿用设计稿的 MLP+GRU/引擎传感器。 */
const eyebrowModel = computed(() => {
  if (dataState.value === 'live') {
    return payload.value?.kind === 'neural' ? 'PatchTST' : '统计降级 · STATISTICAL'
  }
  return 'MLP + GRU'
})
const eyebrowSensor = computed(() => (dataState.value === 'live' ? '哨兵指标' : '引擎传感器'))
const gatesTag = computed(() => {
  if (dataState.value === 'live') return payload.value?.kind === 'neural' ? 'STRUCTURAL' : 'FALLBACK'
  return 'STRUCTURAL'
})
const sourceFootnote = computed(() => {
  if (dataState.value === 'demo') {
    return '演示数据：曲线为确定性合成序列，属虚构示例，不代表任何真实资产或发动机'
  }
  if (dataState.value === 'live') {
    const p = payload.value
    return `数据来自 sentinel_metric_sample（${p?.metricName || '—'}，${p?.sampleCount ?? 0} 点 / ${p?.sampleIntervalSec ?? '—'}s）；` +
      `${p?.mode || 'statistical'} 预测，区间为残差近似、未经覆盖率校准`
  }
  return errorReason.value ? `离线：${errorReason.value}` : '数据来自接口'
})

/** 数据源表：live 态用后端 catalog 的真实采样口径；demo 态回退合成口径。 */
const sourceRows = computed(() => {
  if (dataState.value === 'demo') return []
  const slots = Array.isArray(catalog.value) ? catalog.value : []
  return slots.map(slot => ({
    key: slot.key,
    // 真实指标名（cpu/memory/…），不显示引擎别名
    label: slot.metric || slot.cn || slot.key,
    sampleRate: slot.sampleIntervalSec ?? null,
    // 缺失率/延迟后端没有采集，留空显示 —，不编造 0
    missing: null,
    latency: null
  }))
})

// G5 四重降级：任一命中 = 禁回放
const g5BlockPlayback = computed(() => {
  if (reducedMotion.value) return true
  if (isReducedMotionMode.value) return true
  if (isLightweightVisualMode.value) return true
  if (isDegraded()) return true
  // 窄屏（≤760）禁自动回放
  if (typeof window !== 'undefined' && window.innerWidth <= 760) return true
  return false
})

/** 训练卡的最佳 epoch：live 非神经模型没有训练产物，不能拿占位数字冒充。 */
const trainingBestEpoch = computed(() => {
  const epochs = payload.value?.model?.epochs
  if (epochs != null && Number.isFinite(Number(epochs))) return Math.max(1, Number(epochs) - 4)
  return dataState.value === 'demo' ? 38 : null
})

const crossings = computed(() => {
  // live 态：以后端真实越界为准；为空时说明"视野内没有越界"，不回落合成事件。
  if (dataState.value === 'live') return payload.value?.crossings || []
  if (payload.value?.crossings && payload.value.crossings.length > 0) return payload.value.crossings
  return crossingEvents(currentSensor.value, nowSec.value, horizon.value, 2)
})

// ---------- 初始化 ----------
onMounted(() => {
  try {
    reducedMotion.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch { /* SSR */ }
  boot()
})

onBeforeUnmount(() => { stopLoop?.() })

// G5 降级自动停回放
watch(g5BlockPlayback, (blocked) => {
  if (blocked && playing.value) {
    playing.value = false
  }
})

// 回放：每秒推进 3 个虚拟秒；G5 降级不启动
watch(playing, (next) => {
  stopLoop?.()
  if (next && g5BlockPlayback.value) {
    playing.value = false
    return
  }
  if (next) {
    stopLoop = subscribe((dt) => {
      const advance = (dt / 1000) * playSpeed
      playOffset.value += advance
      if (playOffset.value > 600) playOffset.value = -30
    }, { fps: 30, id: 'forecast-playback' })
  }
})

function togglePlayback() {
  if (g5BlockPlayback.value) return
  // live 态只有一个"现在"时刻，回放会把真实读数推成虚构未来：禁用。
  if (dataState.value === 'live') return
  playing.value = !playing.value
}

function useDemo() {
  composableUseDemo()
  playOffset.value = 0
}

// 键盘（§6）
function onKeyDown(e) {
  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    playing.value = false
    stopLoop?.()
    playOffset.value += e.key === 'ArrowLeft' ? -2 : 2
  } else if (e.code === 'Space' && !e.repeat) {
    e.preventDefault()
    if (!g5BlockPlayback.value) playing.value = !playing.value
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('keydown', onKeyDown)
  onBeforeUnmount(() => window.removeEventListener('keydown', onKeyDown))
}</script>

<style scoped>
.forecast-plane {
  --forecast-bg: var(--ds-surface-base, var(--smart-bg));
  --forecast-card: var(--ds-surface-raised, var(--smart-card));
  --forecast-overlay: var(--ds-surface-overlay, var(--smart-surface-raised));
  --forecast-line: var(--ds-hairline, var(--smart-border));
  --forecast-line-strong: var(--ds-color-border-strong, var(--smart-border-strong));
  --forecast-text: var(--ds-color-text, var(--smart-text));
  --forecast-muted: var(--ds-color-muted, var(--smart-muted));
  --forecast-accent: var(--ds-color-primary, var(--smart-primary));
  --forecast-cyan: var(--ds-color-primary-strong, var(--smart-primary-strong));
  --forecast-ok: var(--ds-color-success, var(--smart-success));
  --forecast-warn: var(--ds-semantic-warning);
  --forecast-bad: var(--ds-semantic-danger);
  --forecast-radius: var(--ds-radius-md, 8px);
  --forecast-font-mono: Consolas, 'Cascadia Mono', ui-monospace, monospace;

  min-height: 100%;
  padding: 22px 24px 40px;
  background: var(--forecast-bg);
  color: var(--forecast-text);
  box-sizing: border-box;
  /* G8：零 backdrop-filter、零粒子、零极光叠加 */
}

/* ---------- 页头 ---------- */
.forecast-page-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: end;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--forecast-line);
  margin-bottom: 18px;
}

.forecast-eyebrow {
  margin: 0 0 10px;
  color: var(--forecast-cyan);
  font: 10px var(--forecast-font-mono);
  letter-spacing: .22em;
  text-transform: uppercase;
}

.forecast-page-head h1 {
  margin: 0;
  font-size: clamp(28px, 3.2vw, 42px);
  font-weight: 500;
  letter-spacing: .01em;
  line-height: 1.05;
}

.forecast-lede {
  max-width: 70ch;
  margin: 12px 0 0;
  color: var(--forecast-muted);
  font-size: 13px;
  line-height: 1.8;
}

.forecast-state-chips {
  display: grid;
  gap: 6px;
  justify-items: end;
  min-width: 240px;
}

.forecast-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 10px;
  border: 1px solid var(--forecast-line-strong);
  border-radius: 999px;
  color: var(--forecast-muted);
  font: 10px var(--forecast-font-mono);
  letter-spacing: .08em;
  white-space: nowrap;
}

.forecast-chip b {
  color: var(--forecast-text);
  font-weight: 500;
}

.forecast-chip--demo {
  border-color: color-mix(in srgb, var(--ds-semantic-warning) 50%, transparent);
  color: var(--forecast-warn);
}

.forecast-chip--warn {
  border-color: color-mix(in srgb, var(--ds-semantic-danger) 45%, transparent);
  color: var(--forecast-bad);
}

.forecast-chip__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.forecast-chip__dot--live {
  background: var(--forecast-ok);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ds-semantic-success) 16%, transparent);
}

.forecast-chip__dot--warn {
  background: var(--forecast-warn);
}

/* ---------- 工具栏 ---------- */
.forecast-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 18px;
  padding: 14px 0;
  border-bottom: 1px solid var(--forecast-line);
  margin-bottom: 18px;
}

.forecast-tool {
  display: flex;
  align-items: center;
  gap: 8px;
}

.forecast-tool > span {
  color: var(--forecast-muted);
  font: 9.5px var(--forecast-font-mono);
  letter-spacing: .14em;
}

.forecast-seg {
  display: inline-flex;
  border: 1px solid var(--forecast-line-strong);
  border-radius: 999px;
  overflow: hidden;
}

.forecast-seg__btn {
  padding: 5px 11px;
  color: var(--forecast-muted);
  font: 11px var(--forecast-font-mono);
  letter-spacing: .06em;
  background: transparent;
  border: 0;
  cursor: pointer;
  transition: color 120ms ease, background-color 120ms ease;
}

.forecast-seg__btn + .forecast-seg__btn {
  border-left: 1px solid var(--forecast-line);
}

.forecast-seg__btn[aria-pressed="true"] {
  background: color-mix(in srgb, var(--forecast-accent) 16%, transparent);
  color: var(--forecast-text);
}

.forecast-sensors {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.forecast-sensor {
  padding: 4px 9px;
  border: 1px solid var(--forecast-line);
  border-radius: 4px;
  color: var(--forecast-muted);
  font: 10.5px var(--forecast-font-mono);
  letter-spacing: .05em;
  background: transparent;
  cursor: pointer;
  transition: color 120ms ease, border-color 120ms ease, background-color 120ms ease;
}

.forecast-sensor[aria-pressed="true"] {
  border-color: var(--forecast-cyan);
  color: var(--forecast-text);
  background: color-mix(in srgb, var(--forecast-cyan) 8%, transparent);
}

.forecast-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 30px;
  padding: 5px 12px;
  border: 1px solid var(--forecast-line-strong);
  border-radius: 999px;
  color: var(--forecast-muted);
  font-size: 12px;
  background: transparent;
  cursor: pointer;
  transition: color 120ms ease, border-color 120ms ease, background-color 120ms ease;
}

.forecast-btn:hover {
  color: var(--forecast-text);
  border-color: var(--forecast-muted);
}

.forecast-btn--on {
  border-color: var(--forecast-accent);
  color: var(--forecast-text);
  background: color-mix(in srgb, var(--forecast-accent) 12%, transparent);
}

/* ---------- 网格 ---------- */
.forecast-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 344px;
  gap: 16px;
  align-items: stretch;
}

.forecast-left-stack {
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  gap: 16px;
  min-width: 0;
}

.forecast-side {
  display: grid;
  gap: 16px;
  align-content: start;
}

.forecast-bottom-row {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
  gap: 16px;
  margin-top: 16px;
}

.forecast-card {
  border: 1px solid var(--forecast-line);
  border-radius: var(--forecast-radius);
  background: var(--forecast-card);
  overflow: hidden;
}

.forecast-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 13px 15px;
  border-bottom: 1px solid var(--forecast-line);
}

.forecast-card-head h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: .03em;
}

.forecast-card-en {
  display: block;
  margin-top: 4px;
  color: var(--forecast-muted);
  font: 8.5px var(--forecast-font-mono);
  letter-spacing: .2em;
}

.forecast-card-aside {
  color: var(--forecast-muted);
  font: 9.5px var(--forecast-font-mono);
  letter-spacing: .1em;
  white-space: nowrap;
}

.forecast-tag {
  padding: 2px 7px;
  border: 1px solid var(--forecast-line-strong);
  border-radius: 3px;
  color: var(--forecast-muted);
  font: 8px var(--forecast-font-mono);
  letter-spacing: .14em;
}

.forecast-tag--demo {
  border-color: color-mix(in srgb, var(--ds-semantic-warning) 45%, transparent);
  color: var(--forecast-warn);
}

/* ---------- 主图卡 ---------- */
.forecast-chart-card {
  display: flex;
  flex-direction: column;
  min-height: 460px;
}

.forecast-chart-wrap {
  position: relative;
  flex: 1;
  min-height: 400px;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.forecast-chart-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  border: 1px dashed var(--forecast-line);
  border-radius: var(--forecast-radius);
  color: var(--forecast-muted);
  font: 12px var(--forecast-font-mono);
  letter-spacing: .1em;
}

.forecast-chart-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: color-mix(in srgb, var(--forecast-bg) 92%, transparent);
  color: var(--forecast-muted);
  font-size: 13px;
  text-align: center;
}

.forecast-chart-empty p {
  margin: 0;
}

/* ---------- 残差卡 ---------- */
.forecast-residual-card {
  border-top: none;
}

.forecast-residual-inner {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 12px 15px;
  color: var(--forecast-muted);
  font: 10px var(--forecast-font-mono);
  letter-spacing: .08em;
}

.forecast-residual-placeholder {
  height: 44px;
  background: linear-gradient(90deg, var(--forecast-line) 1px, transparent 1px),
              linear-gradient(var(--forecast-line) 1px, transparent 1px);
  background-size: 8px 22px;
  border-radius: 4px;
  opacity: .4;
}

.forecast-residual-meta {
  text-align: right;
}

.forecast-residual-meta b {
  color: var(--forecast-text);
  font-weight: 500;
}

.forecast-residual-meta em {
  font-style: normal;
  color: var(--forecast-muted);
  font-size: 10px;
  margin-left: 4px;
}

/* ---------- 侧栏三卡 ---------- */
.forecast-side-card {
  /* 三卡高度由内容自然撑开，P2 调整内部布局 */
}

.forecast-placeholder-body {
  padding: 24px 15px;
  color: var(--forecast-muted);
  font: 11px var(--forecast-font-mono);
  letter-spacing: .1em;
  text-align: center;
}

/* ---------- 底部两栏 ---------- */
.forecast-bottom-card {
  min-height: 180px;
}

/* ---------- 页脚 ---------- */
.forecast-page-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--forecast-line);
  color: var(--forecast-muted);
  font: 9px var(--forecast-font-mono);
  letter-spacing: .12em;
}

.forecast-page-foot b {
  color: var(--forecast-text);
  font-weight: 500;
}

/* ---------- 断点 ---------- */
@media (max-width: 1180px) {
  .forecast-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .forecast-side {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .forecast-side > .forecast-side-card:last-child {
    grid-column: 1 / -1;
  }
}

@media (max-width: 900px) {
  .forecast-bottom-row {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 760px) {
  .forecast-plane {
    padding: 16px 14px 28px;
  }
  .forecast-page-head {
    grid-template-columns: minmax(0, 1fr);
  }
  .forecast-state-chips {
    justify-items: start;
  }
  .forecast-side {
    grid-template-columns: minmax(0, 1fr);
  }
  .forecast-chart-card {
    min-height: 340px;
  }
  .forecast-chart-wrap {
    min-height: 280px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .forecast-plane * {
    transition: none !important;
    animation: none !important;
  }
}
</style>
