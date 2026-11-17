<template>
  <article class="patrol-page">
    <header class="patrol-head">
      <p class="patrol-overline">SENTINEL / PATROL PLAN</p>
      <h1>巡检计划</h1>
      <p class="patrol-lead">
        选择授权探测目标，执行真实 HTTP 探测，并把结论写入纠察中心留痕。
        <strong>探测结果来自真实诊断接口，事件写入纠察中心留痕；无大模型参与判定。</strong>
      </p>
    </header>

    <!-- 五吸引子映射说明卡（纯文案）：对应页面三步 -->
    <section class="attractor-card" aria-label="吸引子映射说明">
      <div class="attractor-item">
        <span class="attractor-key">ANALYZE</span>
        <span class="attractor-arrow">→</span>
        <p><strong>真实探测</strong>：调用 /api/diagnostics/http 对授权目标发起 HTTP 探测，结论只来自真实返回。</p>
      </div>
      <div class="attractor-item">
        <span class="attractor-key">DECIDE</span>
        <span class="attractor-arrow">→</span>
        <p><strong>事件写入</strong>：探测结论经固定规则映射为 PASS/FAIL 事件，写入纠察中心留痕（/api/inspector/check）。</p>
      </div>
      <div class="attractor-item">
        <span class="attractor-key">REVIEW</span>
        <span class="attractor-arrow">→</span>
        <p><strong>人工复核</strong>：FAIL 事件由人工确认或驳回（/api/inspector/verify），复核结果行内留痕。</p>
      </div>
    </section>

    <!-- 目标选择 -->
    <section class="panel">
      <div class="panel-head">
        <h2>1 · 选择探测目标（最多 {{ MAX_TARGETS }} 个）</h2>
        <div class="panel-actions">
          <button type="button" class="btn btn-ghost" :disabled="targetsLoading || !targets.length" @click="selectAll">全选</button>
          <button type="button" class="btn btn-ghost" :disabled="!selectedIds.length" @click="selectedIds = []">清空</button>
          <button type="button" class="btn btn-primary" :disabled="!selectedIds.length || probing" @click="runPatrol">
            {{ probing ? `探测中（${doneCount}/${rows.length}）` : '执行巡检' }}
          </button>
        </div>
      </div>

      <p v-if="targetsLoading" class="hint">正在加载授权探测目标…</p>
      <p v-else-if="targetsError" class="error-line" role="alert">加载探测目标失败：{{ targetsError }}</p>
      <p v-else-if="!targets.length" class="hint">没有授权探测目标。请先在诊断工具页面配置固定探测目标。</p>

      <div v-else class="target-grid" role="group" aria-label="授权探测目标">
        <label v-for="target in targets" :key="target.id" class="target-item">
          <input
            v-model="selectedIds"
            type="checkbox"
            :value="target.id"
            :disabled="probing || (!selectedIds.includes(target.id) && selectedIds.length >= MAX_TARGETS)"
          />
          <span class="target-label">{{ target.label }}</span>
          <span class="target-meta">{{ target.scheme }} · 期望 {{ target.expectedStatus }} · {{ target.id }}</span>
        </label>
      </div>
      <p v-if="selectedIds.length >= MAX_TARGETS" class="hint">已达单次巡检上限 {{ MAX_TARGETS }} 个目标。</p>
    </section>

    <!-- 结果表 -->
    <section v-if="rows.length" class="panel">
      <div class="panel-head">
        <h2>2 · 巡检结果</h2>
        <div class="panel-actions summary-pills">
          <span class="pill pill-total">总计 {{ summary.total }}</span>
          <span class="pill pill-pass">PASS {{ summary.pass }}</span>
          <span class="pill pill-fail">FAIL {{ summary.fail }}</span>
          <span class="pill pill-unknown">未判定 {{ summary.unknown }}</span>
        </div>
      </div>

      <div class="result-table" role="table" aria-label="巡检结果">
        <div class="result-row result-head" role="row">
          <span role="columnheader">目标</span>
          <span role="columnheader">结果</span>
          <span role="columnheader">耗时</span>
          <span role="columnheader">结论</span>
          <span role="columnheader">纠察事件 / 复核</span>
        </div>
        <div v-for="row in rows" :key="row.targetId" class="result-row" role="row">
          <span class="cell-target" role="cell">
            <strong>{{ row.label }}</strong>
            <small>{{ row.targetId }}</small>
          </span>
          <span class="cell-probe" role="cell">
            <template v-if="row.phase === 'running'">探测中…</template>
            <template v-else-if="row.phase === 'error'">
              <span class="error-line">接口异常：{{ row.error }}</span>
            </template>
            <template v-else-if="row.probe">
              <span>{{ row.probe.status }} · 状态码 {{ row.probe.statusCode }} · 断言 {{ row.probe.assertion }}</span>
              <small>{{ row.probe.summary }}</small>
            </template>
            <template v-else>未探测</template>
          </span>
          <span class="cell-elapsed" role="cell">{{ row.phase === 'done' ? `${row.elapsedMs} ms` : '—' }}</span>
          <span role="cell">
            <span v-if="row.conclusion === 'PASS'" class="pill pill-pass">PASS</span>
            <span v-else-if="row.conclusion === 'FAIL'" class="pill pill-fail">FAIL</span>
            <span v-else-if="row.phase === 'running'" class="pill pill-unknown">进行中</span>
            <span v-else class="pill pill-unknown">未判定</span>
          </span>
          <span class="cell-event" role="cell">
            <template v-if="row.eventWriting">写入中…</template>
            <template v-else-if="row.eventError">
              <span class="error-line">写入失败：{{ row.eventError }}</span>
              <button type="button" class="btn btn-ghost" @click="writeEvents">重试写入</button>
            </template>
            <template v-else-if="row.event?.id">
              <RouterLink class="event-link" :to="`/inspector/events/${row.event.id}`">{{ row.event.id }}</RouterLink>
              <template v-if="row.conclusion === 'FAIL'">
                <template v-if="!row.verified">
                  <button
                    type="button"
                    class="btn btn-ghost"
                    :disabled="row.verifying"
                    @click="reviewRow(row, 'CONFIRMED')"
                  >确认故障</button>
                  <button
                    type="button"
                    class="btn btn-ghost"
                    :disabled="row.verifying"
                    @click="reviewRow(row, 'DISMISSED')"
                  >驳回误报</button>
                </template>
                <span v-else class="pill pill-verified">
                  已复核 · {{ row.verificationStatus }}{{ row.verifiedAt ? ` · ${row.verifiedAt}` : '' }}
                </span>
              </template>
            </template>
            <template v-else>未写入</template>
          </span>
        </div>
      </div>

      <div class="panel-actions panel-footer">
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!writableRows.length || writing"
          @click="writeEvents"
        >
          {{ writing ? `写入中（${writtenCount}/${writableRows.length}）` : '写入纠察中心' }}
        </button>
        <span v-if="writeSummary" class="hint">
          本次创建事件 {{ writeSummary.created }} 条，失败 {{ writeSummary.failed }} 条。
        </span>
        <RouterLink class="inspector-link" to="/inspector">前往纠察中心查看事件列表 →</RouterLink>
      </div>
    </section>

    <section v-else class="panel">
      <p class="hint">尚未开始巡检。选择目标后点击「执行巡检」，结果与耗时均来自真实探测，不做任何模拟。</p>
    </section>
  </article>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { diagnosticsApi } from '../../api/diagnostics.ts'
