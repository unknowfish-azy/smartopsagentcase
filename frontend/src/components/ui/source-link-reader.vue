<template><div class="source-reader"><label :for="id">GitHub / HTTPS 链接</label><div class="source-row"><input :id="id" v-model="link" type="url" :disabled="busy" placeholder="https://github.com/owner/repo/tree/main/skills/example" /><button type="button" :disabled="busy || !link.trim()" @click="read">{{ busy ? '读取中…' : '读取链接' }}</button></div><p>GitHub 目录自动读取 {{ kind === 'skill' ? 'SKILL.md' : 'smartops-plugin.json' }}。其他站点需提供允许跨域读取的公开原始文件；私有仓库请手动粘贴内容。</p><p v-if="error" role="alert" class="source-error">{{ error }}</p></div></template>
<script setup>
import { ref, useId, onBeforeUnmount } from 'vue'
import { readRemoteSource } from '../../domain/plugins/remoteSource.ts'
const props = defineProps({ kind: { type: String, required: true } })
const emit = defineEmits(['loaded'])
const id = useId(), link = ref(''), busy = ref(false), error = ref('')
let controller, timer, disposed = false
async function read() {
  if (busy.value) return
  busy.value = true; error.value = ''; controller = new AbortController()
  timer = setTimeout(() => controller.abort(), 15000)
  try { const result = await readRemoteSource(link.value, props.kind, controller.signal); if (!disposed) emit('loaded', result) }
  catch (err) { if (!disposed) error.value = err.name === 'AbortError' ? '读取超时，请重试或粘贴文件内容。' : err instanceof TypeError ? '无法读取链接：请检查网络、跨域权限和原始文件地址。也可手动粘贴内容。' : err.message }
  finally { clearTimeout(timer); if (!disposed) busy.value = false }
}
onBeforeUnmount(() => { disposed = true; clearTimeout(timer); controller?.abort() })
</script>
<style scoped>.source-reader{display:grid;gap:8px}.source-reader label{font-size:12px;color:var(--smart-text)}.source-row{display:flex;gap:8px}.source-row input{min-width:0;flex:1;background:var(--smart-bg);color:var(--smart-text);border:1px solid var(--smart-border);border-radius:7px;padding:10px;font:12px var(--font-cn)}.source-row button{min-height:42px;white-space:nowrap;padding:8px 12px;background:var(--smart-surface);color:var(--smart-primary-strong);border:1px solid var(--smart-border);border-radius:7px;cursor:pointer}.source-row button:disabled{opacity:.5}.source-reader p{font-size:11px;line-height:1.8;color:var(--smart-muted);margin:0}.source-reader .source-error{color:var(--smart-danger)}</style>
