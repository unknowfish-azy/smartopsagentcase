<template>
  <div ref="shellRef" class="eo-shell" :data-theme="resolvedTheme" :data-state="obs.state.value">
    <div class="eo-mask" aria-hidden="true"></div>

    <section class="eo-surface" aria-labelledby="eo-title">
      <!-- 页头 -->
      <header class="eo-head">
        <div class="eo-head-main">
          <p class="eo-eyebrow">ENGINE OBSERVABILITY · 真实事件聚合 · 无事件静默</p>
          <h1 id="eo-title">引擎可观测</h1>
          <p class="eo-lede">
            每条流水线每时每刻在做什么，一屏摊开。所有状态来自真实运行记录，
            <b>无事件即静默</b>——"摸鱼"= 距上次心跳超过该引擎的预期周期，详情可自行核对。
            模型训练无真实事件源，如实标记为未运行，不造假。
          </p>
        </div>
        <div class="eo-head-side">
          <span class="eo-chip" :class="`eo-chip--${obs.state.value}`">
            <i class="eo-dot"></i>
            {{ obs.state.value === 'live' ? '实时' : obs.state.value === 'offline' ? '离线' : '加载中' }}
          </span>
          <span class="eo-chip eo-chip--mute">更新 {{ obs.generatedAtText.value }}</span>
          <button type="button" class="eo-btn" :disabled="obs.state.value === 'loading'" @click="reload">
            {{ obs.state.value === 'loading' ? '载入中' : '刷新' }}
          </button>
        </div>
      </header>

      <!-- 离线 / 加载 态 -->
      <div v-if="obs.state.value === 'offline'" class="eo-empty" role="status">
        <div class="eo-empty-mark">—</div>
        <h2>后端遥测不可用</h2>
        <p>未取到任何引擎快照。本页只展示真实数据，不会用演示数据冒充实况。</p>
        <p class="eo-empty-reason" v-if="obs.errorReason.value">原因：{{ obs.errorReason.value }}</p>
        <button type="button" class="eo-btn eo-btn--primary" @click="reload">重试</button>
      </div>

      <div v-else-if="obs.state.value === 'loading'" class="eo-empty" role="status">
        <div class="eo-empty-mark eo-empty-mark--pulse">·</div>
        <h2>正在读取引擎遥测</h2>
        <p>聚合 6 张真实事件表，请稍候。</p>
      </div>

      <template v-else>
        <!-- 概览条 -->
        <div class="eo-summary" aria-label="引擎状态概览">
          <span v-for="item in summaryItems" :key="item.key" class="eo-summary-item">
            <i class="eo-dot" :class="`eo-dot--${item.key}`"></i>
            {{ item.label }} <b>{{ item.count }}</b>
          </span>
          <span class="eo-summary-note">心跳阈值由后端引擎目录下发，前端不硬编码</span>
        </div>

        <!-- 3D 引擎场：六节点绑真实心跳，无事件静默（详见 engine-observability-3d-v1/DESIGN.md） -->
        <EngineField3D
          :engines="obs.engines.value"
          :selected-id="obs.selectedEngine.value"
          :generated-at-text="obs.generatedAtText.value"
          :narrow="isNarrow"
          @select="obs.selectEngine"
        />

        <!-- 引擎卡片网格（Bento） -->
        <section class="eo-grid" aria-label="引擎状态卡">
          <article
            v-for="eng in obs.engines.value"
            :key="eng.id"
            class="eo-card"
            :class="[
              `eo-card--${statusKey(eng.status)}`,
              { 'eo-card--selected': obs.selectedEngine.value === eng.id }
            ]"
            @click="obs.selectEngine(eng.id)"
          >
            <header class="eo-card-head">
              <div class="eo-card-title">
                <i class="eo-dot" :class="`eo-dot--${statusKey(eng.status)}`"></i>
                <h2>{{ eng.name }}</h2>
              </div>
              <span class="eo-card-id">{{ eng.id }}</span>
            </header>

            <div class="eo-card-status">
              <span class="eo-status-label" :class="`eo-status-label--${statusKey(eng.status)}`">
                {{ statusLabel(eng.status) }}
              </span>
              <span v-if="eng.status === 'NOT_RUN'" class="eo-card-silent">无事件源 · 静默</span>
            </div>

            <p class="eo-card-detail">{{ eng.detail || '—' }}</p>

            <dl class="eo-card-metrics">
              <div>
                <dt>距上次心跳</dt>
                <dd>{{ eng.status === 'NO_DATA' || eng.status === 'NOT_RUN' ? '—' : formatAge(eng.ageSec) }}</dd>
              </div>
              <div>
                <dt>预期周期</dt>
                <dd>{{ eng.expectedPeriodSec > 0 ? eng.expectedPeriodSec + 's' : '—' }}</dd>
              </div>
              <div>
                <dt>真实事件</dt>
                <dd>{{ eng.eventCount }}</dd>
              </div>
            </dl>

            <footer class="eo-card-foot">
              <span class="eo-card-last">最近：{{ eng.lastEventSummary }}</span>
              <time v-if="eng.lastEventAtText !== '—'">{{ eng.lastEventAtText }}</time>
            </footer>
          </article>
        </section>

        <!-- 中部：真实事件时间轴 -->
        <section class="eo-panel eo-timeline-panel" aria-labelledby="eo-tl-title">
          <header class="eo-panel-head">
            <div>
              <h2 id="eo-tl-title">真实事件时间轴</h2>
              <span class="eo-panel-en">EVENT TIMELINE · REAL RECORDS ONLY</span>
            </div>
            <span class="eo-panel-aside">{{ obs.events.value.length }} 条</span>
          </header>
          <div class="eo-timeline-wrap">
            <canvas ref="timelineCanvas" class="eo-timeline-canvas" aria-hidden="true"></canvas>
            <div v-if="!obs.events.value.length" class="eo-timeline-empty">
              当前窗口无真实事件 · 静默（不伪造心跳）
            </div>
            <div v-else class="eo-timeline-legend">
              <span v-for="eng in obs.engines.value.filter(e => e.eventCount > 0)" :key="eng.id">
                <i :style="{ background: statusColor(eng.status) }"></i>{{ eng.name }}
              </span>
            </div>
          </div>
        </section>

        <!-- 底部：选中引擎的事件表格 -->
        <section class="eo-panel eo-events-panel" aria-labelledby="eo-ev-title">
          <header class="eo-panel-head">
            <div>
              <h2 id="eo-ev-title">事件明细 · {{ obs.selected.value?.name || '—' }}</h2>
              <span class="eo-panel-en">EVENT STREAM · MOST RECENT FIRST</span>
            </div>
            <a v-if="engineHref" class="eo-link" :href="engineHref">在原生页面查看 →</a>
          </header>
          <div v-if="obs.eventLoading.value" class="eo-events-empty">读取事件…</div>
          <div v-else-if="!obs.events.value.length" class="eo-events-empty">该引擎暂无真实事件记录。</div>
          <div v-else class="eo-table-scroll">
            <table class="eo-table">
              <thead>
                <tr><th>时间</th><th>类型 / 状态</th><th>摘要</th></tr>
              </thead>
              <tbody>
                <tr v-for="(ev, i) in obs.events.value" :key="i">
                  <td class="eo-mono">{{ formatEventTime(ev.at) }}</td>
                  <td><span class="eo-kind" :class="kindClass(ev.kind)">{{ ev.kind }}</span></td>
                  <td>{{ ev.summary }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>

      <!-- 页脚 -->
      <footer class="eo-foot">
        <span>ENGINE OBSERVABILITY · SENTINEL</span>
        <span>全真实事件 · 无事件静默 · training 未运行不造假</span>
        <span>REDUCED MOTION · {{ reducedMotion ? '静态单帧' : '克制动效' }}</span>
      </footer>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import EngineField3D from '../../components/sentinel/EngineField3D.vue'
import { useEngineObservability } from '../../composables/useEngineObservability.js'
import { resolvedTheme } from '../../theme.js'

const shellRef = ref(null)
const timelineCanvas = ref(null)
const obs = useEngineObservability()
const reducedMotion = ref(false)
const isNarrow = ref(false)
let resizeObserver = null

const summaryItems = computed(() => {
  const counts = { running: 0, stalled: 0, error: 0, nodata: 0, notrun: 0 }
  for (const e of obs.engines.value) {
    const k = statusKey(e.status)
    if (k in counts) counts[k] += 1
  }
  return [
    { key: 'running', label: '运行中', count: counts.running },
    { key: 'stalled', label: '疑似停摆', count: counts.stalled },
    { key: 'error', label: '异常', count: counts.error },
    { key: 'nodata', label: '无数据', count: counts.nodata },
    { key: 'notrun', label: '未运行', count: counts.notrun }
  ]
})

const engineHref = computed(() => {
  const map = {
    'sentinel-poll': '/sentinel',
    'sentinel-guardian': '/sentinel/guardian',
    'web-research': '/research',
    inspector: '/inspector',
    'decision-loop': '/agent/loops',
    'operation-run': '/operations/runs'
  }
  return map[obs.selectedEngine.value] || null
})

function statusKey(status) {
  return String(status || '').toLowerCase().replace(/_/g, '')
}

function statusLabel(status) {
  return {
    RUNNING: '运行中', STALLED: '疑似停摆', ERROR: '异常',
    NO_DATA: '无数据', NOT_RUN: '未运行'
  }[status] || status
}

function statusColor(status) {
  return {
    RUNNING: 'var(--ds-color-success, #5ad691)',
    STALLED: 'var(--ds-semantic-warning, #e3a008)',
    ERROR: 'var(--ds-semantic-danger, #e5484d)',
    NO_DATA: 'var(--ds-color-muted, #8a8f98)',
    NOT_RUN: 'var(--ds-color-muted, #8a8f98)'
  }[status] || 'var(--ds-color-muted, #8a8f98)'
}

function kindClass(kind) {
  const v = String(kind || '').toUpperCase()
  if (v.includes('FAIL') || v.includes('ERROR') || v.includes('TIMEOUT')) return 'eo-kind--bad'
  if (v.includes('WARN') || v.includes('STALL')) return 'eo-kind--warn'
  return 'eo-kind--ok'
}

function formatAge(sec) {
  if (sec == null || Number.isNaN(sec)) return '—'
  if (sec < 60) return sec + 's'
  if (sec < 3600) return Math.floor(sec / 60) + 'm ' + (sec % 60) + 's'
  return Math.floor(sec / 3600) + 'h ' + Math.floor((sec % 3600) / 60) + 'm'
}

function formatEventTime(epoch) {
  if (epoch == null) return '—'
  try {
    return new Date(epoch * 1000).toLocaleString('zh-CN', { hour12: false })
  } catch { return '—' }
}

/** Canvas 时间轴：每条真实事件一个点，横轴按时间比例；无事件不画。 */
function drawTimeline() {
  const canvas = timelineCanvas.value
  if (!canvas) return
  const wrap = canvas.parentElement
  const dpr = window.devicePixelRatio || 1
  const w = Math.max(1, wrap.clientWidth - 32)
  const h = Math.max(1, wrap.clientHeight - 20)
  canvas.width = w * dpr
  canvas.height = h * dpr
  canvas.style.width = w + 'px'
  canvas.style.height = h + 'px'
  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)
  if (!ctx || !obs.events.value.length) return

  const styles = getComputedStyle(shellRef.value)
  const grid = styles.getPropertyValue('--ds-hairline').trim() || 'rgba(127,127,127,.2)'
  ctx.strokeStyle = grid
  ctx.lineWidth = 1
  // 基线 + 三条刻度
  const baseY = h - 18
  ctx.beginPath(); ctx.moveTo(8, baseY); ctx.lineTo(w - 8, baseY); ctx.stroke()
  for (let i = 0; i <= 4; i++) {
    const x = 8 + ((w - 16) * i) / 4
    ctx.beginPath(); ctx.moveTo(x, baseY - 4); ctx.lineTo(x, baseY + 4); ctx.stroke()
  }

  const evs = obs.events.value.filter(e => e.at != null)
  if (!evs.length) return
  const min = Math.min(...evs.map(e => e.at))
  const max = Math.max(...evs.map(e => e.at))
  const span = Math.max(1, max - min)
  const color = statusColor(obs.selected.value?.status)

  evs.forEach((ev, i) => {
    const x = 8 + ((ev.at - min) / span) * (w - 16)
    const lane = i % 3
    const y = baseY - 22 - lane * 16
    ctx.strokeStyle = grid
    ctx.beginPath(); ctx.moveTo(x, baseY); ctx.lineTo(x, y + 5); ctx.stroke()
    ctx.fillStyle = color
    ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill()
  })
}

