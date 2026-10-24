<template>
  <el-tag
      :type="tagType"
      effect="light"
  >
    {{ label }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: {
    type: String,
    default: 'UNKNOWN'
  }
})

const map = {
  ONLINE: {
    label: '在线',
    type: 'success'
  },

  OFFLINE: {
    label: '离线',
    type: 'danger'
  },

  WARNING: {
    label: '告警',
    type: 'warning'
  },

  UNKNOWN: {
    label: '未知',
    type: 'info'
  }
}

const current = computed(() =>
    map[props.status] || map.UNKNOWN
)

const label = computed(
    () => current.value.label
)

const tagType = computed(
    () => current.value.type
)
</script>