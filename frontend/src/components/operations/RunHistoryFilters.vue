<template>
  <form class="filters" @submit.prevent="$emit('search')">
    <label>Trace ID<input v-model="filters.traceId" type="search" placeholder="完整或部分 Trace ID" />
    </label>
    <label>工具<input v-model="filters.toolId" type="search" placeholder="例如 k8s.pods" />
    </label>
    <label>状态<select v-model="filters.status">
      <option value="">全部状态</option>
      <option value="SUCCESS">执行成功</option>
      <option value="FAILED">执行失败</option>
      <option value="RUNNING">执行中</option>
      <option value="CANCELLED">已取消</option>
    </select>
    </label>
    <label>开始时间<input v-model="filters.startedFrom" type="datetime-local" />
    </label>
    <label>结束时间<input v-model="filters.startedTo" type="datetime-local" />
    </label>
    <div class="actions">
      <button class="button primary" type="submit">查询</button>
      <button class="button ghost" type="button" @click="$emit('reset')">重置</button>
    </div>
    <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>
  </form>
</template>

<script setup>
const filters = defineModel('filters', { type: Object, required: true })
defineProps({ formError: { type: String, default: '' } })
defineEmits(['search', 'reset'])
</script>

<style scoped>
.form-error {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--smart-danger, #e06b72);
  font-size: 12px;
}
.button {
  min-height: 40px;
  border: 1px solid var(--smart-border);
  border-radius: 8px;
  padding: 8px 15px;
  color: var(--smart-text);
  background: var(--smart-surface);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.primary {
  border-color: transparent;
  background: var(--smart-primary-strong);
  color: var(--smart-bg);
  font-weight: 650;
}
.ghost {
  border-color: transparent;
  background: transparent;
  color: var(--smart-muted);
}
button:disabled {
  opacity: .45;
  cursor: wait;
}
button:focus-visible,input:focus-visible,select:focus-visible {
  outline: 2px solid var(--smart-primary-strong);
  outline-offset: 3px;
}
.filters {
  display: grid;
  grid-template-columns: 1.2fr 1fr .8fr 1fr 1fr auto;
  align-items: end;
  gap: 12px;
  margin: 26px 0 18px;
  padding: 17px;
  border: 1px solid var(--smart-border);
  border-radius: 12px;
  background: var(--smart-surface);
}
.filters label {
  display: grid;
  gap: 7px;
  min-width: 0;
  color: var(--smart-muted);
  font-size: 11px;
}
.filters input,.filters select {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  min-height: 40px;
  border: 1px solid var(--smart-border);
  border-radius: 7px;
  padding: 8px 11px;
  color: var(--smart-text);
  background: var(--smart-bg);
}
.actions {
  display: flex;
  gap: 6px;
}
@media(max-width:1180px) {
  .filters {
    grid-template-columns: repeat(3,minmax(0,1fr));
  }
}
@media(max-width:800px) {
  .filters {
    grid-template-columns: 1fr 1fr;
  }
}
@media(max-width:520px) {
  .filters {
    grid-template-columns: 1fr;
  }
  .actions button {
    flex: 1;
  }
}
</style>
