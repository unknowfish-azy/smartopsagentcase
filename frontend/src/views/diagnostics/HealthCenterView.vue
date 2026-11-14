<template>
  <section class="hc-page">
    <header class="hc-page-head">
      <p class="hc-overline">SERVICE DIAGNOSTICS</p>
      <h1>健康诊断</h1>
      <p class="hc-lead">
        只显示当前账号有权查看的证据；未执行主动检查的服务不会被标记为正常。
      </p>
    </header>

    <!-- ① 结论带 -->
    <ConclusionBar
      v-if="status"
      :counts="counts"
      :checkedAt="checkedAt"
      :now="now"
      :stale="stale"
      :loading="loading"
      :loadingProgress="loadingProgress"
      @recheck="load"
      @jump-group="jumpGroup"
    />

    <p v-if="error" class="hc-error" role="alert">{{ error }}</p>

    <!-- ② 检查层 + 右侧工具（阶段 2 先完成左侧分组列表；右侧面板阶段 4 完成） -->
    <div class="hc-body">
      <CheckGroupList
        ref="groupListRef"
        :checks="status?.checks || []"
        :admin="admin"
        :stale="stale"
        :loading="loading"
        @go-tool="handleGoTool"
      />

      <!-- ③ 能力边界 + 工具条 -->
      <aside v-if="admin" class="hc-side">
        <PolicyPanel v-if="status?.policy" :policy="status.policy" />
        <ToolBar :active-tool="activeTool" @select="selectTool" />
      </aside>
    </div>

    <!-- 工具参数表单：host / kubernetes / network / database 四个需要用户填字段 -->
    <ToolParamsForm
      v-if="activeTool && !TOOL_AUTO_TARGET.includes(activeTool) && activeTool !== 'config'"
      :active-tool="activeTool"
      :label="activeToolLabel"
      :initial-params="requestParams[activeTool]"
      @submit="handleToolParamsSubmit"
      @update:params="handleParamsUpdate"
    />

    <!-- 统一诊断结果面板：选中工具后就地展开 -->
    <DiagnosisResultPanel
      v-if="activeTool"
      :tool-label="activeToolLabel"
      :result="activeDiagnosisResult"
      :failure-error="activeDiagnosisError"
      :loading="activeDiagnosisLoading"
      @rerun="rerunActiveTool"
    />

    <!-- 旧工具面板保留（NetworkDiagnosticTool / ConfigDiffTool 内部逻辑不重写，PROMPT 硬约束 7） -->
    <section class="hc-tools-legacy">
      <NetworkDiagnosticTool />
      <NetworkDiagnosticTool certificate-mode />
      <ConfigDiffTool />
    </section>
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, computed, watch } from 'vue'
import { diagnosticsApi, TOOL_API_ROUTES, TOOL_AUTO_TARGET } from '../../api/diagnostics.ts'
import { createDiagnosticState, normalizeDiagnosticFailure } from '../../components/diagnostics/healthState.js'
import { countByGroup } from '../../components/diagnostics/healthGroups.js'

import ConclusionBar from '../../components/diagnostics/ConclusionBar.vue'
import CheckGroupList from '../../components/diagnostics/CheckGroupList.vue'
import PolicyPanel from '../../components/diagnostics/PolicyPanel.vue'
import ToolBar from '../../components/diagnostics/ToolBar.vue'
import DiagnosisResultPanel from '../../components/diagnostics/DiagnosisResultPanel.vue'
import ToolParamsForm from '../../components/diagnostics/ToolParamsForm.vue'
import NetworkDiagnosticTool from '../../components/diagnostics/NetworkDiagnosticTool.vue'
import ConfigDiffTool from '../../components/diagnostics/ConfigDiffTool.vue'

const props = defineProps({
  admin: { type: Boolean, default: false }
})

const now = ref(Date.now())
let freshnessTimer

// ---- 健康快照（结论带 + 检查列表的数据来源）----
const { status, checkedAt, loading, stale, error, load } = createDiagnosticState(async () => {
  const result = props.admin ? await diagnosticsApi.adminHealth() : await diagnosticsApi.health()
  now.value = Date.now()
  return result
}, now)

