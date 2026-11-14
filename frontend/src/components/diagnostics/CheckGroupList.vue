<template>
  <section class="hc-card" aria-labelledby="hc-checks-title">
    <header class="hc-card-head">
      <h2 id="hc-checks-title">检查项</h2>
      <span class="hc-overline">{{ totalChecks }} 项 · {{ scopeText }}</span>
    </header>

    <div class="hc-groups">
      <section
        v-for="groupKey in visibleGroupKeys"
        :key="groupKey"
        class="hc-group"
        :class="{ 'hc-group--collapsed': collapsedGroups.has(groupKey) }"
      >
        <button
          class="hc-group-head"
          type="button"
          :aria-expanded="!collapsedGroups.has(groupKey)"
          @click="toggleGroup(groupKey)"
        >
          <span class="hc-caret">{{ collapsedGroups.has(groupKey) ? '▸' : '▾' }}</span>
          <span class="hc-group-dot" :style="{ background: GROUP_META[groupKey].colorToken }" aria-hidden="true"></span>
          <b>{{ GROUP_META[groupKey].title }}</b>
          <span class="hc-group-hint">{{ GROUP_META[groupKey].hint }}</span>
          <span class="hc-group-count">{{ buckets[groupKey].length }}</span>
        </button>
        <CheckRow
          v-for="check in buckets[groupKey]"
          :key="check.id"
          :check="check"
          :stale="stale"
          @go-tool="$emit('go-tool', $event)"
        />
      </section>

      <!-- FORBIDDEN 单独一行 -->
      <div v-if="forbidden.length" class="hc-forbidden-line">
        <span class="hc-st hc-st-forbidden hc-st-outline" aria-hidden="true">⌾</span>
        {{ forbidden.length }} 项无权查看（需要更高权限）
        <span class="hc-forbidden-labels">：{{ forbidden.map(f => f.label).join('、') }}</span>
      </div>

      <!-- 空状态 -->
      <div v-if="totalChecks === 0 && !loading" class="hc-empty">
        暂无检查结果。点击「重新检查」获取当前状态。
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import CheckRow from './CheckRow.vue'
import { partitionChecks, GROUP_ORDER, GROUP_META } from './healthGroups.js'

const props = defineProps({
  checks: { type: Array, default: () => [] },
  admin: { type: Boolean, default: false },
  stale: { type: Boolean, default: false },
  loading: { type: Boolean, default: false }
})

defineEmits(['go-tool'])

const collapsedGroups = ref(new Set(['pass']))

const partitioned = computed(() => partitionChecks(props.checks))
const buckets = computed(() => partitioned.value.buckets)
const forbidden = computed(() => partitioned.value.forbidden)

// 只渲染非空的组，保持 GROUP_ORDER 顺序
const visibleGroupKeys = computed(() =>
  GROUP_ORDER.filter(k => buckets.value[k] && buckets.value[k].length > 0)
)

const totalChecks = computed(() => props.checks.length)

const scopeText = computed(() => props.admin ? '管理员范围' : '当前用户范围')

function toggleGroup(key) {
  const s = new Set(collapsedGroups.value)
  s.has(key) ? s.delete(key) : s.add(key)
  collapsedGroups.value = s
}

// 对外暴露：ConclusionBar 的 jump-group 事件需要能展开并滚动到目标组
defineExpose({
  openGroup(key) {
    collapsedGroups.value = new Set(collapsedGroups.value).delete(key) || collapsedGroups.value
    // 注意：上面 delete 返回 undefined，这里简单处理
    const s = new Set(collapsedGroups.value)
    s.delete(key)
    collapsedGroups.value = s
  },
  scrollToGroup(key) {
    requestAnimationFrame(() => {
      const el = document.querySelector(`[data-hc-group="${key}"]`)
      if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    })
  }
})
</script>

<style scoped>
.hc-card {
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-surface-raised);
  overflow: hidden;
}
.hc-card-head {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--ds-hairline);
}
.hc-card-head h2 {
  margin: 0;
  font-size: var(--ds-type-h3-size);
  font-weight: var(--ds-type-h3-weight);
}
.hc-overline {
  color: var(--ds-semantic-neutral);
  font: var(--ds-type-overline-size)/1 var(--ds-font-mono);
  letter-spacing: .12em;
  text-transform: uppercase;
  margin-left: auto;
}

.hc-groups { /* container */ }

.hc-group { border-top: 1px solid var(--ds-hairline); }
.hc-group:first-of-type { border-top: none; }

.hc-group-head {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 11px 16px;
  text-align: left;
  color: var(--ds-color-muted); font-size: 12.5px;
  border: none; background: transparent;
  cursor: pointer;
  transition: background var(--ds-duration-micro) var(--ds-ease-out),
              color var(--ds-duration-micro) var(--ds-ease-out);
}
.hc-group-head:hover { background: rgba(232, 242, 247, .04); color: var(--ds-color-text); }
.hc-caret {
  width: 10px; color: var(--ds-semantic-neutral);
  transition: transform var(--ds-duration-micro) var(--ds-ease-out);
  font-family: var(--ds-font-mono);
}
.hc-group--collapsed .hc-caret { transform: rotate(-90deg); }
.hc-group--collapsed .hc-row { display: none; }
.hc-group-dot {
  width: 8px; height: 8px; border-radius: 50%;
  flex: 0 0 auto;
}
.hc-group-head b { color: var(--ds-color-text); font-weight: 500; }
.hc-group-hint { color: var(--ds-semantic-neutral); font-size: 11.5px; }
.hc-group-count {
  margin-left: auto; color: var(--ds-semantic-neutral);
  font-variant-numeric: tabular-nums;
}

.hc-forbidden-line {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px;
  border-top: 1px solid var(--ds-hairline);
  color: var(--ds-semantic-neutral); font-size: 12px;
}
.hc-forbidden-labels { color: var(--ds-semantic-neutral); }

.hc-empty {
  padding: 32px 16px;
  text-align: center;
  color: var(--ds-semantic-neutral);
  font-size: 13px;
  line-height: 1.6;
}

@media (max-width: 767px) {
  .hc-card-head { padding: 12px 14px; }
  .hc-group-head { padding: 10px 14px; font-size: 12px; }
  .hc-group-hint { display: none; }
}
</style>
