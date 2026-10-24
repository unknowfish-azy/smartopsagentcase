<template><slot /></template>

<script setup>
import { computed, provide } from 'vue'

const props = defineProps({ state: { type: String, default: 'idle' } })
const stellarOcean = computed(() => ({ state: props.state, weight: { whale: 0.15, jellyfish: 0.55, spider: 0.8, stars: 1 } }))
provide('stellar-ocean', stellarOcean)
</script>
