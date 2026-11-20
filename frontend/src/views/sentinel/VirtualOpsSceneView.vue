<template>
  <div class="vos-page">
    <header class="vos-head">
      <div>
        <p class="eyebrow">SENTINEL · VIRTUAL OPS SANDBOX · 3D</p>
        <h1>虚拟运维场景</h1>
        <p class="lede">
          在 3D 虚拟环境里还原机房与网络拓扑（机柜 / 交换机 / 路由器 / 网关 / 链路），
          选择一个可能失误的运维操作，系统确定性地推演其级联后果并预测影响面与 SLA 风险。
          <b>数据为演示虚拟数据</b>，仅用于演练与风险教育，不作为真实变更决策依据。
        </p>
      </div>
      <div class="vos-head__right">
        <span class="vos-badge vos-badge--demo">预测态 · 演示数据</span>
        <span class="vos-badge vos-badge--mode" :title="'当前视觉模式：' + visualModeLabel">{{ visualModeLabel }}</span>
      </div>
    </header>

    <div class="vos-grid" :class="{ 'vos-grid--narrow': narrow }">
      <!-- 3D 舞台 -->
      <section class="vos-stage" aria-label="虚拟运维三维场景">
        <VirtualOpsScene3D
          :topology="topology"
          :snapshot="currentSnapshot"
          :predictions="assetPredictions"
          :target-id="selectedOp?.targetId || ''"
          :selected-asset-id="selectedAssetId"
          :narrow="narrow"
          @select="selectAsset"
          @focus-prediction="focusPrediction"
        />
        <!-- 画布内前向预测横幅：操作执行瞬间即给出整段推演的峰值后果 -->
        <div v-if="summary" class="vos-stage__forecast" role="status" aria-live="polite">
          <span class="vos-stage__forecast-kicker">后果预测 · 峰值</span>
          <span class="vos-stage__forecast-row">
            最高 <b :class="`sev-${summary.maxSeverity}`">{{ summary.maxSeverityLabel }}</b>
            · SLA <b :class="`risk-${summary.slaRisk}`">{{ summary.slaRiskLabel }}</b>
            · 预估中断 <b>{{ summary.estimatedOutageMinutes }}</b> 分
            · 受影响业务 <b>{{ summary.affectedServiceCount }}</b>
          </span>
          <span v-if="assetPredictions.length" class="vos-stage__forecast-sub">
            {{ assetPredictions.length }} 个资产将受影响，悬浮于 3D 资产上方
          </span>
        </div>
        <div v-if="selectedOp" class="vos-stage__target">
          <span class="vos-stage__target-kicker">目标资产</span>
          <strong>{{ selectedOp.targetId }}</strong>
          <em>{{ selectedOp.cn }}</em>
        </div>
        <div v-else class="vos-stage__empty">
          <p>从右侧选择一个「失误操作」，观察虚拟环境里的级联后果预测</p>
        </div>
      </section>

      <!-- 侧栏：操作目录 + 后果预测 -->
      <aside class="vos-side">
        <article class="vos-card">
          <h2>失误操作目录</h2>
          <p class="vos-card__sub">点击任一操作，立即推演未来 {{ horizon }} 步的级联后果</p>
          <div class="vos-horizon">
            <label for="vos-horizon" class="vos-horizon__label">推演步数</label>
            <input
              id="vos-horizon"
              type="range"
              min="8"
              max="40"
              step="1"
              :value="horizon"
              class="vos-range vos-range--sm"
              aria-label="推演步数"
              :aria-valuetext="`${horizon} 步`"
              @input="setHorizon(($event.target).value)"
            />
            <span class="vos-horizon__val">{{ horizon }} 步</span>
          </div>
          <div class="vos-catalog">
            <div v-for="group in groups" :key="group.kind" class="vos-catalog__group">
              <h3>{{ group.cn }}</h3>
              <button
                v-for="op in group.items"
                :key="op.id"
                type="button"
                class="vos-op"
                :class="{ 'is-active': op.id === selectedOperationId }"
                :aria-pressed="op.id === selectedOperationId ? 'true' : 'false'"
                @click="chooseOperation(op.id)"
              >
                <span class="vos-op__head">
                  <span class="vos-op__cn">{{ op.cn }}</span>
                  <span class="vos-op__risk" :class="`is-${op.risk}`">{{ op.risk === 'high' ? '高风险' : '中风险' }}</span>
                </span>
                <span class="vos-op__en">{{ op.label }} · 目标 {{ op.targetId }}</span>
              </button>
            </div>
          </div>
        </article>

        <article v-if="selectedOp" class="vos-card vos-card--op">
          <h2>操作说明</h2>
          <p class="vos-op-desc">{{ selectedOp.description }}</p>
          <p class="vos-op-brief"><b>可能后果：</b>{{ selectedOp.consequenceBrief }}</p>
        </article>

        <article v-if="summary" class="vos-card">
          <h2>后果预测摘要</h2>
          <div class="vos-kpis">
            <div class="vos-kpi">
              <span class="vos-kpi__v" :class="severityClass(summary.maxSeverity)">{{ summary.maxSeverityLabel }}</span>
              <span class="vos-kpi__k">最高严重度</span>
            </div>
            <div class="vos-kpi">
              <span class="vos-kpi__v" :class="`risk-${summary.slaRisk}`">{{ summary.slaRiskLabel }}</span>
              <span class="vos-kpi__k">SLA 风险</span>
            </div>
            <div class="vos-kpi">
              <span class="vos-kpi__v">{{ summary.estimatedOutageMinutes }}<small>分</small></span>
              <span class="vos-kpi__k">预估中断时长</span>
            </div>
            <div class="vos-kpi">
              <span class="vos-kpi__v">{{ summary.affectedServiceCount }}</span>
              <span class="vos-kpi__k">受影响业务</span>
            </div>
          </div>
          <div v-if="summary.intermittent" class="vos-intermittent">
            <span class="vos-intermittent__dot"></span>间歇性故障：奇数步劣化、偶数步恢复，影响面按整段推演统计
          </div>
          <dl class="vos-stats">
            <div><dt>受影响机柜</dt><dd>{{ summary.affectedRackCount }}</dd></div>
            <div><dt>中断机柜</dt><dd>{{ summary.downRacks }}</dd></div>
            <div v-if="summary.intermittent"><dt>抖动链路</dt><dd>{{ summary.flappingLinksCount }}</dd></div>
            <div v-if="summary.intermittent"><dt>抖动路由器</dt><dd>{{ summary.flappingRoutersCount }}</dd></div>
            <div><dt>受影响网络设备</dt><dd>{{ summary.affectedNetworkCount }}</dd></div>
            <div><dt>中断链路</dt><dd>{{ summary.downLinks }}</dd></div>
            <div><dt>中断业务</dt><dd>{{ summary.downServices }}</dd></div>
            <div><dt>推演步数</dt><dd>{{ summary.horizon }}</dd></div>
          </dl>
          <div v-if="servicePredictions.length" class="vos-svc">
            <h4>受影响业务（预测峰值）</h4>
            <ul class="vos-svc__list">
              <li v-for="s in servicePredictions" :key="s.id">
                <span class="vos-svc__dot" :style="{ background: STATUS_COLORS[s.worstStatus], boxShadow: '0 0 6px ' + STATUS_COLORS[s.worstStatus] }"></span>
                <span class="vos-svc__name">{{ s.label }}</span>
                <span class="vos-svc__crit" :class="`is-${s.criticality}`">{{ criticalityLabel(s.criticality) }}</span>
                <span class="vos-svc__peak" :class="severityClass(s.worstStatus)">预测将{{ STATUS_LABELS[s.worstStatus] }}</span>
                <span class="vos-svc__tick">T+{{ s.firstBadTick }}</span>
              </li>
            </ul>
          </div>
          <div class="vos-advice">
            <h4>规避建议</h4>
            <p>{{ summary.recommendation }}</p>
          </div>
        </article>

        <article v-if="summary && summary.cascadingSteps.length" class="vos-card">
          <h2>级联步骤（预测）</h2>
          <ol class="vos-steps">
            <li
              v-for="(step, i) in summary.cascadingSteps"
              :key="i"
              :class="{ 'is-future': step.tick > playhead }"
            >
              <span class="vos-steps__tick">T+{{ step.tick }}</span>
              <span class="vos-steps__text">{{ step.text }}</span>
            </li>
          </ol>
        </article>
      </aside>
    </div>

    <!-- 底部时间线 -->
    <div class="vos-timeline" v-if="prediction">
      <div class="vos-timeline__controls">
        <button type="button" class="vos-btn" @click="toggle">{{ playing ? '暂停' : (atEnd ? '重播' : '播放') }}</button>
        <button type="button" class="vos-btn vos-btn--ghost" @click="reset">重置</button>
        <button type="button" class="vos-btn vos-btn--ghost" @click="exportReport">导出 Markdown</button>
        <button type="button" class="vos-btn vos-btn--ghost" @click="exportHtmlReport">导出 HTML</button>
        <button type="button" class="vos-btn vos-btn--ghost" @click="printReport">打印 / PDF</button>
      </div>
      <div class="vos-timeline__track">
        <input
          type="range"
          :min="0"
          :max="prediction.timeline.length - 1"
          step="1"
          :value="playhead"
          class="vos-range"
          aria-label="预测时间线"
          :aria-valuetext="timelineValueText"
          @input="seek(($event.target).value)"
        />
        <div class="vos-timeline__marks">
          <span v-for="m in timelineMarks" :key="m" :class="{ 'is-current': m === playhead }">T+{{ m }}</span>
        </div>
      </div>
      <div class="vos-timeline__frame">
        <span class="vos-timeline__tick">T+{{ playhead }} / {{ prediction.timeline.length - 1 }}</span>
        <span class="vos-timeline__live" :class="{ 'is-storm': currentSnapshot?.broadcastStorm }">
          {{ currentSnapshot?.broadcastStorm ? '广播风暴扩散中' : (playing ? '推演播放中' : '已暂停') }}
        </span>
      </div>
    </div>

    <!-- 底部信息条：三态 + 当前帧最热机柜 + 选中资产 -->
    <footer class="vos-foot">
      <div class="vos-foot__states">
        <span class="vos-state is-on" title="当前为预测推演结果">预测态</span>
        <span class="vos-state" title="未发生任何操作的全健康基线">基线态</span>
        <span class="vos-state is-off" title="演示页未接入真实监控">实测态</span>
      </div>
      <div class="vos-foot__hot">
        <span class="vos-foot__label">当前帧最热机柜</span>
        <div class="vos-hot">
          <span v-for="r in frameHot" :key="r.id" :class="`is-${r.status}`" :title="`${r.label} ${r.temp}°C`">
            {{ r.label }} {{ r.temp }}°
          </span>
        </div>
      </div>
      <div class="vos-foot__asset" v-if="selectedAssetId">
        <span class="vos-foot__label">选中资产</span>
        <strong>{{ selectedAssetId }}</strong>
        <em :class="`is-${selectedAssetStatus}`">{{ selectedAssetStatusLabel }}</em>
      </div>
    </footer>

    <!-- 读屏播报：仅在显式操作（选操作 / 定位徽章）时更新，避免播放中逐帧打断 -->
    <p class="vos-sr" role="status" aria-live="polite" aria-atomic="true">{{ announcement }}</p>
  </div>
