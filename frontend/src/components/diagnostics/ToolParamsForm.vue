<template>
  <form class="hc-card hc-tool-form" @submit.prevent="submit">
    <header class="hc-card-head">
      <h2>{{ label }}诊断 · 填写参数</h2>
      <span class="hc-overline">DIAGNOSE</span>
    </header>

    <!-- 字段动态渲染：按 activeTool 显示不同字段组 -->
    <div class="hc-form-body" :class="`hc-form-body--${activeTool}`">
      <!-- host / kubernetes / network 共用 runtimeId + context + namespace -->
      <template v-if="showRuntimeFields">
        <label class="hc-field">
          <span class="hc-field-label">Runtime ID <b>*</b></span>
          <input v-model="form.runtimeId" type="text" required placeholder="后端注册的目标运行时 ID" />
          <small class="hc-field-hint">与 /api/diagnostics/targets 返回的目标 ID 可能不同，请参考运维侧注册表</small>
        </label>
      </template>

      <template v-if="showKubeFields">
        <label class="hc-field">
          <span class="hc-field-label">Kubectl Context <b>*</b></span>
          <input v-model="form.context" type="text" required placeholder="必须显式给出，不自动推断" />
          <small class="hc-field-hint">多集群环境下悄悄跑到另一个集群的诊断结论比没有结论更危险</small>
        </label>
        <label class="hc-field">
          <span class="hc-field-label">Namespace <b>*</b></span>
          <input v-model="form.namespace" type="text" required placeholder="目标 workload 所在 namespace" />
        </label>
      </template>

      <!-- host -->
      <template v-if="activeTool === 'host'">
        <label class="hc-field">
          <span class="hc-field-label">采样秒数</span>
          <input v-model.number="form.sampleSeconds" type="number" min="1" max="5" step="1" />
          <small class="hc-field-hint">后端会夹紧到 1..5，默认 2</small>
        </label>
      </template>

      <!-- kubernetes -->
      <template v-if="activeTool === 'kubernetes'">
        <label class="hc-field">
          <span class="hc-field-label">Workload</span>
          <input v-model="form.workload" type="text" placeholder="可选：Deployment/StatefulSet 名称" />
        </label>
        <label class="hc-field">
          <span class="hc-field-label">Pod</span>
          <input v-model="form.pod" type="text" placeholder="可选：具体 pod 名" />
        </label>
        <label class="hc-field">
          <span class="hc-field-label">Container</span>
          <input v-model="form.container" type="text" placeholder="可选" />
        </label>
        <label class="hc-field">
          <span class="hc-field-label">回溯分钟数</span>
          <input v-model.number="form.sinceMinutes" type="number" min="1" max="1440" step="1" />
          <small class="hc-field-hint">后端默认 60，夹紧到 1..1440</small>
        </label>
      </template>

      <!-- network -->
      <template v-if="activeTool === 'network'">
        <label class="hc-field">
          <span class="hc-field-label">Host</span>
          <input v-model="form.host" type="text" placeholder="可选：目标主机名或 IP" />
        </label>
        <label class="hc-field">
          <span class="hc-field-label">Port</span>
          <input v-model.number="form.port" type="number" min="1" max="65535" step="1" />
          <small class="hc-field-hint">后端默认 443</small>
        </label>
        <label class="hc-field">
          <span class="hc-field-label">Service</span>
          <input v-model="form.service" type="text" placeholder="可选：K8s Service 名" />
        </label>
        <label class="hc-field">
          <span class="hc-field-label">Ingress</span>
          <input v-model="form.ingress" type="text" placeholder="可选" />
        </label>
        <label class="hc-field">
          <span class="hc-field-label">Workload</span>
          <input v-model="form.workload" type="text" placeholder="可选" />
        </label>
        <label class="hc-field hc-field--inline">
          <span class="hc-field-label">TLS <b>*</b></span>
          <label class="hc-toggle">
            <input v-model="form.tls" type="checkbox" />
            <span>启用 TLS 层诊断</span>
          </label>
        </label>
        <label class="hc-field">
          <span class="hc-field-label">总超时秒数</span>
          <input v-model.number="form.timeoutSeconds" type="number" min="10" max="180" step="1" />
          <small class="hc-field-hint">后端默认 60，夹紧到 10..180</small>
        </label>
      </template>

      <!-- database -->
      <template v-if="activeTool === 'database'">
        <label class="hc-field">
          <span class="hc-field-label">引擎 <b>*</b></span>
          <select v-model="form.engine">
            <option value="" disabled>选择数据库引擎</option>
            <option value="mysql">MySQL</option>
            <option value="postgresql">PostgreSQL</option>
            <option value="mssql">SQL Server</option>
            <option value="oracle">Oracle</option>
            <option value="sqlite">SQLite</option>
          </select>
        </label>
        <label class="hc-field">
          <span class="hc-field-label">主机 <b>*</b></span>
          <input v-model="form.host" type="text" required placeholder="数据库主机名或 IP" />
        </label>
        <label class="hc-field">
          <span class="hc-field-label">端口</span>
          <input v-model.number="form.port" type="number" min="1" max="65535" step="1" />
          <small class="hc-field-hint">不填则由引擎类型默认</small>
        </label>
        <label class="hc-field">
          <span class="hc-field-label">数据库 <b>*</b></span>
          <input v-model="form.database" type="text" required placeholder="目标数据库名" />
        </label>
        <label class="hc-field">
          <span class="hc-field-label">凭据引用 <b>*</b></span>
          <input v-model="form.credentialRef" type="text" required placeholder="后端凭据存储的 ID" />
          <small class="hc-field-hint">只引用凭据 ID，不直接传密码；凭据由运维存储</small>
        </label>
        <label class="hc-field">
          <span class="hc-field-label">团队 ID</span>
          <input v-model.number="form.teamId" type="number" placeholder="可选：审计归属" />
        </label>
        <label class="hc-field">
          <span class="hc-field-label">超时秒数</span>
          <input v-model.number="form.timeoutSeconds" type="number" min="1" max="30" step="1" />
          <small class="hc-field-hint">后端默认 10，夹紧到 30</small>
        </label>
        <label class="hc-field">
          <span class="hc-field-label">返回行数上限</span>
          <input v-model.number="form.maxRows" type="number" min="1" max="1000" step="50" />
          <small class="hc-field-hint">后端默认 200，夹紧到 1000，避免把生产库拖慢</small>
        </label>
      </template>
    </div>

    <footer class="hc-form-foot">
      <span class="hc-form-note">
        <b>*</b> 必填 · 超出范围的数字会由后端夹紧到安全默认值 · 不做主动探测只做本地检查
      </span>
      <button
        class="hc-btn hc-btn-primary"
        type="submit"
        :disabled="!isFormValid || submitting"
      >
        {{ submitting ? '诊断中…' : `启动${label}诊断` }}
      </button>
    </footer>
  </form>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { TOOL_DEFAULTS, REQUIRED } from './toolParamsSchema.js'

