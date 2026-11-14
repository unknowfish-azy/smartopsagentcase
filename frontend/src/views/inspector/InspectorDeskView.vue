<template>
  <div class="inspector-desk" :data-view="view">
    <header class="desk-header">
      <div>
        <p class="eyebrow">MEMORY · INSPECTOR DESK · 同一份证据的三种投影</p>
        <h1>洞察台</h1>
        <p class="lede">纠察中心、统计、运行记录不再是三个页面，而是同一条时间轴上的三种看法：点是纠察事件，柱是它的聚合，条是它落到的命令执行。切视图不换轴，选中不丢上下文，证据只在右下角一个抽屉里打开。</p>
      </div>
      <div class="desk-header-meta">
        <div class="window-switch" role="tablist" aria-label="时间窗">
          <button v-for="w in windows" :key="w" role="tab" :aria-selected="windowKey === w" @click="setWindow(w)">{{ w }}</button>
        </div>
        <p class="source"><span class="dot ok"></span>数据源 · {{ dataSourceLabel }}</p>
        <p class="demo-badge" v-if="demo">DEMO · 虚构示例，非真实纠察</p>
        <button class="demo-toggle" @click="toggleDemo">{{ demo ? '退出演示' : '查看演示数据' }}</button>
      </div>
    </header>

    <section class="projection-tabs" role="tablist" aria-label="投影">
      <button v-for="p in projections" :key="p.key" role="tab" :aria-selected="view === p.key" @click="setView(p.key)">
        <span>{{ p.cn }}</span>
        <small>{{ p.en }} · {{ p.desc }}</small>
      </button>
    </section>

    <section class="desk-toolbar">
      <div class="chips"><span class="chip-label">等级</span>
        <button class="chip" :class="{ active: severity === 'ALL' }" @click="setSeverity('ALL')">全部</button>
        <button v-for="s in severities" :key="s.key" class="chip" :class="{ active: severity === s.key }" @click="setSeverity(s.key)">{{ s.cn }}</button>
      </div>
      <div class="chips"><span class="chip-label">工具</span>
        <button class="chip" :class="{ active: tool === 'ALL' }" @click="setTool('ALL')">全部</button>
        <button v-for="t in tools" :key="t.key" class="chip" :class="{ active: tool === t.key }" @click="setTool(t.key)">{{ t.key.split('-')[0] }}</button>
      </div>
      <button class="chip linked-only" :class="{ active: linkedOnly }" @click="toggleLinkedOnly">只看已关联</button>
      <div class="window-summary">窗口 <strong>{{ windowSummary.events }}</strong> 条纠察 · <strong>{{ windowSummary.runs }}</strong> 条运行 · <strong>{{ windowSummary.linked }}</strong> 条已关联</div>
    </section>

    <div class="desk-body">
      <DeskAxis
        :view="view"
        :window-key="windowKey"
        :events="visibleEvents"
        :runs="visibleRuns"
        :range="range"
        :selected="selected"
        :events-status="eventsState.status"
        :runs-status="runsState.status"
        :events-error="eventsState.error"
        :runs-error="runsState.error"
        @select="selectItem"
        @retry="load"
      />

      <aside class="side">
        <DeskSelection :selected="selected" :link="selectedLink" />
        <DeskProjections :selected="selected" :link="selectedLink" :view="view" :stats-bin="selectedStatsBin" />
        <DeskTotals :stats="statsState.data" />
      </aside>
    </div>

    <DeskDrawer
      :open="drawerOpen"
      :tab="drawerTab"
      :selected="selected"
      @toggle="drawerOpen ? closeDrawer() : openDrawer()"
      @tab="setDrawerTab"
    />

    <footer class="desk-footer">
      <span>INSPECTOR DESK · MEMORY</span>
      <span>演示数据：确定性合成序列，不代表任何真实纠察或命令</span>
      <span>关联只在 traceId 命中时成立；未命中显示「未关联」，不做时间邻近猜测</span>
      <span>REDUCED MOTION · 关闭视图切换形变</span>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { useInspectorDesk } from '../../composables/useInspectorDesk'
import { SEVERITIES, TOOLS, binEvents } from '../../components/inspector/desk/deskModel'
import DeskAxis from '../../components/inspector/desk/DeskAxis.vue'
import DeskSelection from '../../components/inspector/desk/DeskSelection.vue'
import DeskProjections from '../../components/inspector/desk/DeskProjections.vue'
import DeskTotals from '../../components/inspector/desk/DeskTotals.vue'
import DeskDrawer from '../../components/inspector/desk/DeskDrawer.vue'

const desk = useInspectorDesk()
const {
  view, windowKey, severity, tool, linkedOnly, selected, selectedLink,
  drawerOpen, drawerTab, demo,
  eventsState, runsState, statsState,
  range, visibleEvents, visibleRuns, windowSummary,
  setView, setWindow, setSeverity, setTool, toggleLinkedOnly,
  selectItem, openDrawer, closeDrawer, setDrawerTab,
  toggleDemo, moveSelection, load
} = desk

