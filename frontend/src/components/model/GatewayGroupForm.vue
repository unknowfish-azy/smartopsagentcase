<template>
  <form class="group-form" @submit.prevent="submit">
    <label>组标识<input v-model.trim="form.slug" required placeholder="ops-default"></label>
    <label>显示名称<input v-model.trim="form.name" required placeholder="运维模型组"></label>
    <label>连接 ID<input v-model.number="form.connectionId" required type="number" min="1"></label>
    <label>请求数 / 24h<input v-model="form.requestLimit24h" type="number" min="0" placeholder="不限"></label>
    <label>Token / 24h<input v-model="form.tokenLimit24h" type="number" min="0" placeholder="不限"></label>
    <button class="gateway-action" type="submit" :disabled="saving">{{ saving ? '保存中' : '保存模型组' }}</button>
  </form>
</template>
<script setup>
import { reactive } from 'vue'
defineProps({ saving: Boolean })
const emit = defineEmits(['submit'])
const form = reactive({ slug: '', name: '', connectionId: null, requestLimit24h: '', tokenLimit24h: '' })
function submit() { emit('submit', { ...form, requestLimit24h: form.requestLimit24h === '' ? null : Number(form.requestLimit24h), tokenLimit24h: form.tokenLimit24h === '' ? null : Number(form.tokenLimit24h) }) }
</script>
<style scoped>
.group-form{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;align-items:end}.group-form label{display:grid;gap:7px;font-size:12px;color:var(--smart-muted)}.group-form input{height:40px;box-sizing:border-box;padding:0 10px;border:1px solid var(--smart-border);border-radius:7px;background:var(--smart-bg);color:var(--smart-text)}.gateway-action{min-height:40px;padding:9px 14px;border:0;border-radius:7px;background:var(--smart-primary);color:var(--smart-accent-foreground);cursor:pointer}@media(max-width:700px){.group-form{grid-template-columns:1fr}}
</style>