const props = defineProps({
  activeTool: { type: String, required: true },
  label: { type: String, default: '工具' },
  initialParams: { type: Object, default: null }
})
const emit = defineEmits(['submit', 'update:params'])

// ---- 每个工具独立的默认值（从 toolParamsSchema.js 抽取，组件与测试共用）----

const form = reactive({ ...(TOOL_DEFAULTS[props.activeTool] || {}) })

// 切工具时 rehydrate：优先用已保存的 params，否则 fallback 到默认值 + 后端传进来的 initialParams
watch(() => props.activeTool, (newTool) => {
  const defaults = TOOL_DEFAULTS[newTool] || {}
  // 先清空再填，避免残留旧工具字段
  Object.keys(form).forEach(k => delete form[k])
  Object.assign(form, defaults)
  if (props.initialParams) {
    Object.assign(form, props.initialParams)
  }
}, { immediate: true })

// initialParams 变化时同步（HealthCenterView 可能在提交后把 params 写回）
watch(() => props.initialParams, (params) => {
  if (params) Object.assign(form, params)
}, { deep: true })

const showRuntimeFields = computed(() =>
  ['host', 'kubernetes', 'network'].includes(props.activeTool)
)
const showKubeFields = computed(() =>
  ['kubernetes', 'network'].includes(props.activeTool)
)

