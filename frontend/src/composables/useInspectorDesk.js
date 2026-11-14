/**
 * useInspectorDesk.js — 洞察台数据与状态层
 *
 * 职责：拉取 events / summary / statistics / runs，维护三态，
 *       同步 URL 深链，管理选中对象、时间窗、筛选。
 *
 * 设计约束：
 *   - 三个请求独立失败不互相影响（partial 状态）；
 *   - 窗口聚合由前端按分箱计算，statistics 接口只用于右栏全量统计；
 *   - 演示数据来自 deskModel.buildDemoData，不得写入持久化。
 */
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getInspectorEvents, getInspectorStatistics, getInspectorSummary } from '../api/inspector'
import { getOperationRuns } from '../api/operations.ts'
import {
  buildDemoData, eventsByTraceMap, filterEvents, filterRuns,
  linkState, linkStateRun, normalizeEvents, normalizeRuns,
  runsByTraceMap, windowRange
} from '../components/inspector/desk/deskModel'

const VIEWS = ['events', 'stats', 'runs']
const WINDOWS = ['24h', '7d', '30d']

export function useInspectorDesk() {
  const route = useRoute()
  const router = useRouter()

  const view = ref(parseView(route.query.view))
  const windowKey = ref(parseWindow(route.query.window))
  const severity = ref('ALL')
  const tool = ref('ALL')
  const linkedOnly = ref(false)
  const selectedId = ref(route.query.id || null)
  const drawerOpen = ref(false)
  const drawerTab = ref('evidence')
  const demo = ref(false)

  // 三态：每个数据源独立
  const eventsState = ref({ status: 'loading', data: [], error: '' })
  const runsState = ref({ status: 'loading', data: [], error: '' })
  const summaryState = ref({ status: 'loading', data: {}, error: '' })
  const statsState = ref({ status: 'loading', data: {}, error: '' })

  const range = computed(() => windowRange(windowKey.value))

  const runsByTrace = computed(() => runsByTraceMap(runsState.value.data))
  const eventsByTrace = computed(() => eventsByTraceMap(eventsState.value.data))

  const visibleEvents = computed(() => filterEvents(eventsState.value.data, {
    severity: severity.value, linkedOnly: linkedOnly.value, runsByTrace: runsByTrace.value
  }))
  const visibleRuns = computed(() => filterRuns(runsState.value.data, {
    tool: tool.value, linkedOnly: linkedOnly.value, eventsByTrace: eventsByTrace.value
  }))

  const selected = computed(() => {
    if (!selectedId.value) return null
    const ev = eventsState.value.data.find(e => e.id === selectedId.value)
    if (ev) return { __type: 'event', ...ev }
    const run = runsState.value.data.find(r => r.id === selectedId.value)
    if (run) return { __type: 'run', ...run }
    return null
  })

  const selectedLink = computed(() => {
    if (!selected.value) return null
    if (selected.value.__type === 'event') {
      return linkState(selected.value, runsByTrace.value)
    }
    return linkStateRun(selected.value, eventsByTrace.value)
  })

  const windowSummary = computed(() => ({
    events: visibleEvents.value.length,
    runs: visibleRuns.value.length,
    linked: visibleEvents.value.filter(e => e.traceId && runsByTrace.value.has(e.traceId)).length
  }))

  /* ---------- URL 同步 ---------- */

  let syncing = false
  function syncUrl() {
    if (syncing) return
    syncing = true
    const query = { ...route.query }
    query.view = view.value
    query.window = windowKey.value
    if (selectedId.value) query.id = selectedId.value
    else delete query.id
    router.replace({ query }).catch(() => {}).finally(() => { syncing = false })
  }

  watch([view, windowKey, selectedId], syncUrl)

  /* ---------- 取数 ---------- */

  let token = 0
  async function load() {
    const myToken = ++token
    const { start, end } = range.value

    if (demo.value) {
      const data = buildDemoData(windowKey.value)
      eventsState.value = { status: 'ready', data: data.events, error: '' }
      runsState.value = { status: 'ready', data: data.runs, error: '' }
      summaryState.value = { status: 'ready', data: {}, error: '' }
      statsState.value = { status: 'ready', data: buildDemoStats(), error: '' }
      return
    }

    // 三个请求独立，互不阻塞
    eventsState.value = { status: 'loading', data: eventsState.value.data, error: '' }
    runsState.value = { status: 'loading', data: runsState.value.data, error: '' }

    const params = new URLSearchParams()
    params.set('startedFrom', new Date(start).toISOString())
    params.set('startedTo', new Date(end).toISOString())
    params.set('pageSize', '100')

    try {
      const res = await getInspectorEvents(200)
      if (myToken !== token) return
      const list = Array.isArray(res?.data) ? res.data : (Array.isArray(res) ? res : [])
      eventsState.value = { status: 'ready', data: normalizeEvents(list), error: '' }
    } catch (err) {
      if (myToken !== token) return
      eventsState.value = { status: 'error', data: [], error: err.message || '纠察事件加载失败' }
    }

    try {
      const res = await getOperationRuns({ startedFrom: new Date(start).toISOString(), startedTo: new Date(end).toISOString(), pageSize: 100 })
      if (myToken !== token) return
      const items = res?.data?.items || res?.items || (Array.isArray(res?.data) ? res.data : [])
      runsState.value = { status: 'ready', data: normalizeRuns(items), error: '' }
    } catch (err) {
      if (myToken !== token) return
      runsState.value = { status: 'error', data: [], error: err.message || '运行记录加载失败' }
    }

    try {
      const res = await getInspectorSummary()
      if (myToken !== token) return
      summaryState.value = { status: 'ready', data: res?.data || {}, error: '' }
    } catch (err) {
      if (myToken !== token) return
      summaryState.value = { status: 'error', data: {}, error: err.message || '' }
    }

    try {
      const res = await getInspectorStatistics()
      if (myToken !== token) return
      statsState.value = { status: 'ready', data: res?.data || {}, error: '' }
    } catch (err) {
      if (myToken !== token) return
      statsState.value = { status: 'error', data: {}, error: err.message || '' }
    }
  }

  function buildDemoStats() {
    return { byCategory: { DATABASE: 16, CLOUD_NATIVE: 17, OBSERVABILITY: 20, STABILITY: 11 } }
  }

  /* ---------- 操作 ---------- */

  function setView(v) {
    if (!VIEWS.includes(v)) return
    view.value = v
  }

  function setWindow(w) {
    if (!WINDOWS.includes(w)) return
    windowKey.value = w
    selectedId.value = null
    drawerOpen.value = false
    load()
  }

  function setSeverity(s) { severity.value = s }
  function setTool(t) { tool.value = t }
  function toggleLinkedOnly() { linkedOnly.value = !linkedOnly.value }

  function selectItem(item) {
    if (!item || item.__type === 'bin') return
    selectedId.value = item.id
  }

  function clearSelection() {
    selectedId.value = null
    drawerOpen.value = false
  }

  function openDrawer() { drawerOpen.value = true }
  function closeDrawer() { drawerOpen.value = false }
  function setDrawerTab(t) { drawerTab.value = t }

  function toggleDemo() {
    demo.value = !demo.value
    load()
  }

  /* ---------- 键盘：←/→ 移动选中 ---------- */

  function moveSelection(dir) {
    const items = view.value === 'runs' ? visibleRuns.value : visibleEvents.value
    if (!items.length) return
    let idx = items.findIndex(item => item.id === selectedId.value)
    if (idx < 0) idx = dir > 0 ? -1 : items.length
    idx = Math.max(0, Math.min(items.length - 1, idx + dir))
    selectedId.value = items[idx].id
  }

  onMounted(load)
  onBeforeUnmount(() => { token++ })

  /* ---------- traceId 深链：数据就绪后自动定位关联对象 ---------- */
  let traceLinkApplied = false
  watch([eventsState, runsState], () => {
    if (traceLinkApplied) return
    if (eventsState.value.status !== 'ready' || runsState.value.status !== 'ready') return
    const traceId = route.query.traceId
    if (!traceId) return
    // 优先选中同 trace 的运行，其次事件
    const run = runsState.value.data.find(r => r.traceId === traceId)
    if (run) {
      selectedId.value = run.id
      view.value = 'runs'
    } else {
      const event = eventsState.value.data.find(e => e.traceId === traceId)
      if (event) {
        selectedId.value = event.id
        view.value = 'events'
      }
    }
    traceLinkApplied = true
  })

  return {
    // 状态
    view, windowKey, severity, tool, linkedOnly, selectedId, selected, selectedLink,
    drawerOpen, drawerTab, demo,
    eventsState, runsState, summaryState, statsState,
    range, visibleEvents, visibleRuns, windowSummary,
    runsByTrace, eventsByTrace,
    // 操作
    setView, setWindow, setSeverity, setTool, toggleLinkedOnly,
    selectItem, clearSelection, openDrawer, closeDrawer, setDrawerTab,
    toggleDemo, moveSelection, load
  }
}

function parseView(v) {
  return VIEWS.includes(v) ? v : 'events'
}
function parseWindow(w) {
  return WINDOWS.includes(w) ? w : '24h'
}
