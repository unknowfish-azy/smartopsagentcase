<template>
  <p class="sentinel-notice" :class="`sentinel-notice--${tone}`" role="status">
    <strong>{{ title }}</strong><span v-if="detail">{{ detail }}</span>
  </p>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  detail: { type: String, default: '' },
  tone: { type: String, default: 'info' } // info | warn | danger | ok
})
</script>
