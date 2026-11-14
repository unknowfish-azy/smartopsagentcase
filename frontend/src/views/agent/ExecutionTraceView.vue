<template>
  <div ref="traceShellRef" class="trace-shell" :data-theme="resolvedTheme">
    <!-- 启佑风格背景层：粒子网络（拉满强度） + 双层极光 + 流星 -->
    <CanvasAmbientField v-if="!isMobile" class="trace-ambient" :palette-root="traceShellRef" :star-multiplier="1.8" connect-particles :connect-max-dist="130" />
    <div v-if="!isMobile" class="trace-aurora" aria-hidden="true"></div>
    <MeteorShower v-if="!isMobile" class="trace-meteors" />
    <div class="trace-mask" aria-hidden="true"></div>

    <div class="page">
      <header>
        <div class="header-left">
          <h1>Execution Trace</h1>
          <p>只展示可审计 Reasoning Summary，不展示隐藏 Chain-of-Thought</p>
        </div>
        <RouterLink to="/agent" class="back-link">返回控制中心</RouterLink>
      </header>

      <el-alert v-if="error" :title="error" type="error" show-icon />

      <!-- 演示执行轨迹：4 步骤时序线（对齐 Trae Agent 截图） -->
      <section class="virtual-trace">
        <div class="virtual-label">PREVIEW DATA · VIRTUAL TRACE</div>
        <h2>演示执行轨迹</h2>
        <ol class="trace-steps">
          <li v-for="(step, idx) in virtualSteps" :key="step.name" class="trace-step" :class="{ active: step.status !== 'NOT RUN', done: step.status === 'DONE', check: step.status === 'CHECK', pending: step.status === 'NOT RUN' }">
            <span class="trace-index">{{ step.index }}</span>
            <div class="trace-connector" :data-done="idx < doneIndex"></div>
            <div class="trace-body">
              <strong>{{ step.name }}</strong>
              <small>{{ step.detail }}</small>
            </div>
            <span class="trace-status">{{ step.status }}</span>
          </li>
        </ol>
        <div class="trace-empty-hint" v-if="!loading && !event.id">未找到可展示的真实执行轨迹</div>
      </section>

      <template v-if="event.id">
        <InspectorTrace :event="event" />
        <section class="reasoning-card">
          <h2>Reasoning Summary</h2>
          <p>{{ event.metadata?.reasoningSummary || event.reason || 'N/A' }}</p>
        </section>
        <div class="grid">
          <article><span>Tool</span><strong>{{ event.metadata?.tool || 'N/A' }}</strong></article>
          <article><span>Evidence</span><strong>{{ event.evidence?.length ?? 0 }}</strong></article>
          <article><span>Risk</span><strong>{{ event.severity || 'N/A' }}</strong></article>
          <article><span>Approval</span><strong>{{ event.metadata?.approval || 'N/A' }}</strong></article>
          <article><span>Execution</span><strong>{{ event.metadata?.execution || 'N/A' }}</strong></article>
          <article><span>Verification</span><strong>{{ event.verification?.status || 'NOT RUN' }}</strong></article>
          <article><span>Inspector</span><strong>{{ event.status || 'N/A' }}</strong></article>
          <article><span>Human Review</span><strong>{{ event.requiresHuman ? 'REQUIRED' : 'NO' }}</strong></article>
        </div>
        <div class="columns">
          <section><h2>Evidence</h2><InspectorEvidence :evidence="event.evidence" /></section>
          <section><h2>Issues</h2><InspectorIssueList :issues="event.issues" /></section>
        </div>
      </template>

      <AppEmpty v-else-if="!loading" description="未找到可展示的真实执行轨迹" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, computed, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { getInspectorEvent, getInspectorEvents } from '../../api/inspector'
import AppEmpty from '../../components/common/AppEmpty.vue'
import InspectorTrace from '../../components/inspector/InspectorTrace.vue'
import InspectorEvidence from '../../components/inspector/InspectorEvidence.vue'
import InspectorIssueList from '../../components/inspector/InspectorIssueList.vue'
import { resolvedTheme as _resolvedTheme } from '../../theme.js'

