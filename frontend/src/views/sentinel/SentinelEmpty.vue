<template>
  <section class="sentinel-empty" aria-live="polite">
    <h3>{{ title }}</h3>
    <p>{{ description }}</p>
    <slot />
  </section>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' }
})
</script>
