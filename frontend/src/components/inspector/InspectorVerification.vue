<template><div class="verification"><strong>Verification</strong><span>{{ verification ? (verification.status || 'N/A') : 'NOT RUN' }}</span><p v-if="verification">Resolved: {{ verification.resolved ?? 'N/A' }}</p></div></template>
<script setup>defineProps({verification:{type:Object,default:null}})</script>
<style scoped>.verification{padding:16px;border:1px solid var(--smart-border);border-radius:10px}.verification span{float:right;font-weight:700}.verification p{margin-bottom:0;color:var(--smart-muted)}</style>