function reload() {
  obs.fetchSnapshot().then(drawTimeline)
}

function updateNarrow() {
  isNarrow.value = window.innerWidth <= 760
}

onMounted(() => {
  try { reducedMotion.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch { /* SSR */ }
  updateNarrow()
  window.addEventListener('resize', updateNarrow)
  obs.fetchSnapshot().then(drawTimeline)
  obs.startPolling()
  if (typeof ResizeObserver !== 'undefined' && timelineCanvas.value) {
    resizeObserver = new ResizeObserver(() => drawTimeline())
    resizeObserver.observe(timelineCanvas.value.parentElement)
  }
})

watch(() => [obs.events.value.length, obs.selectedEngine.value], () => {
  requestAnimationFrame(drawTimeline)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateNarrow)
  obs.dispose()
  resizeObserver?.disconnect()
})
</script>

<style scoped>
.eo-shell {
  --eo-bg: var(--ds-surface-base, var(--smart-bg));
  --eo-card: var(--ds-surface-raised, var(--smart-card));
  --eo-line: var(--ds-hairline, var(--smart-border));
  --eo-line-strong: var(--ds-color-border-strong, var(--smart-border-strong));
  --eo-text: var(--ds-color-text, var(--smart-text));
  --eo-muted: var(--ds-color-muted, var(--smart-muted));
  --eo-accent: var(--ds-color-primary, var(--smart-primary));
  --eo-ok: var(--ds-color-success, var(--smart-success));
  --eo-warn: var(--ds-semantic-warning);
  --eo-bad: var(--ds-semantic-danger);
  --eo-mono: Consolas, 'Cascadia Mono', ui-monospace, monospace;
  position: relative;
  min-height: 100%;
  padding: 22px 24px 40px;
  background: var(--eo-bg);
  color: var(--eo-text);
  box-sizing: border-box;
  overflow: hidden;
}
.eo-mask { position: absolute; inset: 0; background: linear-gradient(180deg, transparent, color-mix(in srgb, var(--eo-bg) 72%, transparent)); pointer-events: none; }
.eo-surface { position: relative; z-index: 1; }

