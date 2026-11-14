<!--
  InsightCanopy.vue — L2 洞察层（DESIGN §3.2 / §3.3 / §6.1）。

  悬浮字幕：自然语言结论 / confidence 标记 / 绑定条数。
  无实底，只有顶边 1px 规则线。

  confidence 标记（§3.2）：
    derived / corroborates → 实心小圆点（--ds-accent）
    contradicts            → 菱形虚边（status 警示色）
    operational            → 空心圆点（--ds-text-secondary）

  「未绑定」必须显式成文，不得隐藏。
-->
<script setup>
import { computed } from 'vue'

const props = defineProps({
  insight:   { type: Object, required: true },
  position:  { type: Object, default: () => ({ x: 0, y: 0 }) },
  lod:       { type: String, default: 'mid' },
})

const emit = defineEmits(['click'])

const bindingMode = computed(() => props.insight?.binding?.mode || 'operational')
const atomsCount  = computed(() => props.insight?.binding?.atoms?.length ?? 0)
const confidence  = computed(() => props.insight?.confidence || 'derived')
const isUnbound   = computed(() =>
  bindingMode.value === 'operational' || atomsCount.value === 0
)

const markClass = computed(() => ({
  'ic-mark--derived':      bindingMode.value === 'derived',
  'ic-mark--corroborates': bindingMode.value === 'corroborates',
  'ic-mark--contradicts':  bindingMode.value === 'contradicts',
  'ic-mark--operational':  bindingMode.value === 'operational',
}))
</script>

<template>
  <div
    class="insight-canopy"
    :class="{ 'ic--unbound': isUnbound, 'ic--focus': lod === 'focus' }"
    :style="{ transform: `translate3d(${position.x}px, ${-position.y}px, 0)` }"
    role="button"
    tabindex="0"
    :aria-label="`洞察层 · ${insight.id}，置信度 ${confidence}，${isUnbound ? '未绑定知识' : `绑定 ${atomsCount} 条知识`}`"
    @click="emit('click', insight)"
    @keydown.enter.prevent="emit('click', insight)"
  >
    <!-- 顶边 1px 规则线 -->
    <div class="ic-top"></div>

    <div class="ic-body">
      <!-- confidence 标记 -->
      <span class="ic-mark" :class="markClass"></span>

      <!-- 洞察标题 / 标签 -->
      <div class="ic-title-row">
        <span v-if="insight.badge" class="ic-badge">{{ insight.badge }}</span>
        <span class="ic-title">{{ insight.title || insight.id }}</span>
      </div>

      <!-- 绑定状态 -->
      <div class="ic-bind-row" v-if="!isUnbound">
        <span class="ic-bind-text">引用 {{ atomsCount }} 条知识</span>
      </div>
      <div class="ic-bind-row ic-bind-row--unbound" v-else>
        <span class="ic-bind-text">未绑定知识（纯运行态）</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.insight-canopy {
  position: absolute;
  transform-style: preserve-3d;
  background: transparent;
  border-radius: var(--ds-radius-md);
  min-width: 220px;
  max-width: 320px;
  padding: 0 12px 10px 12px;
  cursor: pointer;
  transition: border-color 120ms var(--ds-ease-out), box-shadow 120ms var(--ds-ease-out);
}

.ic-top {
  height: 1px;
  width: 100%;
  background: rgba(159,190,207,.18);
  margin-bottom: 8px;
}

.ic-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  backdrop-filter: none;  /* DESIGN §3.3：不准用 */
}

.ic-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ic-mark {
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.ic-mark--derived,
.ic-mark--corroborates {
  background: var(--ds-accent, #7ad7f5);
}
.ic-mark--contradicts {
  width: 10px; height: 10px;
  background: transparent;
  border: 1px solid var(--ds-semantic-danger, #f56c6c);
  transform: rotate(45deg);
  border-radius: 0;
}
.ic-mark--operational {
  background: transparent;
  border: 1px solid var(--ds-text-secondary, rgba(159,190,207,.45));
}

.ic-badge {
  font-size: 10px;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--ds-semantic-neutral);
  font-family: var(--ds-font-mono);
  padding: 1px 5px;
  border: 1px solid var(--ds-hairline);
  border-radius: var(--ds-radius-sm);
}

.ic-title {
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1.3;
  color: var(--ds-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ic-bind-row {
  display: flex;
  gap: 4px;
  align-items: center;
}
.ic-bind-text {
  font-size: 11px;
  color: var(--ds-text-secondary);
  font-family: var(--ds-font-mono);
}
.ic-bind-row--unbound .ic-bind-text {
  color: var(--ds-semantic-neutral);
  font-style: italic;
}

.ic--focus {
  background: rgba(10,14,19,.6);
  box-shadow: var(--ds-elevation-3);
}
.ic--unbound {
  opacity: .85;
}
</style>