const CanvasAmbientField = defineAsyncComponent(() => import('../../components/common/CanvasAmbientField.vue'))
const MeteorShower = defineAsyncComponent(() => import('../../components/common/MeteorShower.vue'))

const route = useRoute()
const event = ref({})
const loading = ref(true)
const error = ref('')
const traceShellRef = ref(null)

const resolvedTheme = computed(() => _resolvedTheme.value)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 1024)
function updateMobile() { isMobile.value = window.innerWidth < 1024 }

const virtualSteps = [
  { index: '01', name: 'Understand request', detail: 'Task intent parsed', status: 'DONE' },
  { index: '02', name: 'Collect evidence', detail: 'Read-only sources queried', status: 'DONE' },
  { index: '03', name: 'Risk gate', detail: 'Approval requirement evaluated', status: 'CHECK' },
  { index: '04', name: 'Verification', detail: 'Awaiting real execution result', status: 'NOT RUN' }
]
const doneIndex = computed(() => virtualSteps.findIndex(s => s.status === 'NOT RUN'))

onMounted(async () => {
  window.addEventListener('resize', updateMobile)
  try {
    let id = route.query.inspectionId
    if (!id) {
      const list = await getInspectorEvents(1)
      id = list.data?.[0]?.id
    }
    if (id) {
      const detail = await getInspectorEvent(id)
      event.value = detail.data || {}
    }
  } catch (e) {
    error.value = e.message || '轨迹加载失败'
  } finally {
    loading.value = false
  }
})
onBeforeUnmount(() => window.removeEventListener('resize', updateMobile))
</script>

<style scoped>
/* === 启佑风格：深星空底 + 粒子背景 === */
.trace-shell {
  position: relative;
  min-height: calc(100vh - 64px);
  padding: 32px 40px;
  overflow: hidden;
  background:
    radial-gradient(ellipse at 80% 10%, color-mix(in srgb, var(--smart-primary-strong) 12%, transparent) 0%, transparent 50%),
    radial-gradient(ellipse at 20% 90%, rgba(63, 185, 80, .08) 0%, transparent 50%),
    var(--ds-surface-base);
}
.trace-shell[data-theme='light'] {
  background:
    radial-gradient(ellipse at 80% 10%, rgba(26, 110, 154, .08) 0%, transparent 50%),
    radial-gradient(ellipse at 20% 90%, rgba(26, 127, 55, .05) 0%, transparent 50%),
    #EAF3FA;
}
.trace-ambient {
  position: absolute; inset: 0; z-index: 0; opacity: .48; pointer-events: none;
}
.trace-meteors {
  position: absolute; inset: 0; z-index: 0; opacity: .35; pointer-events: none;
}
.trace-aurora {
  position: absolute; inset: 0; z-index: 0; pointer-events: none;
  background:
    radial-gradient(ellipse at 75% 15%, color-mix(in srgb, var(--smart-primary-strong) 22%, transparent) 0%, transparent 45%),
    radial-gradient(ellipse at 30% 85%, rgba(63, 185, 80, .16) 0%, transparent 45%);
  filter: blur(24px);
  background-size: 240% 240%;
  animation: trace-drift 16s ease-in-out infinite alternate;
}
.trace-shell[data-theme='light'] .trace-aurora {
  background:
    radial-gradient(ellipse at 75% 15%, color-mix(in srgb, var(--smart-primary) 14%, transparent) 0%, transparent 45%),
    radial-gradient(ellipse at 30% 85%, rgba(26, 127, 55, .10) 0%, transparent 45%);
}
.trace-shell[data-theme='light'] .trace-aurora::after {
  background: radial-gradient(ellipse 30% 20% at 15% 50%, rgba(26, 110, 154, .22), transparent 70%);
}
/* 扫光球（和 LoginView 同构） */
.trace-aurora::after {
  content: ''; position: absolute; inset: 0;
  background: radial-gradient(ellipse 30% 20% at 15% 50%, rgba(122, 215, 245, .35), transparent 70%);
  filter: blur(18px);
  animation: trace-sweep 24s ease-in-out infinite;
}
/* drift 加速：原 22s → 16s，与步骤触发节奏同频（2.4s × 4 步 ≈ 9.6s，半周期对齐） */
@keyframes trace-drift {
  0%   { background-position: 0% 0%, 100% 100%; transform: translate3d(0, 0, 0); }
  100% { background-position: 30% 10%, 70% 90%; transform: translate3d(-2%, 2%, 0); }
}
@keyframes trace-sweep {
  0%, 100% { opacity: .55; transform: translate3d(0, 0, 0); }
  50%      { opacity: 1;    transform: translate3d(-8%, 4%, 0); }
}
@media (prefers-reduced-motion: reduce) { .trace-aurora, .trace-aurora::after { animation: none; } }
.trace-mask {
  position: absolute; inset: 0; z-index: 0; pointer-events: none;
  background: radial-gradient(ellipse at center, transparent 40%, rgba(4, 11, 22, .42) 100%);
}
.trace-shell[data-theme='light'] .trace-mask {
  background: radial-gradient(ellipse at center, transparent 40%, rgba(234, 243, 250, .42) 100%);
}