</template>

<script setup>
/**
 * 虚拟运维场景页：3D 虚拟环境 + 操作失误后果预测。
 * 数据全部来自 domain 层确定性推演（演示虚拟数据），不请求、不伪造真实机房信息。
 */
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import { STATUS_COLORS, STATUS_LABELS, buildDrillReport, buildDrillReportHtml } from '../../domain/sentinel/virtualOpsScene.js'
import { useVirtualOpsScene } from '../../composables/useVirtualOpsScene.js'
import { isLightweightVisualMode, isReducedMotionMode } from '../../visual/visualMode.js'
// 3D 舞台依赖 three（体积较大）：异步加载，页面骨架与侧栏先渲染，three 按需拉取。
const VirtualOpsScene3D = defineAsyncComponent(() => import('../../components/sentinel/VirtualOpsScene3D.vue'))

const {
  topology, catalog, horizon, selectedOperationId, prediction, summary,
  assetPredictions, currentSnapshot, playhead, playing, atEnd, selectedAssetId,
  selectOperation, toggle, reset, pause, seek, selectAsset, setHorizon
} = useVirtualOpsScene({ horizon: 24, tickMs: 520 })

const narrow = ref(false)
let mq = null
function syncNarrow() {
  narrow.value = !!(mq && mq.matches)
}
onMounted(() => {
  if (typeof window === 'undefined') return
  mq = window.matchMedia('(max-width: 1024px)')
  syncNarrow()
  mq.addEventListener?.('change', syncNarrow)
})
onBeforeUnmount(() => mq?.removeEventListener?.('change', syncNarrow))

