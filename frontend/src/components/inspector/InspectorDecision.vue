<template><section class="decision"><InspectorSeverityTag :value="event.status"/><h3>{{ event.reason || 'N/A' }}</h3><p>{{ event.recommendation || '暂无建议' }}</p></section></template>
<script setup>import InspectorSeverityTag from './InspectorSeverityTag.vue'; defineProps({event:{type:Object,default:()=>({})}})</script>
<style scoped>.decision{padding:18px;border:1px solid var(--smart-border);border-radius:12px}.decision h3{margin:12px 0 6px}.decision p{margin:0;color:var(--smart-muted)}</style>