.eo-head { display: flex; justify-content: space-between; gap: 20px; align-items: flex-end; padding-bottom: 18px; border-bottom: 1px solid var(--eo-line); margin-bottom: 18px; }
.eo-eyebrow { margin: 0 0 10px; color: var(--eo-accent); font: 10px var(--eo-mono); letter-spacing: .2em; text-transform: uppercase; }
.eo-head h1 { margin: 0; font-size: clamp(26px, 3vw, 38px); font-weight: 500; letter-spacing: .01em; }
.eo-lede { max-width: 74ch; margin: 10px 0 0; color: var(--eo-muted); font-size: 12.5px; line-height: 1.75; }
.eo-lede b { color: var(--eo-text); font-weight: 500; }
.eo-head-side { display: grid; gap: 7px; justify-items: end; min-width: 190px; }
.eo-chip { display: inline-flex; align-items: center; gap: 7px; padding: 5px 11px; border: 1px solid var(--eo-line-strong); border-radius: 999px; color: var(--eo-muted); font: 10px var(--eo-mono); letter-spacing: .08em; white-space: nowrap; }
.eo-chip--live .eo-dot { background: var(--eo-ok); }
.eo-chip--offline .eo-dot { background: var(--eo-bad); }
.eo-chip--loading .eo-dot { background: var(--eo-warn); }
.eo-chip--mute { border-style: dashed; }
.eo-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; display: inline-block; flex: none; }
.eo-dot--running { background: var(--eo-ok); }
.eo-dot--stalled { background: var(--eo-warn); }
.eo-dot--error { background: var(--eo-bad); }
.eo-dot--nodata, .eo-dot--notrun { background: var(--eo-muted); }
.eo-btn { padding: 6px 14px; border: 1px solid var(--eo-line-strong); border-radius: 999px; background: transparent; color: var(--eo-muted); font-size: 12px; cursor: pointer; transition: color 120ms ease, border-color 120ms ease; }
.eo-btn:hover:not(:disabled) { color: var(--eo-text); border-color: var(--eo-muted); }
.eo-btn:disabled { opacity: .5; cursor: default; }
.eo-btn--primary { border-color: var(--eo-accent); color: var(--eo-text); }