const visualModeLabel = computed(() => {
  if (isReducedMotionMode.value) return '减少动态'
  if (isLightweightVisualMode.value) return '轻量模式'
  return '标准模式'
})

const selectedOp = computed(() => catalog.find(o => o.id === selectedOperationId.value) || null)

const KIND_LABEL = { power: '电源操作', cooling: '制冷操作', network: '网络实验', compute: '计算资源', config: '配置操作' }
const groups = computed(() => {
  const map = new Map()
  for (const op of catalog) {
    if (!map.has(op.kind)) map.set(op.kind, { kind: op.kind, cn: KIND_LABEL[op.kind] || op.kind, items: [] })
    map.get(op.kind).items.push(op)
  }
  return [...map.values()]
})

const timelineMarks = computed(() => {
  const last = prediction.value ? prediction.value.timeline.length - 1 : 0
  const marks = []
  for (let t = 0; t <= last; t += Math.max(1, Math.round(last / 6))) marks.push(t)
  if (marks[marks.length - 1] !== last) marks.push(last)
  return marks
})

const frameHot = computed(() => {
  const s = currentSnapshot.value
  if (!s) return []
  return Object.values(s.racks)
    .slice()
    .sort((a, b) => b.temp - a.temp)
    .slice(0, 5)
    .map(r => ({ id: r.id, label: r.label, temp: r.temp, status: r.status }))
})

