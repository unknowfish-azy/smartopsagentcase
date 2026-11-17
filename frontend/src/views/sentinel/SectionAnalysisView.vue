<template>
  <div class="section-plane" :data-state="dataState">
    <!-- 页头 -->
    <header class="sp-page-head">
      <div>
        <p class="sp-eyebrow">COMPARATIVE ANALYSIS · 多测点对比 · 引擎传感器</p>
        <h1>断面对比</h1>
        <p class="sp-lede">
          把多个传感器测点的读数换算成"相对基线带宽的偏移 %"后叠加在同一时间轴上，横向比较各测点的离散落差与风险分级。纵轴是无量纲偏移而非原始读数；分级只描述当前状态，越界处置仍走告警与工单链路。
        </p>
      </div>
      <div class="sp-state-chips">
        <span class="sp-chip">
          <i class="sp-chip__dot sp-chip__dot--live"></i>
          数据流 <b>{{ dataState === 'live' ? '正常' : dataState === 'demo' ? '演示' : '离线' }}</b>
        </span>
        <span class="sp-chip">窗口 <b>{{ windowSec }}s</b> · 测点 <b>{{ selectedSensors.length }}</b></span>
        <span v-if="dataState === 'demo'" class="sp-chip sp-chip--demo">
          DEMO · 虚构示例，非真实读数
        </span>
        <span v-else class="sp-chip">
          MODE {{ dataState.toUpperCase() }}
        </span>
      </div>
    </header>

    <!-- 工具栏：测点多选 + 窗口 -->
    <section class="sp-toolbar" role="toolbar" aria-label="断面对比工具栏">
      <div class="sp-tool" role="group" aria-label="参与对比的测点">
        <span>测点</span>
        <div class="sp-sensors">
          <button
            v-for="s in allSensors"
            :key="s.key"
            type="button"
            class="sp-sensor"
            :aria-pressed="selectedKeys.includes(s.key)"
            @click="toggleSensor(s.key)"
          >{{ s.en }}</button>
        </div>
      </div>
      <div class="sp-tool" role="group" aria-label="历史窗口">
        <span>窗口</span>
        <div class="sp-seg">
          <button
            v-for="w in [60, 120, 240]"
            :key="w"
            type="button"
            class="sp-seg__btn"
            :aria-pressed="windowSec === w"
            @click="windowSec = w"
          >{{ w }}s</button>
        </div>
      </div>
      <button type="button" class="sp-btn" @click="retry">刷新</button>
    </section>

    <!-- 主体网格 -->
    <div class="sp-grid">
      <!-- 左：主图 -->
      <section class="sp-card sp-chart-card" aria-labelledby="sp-chart-title">
        <header class="sp-card-head">
          <div>
            <h2 id="sp-chart-title">偏移叠加 · {{ selectedSensors.map(s => s.en).join(' / ') || '未选择' }}</h2>
            <span class="sp-card-en">OVERLAY · NORMALIZED OFFSET %</span>
          </div>
          <span class="sp-card-aside">窗口 −{{ windowSec }}s → 现在 · 纵轴：相对基线带宽 %</span>
        </header>
        <div class="sp-chart-wrap">
          <SectionOverlayChart
            v-if="selectedSensors.length"
            :sensors="selectedSensors"
            :series="payload?.series || {}"
            :generated-at="generatedAt"
            :window-sec="windowSec"
          />
          <div v-else class="sp-chart-placeholder">未选择测点</div>
          <div v-if="dataState === 'offline'" class="sp-chart-empty">
            <p>后端接口未就绪，无法获取实时数据。</p>
            <button type="button" class="sp-btn" @click="useDemo">查看演示数据集</button>
          </div>
        </div>
      </section>

      <!-- 右：读数汇总 -->
      <section class="sp-card sp-side-card" aria-labelledby="sp-snap-title">
        <header class="sp-card-head">
          <div>
            <h2 id="sp-snap-title">读数汇总</h2>
            <span class="sp-card-en">SNAPSHOT · RAW + OFFSET</span>
          </div>
          <span v-if="dataState === 'demo'" class="sp-tag sp-tag--demo">DEMO</span>
        </header>
        <div class="sp-snap-body">
          <div v-for="row in snapshots" :key="row.key" class="sp-snap-row">
            <span class="sp-snap-name"><b>{{ row.en }}</b><small>{{ row.cn }}</small></span>
            <span class="sp-snap-value">{{ row.value == null ? '—' : row.value.toLocaleString('zh-CN', { minimumFractionDigits: row.digits, maximumFractionDigits: row.digits }) }} <small>{{ row.unit }}</small></span>
            <span class="sp-snap-offset">{{ row.offset == null ? '—' : `${row.offset > 0 ? '+' : ''}${row.offset}%` }}</span>
            <span class="sp-snap-grade" :class="`sp-grade--${row.grade}`">{{ gradeLabel(row.grade) }}</span>
          </div>
          <p v-if="!snapshots.length" class="sp-empty">—</p>
        </div>
      </section>
    </div>

    <!-- 底部两栏：离散落差 + 分级评价 -->
    <div class="sp-bottom-row">
      <section class="sp-card sp-bottom-card" aria-labelledby="sp-spread-title">
        <header class="sp-card-head">
          <div>
            <h2 id="sp-spread-title">离散落差</h2>
            <span class="sp-card-en">SPREAD · PEAK |OFFSET| PER SENSOR</span>
          </div>
          <span v-if="dataState === 'demo'" class="sp-tag sp-tag--demo">DEMO</span>
        </header>
        <div class="sp-spread-wrap">
          <SectionSpread :rows="spreadRows" />
        </div>
      </section>

      <section class="sp-card sp-bottom-card" aria-labelledby="sp-grade-title">
        <header class="sp-card-head">
          <div>
            <h2 id="sp-grade-title">分级评价</h2>
            <span class="sp-card-en">GRADES · OK / WATCH / WARN / CRIT</span>
          </div>
          <span v-if="dataState === 'demo'" class="sp-tag sp-tag--demo">DEMO</span>
        </header>
        <SectionGrades :rows="snapshots" />
      </section>
    </div>

    <!-- 页脚 -->
    <footer class="sp-page-foot">
      <span>SECTION ANALYSIS · SENTINEL</span>
      <span>{{ dataState === 'demo' ? '演示数据：曲线为确定性合成序列，属虚构示例，不代表任何真实发动机' : '数据来自接口' }}</span>
      <span>偏移 % · 事实：分级不触发处置，越界人工确认后走告警链路</span>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { SENSORS, getSensor } from '../../domain/forecast/syntheticSeries.js'
