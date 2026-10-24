<template><div v-if="issues.length" class="list"><article v-for="(issue,index) in issues" :key="index"><InspectorSeverityTag :value="issue.severity"/><strong>{{ issue.category }}</strong><p>{{ issue.reason }}</p><small>{{ issue.recommendation }}</small></article></div><AppEmpty v-else description="没有纠察问题"/></template>
<script setup>
import InspectorSeverityTag from './InspectorSeverityTag.vue'; import AppEmpty from '../common/AppEmpty.vue'
defineProps({ issues:{type:Array,default:()=>[]} })
</script>
<style scoped>.list{display:grid;gap:10px}.list article{padding:14px;border:1px solid var(--smart-border);border-radius:10px}.list strong{margin-left:8px}.list p{margin:10px 0 4px}.list small{color:var(--smart-muted)}</style>