.eo-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; min-height: 380px; text-align: center; color: var(--eo-muted); }
.eo-empty-mark { font: 40px var(--eo-mono); color: var(--eo-line-strong); }
.eo-empty-mark--pulse { animation: eoPulse 1.4s ease-in-out infinite; }
@keyframes eoPulse { 0%,100% { opacity: .35; } 50% { opacity: 1; } }
.eo-empty h2 { margin: 0; font-size: 17px; font-weight: 500; color: var(--eo-text); }
.eo-empty p { margin: 0; font-size: 13px; }
.eo-empty-reason { font: 11px var(--eo-mono); color: var(--eo-bad); }

.eo-summary { display: flex; flex-wrap: wrap; gap: 10px 22px; align-items: center; padding: 12px 0 18px; }
.eo-summary-item { display: inline-flex; align-items: center; gap: 7px; color: var(--eo-muted); font-size: 12px; }
.eo-summary-item b { color: var(--eo-text); font-weight: 500; font-family: var(--eo-mono); }
.eo-summary-note { margin-left: auto; color: var(--eo-muted); font: 9.5px var(--eo-mono); letter-spacing: .08em; opacity: .75; }

.eo-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(258px, 1fr)); gap: 14px; }
.eo-card { display: flex; flex-direction: column; gap: 11px; padding: 15px; border: 1px solid var(--eo-line); border-radius: var(--ds-radius-md, 8px); background: var(--eo-card); cursor: pointer; transition: border-color 140ms ease, background-color 140ms ease; }
.eo-card:hover { border-color: var(--eo-line-strong); }
.eo-card--selected { border-color: var(--eo-accent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--eo-accent) 30%, transparent); }
.eo-card--stalled { animation: eoBreath 2.6s ease-in-out infinite; }
@keyframes eoBreath { 0%,100% { border-color: var(--eo-line); } 50% { border-color: color-mix(in srgb, var(--eo-warn) 55%, transparent); } }
.eo-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.eo-card-title { display: inline-flex; align-items: center; gap: 8px; }
.eo-card-title h2 { margin: 0; font-size: 14px; font-weight: 500; }
.eo-card-id { color: var(--eo-muted); font: 8.5px var(--eo-mono); letter-spacing: .06em; }
.eo-card-status { display: flex; align-items: center; gap: 10px; }
.eo-status-label { font: 11px var(--eo-mono); letter-spacing: .05em; }
.eo-status-label--running { color: var(--eo-ok); }
.eo-status-label--stalled { color: var(--eo-warn); }
.eo-status-label--error { color: var(--eo-bad); }
.eo-status-label--nodata, .eo-status-label--notrun { color: var(--eo-muted); }
.eo-card-silent { color: var(--eo-muted); font: 9px var(--eo-mono); }
.eo-card-detail { margin: 0; min-height: 32px; color: var(--eo-muted); font-size: 11.5px; line-height: 1.55; }
.eo-card-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 0; padding-top: 10px; border-top: 1px solid var(--eo-line); }
.eo-card-metrics div { min-width: 0; }
.eo-card-metrics dt { color: var(--eo-muted); font: 9px var(--eo-mono); letter-spacing: .04em; }
.eo-card-metrics dd { margin: 4px 0 0; color: var(--eo-text); font: 13px var(--eo-mono); }
.eo-card-foot { display: flex; justify-content: space-between; gap: 8px; color: var(--eo-muted); font: 9px var(--eo-mono); }
.eo-card-last { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.eo-card-foot time { flex: none; }

.eo-panel { margin-top: 16px; border: 1px solid var(--eo-line); border-radius: var(--ds-radius-md, 8px); background: var(--eo-card); overflow: hidden; }
.eo-panel-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 13px 15px; border-bottom: 1px solid var(--eo-line); }
.eo-panel-head h2 { margin: 0; font-size: 14px; font-weight: 500; }
.eo-panel-en { display: block; margin-top: 4px; color: var(--eo-muted); font: 8.5px var(--eo-mono); letter-spacing: .18em; }
.eo-panel-aside { color: var(--eo-muted); font: 9.5px var(--eo-mono); }
.eo-link { color: var(--eo-accent); font: 11px var(--eo-mono); text-decoration: none; }
.eo-link:hover { text-decoration: underline; }
.eo-timeline-wrap { position: relative; min-height: 150px; padding: 10px 16px; }
.eo-timeline-canvas { display: block; }
.eo-timeline-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--eo-muted); font: 11px var(--eo-mono); letter-spacing: .06em; }
.eo-timeline-legend { display: flex; flex-wrap: wrap; gap: 8px 16px; margin-top: 8px; color: var(--eo-muted); font: 9.5px var(--eo-mono); }
.eo-timeline-legend span { display: inline-flex; align-items: center; gap: 6px; }
.eo-timeline-legend i { width: 7px; height: 7px; border-radius: 50%; }
.eo-events-empty { padding: 28px 15px; text-align: center; color: var(--eo-muted); font-size: 12px; }
.eo-table-scroll { overflow-x: auto; }
.eo-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.eo-table th { text-align: left; padding: 9px 15px; color: var(--eo-muted); font: 9px var(--eo-mono); letter-spacing: .12em; border-bottom: 1px solid var(--eo-line); }
.eo-table td { padding: 9px 15px; border-bottom: 1px solid var(--eo-line); color: var(--eo-text); }
.eo-table tbody tr:last-child td { border-bottom: 0; }
.eo-mono { font-family: var(--eo-mono); color: var(--eo-muted); font-size: 11px; }
.eo-kind { display: inline-block; padding: 2px 7px; border-radius: 3px; font: 9px var(--eo-mono); letter-spacing: .06em; border: 1px solid var(--eo-line-strong); }
.eo-kind--ok { color: var(--eo-ok); }
.eo-kind--warn { color: var(--eo-warn); }
.eo-kind--bad { color: var(--eo-bad); }

.eo-foot { display: flex; flex-wrap: wrap; gap: 8px 20px; justify-content: space-between; margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--eo-line); color: var(--eo-muted); font: 9px var(--eo-mono); letter-spacing: .1em; }

@media (max-width: 760px) {
  .eo-shell { padding: 16px 14px 28px; }
  .eo-head { flex-direction: column; align-items: flex-start; }
  .eo-head-side { justify-items: start; }
  .eo-grid { grid-template-columns: minmax(0, 1fr); }
  .eo-summary-note { margin-left: 0; width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  .eo-shell * { animation: none !important; transition: none !important; }
}
</style>
