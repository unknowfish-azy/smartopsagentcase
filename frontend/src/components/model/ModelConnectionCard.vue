<script setup>
import { Connection } from '@element-plus/icons-vue'
defineProps({ connection: { type: Object, required: true }, busy: Boolean, result: { type: Object, default: null } })
const emit = defineEmits(['edit', 'delete', 'toggle', 'test'])
</script>
<template>
  <article class="model-card" :aria-label="connection.name">
    <header><Connection class="model-icon" aria-hidden="true" /><div class="model-heading"><h3>{{ connection.name }}</h3><p>{{ connection.provider }}</p></div><span class="status">{{ connection.enabled ? '已启用' : '已停用' }}</span></header>
    <dl><div><dt>模型 ID</dt><dd>{{ connection.modelName }}</dd></div><div><dt>服务地址</dt><dd>{{ connection.baseUrl }}</dd></div><div><dt>访问密钥</dt><dd>{{ connection.apiKeyMasked || '已保存' }}</dd></div><div><dt>请求超时</dt><dd>{{ connection.timeoutSeconds }} 秒</dd></div></dl>
    <p class="test-state" :class="{ error: result?.status === 'error' }">{{ result ? (result.status === 'success' ? `最近测试成功 · ${result.durationMs} ms` : '最近测试失败，请查看测试详情') : '尚未测试连接' }}</p>
    <footer><button type="button" :disabled="busy || !connection.enabled" @click="emit('test', connection)">测试模型</button><button type="button" :disabled="busy" @click="emit('edit', connection)">编辑</button><button type="button" :disabled="busy" @click="emit('toggle', connection)">{{ connection.enabled ? '停用' : '启用' }}</button><button type="button" class="danger" :disabled="busy" @click="emit('delete', connection)">删除</button></footer>
  </article>
</template>
<style scoped>
.model-card{min-width:0;padding:22px;border:1px solid var(--smart-border);border-radius:14px;background:var(--smart-surface);color:var(--smart-text)}header{display:flex;align-items:center;gap:12px}.model-icon{flex:0 0 24px;width:24px;height:24px;color:var(--smart-primary-strong)}.model-heading{min-width:0;flex:1}h3{margin:0;font-size:17px;overflow-wrap:anywhere}header p{margin:5px 0 0;font-size:12px;color:var(--smart-muted)}.status{white-space:nowrap;padding:5px 8px;border:1px solid var(--smart-border);border-radius:20px;color:var(--smart-primary-strong);font-size:11px}dl{display:grid;gap:13px;margin:22px 0}dl div{display:grid;grid-template-columns:70px minmax(0,1fr);gap:12px;font-size:12px}dt{color:var(--smart-muted)}dd{margin:0;text-align:right;overflow-wrap:anywhere}.test-state{padding-top:14px;border-top:1px solid var(--smart-border);font-size:12px;color:var(--smart-muted)}footer{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}button{min-height:36px;padding:8px 10px;border:1px solid var(--smart-border);border-radius:8px;background:transparent;color:var(--smart-text);cursor:pointer;font-size:12px}button:first-child{color:var(--smart-primary-strong)}button:hover:not(:disabled){border-color:var(--smart-primary)}button:disabled{opacity:.4;cursor:not-allowed}button:focus-visible{outline:2px solid var(--smart-primary);outline-offset:3px}.danger,.error{color:var(--smart-danger)}
</style>