import { recordInspection, verifyInspection } from '../../api/inspector'
import { mapProbeToInspection, summarizePatrol } from '../../utils/patrolPlan.js'

/** 单次巡检目标上限 */
const MAX_TARGETS = 8

/** 探测并发上限（与项目爬取/探测类任务的并发约定一致） */
const PROBE_CONCURRENCY = 4

// ---- 授权目标（字段契约来自 DiagnosticTargetPolicy.TargetSummary：id/label/scheme/expectedStatus）----
const targets = ref([])
const targetsLoading = ref(false)
const targetsError = ref('')
const selectedIds = ref([])

// ---- 巡检结果行：一切结论来自真实探测，未探测/失败如实显示 ----
const rows = reactive([])
const probing = ref(false)

// ---- 事件写入与人工复核 ----
const writing = ref(false)
const writeSummary = ref(null)

async function loadTargets() {
  targetsLoading.value = true
  targetsError.value = ''
  try {
    targets.value = await diagnosticsApi.targets() || []
  } catch (failure) {
    // 显示真实错误文本，不用假数据兜底
    targetsError.value = failure?.message || String(failure)
    targets.value = []
  } finally {
    targetsLoading.value = false
  }
}

function selectAll() {
  selectedIds.value = targets.value.slice(0, MAX_TARGETS).map(target => target.id)
}