/* === 主内容层 === */
.page {
  position: relative; z-index: 1;
  display: grid; gap: 18px;
  color: var(--smart-text);
}

/* === Header === */
header {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 24px 28px;
  background: color-mix(in srgb, var(--smart-surface) 65%, transparent);
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 22%, transparent);
  border-radius: 14px;
  backdrop-filter: blur(14px);
}
header h1 { font-size: 22px; margin: 0 0 4px; letter-spacing: .02em; }
header p { color: var(--smart-muted); font-size: 13px; margin: 0; }
.back-link {
  padding: 8px 16px; border-radius: 8px;
  background: color-mix(in srgb, var(--smart-primary-strong) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 30%, transparent);
  color: var(--smart-primary-strong); font-size: 13px; text-decoration: none;
  transition: background .2s;
}
.back-link:hover { background: color-mix(in srgb, var(--smart-primary-strong) 22%, transparent); }

/* === 4 步骤时序卡 === */
.virtual-trace {
  padding: 28px;
  background: color-mix(in srgb, var(--smart-surface) 55%, transparent);
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 22%, transparent);
  border-radius: 14px;
  backdrop-filter: blur(14px);
}
.virtual-label { color: var(--ds-semantic-warning); font-size: 10px; letter-spacing: .18em; margin-bottom: 6px; }
.virtual-trace h2 { font-size: 18px; margin: 0 0 22px; }

.trace-steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 0; }
.trace-step {
  display: grid;
  grid-template-columns: 48px 18px 1fr auto;
  gap: 0; align-items: start;
  padding: 16px 0;
  border-top: 1px solid color-mix(in srgb, var(--smart-primary-strong) 12%, transparent);
  position: relative;
}
.trace-index {
  font-family: 'SF Mono', Consolas, monospace;
  font-size: 13px; font-weight: 700;
  color: var(--smart-primary-strong); letter-spacing: .04em;
  padding-top: 2px;
}

