<template><div class="risk"><span>Risk</span><InspectorSeverityTag :value="severity"/><small>{{ requiresHuman ? 'Human review required' : 'Automated review' }}</small></div></template>
<script setup>import InspectorSeverityTag from './InspectorSeverityTag.vue'; defineProps({severity:{type:String,default:'INFO'},requiresHuman:Boolean})</script>
<style scoped>.risk{display:flex;align-items:center;gap:10px;padding:14px;border:1px solid var(--smart-border);border-radius:10px}.risk small{margin-left:auto;color:var(--smart-muted)}</style>