const counts = computed(() => countByGroup(status.value?.checks || []))
const loadingProgress = computed(() =>
  loading.value && status.value?.checks?.length ? `/${status.value.checks.length}` : ''
)

const groupListRef = ref(null)
const activeTool = ref(null)

function jumpGroup(groupKey) {
  groupListRef.value?.openGroup(groupKey)
  groupListRef.value?.scrollToGroup(groupKey)
}

function selectTool(toolId) {
  activeTool.value = activeTool.value === toolId ? null : toolId
}

const CHECK_TOOL_MAP = Object.freeze({
  network: 'network',
  database: 'database',
  host: 'host',
  kubernetes: 'kubernetes',
  harbor: 'config'
})

function handleGoTool(check) {
  const toolId = CHECK_TOOL_MAP[check.id] || CHECK_TOOL_MAP[check.scope]
  if (toolId) {
    activeTool.value = toolId
  }
}

// ---- 统一结果面板状态 + 真实 API 路由 ----
const TOOL_LABELS = Object.freeze({
  host: '主机', database: '数据库', kubernetes: 'Kubernetes',
  network: '网络路径', http: 'HTTP 探针', certificate: '证书', config: '配置差异'
})
const activeToolLabel = computed(() => TOOL_LABELS[activeTool.value] || '')

const activeDiagnosisResult = ref(null)
const activeDiagnosisError = ref(null)
const activeDiagnosisLoading = ref(false)

// ---- 授权目标（http / certificate 自动取 targets[0].id）----
const targets = ref([])
const targetsReady = ref(false)

async function fetchTargets() {
  try {
    targets.value = await diagnosticsApi.targets() || []
  } catch {
    targets.value = []
  } finally {
    targetsReady.value = true
  }
}

// ---- 主动诊断：根据 activeTool 路由到正确 API ----
async function rerunActiveTool() {
  const toolId = activeTool.value
  if (!toolId) return

  const apiName = TOOL_API_ROUTES[toolId]
  if (!apiName) {
    activeDiagnosisError.value = '该工具暂不支持主动诊断。请使用下方「配置差异」面板。'
    activeDiagnosisResult.value = null
    return
  }

  const api = diagnosticsApi[apiName]
  if (typeof api !== 'function') {
    activeDiagnosisError.value = '内部错误：诊断 API 未注册。'
    return
  }

  activeDiagnosisLoading.value = true
  activeDiagnosisError.value = null
  // 保留旧 result 让用户对照，只在失败后清
  let response = null
  try {
    // 根据工具类型组装请求体（契约来自后端 Controller）
    const payload = await buildPayload(toolId)
    response = await api(payload)
    activeDiagnosisResult.value = response
    activeDiagnosisError.value = null
  } catch (failure) {
    // DESIGN §8.4：诊断失败只在结果面板内部报，且明确写"这不代表目标服务不健康"
    const { message } = normalizeDiagnosticFailure(failure)
    activeDiagnosisError.value = `${message}，这不代表目标服务不健康`
    // 不把旧 result 清零 — 诚实做法（健康快照 re-check 也不阻塞旧结果）
  } finally {
    activeDiagnosisLoading.value = false
  }
}

/** 根据工具类型组装请求体。
 *  契约来自 backend/*DiagnosisController.java — 不臆造字段。
 *
 *  auto-target 类（http / certificate）：自动取 targets[0].id，用户无需输入。
 *  需要复杂字段的（host / kubernetes / network / database）：
 *    从 requestParams[tool] 取，允许外部通过 setRequestParams 预填。
 *    缺失必填字段时 reject → 被 rerunActiveTool catch → 归类成 CONFIGURATION 错误。
 */
// ---- requestParams 存储：每个工具独立子对象（互不覆盖）----
const requestParams = ref({})

function setRequestParams(toolId, params) {
  requestParams.value = { ...requestParams.value, [toolId]: params }
}
defineExpose({ setRequestParams })