import { gradeAt, peakOffset, sensorSnapshot } from '../../domain/sections/sectionSeries.js'
import { useSectionSeries } from '../../composables/useSectionSeries.js'
import SectionOverlayChart from '../../components/sections/SectionOverlayChart.vue'
import SectionSpread from '../../components/sections/SectionSpread.vue'
import SectionGrades from '../../components/sections/SectionGrades.vue'

const allSensors = SENSORS

const {
  state: dataState,
  payload,
  selected,
  windowSec,
  useDemo,
  retry,
  boot
} = useSectionSeries({ selected: ['ect', 'egt', 'oilp'], windowSec: 120 })

const selectedKeys = computed(() => selected.value)
const selectedSensors = computed(() => selected.value.map(k => getSensor(k)).filter(Boolean))
const generatedAt = computed(() => payload.value?.generatedAtSec || Math.floor(Date.now() / 1000))

const snapshots = computed(() => {
  // G6：offline（payload 为 null）显示 —，不推导、不编造
  if (!payload.value) return []
  if (payload.value.snapshots?.length) return payload.value.snapshots
  // live 数据缺 snapshots 字段时按窗口实时推导（确定性，不编造）
  return selectedSensors.value.map(s => sensorSnapshot(s, generatedAt.value))
})

const spreadRows = computed(() => {
  const keys = selectedKeys.value
  if (!keys.length || !payload.value?.series) return []
  const series = payload.value.series
  const t1 = generatedAt.value
  const t0 = t1 - windowSec.value
  const peaks = keys.map(key => {
    const sensor = getSensor(key)
    const pts = series[key] || []
    // 优先用返回序列直接算峰值（不额外采样，保持与图一致）
    let peak = 0
    for (const p of pts) peak = Math.max(peak, Math.abs(p.o))
    if (!pts.length) peak = peakOffset(sensor, t0, t1)
    return { key, cn: sensor.cn, en: sensor.en, peak, grade: gradeAt(sensor, t1) }
  })
  return peaks.sort((a, b) => b.peak - a.peak)
})

const GRADE_LABELS = { ok: '正常', watch: '注意', warn: '预警', crit: '严重' }
function gradeLabel(grade) { return GRADE_LABELS[grade] || '—' }

function toggleSensor(key) {
  const idx = selected.value.indexOf(key)
  if (idx >= 0) {
    if (selected.value.length > 1) selected.value = selected.value.filter(k => k !== key)
  } else {
    selected.value = [...selected.value, key]
  }
}

onMounted(() => { boot() })
</script>