const summary = computed(() => summarizePatrol(rows))
const doneCount = computed(() => rows.filter(row => row.phase === 'done' || row.phase === 'error').length)

/** 可写入纠察中心的行：探测已完成且尚未成功写入 */
const writableRows = computed(() => rows.filter(row => (row.phase === 'done' || row.phase === 'error') && !row.event && !row.eventWriting))
const writtenCount = computed(() => rows.filter(row => row.event?.id).length)

/**
 * 以固定并发上限执行探测（Promise 池模式）。
 */
async function runPool(items, worker, limit) {
  const queue = [...items]
  const runners = Array.from({ length: Math.min(limit, queue.length) }, async () => {
    while (queue.length) {
      const item = queue.shift()
      await worker(item)
    }
  })
  await Promise.all(runners)
}

/** 执行巡检：并发上限 4，逐个调用真实 HTTP 探测 */
async function runPatrol() {
  const selected = targets.value.filter(target => selectedIds.value.includes(target.id))
  if (!selected.length) return

  rows.splice(0, rows.length, ...selected.map(target => ({
    targetId: target.id,
    label: target.label,
    phase: 'running',        // running | done | error
    probe: null,             // POST /api/diagnostics/http 的真实返回
    error: null,             // 接口异常时的真实错误文本
    elapsedMs: 0,
    conclusion: null,        // PASS | FAIL | null（未判定）
    event: null,             // 写入纠察中心后返回的事件（含 id）
    eventWriting: false,
    eventError: null,
    verified: false,
    verifying: false,
    verificationStatus: null,
    verifiedAt: null
  })))

  probing.value = true
  writeSummary.value = null

  await runPool(rows, async row => {
    const started = performance.now()
    try {
      const probe = await diagnosticsApi.http({ targetId: row.targetId })
      row.probe = probe
      row.elapsedMs = Math.round(performance.now() - started)
      row.phase = 'done'
      // 后端已综合状态码与断言：HEALTHY → PASS，否则 FAIL
      row.conclusion = probe?.status === 'HEALTHY' ? 'PASS' : 'FAIL'
    } catch (failure) {
      // 接口异常：如实记录真实错误文本，结论 FAIL（需要人工关注）
      row.error = failure?.message || String(failure)
      row.elapsedMs = Math.round(performance.now() - started)
      row.phase = 'error'
      row.conclusion = 'FAIL'
    }
  }, PROBE_CONCURRENCY)

  probing.value = false
}

/** 把已完成结果写入纠察中心（POST /api/inspector/check） */
async function writeEvents() {
  const pending = rows.filter(row => (row.phase === 'done' || row.phase === 'error') && !row.event)
  if (!pending.length) return

  writing.value = true
  let created = 0
  let failed = 0

  await runPool(pending, async row => {
    row.eventWriting = true
    row.eventError = null
    try {
      const payload = mapProbeToInspection(
        row.targetId,
        row.phase === 'done' ? row.probe : null,
        row.elapsedMs,
        row.error
      )
      const response = await recordInspection(payload)
      // request 拦截器返回 { code, message, data }，事件本体在 data（含 id）
      const event = response?.data ?? response
      if (!event?.id) throw new Error('纠察接口未返回事件 id')
      row.event = event
      created += 1
    } catch (failure) {
      row.eventError = failure?.message || String(failure)
      failed += 1
    } finally {
      row.eventWriting = false
    }
  }, PROBE_CONCURRENCY)

  writeSummary.value = { created, failed }
  writing.value = false
}