/* 时序连接竖线 + 数据流脉冲（从上往下流动的光点） */
.trace-connector {
  position: relative; width: 18px; height: 100%;
}
.trace-connector::before {
  content: ''; position: absolute;
  left: 6px; top: 0; bottom: -16px;
  width: 2px;
  background: color-mix(in srgb, var(--smart-primary-strong) 18%, transparent);
}
.trace-step:last-child .trace-connector::before { bottom: 50%; }
.trace-connector[data-done='true']::before { background: linear-gradient(to bottom, var(--ds-semantic-success), color-mix(in srgb, var(--smart-primary-strong) 40%, transparent)); }
/* 数据流脉冲光点（沿已完成步骤向下流） */
.trace-step.done .trace-connector::before,
.trace-step.check .trace-connector::before {
  box-shadow: inset 0 -10px 12px color-mix(in srgb, var(--ds-semantic-success) 80%, transparent);
}
.trace-step.done .trace-connector::before { animation: trace-pulse-flow 1.6s ease-in-out infinite; }
.trace-step.check .trace-connector::before { animation: trace-pulse-flow 2.2s ease-in-out infinite; }
@keyframes trace-pulse-flow {
  0%, 100% { box-shadow: inset 0 -14px 14px color-mix(in srgb, var(--ds-semantic-success) 0%, transparent); }
  50%      { box-shadow: inset 0 14px 14px color-mix(in srgb, var(--ds-semantic-success) 90%, transparent); }
}
/* 节点圆点（三级脉冲：接收→放大→发射） */
.trace-connector::after {
  content: ''; position: absolute;
  left: 2px; top: 6px;
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--ds-surface-base);
  border: 2px solid color-mix(in srgb, var(--smart-primary-strong) 45%, transparent);
  box-shadow: 0 0 8px color-mix(in srgb, var(--smart-primary-strong) 18%, transparent);
}
/* 三级脉冲：收到→放大→发射光环 */
.trace-step.done .trace-connector::after,
.trace-step.check .trace-connector::after {
  animation: trace-neuron 2.4s ease-in-out infinite;
}
@keyframes trace-neuron {
  0%, 100% { width: 10px; height: 10px; box-shadow: 0 0 6px currentColor, 0 0 0 0 currentColor; }
  30%      { width: 14px; height: 14px; box-shadow: 0 0 18px currentColor, 0 0 0 4px color-mix(in srgb, var(--ds-semantic-success) 35%, transparent); }
  60%      { width: 10px; height: 10px; box-shadow: 0 0 10px currentColor, 0 0 0 20px rgba(63, 185, 80, 0); }
}
.trace-step.done .trace-connector::after { background: var(--ds-semantic-success); border-color: var(--ds-semantic-success); color: var(--ds-semantic-success); }
.trace-step.check .trace-connector::after { background: var(--ds-semantic-warning); border-color: var(--ds-semantic-warning); color: var(--ds-semantic-warning); }
.trace-step.pending .trace-connector::after { background: var(--ds-surface-base); border-color: color-mix(in srgb, var(--smart-muted) 60%, transparent); }
@media (prefers-reduced-motion: reduce) {
  .trace-step.done .trace-connector::before, .trace-step.check .trace-connector::before { animation: none; }
  .trace-step.done .trace-connector::after, .trace-step.check .trace-connector::after { animation: none; }
}

.trace-body { display: grid; gap: 4px; padding-top: 2px; }
.trace-body strong { font-size: 14px; font-weight: 600; color: var(--smart-text); }
.trace-body small { font-size: 12px; color: var(--smart-muted); }

.trace-status {
  font-family: 'SF Mono', Consolas, monospace;
  font-size: 11px; font-weight: 600;
  letter-spacing: .1em; text-transform: uppercase;
  padding: 4px 10px; border-radius: 6px;
  align-self: center;
}
.trace-step.done .trace-status { background: color-mix(in srgb, var(--ds-semantic-success) 15%, transparent); color: var(--ds-semantic-success); }
.trace-step.check .trace-status { background: color-mix(in srgb, var(--ds-semantic-warning) 15%, transparent); color: var(--ds-semantic-warning); }
.trace-step.pending .trace-status { background: color-mix(in srgb, var(--smart-muted) 15%, transparent); color: var(--smart-muted); }

.trace-empty-hint {
  margin-top: 20px; padding-top: 16px;
  border-top: 1px solid rgba(122, 215, 245, .1);
  text-align: center; color: var(--smart-muted); font-size: 13px;
}

