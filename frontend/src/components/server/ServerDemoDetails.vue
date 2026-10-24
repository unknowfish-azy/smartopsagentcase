<template>
  <el-dialog :model-value="Boolean(server)" title="虚拟服务器演示详情" width="min(680px, calc(100vw - 32px))" class="server-demo-dialog" append-to-body destroy-on-close @update:model-value="!$event && emit('close')">
    <section v-if="server" class="demo-details">
      <p class="demo-notice">演示数据，非真实监控 · 固定样例，不会连接服务器或执行命令</p>
      <h2>{{ server.name }}</h2>
      <dl class="demo-facts"><div><dt>演示角色</dt><dd>{{ server.role }}</dd></div><div><dt>模拟状态</dt><dd><ServerStatusTag :status="server.status" /></dd></div><div><dt>示例地址</dt><dd>{{ server.host }}:{{ server.port }}</dd></div><div><dt>系统</dt><dd>{{ server.os }}</dd></div><div><dt>虚拟配置</dt><dd>{{ server.specification }}</dd></div><div><dt>模拟运行时长</dt><dd>{{ server.uptime }}</dd></div></dl>
      <div class="demo-metrics">
        <div v-for="metric in metrics" :key="metric.key" class="demo-metric"><div><strong>{{ metric.label }}</strong><span>{{ server.metrics[metric.key] === null ? '未采集（模拟）' : `${server.metrics[metric.key]}%（模拟）` }}</span></div><meter v-if="server.metrics[metric.key] !== null" :value="server.metrics[metric.key]" min="0" max="100" :aria-label="`${metric.label}模拟使用率`" /></div>
      </div>
      <p class="demo-scenario">{{ server.scenario }}</p>
    </section>
    <template #footer><el-button @click="emit('close')">关闭演示</el-button></template>
  </el-dialog>
</template>

<script setup>
import ServerStatusTag from './ServerStatusTag.vue'
defineProps({ server: { type: Object, default: null } })
const emit = defineEmits(['close'])
const metrics = [{ key: 'cpu', label: 'CPU' }, { key: 'memory', label: '内存' }, { key: 'disk', label: '磁盘' }]
</script>

<style scoped>
.demo-details{color:var(--smart-text);overflow-wrap:anywhere}.demo-notice{margin-top:0;padding:12px;border:1px solid var(--smart-border-strong);border-radius:6px;color:var(--smart-primary-strong);background:var(--smart-primary-soft);line-height:1.7}.demo-details h2{font-size:22px;color:var(--smart-text)}.demo-facts{display:grid;grid-template-columns:1fr 1fr;gap:18px}.demo-facts dt{color:var(--smart-muted);font-size:12px}.demo-facts dd{margin:6px 0 0}.demo-metrics{display:grid;gap:14px;padding:18px 0;border-top:1px solid var(--smart-border)}.demo-metric>div{display:flex;justify-content:space-between;gap:12px}.demo-metric span{color:var(--smart-muted)}.demo-metric meter{display:block;width:100%;height:18px;margin-top:6px;accent-color:var(--smart-primary)}.demo-scenario{color:var(--smart-muted);line-height:1.8}@media(max-width:500px){.demo-facts{grid-template-columns:1fr}.demo-metric>div{flex-wrap:wrap}}
</style>