/** 人工复核 FAIL 事件（POST /api/inspector/verify） */
async function reviewRow(row, status) {
  if (!row.event?.id || row.verifying) return
  row.verifying = true
  try {
    await verifyInspection({
      inspectionId: row.event.id,
      resolved: status === 'CONFIRMED',
      status,
      details: { reviewedAt: new Date().toISOString() }
    })
    row.verified = true
    row.verificationStatus = status
    row.verifiedAt = new Date().toLocaleTimeString()
  } catch (failure) {
    // 复核失败只在行内提示真实错误，不改判定
    row.eventError = `复核失败：${failure?.message || String(failure)}`
  } finally {
    row.verifying = false
  }
}

onMounted(loadTargets)
</script>

<style scoped>
.patrol-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 48px 0 70px;
  color: var(--ds-color-text);
}

/* ---- 页头 ---- */
.patrol-head h1 {
  margin: 12px 0 10px;
  font: 400 clamp(2rem, 4vw, 3rem)/1.1 var(--ds-font-cn);
  letter-spacing: -0.02em;
}
.patrol-overline {
  color: var(--ds-color-primary-strong);
  font: var(--ds-type-overline-size)/1 var(--ds-font-mono);
  letter-spacing: .12em;
}
.patrol-lead {
  max-width: 680px;
  margin: 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-type-body-size);
  line-height: var(--ds-line-loose);
}
.patrol-lead strong { color: var(--ds-color-text); }

/* ---- 五吸引子映射说明卡 ---- */
.attractor-card {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--ds-space-3);
  margin-top: var(--ds-space-6);
  padding: var(--ds-space-4);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-surface-raised);
}
.attractor-item { display: flex; flex-direction: column; gap: var(--ds-space-2); }
.attractor-key {
  color: var(--ds-color-primary-strong);
  font: var(--ds-type-overline-size)/1 var(--ds-font-mono);
  letter-spacing: .12em;
}
.attractor-arrow { color: var(--ds-color-muted); font-size: var(--ds-font-sm); }
.attractor-item p {
  margin: 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-type-body-caption-size);
  line-height: var(--ds-line-base);
}
.attractor-item strong { color: var(--ds-color-text); }

/* ---- 面板 ---- */
.panel {
  margin-top: var(--ds-space-6);
  padding: var(--ds-card-padding);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-surface-raised);
}
.panel-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-3);
  margin-bottom: var(--ds-space-4);
}
.panel-head h2 {
  margin: 0;
  font: var(--ds-type-h3-size)/1.3 var(--ds-font-cn);
  font-weight: var(--ds-type-h3-weight);
}
.panel-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ds-space-2); }
.panel-footer { margin-top: var(--ds-space-4); }

/* ---- 按钮（动效 ≤200ms）---- */
.btn {
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-sm);
  background: transparent;
  color: var(--ds-color-text);
  padding: 6px 14px;
  font-size: var(--ds-type-body-size);
  cursor: pointer;
  transition: background-color var(--ds-duration-micro) var(--ds-ease-out),
              border-color var(--ds-duration-micro) var(--ds-ease-out),
              opacity var(--ds-duration-micro) var(--ds-ease-out);
}
.btn:hover:not(:disabled) { background: var(--ds-pill-neutral-bg); border-color: var(--ds-color-primary); }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.btn-primary {
  background: var(--ds-color-primary);
  border-color: var(--ds-color-primary);
  color: #fff;
}
.btn-primary:hover:not(:disabled) { background: var(--ds-color-primary-strong); border-color: var(--ds-color-primary-strong); }