/* === 推理摘要卡：AI 推理输出感（呼吸 + 边框光流） === */
.reasoning-card {
  padding: 20px 24px;
  background: color-mix(in srgb, var(--smart-surface) 55%, transparent);
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 18%, transparent);
  border-radius: 12px;
  backdrop-filter: blur(10px);
  position: relative;
  overflow: hidden;
}
.reasoning-card::before {
  content: ''; position: absolute; inset: -1px; border-radius: 13px;
  background: linear-gradient(120deg, transparent 0%, color-mix(in srgb, var(--smart-primary-strong) 18%, transparent) 30%, color-mix(in srgb, var(--ds-semantic-success) 15%, transparent) 60%, transparent 100%);
  animation: trace-reason-flow 6s linear infinite;
  pointer-events: none;
}
.reasoning-card::after {
  content: ''; position: absolute; inset: 0; border-radius: 12px;
  background: inherit; z-index: -1;
}
@keyframes trace-reason-flow {
  0%   { background-position: 0% 0%; opacity: .7; }
  100% { background-position: 200% 0%; opacity: 1; }
}
.reasoning-card h2 { font-size: 15px; margin: 0 0 10px; color: var(--smart-primary-strong); position: relative; z-index: 1; }
.reasoning-card p { margin: 0; color: var(--smart-muted); font-size: 13px; line-height: 1.6; position: relative; z-index: 1; animation: trace-reason-breathe 4s ease-in-out infinite; }
@keyframes trace-reason-breathe {
  0%, 100% { opacity: 1; }
  50%      { opacity: .78; }
}

/* === 指标网格：实时脉冲（模拟传感器读数） === */
.grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
}
.grid article {
  padding: 16px;
  background: color-mix(in srgb, var(--smart-surface) 50%, transparent);
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 15%, transparent);
  border-radius: 10px;
  backdrop-filter: blur(10px);
  transition: border-color .3s;
}
.grid article:hover { border-color: color-mix(in srgb, var(--smart-primary-strong) 35%, transparent); }
.grid article:nth-child(1) strong { animation: trace-digit-pulse 3.6s ease-in-out infinite; animation-delay: 0s; }
.grid article:nth-child(2) strong { animation: trace-digit-pulse 3.6s ease-in-out infinite; animation-delay: .4s; }
.grid article:nth-child(3) strong { animation: trace-digit-pulse 3.6s ease-in-out infinite; animation-delay: .8s; }
.grid article:nth-child(4) strong { animation: trace-digit-pulse 3.6s ease-in-out infinite; animation-delay: 1.2s; }
.grid article:nth-child(5) strong { animation: trace-digit-pulse 3.6s ease-in-out infinite; animation-delay: 1.6s; }
.grid article:nth-child(6) strong { animation: trace-digit-pulse 3.6s ease-in-out infinite; animation-delay: 2.0s; }
.grid article:nth-child(7) strong { animation: trace-digit-pulse 3.6s ease-in-out infinite; animation-delay: 2.4s; }
.grid article:nth-child(8) strong { animation: trace-digit-pulse 3.6s ease-in-out infinite; animation-delay: 2.8s; }
@keyframes trace-digit-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  40%      { transform: scale(1.05); opacity: .85; }
  60%      { transform: scale(.97); opacity: 1; }
}
.grid span { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: var(--smart-muted); }
.grid strong { display: block; margin-top: 8px; font-size: 14px; color: var(--smart-text); overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }

/* === 双栏 === */
.columns { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.columns section {
  padding: 20px 24px;
  background: color-mix(in srgb, var(--smart-surface) 50%, transparent);
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 15%, transparent);
  border-radius: 12px;
  backdrop-filter: blur(10px);
}
.columns section h2 { font-size: 14px; margin: 0 0 12px; color: var(--smart-primary-strong); }

/* === 响应式 === */
@media (max-width: 1024px) {
  .trace-shell { padding: 20px; }
  .grid { grid-template-columns: repeat(2, 1fr); }
  .columns { grid-template-columns: 1fr; }
  .trace-step { grid-template-columns: 40px 14px 1fr auto; }
}
@media (max-width: 640px) {
  .trace-shell { padding: 16px; }
  header { flex-direction: column; gap: 16px; }
  .grid { grid-template-columns: 1fr 1fr; }
}
</style>
