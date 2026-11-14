<template>
  <div v-if="flags.length" class="hc-evidence" role="note">
    <b>证据不完整</b>
    <span>· 下面的结论基于不完整的数据</span>
    <ul class="hc-evidence-list">
      <li v-for="f in flags" :key="f.key">
        {{ f.text }} — <span class="hc-evidence-why">{{ f.why }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { bannerFlags } from './evidenceBanner.js'

const props = defineProps({
  // 四个后端标志位（DESIGN §8.3）
  permissionDenied: { type: Boolean, default: false },
  dataMissing:      { type: Boolean, default: false },
  unverified:       { type: Boolean, default: false },
  truncated:        { type: Boolean, default: false }
})

const flags = computed(() => bannerFlags({
  permissionDenied: props.permissionDenied,
  dataMissing: props.dataMissing,
  unverified: props.unverified,
  truncated: props.truncated
}))
</script>

<style scoped>
.hc-evidence {
  margin: 14px 16px;
  padding: 11px 13px;
  border-radius: var(--ds-radius-md);
  border: 1px solid color-mix(in srgb, var(--ds-semantic-warning) 34%, transparent);
  background: color-mix(in srgb, var(--ds-semantic-warning) 7%, transparent);
  color: var(--ds-color-muted);
  font-size: 12px;
  line-height: 1.6;
}
.hc-evidence b {
  color: var(--ds-semantic-warning);
  font-weight: 500;
}
.hc-evidence-list {
  margin: 6px 0 0;
  padding-left: 16px;
}
.hc-evidence-list li {
  margin: 2px 0;
}
.hc-evidence-why {
  color: var(--ds-semantic-neutral);
}
</style>