// ---- 必填校验（REQUIRED 从 toolParamsSchema.js 导入） ----

const isFormValid = computed(() => {
  const required = REQUIRED[props.activeTool] || []
  return required.every(key => {
    const v = form[key]
    if (typeof v === 'boolean') return true // tls 是 boolean，默认 true 总是有值
    return v != null && String(v).trim() !== ''
  })
})

const submitting = ref(false)

async function submit() {
  if (!isFormValid.value) return
  // 提交时把 null/空字符串字段过滤掉，避免后端接收无效值
  const payload = {}
  for (const [k, v] of Object.entries(form)) {
    if (v === null || v === undefined) continue
    if (typeof v === 'string' && v.trim() === '') continue
    // 默认值也带上（后端会夹紧），让请求体自描述
    payload[k] = v
  }
  submitting.value = true
  try {
    emit('submit', payload)
    emit('update:params', payload)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.hc-tool-form { margin-top: 18px; }

.hc-form-body {
  display: grid;
  gap: 12px 14px;
  padding: 14px 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border-top: 1px solid var(--ds-hairline);
}
.hc-form-body--host { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.hc-form-body--kubernetes { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.hc-form-body--network { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.hc-form-body--database { grid-template-columns: repeat(2, minmax(0, 1fr)); }

.hc-field {
  display: flex; flex-direction: column; gap: 4px;
  font-size: 12.5px;
}
.hc-field--inline { flex-direction: row; align-items: center; gap: 10px; }

.hc-field-label {
  color: var(--ds-color-muted);
  font-size: 11.5px;
  letter-spacing: .01em;
}
.hc-field-label b { color: var(--ds-semantic-danger); font-weight: 600; margin-left: 1px; }

.hc-field input[type="text"],
.hc-field input[type="number"],
.hc-field select {
  min-height: 36px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  padding: 7px 10px;
  background: var(--ds-surface-base);
  color: var(--ds-color-text);
  font-size: 13px;
  transition: border-color var(--ds-duration-micro) var(--ds-ease-out),
              background var(--ds-duration-micro) var(--ds-ease-out);
}
.hc-field input:focus, .hc-field select:focus {
  border-color: var(--ds-color-primary-strong);
  background: var(--ds-surface-raised);
  outline: none;
}
.hc-field input[type="checkbox"] { accent-color: var(--ds-color-primary-strong); }

.hc-field-hint {
  color: var(--ds-semantic-neutral);
  font-size: 11px;
  line-height: 1.4;
}

.hc-toggle {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--ds-color-text);
  cursor: pointer;
  font-size: 12.5px;
}

.hc-form-foot {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px;
  border-top: 1px solid var(--ds-hairline);
}
.hc-form-note {
  color: var(--ds-semantic-neutral);
  font-size: 11.5px;
  line-height: 1.5;
  flex: 1;
}
.hc-form-note b { color: var(--ds-semantic-danger); }

/* ---- 响应式 ---- */
@media (max-width: 1023px) {
  .hc-form-body { grid-template-columns: 1fr; }
}
@media (max-width: 767px) {
  .hc-form-body { padding: 12px 14px; }
  .hc-form-foot { flex-direction: column; align-items: stretch; gap: 10px; }
  .hc-form-foot .hc-btn { width: 100%; }
}
</style>
