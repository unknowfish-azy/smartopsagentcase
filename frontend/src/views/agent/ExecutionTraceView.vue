<template>
  <div ref="traceShellRef" class="trace-shell" :data-theme="resolvedTheme">
    <!-- 启佑风格背景层：粒子网络 + 极光光带 -->
    <CanvasAmbientField v-if="!isMobile" class="trace-ambient" :palette-root="traceShellRef" :star-multiplier="1.2" connect-particles :connect-max-dist="110" />
    <div v-if="!isMobile" class="trace-aurora" aria-hidden="true"></div>
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
import { resolvedTheme as _resolvedTheme } from '../../stores/theme.js'

const CanvasAmbientField = defineAsyncComponent(() => import('../../components/common/CanvasAmbientField.vue'))

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
    radial-gradient(ellipse at 80% 10%, rgba(122, 215, 245, .12) 0%, transparent 50%),
    radial-gradient(ellipse at 20% 90%, rgba(63, 185, 80, .08) 0%, transparent 50%),
    #040B16;
}
.trace-shell[data-theme='light'] {
  background:
    radial-gradient(ellipse at 80% 10%, rgba(26, 110, 154, .08) 0%, transparent 50%),
    radial-gradient(ellipse at 20% 90%, rgba(26, 127, 55, .05) 0%, transparent 50%),
    #EAF3FA;
}
.trace-ambient {
  position: absolute; inset: 0; z-index: 0; opacity: .38; pointer-events: none;
}
.trace-aurora {
  position: absolute; inset: 0; z-index: 0; pointer-events: none;
  background:
    radial-gradient(ellipse at 75% 15%, rgba(122, 215, 245, .18) 0%, transparent 45%),
    radial-gradient(ellipse at 30% 85%, rgba(63, 185, 80, .12) 0%, transparent 45%);
  filter: blur(24px);
  background-size: 240% 240%;
  animation: trace-drift 28s ease-in-out infinite alternate;
}
@keyframes trace-drift {
  0%   { background-position: 0% 0%, 100% 100%; transform: translate3d(0, 0, 0); }
  100% { background-position: 30% 10%, 70% 90%; transform: translate3d(-2%, 2%, 0); }
}
@media (prefers-reduced-motion: reduce) { .trace-aurora { animation: none; } }
.trace-mask {
  position: absolute; inset: 0; z-index: 0; pointer-events: none;
  background: radial-gradient(ellipse at center, transparent 40%, rgba(4, 11, 22, .55) 100%);
}
.trace-shell[data-theme='light'] .trace-mask {
  background: radial-gradient(ellipse at center, transparent 40%, rgba(234, 243, 250, .55) 100%);
}

