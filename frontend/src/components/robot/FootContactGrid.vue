<script setup>
/**
 * 蜘蛛 8 足触地指示：绿色 = 支撑相触地，橙色 = 摆动相抬腿。
 * 控制台遥测面板与设备详情弹窗共用。
 */
import { computed } from 'vue'

const props = defineProps({
  contacts: { type: Array, default: () => [] }
})

const feet = computed(() => props.contacts.map((contact) => Boolean(contact)))
</script>

<template>
  <div class="spider-feet">
    <span
      v-for="(contact, index) in feet"
      :key="index"
      class="spider-foot"
      :class="contact ? 'is-contact' : 'is-swing'"
      :title="`Leg${index} ${contact ? '触地' : '摆动'}`"
    >
      <i aria-hidden="true" />Leg{{ index }}
    </span>
  </div>
</template>

<style scoped>
.spider-feet {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--ds-space-2);
}

.spider-foot {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  font-variant-numeric: tabular-nums;
}

.spider-foot i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ds-color-border-strong);
}

.spider-foot.is-contact {
  border-color: var(--ds-color-success);
  color: var(--ds-color-text);
}

.spider-foot.is-contact i {
  background: var(--ds-color-success);
  box-shadow: 0 0 6px var(--ds-color-success);
}

.spider-foot.is-swing i {
  background: var(--ds-color-warning);
}
</style>