const windows = ['24h', '7d', '30d']
const severities = SEVERITIES
const tools = TOOLS

const projections = [
  { key: 'events', cn: '纠察', en: 'INSPECTIONS', desc: '每个事件是一个点：等级 · 目标 · 时间' },
  { key: 'stats', cn: '统计', en: 'AGGREGATES', desc: '同一批事件按时间分箱堆叠，类别/目标另算' },
  { key: 'runs', cn: '运行', en: 'RUNS', desc: '命令执行是横条：工具 · 时长 · 退出码' }
]

const dataSourceLabel = computed(() => {
  if (demo.value) return '演示'
  if (eventsState.status === 'error' || runsState.status === 'error') return '部分失败'
  if (eventsState.status === 'loading') return '加载中'
  return '正常'
})

// 选中对象所在的统计分箱
const selectedStatsBin = computed(() => {
  if (!selected.value) return null
  const bins = binEvents(visibleEvents.value, windowKey.value, range.value.start, range.value.end)
  return bins.find(b => selected.value.at >= b.from && selected.value.at < b.to) || null
})

/* ---------- 键盘 ---------- */
function onKeydown(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
  if (e.key === '1') setView('events')
  else if (e.key === '2') setView('stats')
  else if (e.key === '3') setView('runs')
  else if (e.key === 'ArrowLeft') { e.preventDefault(); moveSelection(-1) }
  else if (e.key === 'ArrowRight') { e.preventDefault(); moveSelection(1) }
  else if (e.key === 'Enter') { if (selected.value) openDrawer() }
  else if (e.key === 'Escape') { closeDrawer(); desk.clearSelection() }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.inspector-desk {
  display: grid;
  gap: 16px;
  padding: 24px;
  color: #E8F2F7;
  background: #0E1116;
  min-height: 100%;
}
.desk-header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; }
.eyebrow { color: #7ad7f5; font-size: 11px; letter-spacing: .14em; margin: 0 0 8px; text-transform: uppercase; }
h1 { font-size: 40px; margin: 0 0 8px; font-weight: 700; }
.lede { max-width: 560px; color: #92A6B5; margin: 0; line-height: 1.6; font-size: 13px; }
.desk-header-meta { display: grid; gap: 8px; justify-items: end; }
.window-switch { display: flex; gap: 4px; background: #151A21; border: 1px solid #1E2630; border-radius: 8px; padding: 3px; }
.window-switch button { background: transparent; border: 0; color: #92A6B5; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.window-switch button[aria-selected="true"] { background: #1E5FA8; color: #fff; }
.source { color: #92A6B5; font-size: 12px; margin: 0; display: flex; align-items: center; gap: 6px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot.ok { background: #4ade80; }
.demo-badge { color: #e7c56d; border: 1px solid rgba(231,197,109,.3); padding: 4px 10px; border-radius: 6px; font-size: 12px; margin: 0; }
.demo-toggle { background: #151A21; border: 1px solid #1E2630; color: #92A6B5; padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }
.demo-toggle:hover { border-color: #1E5FA8; color: #E8F2F7; }

.projection-tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.projection-tabs button { text-align: left; background: #151A21; border: 1px solid #1E2630; border-radius: 10px; padding: 14px 16px; cursor: pointer; color: #92A6B5; }
.projection-tabs button[aria-selected="true"] { border-color: #1E5FA8; color: #E8F2F7; background: linear-gradient(145deg, #13233a, #0f1622); }
.projection-tabs span { display: block; font-size: 16px; font-weight: 600; margin-bottom: 4px; color: #E8F2F7; }
.projection-tabs small { color: #6B7D8C; font-size: 12px; }

.desk-toolbar { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
.chips { display: flex; gap: 6px; align-items: center; }
.chip-label { color: #6B7D8C; font-size: 12px; }
.chip { background: #151A21; border: 1px solid #1E2630; color: #92A6B5; padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }
.chip.active { border-color: #1E5FA8; color: #E8F2F7; }
.linked-only { background: transparent; }
.linked-only.active { border-color: #7ad7f5; color: #7ad7f5; }
.window-summary { margin-left: auto; color: #6B7D8C; font-size: 12px; }
.window-summary strong { color: #E8F2F7; }

.desk-body { display: grid; grid-template-columns: 1fr 344px; gap: 16px; align-items: stretch; }
.side { display: grid; gap: 12px; align-content: start; }

.desk-footer { display: flex; gap: 24px; flex-wrap: wrap; color: #465568; font-size: 11px; padding-top: 8px; }

@media (max-width: 1180px) {
  .desk-body { grid-template-columns: 1fr; }
  .side { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 760px) {
  .inspector-desk { padding: 16px; }
  h1 { font-size: 28px; }
  .desk-header { flex-direction: column; }
  .desk-header-meta { justify-items: start; }
  .projection-tabs { grid-template-columns: 1fr; }
  .side { grid-template-columns: 1fr; }
}
</style>