<style scoped>
.section-plane {
  --sp-bg: var(--ds-surface-base, var(--smart-bg));
  --sp-card: var(--ds-surface-raised, var(--smart-card));
  --sp-line: var(--ds-hairline, var(--smart-border));
  --sp-line-strong: var(--ds-color-border-strong, var(--smart-border-strong));
  --sp-text: var(--ds-color-text, var(--smart-text));
  --sp-muted: var(--ds-color-muted, var(--smart-muted));
  --sp-accent: var(--ds-color-primary, var(--smart-primary));
  --sp-cyan: var(--ds-color-primary-strong, var(--smart-primary-strong));
  --sp-ok: var(--ds-semantic-success, var(--smart-success));
  --sp-warn: var(--ds-semantic-warning);
  --sp-bad: var(--ds-semantic-danger);
  --sp-radius: var(--ds-radius-md, 8px);
  --sp-font-mono: Consolas, 'Cascadia Mono', ui-monospace, monospace;

  min-height: 100%;
  padding: 22px 24px 40px;
  background: var(--sp-bg);
  color: var(--sp-text);
  box-sizing: border-box;
  /* G8：零 backdrop-filter、零粒子、零极光叠加 */
}

/* ---------- 页头 ---------- */
.sp-page-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: end;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--sp-line);
  margin-bottom: 18px;
}

.sp-eyebrow {
  margin: 0 0 10px;
  color: var(--sp-cyan);
  font: 10px var(--sp-font-mono);
  letter-spacing: .22em;
  text-transform: uppercase;
}

.sp-page-head h1 {
  margin: 0;
  font-size: clamp(28px, 3.2vw, 42px);
  font-weight: 500;
  letter-spacing: .01em;
  line-height: 1.05;
}

.sp-lede {
  max-width: 70ch;
  margin: 12px 0 0;
  color: var(--sp-muted);
  font-size: 13px;
  line-height: 1.8;
}

.sp-state-chips {
  display: grid;
  gap: 6px;
  justify-items: end;
  min-width: 220px;
}

.sp-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 10px;
  border: 1px solid var(--sp-line-strong);
  border-radius: 999px;
  color: var(--sp-muted);
  font: 10px var(--sp-font-mono);
  letter-spacing: .08em;
  white-space: nowrap;
}

.sp-chip b {
  color: var(--sp-text);
  font-weight: 500;
}

.sp-chip--demo {
  border-color: color-mix(in srgb, var(--sp-warn) 50%, transparent);
  color: var(--sp-warn);
}

.sp-chip__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.sp-chip__dot--live {
  background: var(--sp-ok);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--sp-ok) 16%, transparent);
}

/* ---------- 工具栏 ---------- */
.sp-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 18px;
  padding: 14px 0;
  border-bottom: 1px solid var(--sp-line);
  margin-bottom: 18px;
}

.sp-tool {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sp-tool > span {
  color: var(--sp-muted);
  font: 9.5px var(--sp-font-mono);
  letter-spacing: .14em;
}

.sp-seg {
  display: inline-flex;
  border: 1px solid var(--sp-line-strong);
  border-radius: 999px;
  overflow: hidden;
}

.sp-seg__btn {
  padding: 5px 11px;
  color: var(--sp-muted);
  font: 11px var(--sp-font-mono);
  letter-spacing: .06em;
  background: transparent;
  border: 0;
  cursor: pointer;
  transition: color 120ms ease, background-color 120ms ease;
}

.sp-seg__btn + .sp-seg__btn {
  border-left: 1px solid var(--sp-line);
}

.sp-seg__btn[aria-pressed="true"] {
  background: color-mix(in srgb, var(--sp-accent) 16%, transparent);
  color: var(--sp-text);
}

.sp-sensors {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sp-sensor {
  padding: 4px 9px;
  border: 1px solid var(--sp-line);
  border-radius: 4px;
  color: var(--sp-muted);
  font: 10.5px var(--sp-font-mono);
  letter-spacing: .05em;
  background: transparent;
  cursor: pointer;
  transition: color 120ms ease, border-color 120ms ease, background-color 120ms ease;
}

.sp-sensor[aria-pressed="true"] {
  border-color: var(--sp-cyan);
  color: var(--sp-text);
  background: color-mix(in srgb, var(--sp-cyan) 8%, transparent);
}

.sp-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 30px;
  padding: 5px 12px;
  border: 1px solid var(--sp-line-strong);
  border-radius: 999px;
  color: var(--sp-muted);
  font-size: 12px;
  background: transparent;
  cursor: pointer;
  transition: color 120ms ease, border-color 120ms ease, background-color 120ms ease;
}

.sp-btn:hover {
  color: var(--sp-text);
  border-color: var(--sp-muted);
}

/* ---------- 网格 ---------- */
.sp-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 344px;
  gap: 16px;
  align-items: stretch;
}