const selectedAssetStatus = computed(() => {
  const s = currentSnapshot.value
  const id = selectedAssetId.value
  if (!s || !id) return 'ok'
  return s.racks?.[id]?.status || s.switches?.[id]?.status
    || s.routers?.[id]?.status || s.gateways?.[id]?.status || 'ok'
})
const selectedAssetStatusLabel = computed(() => STATUS_LABELS[selectedAssetStatus.value] || selectedAssetStatus.value)

function severityClass(status) {
  return `sev-${status}`
}

// 业务服务级前向预测：峰值状态 + 重要级别，用于侧栏列表与 3D 徽章。
const servicePredictions = computed(() => assetPredictions.value.filter(p => p.kind === 'service'))
const CRITICALITY_LABEL = { core: '核心', important: '重要', normal: '一般' }
function criticalityLabel(c) { return CRITICALITY_LABEL[c] || c }

/**
 * 点击 3D 预测徽章：暂停播放并定位到该资产的首次劣化帧（firstBadTick），
 * 同时选中对应资产（业务服务选中其宿主机架），把「看到预测」接到「定位到那一刻」。
 */
function focusPrediction(p) {
  pause()
  const id = p.kind === 'service' ? (p.rackId || p.id) : p.id
  if (selectedAssetId.value !== id) selectAsset(id)
  seek(p.firstBadTick)
  announce(`已定位到${p.label}首次劣化帧 T+${p.firstBadTick}，预测将${STATUS_LABELS[p.worstStatus] || p.worstStatus}。`)
}

/* ------------------------------ 无障碍播报 ------------------------------ */
const announcement = ref('')
function announce(msg) { announcement.value = msg }
// 时间线滑块读屏值：直接用范围输入会比裸数字更易理解。
const timelineValueText = computed(() => {
  if (!prediction.value) return ''
  const storm = currentSnapshot.value?.broadcastStorm ? '，广播风暴扩散中' : ''
  return `T+${playhead.value}，共 ${prediction.value.timeline.length - 1} 步${storm}`
})
function chooseOperation(id) {
  selectOperation(id)
  const op = catalog.find(o => o.id === id)
  const s = summary.value
  if (!op || !s) { announce('已清除操作选择'); return }
  announce(`已选择${op.cn}。预测最高后果${s.maxSeverityLabel}，SLA ${s.slaRiskLabel}，${assetPredictions.value.length} 个资产将劣化，受影响业务 ${s.affectedServiceCount} 个。`)
}

