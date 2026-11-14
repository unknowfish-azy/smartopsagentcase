<template>
  <section class="hc-card hc-tools-card" aria-labelledby="hc-tools-title">
    <header class="hc-card-head">
      <h2 id="hc-tools-title">主动诊断</h2>
      <span class="hc-overline">TOOLS</span>
    </header>

    <div class="hc-tools">
      <button
        v-for="t in tools"
        :key="t.id"
        class="hc-chip"
        type="button"
        :aria-pressed="activeTool === t.id"
        :title="t.hint"
        @click="$emit('select', t.id)"
      >
        {{ t.label }}
      </button>
    </div>

    <p class="hc-tools-note">
      选择授权目标后运行。结果会在下方就地展开。
    </p>
  </section>
</template>

<script setup>
defineProps({
  activeTool: { type: String, default: null }
})
defineEmits(['select'])

// 四个后端主动诊断 + HTTP + 证书 + 配置差异（PROMPT §阶段 4）
const tools = Object.freeze([
  { id: 'host',       label: '主机',     hint: '主机级诊断：进程/端口/资源' },
  { id: 'database',   label: '数据库',   hint: '数据库连接与表权限检查' },
  { id: 'kubernetes', label: 'Kubernetes', hint: 'K8s 集群与工作负载诊断' },
  { id: 'network',    label: '网络路径', hint: 'DNS → TCP → TLS 分层诊断' },
  { id: 'http',       label: 'HTTP 探针', hint: '发一次真实 HTTP 请求看响应' },
  { id: 'certificate',label: '证书',     hint: 'TLS 证书链与有效期检查' },
  { id: 'config',     label: '配置差异', hint: '对比当前配置与基线' }
])
</script>

<style scoped>
.hc-tools-card { margin-top: 14px; }

.hc-tools {
  padding: 14px 16px;
  display: flex; flex-wrap: wrap; gap: 8px;
  border-top: 1px solid var(--ds-hairline);
}

.hc-chip {
  display: inline-flex; align-items: center; gap: 6px;
  height: 30px; padding: 0 11px;
  border-radius: var(--ds-radius-md);
  border: 1px solid var(--ds-color-border);
  color: var(--ds-color-muted);
  font-size: 12.5px;
  white-space: nowrap;
  background: transparent;
  cursor: pointer;
  transition: background var(--ds-duration-micro) var(--ds-ease-out),
              border-color var(--ds-duration-micro) var(--ds-ease-out),
              color var(--ds-duration-micro) var(--ds-ease-out);
}
.hc-chip:hover {
  background: color-mix(in srgb, var(--smart-text) 5%, transparent);
  color: var(--ds-color-text);
}
.hc-chip[aria-pressed="true"] {
  background: color-mix(in srgb, var(--ds-color-primary-strong) 10%, transparent);
  border-color: color-mix(in srgb, var(--ds-color-primary-strong) 45%, transparent);
  color: color-mix(in srgb, var(--smart-primary-strong) 90%, var(--smart-text));
}

.hc-tools-note {
  margin: 0;
  padding: 0 16px 14px;
  color: var(--ds-semantic-neutral);
  font-size: 11.5px;
  line-height: 1.55;
}
</style>