.sp-bottom-row {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
  gap: 16px;
  margin-top: 16px;
}

.sp-card {
  border: 1px solid var(--sp-line);
  border-radius: var(--sp-radius);
  background: var(--sp-card);
  overflow: hidden;
}

.sp-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 13px 15px;
  border-bottom: 1px solid var(--sp-line);
}

.sp-card-head h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: .03em;
}

.sp-card-en {
  display: block;
  margin-top: 4px;
  color: var(--sp-muted);
  font: 8.5px var(--sp-font-mono);
  letter-spacing: .2em;
}

.sp-card-aside {
  color: var(--sp-muted);
  font: 9.5px var(--sp-font-mono);
  letter-spacing: .1em;
  white-space: nowrap;
}

.sp-tag {
  padding: 2px 7px;
  border: 1px solid var(--sp-line-strong);
  border-radius: 3px;
  color: var(--sp-muted);
  font: 8px var(--sp-font-mono);
  letter-spacing: .14em;
}

.sp-tag--demo {
  border-color: color-mix(in srgb, var(--sp-warn) 45%, transparent);
  color: var(--sp-warn);
}

/* ---------- 主图卡 ---------- */
.sp-chart-card {
  display: flex;
  flex-direction: column;
  min-height: 460px;
}

.sp-chart-wrap {
  position: relative;
  flex: 1;
  min-height: 400px;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.sp-chart-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  border: 1px dashed var(--sp-line);
  border-radius: var(--sp-radius);
  color: var(--sp-muted);
  font: 12px var(--sp-font-mono);
  letter-spacing: .1em;
}

.sp-chart-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: color-mix(in srgb, var(--sp-bg) 92%, transparent);
  color: var(--sp-muted);
  font-size: 13px;
  text-align: center;
}

.sp-chart-empty p { margin: 0; }

/* ---------- 读数汇总 ---------- */
.sp-snap-body {
  display: grid;
  gap: 10px;
  padding: 14px 15px;
}

.sp-snap-row {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr) auto auto;
  gap: 10px;
  align-items: center;
  padding: 8px 10px;
  border: 1px solid var(--sp-line);
  border-radius: 6px;
}

.sp-snap-name { display: grid; line-height: 1.25; }
.sp-snap-name b {
  font: 11px var(--sp-font-mono);
  letter-spacing: .05em;
}
.sp-snap-name small {
  font: 9px var(--sp-font-mono);
  color: var(--sp-muted);
}

.sp-snap-value {
  font: 13px var(--sp-font-mono);
  text-align: right;
}
.sp-snap-value small { color: var(--sp-muted); font-size: 10px; }

.sp-snap-offset {
  font: 11px var(--sp-font-mono);
  color: var(--sp-cyan);
  min-width: 5em;
  text-align: right;
}

.sp-snap-grade {
  font: 10px var(--sp-font-mono);
  letter-spacing: .08em;
  min-width: 3em;
  text-align: right;
}

.sp-grade--ok { color: var(--sp-ok); }
.sp-grade--watch { color: var(--sp-accent); }
.sp-grade--warn { color: var(--sp-warn); }
.sp-grade--crit { color: var(--sp-bad); }

.sp-empty {
  margin: 0;
  color: var(--sp-muted);
  font: 11px var(--sp-font-mono);
  text-align: center;
}

/* ---------- 底部 ---------- */
.sp-bottom-card { min-height: 180px; }

.sp-spread-wrap {
  height: 150px;
  padding: 10px 12px;
}

/* ---------- 页脚 ---------- */
.sp-page-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--sp-line);
  color: var(--sp-muted);
  font: 9px var(--sp-font-mono);
  letter-spacing: .12em;
}

/* ---------- 断点 ---------- */
@media (max-width: 1180px) {
  .sp-grid { grid-template-columns: minmax(0, 1fr); }
}

@media (max-width: 900px) {
  .sp-bottom-row { grid-template-columns: minmax(0, 1fr); }
}

@media (max-width: 760px) {
  .section-plane { padding: 16px 14px 28px; }
  .sp-page-head { grid-template-columns: minmax(0, 1fr); }
  .sp-state-chips { justify-items: start; }
  .sp-chart-card { min-height: 340px; }
  .sp-chart-wrap { min-height: 280px; }
}

@media (prefers-reduced-motion: reduce) {
  .section-plane * {
    transition: none !important;
    animation: none !important;
  }
}
</style>