/* ---- 目标多选 ---- */
.target-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--ds-space-2);
}
.target-item {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  column-gap: var(--ds-space-2);
  align-items: center;
  padding: var(--ds-space-2) var(--ds-space-3);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  cursor: pointer;
  transition: border-color var(--ds-duration-micro) var(--ds-ease-out),
              background-color var(--ds-duration-micro) var(--ds-ease-out);
}
.target-item:hover { border-color: var(--ds-color-primary); background: var(--ds-pill-info-bg); }
.target-label { font-size: var(--ds-type-body-size); font-weight: 600; }
.target-meta {
  grid-column: 2;
  color: var(--ds-color-muted);
  font: var(--ds-type-caption-size)/1.4 var(--ds-font-mono);
}

/* ---- 结果表 ---- */
.result-table { display: flex; flex-direction: column; gap: var(--ds-space-2); }
.result-row {
  display: grid;
  grid-template-columns: minmax(120px, 1.2fr) minmax(0, 2fr) 80px 90px minmax(160px, 1.6fr);
  gap: var(--ds-space-3);
  align-items: start;
  padding: var(--ds-space-3);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
}
.result-row.result-head {
  color: var(--ds-color-muted);
  font: var(--ds-type-caption-size)/1 var(--ds-font-mono);
  letter-spacing: .06em;
  text-transform: uppercase;
  border-style: dashed;
}
.cell-target { display: flex; flex-direction: column; gap: 2px; }
.cell-target small {
  color: var(--ds-color-muted);
  font: var(--ds-type-caption-size)/1.3 var(--ds-font-mono);
  word-break: break-all;
}
.cell-probe { display: flex; flex-direction: column; gap: 2px; font-size: var(--ds-type-body-caption-size); }
.cell-probe small { color: var(--ds-color-muted); }
.cell-elapsed { font: var(--ds-type-body-size)/1.4 var(--ds-font-mono); font-variant-numeric: var(--ds-type-num); }
.cell-event { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ds-space-2); font-size: var(--ds-type-body-caption-size); }
.cell-event .btn { padding: 3px 10px; font-size: var(--ds-type-caption-size); }
.event-link {
  color: var(--ds-color-primary-strong);
  font: var(--ds-type-body-caption-size)/1 var(--ds-font-mono);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: border-color var(--ds-duration-micro) var(--ds-ease-out);
}
.event-link:hover { border-bottom-color: var(--ds-color-primary-strong); }

/* ---- 状态 pill ---- */
.pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: var(--ds-radius-pill);
  font: var(--ds-type-caption-size)/1.6 var(--ds-font-mono);
  white-space: nowrap;
}
.pill-total { background: var(--ds-pill-neutral-bg); color: var(--ds-color-text); }
.pill-pass { background: var(--ds-pill-success-bg); color: var(--ds-pill-success-fg); }
.pill-fail { background: var(--ds-pill-danger-bg); color: var(--ds-pill-danger-fg); }
.pill-unknown { background: var(--ds-pill-info-bg); color: var(--ds-pill-info-fg); }
.pill-verified { background: var(--ds-pill-success-bg); color: var(--ds-pill-success-fg); }

/* ---- 提示与错误 ---- */
.hint { margin: var(--ds-space-2) 0 0; color: var(--ds-color-muted); font-size: var(--ds-type-body-caption-size); }
.error-line { color: var(--ds-semantic-danger); font-size: var(--ds-type-body-caption-size); word-break: break-all; }
.inspector-link {
  margin-left: auto;
  color: var(--ds-color-primary-strong);
  font-size: var(--ds-type-body-caption-size);
  text-decoration: none;
}
.inspector-link:hover { text-decoration: underline; }

/* ---- 窄屏单列 ---- */
@media (max-width: 900px) {
  .patrol-page { padding: 32px 16px 56px; }
  .attractor-card { grid-template-columns: 1fr; }
  .target-grid { grid-template-columns: 1fr; }
  .result-row { grid-template-columns: 1fr; gap: var(--ds-space-2); }
  .result-row.result-head { display: none; }
  .inspector-link { margin-left: 0; }
}

/* ---- 动效降级：prefers-reduced-motion 下全部关闭 ---- */
@media (prefers-reduced-motion: reduce) {
  .patrol-page *,
  .patrol-page *::before,
  .patrol-page *::after {
    animation: none !important;
    transition: none !important;
    scroll-behavior: auto !important;
  }
}
</style>
