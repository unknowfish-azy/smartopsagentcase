<template>
  <div class="quota-editor">
    <button type="button" class="quota-button" @click="open">配额</button>
    <div v-if="openState" class="quota-popover">
      <label>请求数 / 24h<input v-model="requests" type="number" min="0" placeholder="不限" /></label>
      <label>Token / 24h<input v-model="tokens" type="number" min="0" placeholder="不限" /></label>
      <div><button type="button" @click="cancel">取消</button><button type="button" class="save" :disabled="saving" @click="save">{{ saving ? '保存中' : '保存' }}</button></div>
      <p v-if="error">{{ error }}</p>
    </div>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import { updateGatewayKeyQuota } from '../../api/model'
const props = defineProps({ item: { type: Object, required: true } })
const emit = defineEmits(['saved'])
const openState = ref(false), saving = ref(false), error = ref(''), requests = ref(props.item.requestLimit24h > -1 ? props.item.requestLimit24h : ''), tokens = ref(props.item.tokenLimit24h > -1 ? props.item.tokenLimit24h : '')
function open() { openState.value = true; error.value = '' }
function cancel() { openState.value = false }
async function save() { saving.value = true; error.value = ''; try { const payload = { requestLimit24h: requests.value === '' ? null : Number(requests.value), tokenLimit24h: tokens.value === '' ? null : Number(tokens.value) }; await updateGatewayKeyQuota(props.item.id, payload); emit('saved', payload); openState.value = false } catch (e) { error.value = e.message || '保存失败' } finally { saving.value = false } }
</script>
<style scoped>
.quota-editor{position:relative;display:inline-block}.quota-button,.quota-popover button{min-height:32px;padding:6px 9px;border:1px solid var(--smart-border);border-radius:6px;background:var(--smart-surface);color:var(--smart-text);cursor:pointer}.quota-popover{position:absolute;z-index:3;right:0;top:38px;width:210px;display:grid;gap:9px;padding:12px;border:1px solid var(--smart-border);background:var(--smart-surface);box-shadow:0 12px 28px rgba(0,0,0,.18)}.quota-popover label{display:grid;gap:4px;font-size:11px;color:var(--smart-muted)}.quota-popover input{height:30px;padding:0 7px;border:1px solid var(--smart-border);background:var(--smart-bg);color:var(--smart-text)}.quota-popover div{display:flex;justify-content:flex-end;gap:6px}.quota-popover .save{background:var(--smart-primary);color:var(--smart-accent-foreground);border-color:transparent}.quota-popover p{margin:0;color:var(--smart-danger,#f08d9c);font-size:11px}
</style>