/** 汇总导出所需的操作、预测与生成时间；无选中操作时返回 null。 */
function reportContext() {
  const op = selectedOp.value
  const p = prediction.value
  if (!op || !p) return null
  return { op, prediction: p, stamp: new Date().toLocaleString('zh-CN', { hour12: false }) }
}

/** 以 Blob 下载文本文件（延迟释放 URL，避免部分浏览器下载被中断）。 */
function downloadText(text, type, filename) {
  const blob = new Blob([text], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** 导出演练报告（Markdown）：峰值后果 + 业务影响 + 资产峰值 + 级联步骤 + 规避建议。 */
function exportReport() {
  const ctx = reportContext()
  if (!ctx) return
  const text = buildDrillReport(ctx.op, ctx.prediction, assetPredictions.value, ctx.stamp)
  downloadText(text, 'text/markdown;charset=utf-8', `演练报告-${ctx.op.id}-${Date.now()}.md`)
  announce(`已导出${ctx.op.cn}的 Markdown 演练报告。`)
}

/** 导出演练报告（自包含 HTML）：便于直接归档与跨端查看。 */
function exportHtmlReport() {
  const ctx = reportContext()
  if (!ctx) return
  const html = buildDrillReportHtml(ctx.op, ctx.prediction, assetPredictions.value, ctx.stamp)
  downloadText(html, 'text/html;charset=utf-8', `演练报告-${ctx.op.id}-${Date.now()}.html`)
  announce(`已导出${ctx.op.cn}的 HTML 演练报告。`)
}

/** 打印 / 另存为 PDF：在新窗口写入同一份 HTML，唤起浏览器打印对话框。 */
function printReport() {
  const ctx = reportContext()
  if (!ctx) return
  const html = buildDrillReportHtml(ctx.op, ctx.prediction, assetPredictions.value, ctx.stamp)
  const win = window.open('', '_blank')
  if (!win) {
    // 弹窗被拦截时退化为下载 HTML，用户仍可手动打印为 PDF。
    downloadText(html, 'text/html;charset=utf-8', `演练报告-${ctx.op.id}-${Date.now()}.html`)
    announce('浏览器拦截了打印窗口，已改为下载 HTML 报告，可在浏览器中打印为 PDF。')
    return
  }
  win.document.open()
  win.document.write(html)
  win.document.close()
  win.document.title = `演练报告-${ctx.op.cn}`
  const fire = () => { win.focus(); win.print() }
  // 等新窗口样式与字体就绪后再唤起打印，避免打印出空帧。
  if (win.document.readyState === 'complete') setTimeout(fire, 150)
  else win.addEventListener('load', () => setTimeout(fire, 150), { once: true })
  announce(`已打开${ctx.op.cn}的打印视图，可在打印对话框选择另存为 PDF。`)
}
</script>

<style scoped>
.vos-page { padding: 22px var(--page-pad, 28px) 28px; color: var(--ds-color-text, #e8f2f7); }
/* 读屏专用文本：视觉隐藏但保留在无障碍树中 */
.vos-sr { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
.eyebrow { margin: 0; font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: var(--ds-color-primary, #2496ed); font-weight: 600; }
.vos-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.vos-head h1 { margin: 4px 0 6px; font-size: 26px; font-weight: 600; }
.lede { margin: 0; max-width: 760px; color: var(--ds-color-muted, #92a6b5); font-size: 13px; line-height: 1.6; }
.lede b { color: var(--ds-color-text, #e8f2f7); }
.vos-head__right { display: flex; gap: 8px; flex-wrap: wrap; }
.vos-badge { font-size: 11px; padding: 5px 10px; border-radius: 999px; border: 1px solid var(--ds-hairline, rgba(255,255,255,.08)); color: var(--ds-color-muted, #92a6b5); background: var(--ds-color-card, #0a1118); }
.vos-badge--demo { color: #7ad7f5; border-color: rgba(122,215,245,.35); background: rgba(36,150,237,.12); }
.vos-badge--mode { color: var(--ds-color-muted, #92a6b5); }

.vos-grid { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(300px, 1fr); gap: 16px; }
.vos-grid--narrow { grid-template-columns: 1fr; }

.vos-stage { position: relative; min-height: 540px; border-radius: 14px; overflow: hidden; border: 1px solid var(--ds-hairline, rgba(255,255,255,.08)); }
.vos-stage__target { position: absolute; top: 12px; left: 12px; display: flex; flex-direction: column; gap: 2px;
  background: rgba(2,6,23,.6); padding: 8px 12px; border-radius: 10px; border: 1px solid rgba(56,189,248,.35); backdrop-filter: blur(6px); }
.vos-stage__target-kicker { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: #7ad7f5; }
.vos-stage__target strong { font-size: 16px; }
.vos-stage__target em { font-style: normal; font-size: 12px; color: var(--ds-color-muted, #92a6b5); }
.vos-stage__forecast { position: absolute; top: 12px; right: 12px; display: flex; flex-direction: column; gap: 3px;
  background: rgba(2,6,23,.62); padding: 8px 12px; border-radius: 10px; border: 1px solid rgba(249,115,22,.4);
  backdrop-filter: blur(6px); pointer-events: none; max-width: 320px; }
.vos-stage__forecast-kicker { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: #f97316; }
.vos-stage__forecast-row { font-size: 12px; color: var(--ds-color-text, #e8f2f7); line-height: 1.5; }
.vos-stage__forecast-row b { font-weight: 600; }
.vos-stage__forecast-sub { font-size: 11px; color: var(--ds-color-muted, #92a6b5); }
.vos-stage__empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; pointer-events: none; }
.vos-stage__empty p { color: var(--ds-color-muted, #92a6b5); font-size: 13px; background: rgba(2,6,23,.55); padding: 8px 14px; border-radius: 999px; }

.vos-side { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.vos-card { background: var(--ds-color-card, #0a1118); border: 1px solid var(--ds-hairline, rgba(255,255,255,.08)); border-radius: 12px; padding: 14px; }
.vos-card h2 { margin: 0 0 6px; font-size: 14px; font-weight: 600; }
.vos-card__sub { margin: 0 0 10px; font-size: 12px; color: var(--ds-color-muted, #92a6b5); }
.vos-card h4 { margin: 10px 0 6px; font-size: 12px; color: var(--ds-color-muted, #92a6b5); font-weight: 600; }

.vos-catalog__group h3 { margin: 10px 0 6px; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: var(--ds-color-primary, #2496ed); }
.vos-catalog__group:first-child h3 { margin-top: 0; }
.vos-op { width: 100%; text-align: left; background: var(--ds-color-surface, #071018); border: 1px solid var(--ds-hairline, rgba(255,255,255,.08));
  border-radius: 8px; padding: 9px 10px; margin-bottom: 6px; cursor: pointer; color: var(--ds-color-text, #e8f2f7); transition: border-color .15s, background .15s; }
.vos-op:hover { border-color: rgba(122,215,245,.4); }
.vos-op.is-active { border-color: #38bdf8; background: rgba(56,189,248,.1); box-shadow: inset 2px 0 0 #38bdf8; }
.vos-op__head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.vos-op__cn { font-size: 13px; font-weight: 600; }
.vos-op__en { display: block; font-size: 11px; color: var(--ds-color-muted, #92a6b5); margin-top: 2px; }
.vos-op__risk { font-size: 10px; padding: 2px 7px; border-radius: 999px; }
.vos-op__risk.is-high { color: #ef4444; background: rgba(239,68,68,.16); }
.vos-op__risk.is-medium { color: #f59e0b; background: rgba(245,158,11,.16); }

.vos-op-desc { margin: 0 0 8px; font-size: 13px; line-height: 1.55; }
.vos-op-brief { margin: 0; font-size: 12px; color: var(--ds-color-muted, #92a6b5); line-height: 1.55; }
.vos-op-brief b { color: #f59e0b; }

.vos-kpis { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 10px; }
.vos-kpi { background: var(--ds-color-surface, #071018); border: 1px solid var(--ds-hairline, rgba(255,255,255,.08)); border-radius: 8px; padding: 8px 10px; display: flex; flex-direction: column; }
.vos-kpi__v { font-size: 20px; font-weight: 600; line-height: 1.2; }
.vos-kpi__v small { font-size: 11px; font-weight: 400; color: var(--ds-color-muted, #92a6b5); margin-left: 2px; }
.vos-kpi__k { font-size: 11px; color: var(--ds-color-muted, #92a6b5); margin-top: 2px; }
.sev-ok { color: #22c55e; } .sev-degraded { color: #facc15; } .sev-warn { color: #f59e0b; } .sev-critical { color: #f97316; } .sev-down { color: #ef4444; }
.risk-high { color: #ef4444; } .risk-medium { color: #f97316; } .risk-low { color: #facc15; } .risk-none { color: #22c55e; }

.vos-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px 10px; margin: 0; font-size: 12px; }
.vos-stats div { display: flex; justify-content: space-between; border-bottom: 1px dashed var(--ds-hairline, rgba(255,255,255,.06)); padding: 3px 0; }
.vos-stats dt { color: var(--ds-color-muted, #92a6b5); }
.vos-stats dd { margin: 0; font-weight: 600; }

.vos-svc__list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.vos-svc__list li { display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 6px 10px; background: var(--ds-color-card, #0a1118); border: 1px solid var(--ds-hairline, rgba(255,255,255,.08)); border-radius: 8px; }
.vos-svc__dot { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 auto; }
.vos-svc__name { color: var(--ds-color-text, #e8f2f7); font-weight: 500; }
.vos-svc__crit { font-size: 10px; padding: 1px 7px; border-radius: 999px; margin-left: auto; }
.vos-svc__crit.is-core { color: #ef4444; background: rgba(239,68,68,.14); border: 1px solid rgba(239,68,68,.3); }
.vos-svc__crit.is-important { color: #f59e0b; background: rgba(245,158,11,.14); border: 1px solid rgba(245,158,11,.3); }
.vos-svc__crit.is-normal { color: #92a6b5; background: rgba(146,166,181,.12); border: 1px solid rgba(146,166,181,.25); }
.vos-svc__peak { font-size: 11px; font-weight: 600; }
.vos-svc__tick { font-family: var(--ds-font-mono, monospace); font-size: 10px; color: var(--ds-color-muted, #92a6b5); background: rgba(255,255,255,.06); border: 1px solid var(--ds-hairline, rgba(255,255,255,.1)); padding: 1px 6px; border-radius: 4px; }
.vos-advice p { margin: 0; font-size: 12px; color: #9ad8a8; line-height: 1.55; background: rgba(63,185,80,.08); border: 1px solid rgba(63,185,80,.2); border-radius: 8px; padding: 8px 10px; }

.vos-steps { margin: 0; padding: 0; list-style: none; max-height: 280px; overflow: auto; }
.vos-steps li { display: flex; gap: 8px; font-size: 12px; padding: 5px 0; border-bottom: 1px dashed var(--ds-hairline, rgba(255,255,255,.06)); line-height: 1.45; }
.vos-steps li.is-future { opacity: .45; }
.vos-steps__tick { flex: 0 0 auto; font-family: var(--ds-font-mono, monospace); color: #7ad7f5; font-size: 11px; }

.vos-timeline { display: flex; align-items: center; gap: 12px; margin-top: 14px; background: var(--ds-color-card, #0a1118); border: 1px solid var(--ds-hairline, rgba(255,255,255,.08)); border-radius: 12px; padding: 10px 14px; flex-wrap: wrap; }
.vos-timeline__controls { display: flex; gap: 6px; }
.vos-btn { font-size: 12px; padding: 6px 14px; border-radius: 8px; border: 1px solid rgba(56,189,248,.4); background: rgba(56,189,248,.14); color: #cdeeff; cursor: pointer; }
.vos-btn:hover { background: rgba(56,189,248,.24); }
.vos-btn--ghost { background: transparent; border-color: var(--ds-hairline, rgba(255,255,255,.12)); color: var(--ds-color-muted, #92a6b5); }
.vos-timeline__track { flex: 1 1 280px; min-width: 200px; }
.vos-range { width: 100%; accent-color: #38bdf8; }
.vos-timeline__marks { display: flex; justify-content: space-between; font-size: 10px; color: var(--ds-color-muted, #92a6b5); margin-top: 3px; }
.vos-timeline__marks .is-current { color: #7ad7f5; font-weight: 600; }
.vos-timeline__frame { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; font-size: 11px; color: var(--ds-color-muted, #92a6b5); font-family: var(--ds-font-mono, monospace); }
.vos-timeline__live.is-storm { color: #ef4444; }

.vos-foot { display: flex; align-items: center; gap: 18px; margin-top: 12px; background: var(--ds-color-surface, #071018); border: 1px solid var(--ds-hairline, rgba(255,255,255,.08)); border-radius: 12px; padding: 10px 14px; flex-wrap: wrap; }
.vos-foot__states { display: flex; gap: 6px; }
.vos-state { font-size: 11px; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--ds-hairline, rgba(255,255,255,.1)); color: var(--ds-color-muted, #92a6b5); }
.vos-state.is-on { color: #7ad7f5; border-color: rgba(56,189,248,.4); background: rgba(56,189,248,.12); }
.vos-state.is-off { opacity: .5; }
.vos-foot__label { font-size: 11px; color: var(--ds-color-muted, #92a6b5); margin-right: 6px; }
.vos-hot { display: flex; gap: 6px; flex-wrap: wrap; }
.vos-hot span { font-size: 11px; padding: 3px 8px; border-radius: 6px; background: var(--ds-color-card, #0a1118); border: 1px solid var(--ds-hairline, rgba(255,255,255,.08)); }
.vos-hot .is-warn { color: #f59e0b; border-color: rgba(245,158,11,.35); }
.vos-hot .is-critical { color: #f97316; border-color: rgba(249,115,22,.4); }
.vos-hot .is-down { color: #ef4444; border-color: rgba(239,68,68,.4); }
.vos-foot__asset { display: flex; align-items: center; gap: 6px; margin-left: auto; }
.vos-foot__asset strong { font-size: 13px; }
.vos-foot__asset em { font-style: normal; font-size: 11px; padding: 2px 8px; border-radius: 999px; }
.vos-foot__asset em.is-ok { color: #22c55e; background: rgba(34,197,94,.14); }
.vos-foot__asset em.is-degraded { color: #facc15; background: rgba(250,204,21,.14); }
.vos-foot__asset em.is-warn { color: #f59e0b; background: rgba(245,158,11,.14); }
.vos-foot__asset em.is-critical { color: #f97316; background: rgba(249,115,22,.16); }
.vos-foot__asset em.is-down { color: #ef4444; background: rgba(239,68,68,.16); }

.vos-horizon { display: flex; align-items: center; gap: 10px; margin: 0 0 12px; padding: 8px 10px; background: var(--ds-color-surface, #071018); border: 1px solid var(--ds-hairline, rgba(255,255,255,.08)); border-radius: 8px; }
.vos-horizon__label { font-size: 11px; color: var(--ds-color-muted, #92a6b5); flex: 0 0 auto; }
.vos-horizon__val { font-size: 11px; font-family: var(--ds-font-mono, monospace); color: #7ad7f5; flex: 0 0 auto; min-width: 38px; text-align: right; }
.vos-range--sm { accent-color: #38bdf8; }
.vos-intermittent { display: flex; align-items: center; gap: 8px; font-size: 11px; color: #fcd34d; background: rgba(245,158,11,.1); border: 1px solid rgba(245,158,11,.3); border-radius: 8px; padding: 6px 10px; margin-bottom: 10px; line-height: 1.4; }
.vos-intermittent__dot { width: 8px; height: 8px; border-radius: 50%; background: #f59e0b; box-shadow: 0 0 8px #f59e0b; flex: 0 0 auto; }

@media (max-width: 1024px) {
  .vos-stage { min-height: 420px; }
  .vos-kpis { grid-template-columns: repeat(2, 1fr); }
}
</style>