/** ToolParamsForm.submit → 这里：把表单值写进 requestParams，然后立即跑一次诊断。
 *  这样用户点「启动诊断」按钮就能完成「填字段 → 调 API → 看结果」完整链路。
 */
function handleToolParamsSubmit(payload) {
  setRequestParams(activeTool.value, payload)
  rerunActiveTool()
}

function handleParamsUpdate(payload) {
  setRequestParams(activeTool.value, payload)
}

async function buildPayload(toolId) {
  const auto = TOOL_AUTO_TARGET.includes(toolId)
  if (auto) {
    if (!targetsReady.value) await fetchTargets()
    const targetId = targets.value[0]?.id
    if (!targetId) {
      // 没有授权目标时，抛出结构化错误让 normalizeDiagnosticFailure 归类为 CONFIGURATION
      const err = new Error('没有授权目标，请先在诊断工具页面配置固定探测目标')
      err.errorCategory = 'CONFIGURATION'
      throw err
    }
    return toolId === 'certificate' ? targetId : { targetId }
  }

  // 复杂工具：从 requestParams 取
  const p = requestParams.value[toolId]
  if (!p || typeof p !== 'object' || !Object.keys(p).length) {
    const err = new Error('缺少诊断请求参数，请先填入 runtimeId / context / namespace 等必填字段')
    err.errorCategory = 'CONFIGURATION'
    throw err
  }
  return p
}

// 切工具时重置结果，避免残留上一个工具的输出
watch(activeTool, () => {
  activeDiagnosisResult.value = null
  activeDiagnosisError.value = null
  activeDiagnosisLoading.value = false
})

onMounted(() => {
  load()
  fetchTargets()
  freshnessTimer = window.setInterval(() => { now.value = Date.now() }, 5000)
})
onBeforeUnmount(() => window.clearInterval(freshnessTimer))
</script>

<style scoped>
.hc-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 48px 0 70px;
  color: var(--ds-color-text);
}

.hc-page-head { margin-bottom: 20px; }
.hc-page-head h1 {
  max-width: 700px;
  margin: 12px 0 10px;
  font: 400 clamp(2rem, 4vw, 3rem)/1.1 var(--ds-font-cn);
  letter-spacing: -0.02em;
}
.hc-overline {
  color: var(--ds-color-primary-strong);
  font: var(--ds-type-overline-size)/1 var(--ds-font-mono);
  letter-spacing: .12em;
}
.hc-lead {
  max-width: 680px;
  color: var(--ds-color-muted);
  line-height: 1.7;
  margin: 0;
  font-size: var(--ds-type-body-size);
}

.hc-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 18px;
  margin-top: 18px;
  align-items: start;
}

.hc-error {
  margin: 14px 0 0;
  color: var(--ds-semantic-danger);
  padding: 10px 14px;
  border-radius: var(--ds-radius-md);
  border: 1px solid color-mix(in srgb, var(--ds-semantic-danger) 34%, transparent);
  background: color-mix(in srgb, var(--ds-semantic-danger) 8%, transparent);
}

.hc-side-placeholder {
  border: 1px dashed var(--ds-color-border-strong);
  border-radius: var(--ds-radius-lg);
  padding: 14px 16px;
  background: color-mix(in srgb, var(--ds-surface-raised) 60%, transparent);
}
.hc-placeholder {
  color: var(--ds-semantic-neutral);
  font-size: 12px;
  line-height: 1.5;
  margin: 8px 0 0;
}
.hc-policy-raw {
  margin: 10px 0 0;
  color: var(--ds-color-muted);
  font: 11px/1.6 var(--ds-font-mono);
  word-break: break-all;
}

.hc-tools-legacy {
  display: grid; gap: 18px;
  margin-top: 28px;
}

/* ---- 响应式 ---- */
@media (max-width: 1023px) {
  .hc-body { grid-template-columns: 1fr; }
}
@media (max-width: 767px) {
  .hc-page { padding: 28px 0 50px; }
  .hc-page-head h1 { font-size: clamp(1.6rem, 8vw, 2.4rem); }
}
</style>