/* === 主内容层 === */
.page {
  position: relative; z-index: 1;
  display: grid; gap: 18px;
  color: #E6EDF3;
}
.trace-shell[data-theme='light'] .page { color: #0C2535; }

/* === Header === */
header {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 24px 28px;
  background: rgba(16, 33, 55, .65);
  border: 1px solid rgba(122, 215, 245, .22);
  border-radius: 14px;
  backdrop-filter: blur(14px);
}
.trace-shell[data-theme='light'] header {
  background: rgba(255, 255, 255, .78);
  border-color: rgba(26, 110, 154, .18);
}
header h1 { font-size: 22px; margin: 0 0 4px; letter-spacing: .02em; }
header p { color: #8B98A5; font-size: 13px; margin: 0; }
.back-link {
  padding: 8px 16px; border-radius: 8px;
  background: rgba(122, 215, 245, .12);
  border: 1px solid rgba(122, 215, 245, .3);
  color: #7AD7F5; font-size: 13px; text-decoration: none;
  transition: background .2s;
}
.back-link:hover { background: rgba(122, 215, 245, .22); }

/* === 4 步骤时序卡 === */
.virtual-trace {
  padding: 28px;
  background: rgba(16, 33, 55, .55);
  border: 1px solid rgba(122, 215, 245, .22);
  border-radius: 14px;
  backdrop-filter: blur(14px);
}
.trace-shell[data-theme='light'] .virtual-trace {
  background: rgba(255, 255, 255, .72);
  border-color: rgba(26, 110, 154, .18);
}
.virtual-label { color: #E7C56D; font-size: 10px; letter-spacing: .18em; margin-bottom: 6px; }
.virtual-trace h2 { font-size: 18px; margin: 0 0 22px; }

.trace-steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 0; }
.trace-step {
  display: grid;
  grid-template-columns: 48px 18px 1fr auto;
  gap: 0; align-items: start;
  padding: 16px 0;
  border-top: 1px solid rgba(122, 215, 245, .12);
  position: relative;
}
.trace-index {
  font-family: 'SF Mono', Consolas, monospace;
  font-size: 13px; font-weight: 700;
  color: #7AD7F5; letter-spacing: .04em;
  padding-top: 2px;
}
.trace-shell[data-theme='light'] .trace-index { color: #1A6E9A; }

/* 时序连接竖线 */
.trace-connector {
  position: relative; width: 18px; height: 100%;
}
.trace-connector::before {
  content: ''; position: absolute;
  left: 6px; top: 0; bottom: -16px;
  width: 2px;
  background: rgba(122, 215, 245, .18);
}
.trace-step:last-child .trace-connector::before { bottom: 50%; }
.trace-connector[data-done='true']::before { background: linear-gradient(to bottom, #3FB950, rgba(122, 215, 245, .4)); }
/* 节点圆点 */
.trace-connector::after {
  content: ''; position: absolute;
  left: 2px; top: 6px;
  width: 10px; height: 10px; border-radius: 50%;
  background: #040B16;
  border: 2px solid rgba(122, 215, 245, .45);
  box-shadow: 0 0 8px rgba(122, 215, 245, .18);
}
.trace-step.done .trace-connector::after { background: #3FB950; border-color: #3FB950; box-shadow: 0 0 10px rgba(63, 185, 80, .5); }
.trace-step.check .trace-connector::after { background: #E7C56D; border-color: #E7C56D; box-shadow: 0 0 10px rgba(231, 197, 109, .5); }
.trace-step.pending .trace-connector::after { background: #040B16; border-color: rgba(107, 114, 128, .6); }

.trace-body { display: grid; gap: 4px; padding-top: 2px; }
.trace-body strong { font-size: 14px; font-weight: 600; color: #E6EDF3; }
.trace-shell[data-theme='light'] .trace-body strong { color: #0C2535; }
.trace-body small { font-size: 12px; color: #6B7280; }

.trace-status {
  font-family: 'SF Mono', Consolas, monospace;
  font-size: 11px; font-weight: 600;
  letter-spacing: .1em; text-transform: uppercase;
  padding: 4px 10px; border-radius: 6px;
  align-self: center;
}
.trace-step.done .trace-status { background: rgba(63, 185, 80, .15); color: #3FB950; }
.trace-step.check .trace-status { background: rgba(231, 197, 109, .15); color: #E7C56D; }
.trace-step.pending .trace-status { background: rgba(107, 114, 128, .15); color: #6B7280; }

.trace-empty-hint {
  margin-top: 20px; padding-top: 16px;
  border-top: 1px solid rgba(122, 215, 245, .1);
  text-align: center; color: #6B7280; font-size: 13px;
}

/* === 推理摘要卡 === */
.reasoning-card {
  padding: 20px 24px;
  background: rgba(16, 33, 55, .55);
  border: 1px solid rgba(122, 215, 245, .18);
  border-radius: 12px;
  backdrop-filter: blur(10px);
}
.trace-shell[data-theme='light'] .reasoning-card {
  background: rgba(255, 255, 255, .72);
  border-color: rgba(26, 110, 154, .14);
}
.reasoning-card h2 { font-size: 15px; margin: 0 0 10px; color: #7AD7F5; }
.reasoning-card p { margin: 0; color: #A0AEC0; font-size: 13px; line-height: 1.6; }

/* === 指标网格 === */
.grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
}
.grid article {
  padding: 16px;
  background: rgba(16, 33, 55, .5);
  border: 1px solid rgba(122, 215, 245, .15);
  border-radius: 10px;
  backdrop-filter: blur(10px);
}
.trace-shell[data-theme='light'] .grid article {
  background: rgba(255, 255, 255, .72);
  border-color: rgba(26, 110, 154, .14);
}
.grid span { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: #6B7280; }
.grid strong { display: block; margin-top: 8px; font-size: 14px; color: #E6EDF3; overflow-wrap: anywhere; }
.trace-shell[data-theme='light'] .grid strong { color: #0C2535; }

/* === 双栏 === */
.columns { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.columns section {
  padding: 20px 24px;
  background: rgba(16, 33, 55, .5);
  border: 1px solid rgba(122, 215, 245, .15);
  border-radius: 12px;
  backdrop-filter: blur(10px);
}
.trace-shell[data-theme='light'] .columns section {
  background: rgba(255, 255, 255, .72);
  border-color: rgba(26, 110, 154, .14);
}
.columns section h2 { font-size: 14px; margin: 0 0 12px; color: #7AD7F5; }

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
