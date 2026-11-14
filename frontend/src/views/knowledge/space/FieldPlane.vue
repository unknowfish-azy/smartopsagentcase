<!--
  FieldPlane.vue — 单个世界平面（DOM），按 LOD 切换内部结构。

  DESIGN §6.1 LOD 表：
    far   → 无正文（仅当父域簇外框存在时才渲染），aria-hidden，不参与 Tab 序
    mid   → 标题 + type chip（2 元素）
    near  → 标题 + 摘要 + tags（3–6 元素）
    focus → near + 选中态边框；正文走侧栏（2D，在 FieldStage 外）

  命中区 ≥ 44px（DESIGN §8）。aria-label 复述位置与身份。
  空间 transform：translate3d(x, y, z) + preserve-3d（让子元素继续保留 3D）
-->
<script setup>
import { computed } from 'vue'

const props = defineProps({
  plane:     { type: Object, required: true },    // useFieldLayout 输出的 FieldPlane
  lod:       { type: String, default: 'mid' },    // 'far' | 'mid' | 'near' | 'focus'
  isFocus:   { type: Boolean, default: false },
  hit:       { type: Boolean, default: false },   // 检索命中
})

const emit = defineEmits(['click', 'keydown'])

// LOD 决定子元素数（DESIGN P3：表示替换，不是缩放）
const showTitle    = computed(() => ['mid', 'near', 'focus'].includes(props.lod))
const showTypeChip = computed(() => ['mid', 'near', 'focus'].includes(props.lod))
const showSummary  = computed(() => ['near', 'focus'].includes(props.lod))
const showTags     = computed(() => ['near', 'focus'].includes(props.lod))

// far / mid 不参与 Tab 序，aria-hidden
const interactive = computed(() => ['near', 'focus'].includes(props.lod))

// 3D 定位
const planeStyle = computed(() => ({
  // 相对世界原点定位（世界已 translate 回 center）
  transform: `translate3d(${props.plane.x}px, ${-props.plane.y}px, ${props.plane.z}px)`,
  width: `${props.plane.w}px`,
  height: `${props.plane.h}px`,
}))

const isInsight = computed(() => props.plane.kind === 'insight')
</script>

<template>
  <div
    v-if="plane"
    class="field-plane"
    :class="{
      'field-plane--insight': isInsight,
      'field-plane--knowledge': !isInsight,
      'field-plane--hit': hit,
      'field-plane--focus': isFocus,
      'field-plane--mid': lod === 'mid',
      'field-plane--near': lod === 'near' || lod === 'focus',
    }"
    :style="planeStyle"
    :data-kind="plane.kind"
    :data-lod="lod"
    :aria-hidden="!interactive"
    :tabindex="interactive ? 0 : -1"
    :aria-label="interactive
      ? (isInsight
          ? `洞察层 · ${plane.insightId}，引用知识 ${plane.kind}`
          : `知识层 · ${plane.domainId || ''} · ${plane.atomId || ''}`)
      : ''"
    role="button"
    @click="emit('click', plane)"
    @keydown.enter.prevent="emit('keydown', plane)"
  >
    <!-- LOD far：不渲染 DOM 内容，让父级域簇外框/洞察带代表 -->
    <template v-if="lod !== 'far'">
      <!-- L1 知识平面：accent 顶边 2px -->
      <span v-if="!isInsight" class="fp-accent-top"></span>

      <!-- L2 洞察平面：顶边 1px 规则线 -->
      <span v-if="isInsight" class="fp-canopy-top"></span>

      <div class="fp-body">
        <!-- mid/near/focus 都显示标题 -->
        <span v-if="showTitle" class="fp-title">
          {{ isInsight ? `[洞察]` : '' }}{{ plane.atomId || plane.insightId }}
        </span>

        <!-- near/focus 显示摘要 -->
        <span v-if="showSummary" class="fp-summary">
          {{ plane.atomId || '' }}
        </span>

        <!-- mid/near/focus 显示 type chip -->
        <span v-if="showTypeChip" class="fp-type-chip">
          {{ isInsight ? 'INSIGHT' : 'KNOWLEDGE' }}
        </span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.field-plane {
  position: absolute;
  transform-style: preserve-3d;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: stretch;
  border-radius: var(--ds-radius-md);
  box-sizing: border-box;
  min-height: 44px;            /* 触控命中区 DESIGN §8 */
  min-width: 44px;
  transition: border-color 120ms var(--ds-ease-out), box-shadow 120ms var(--ds-ease-out);
  cursor: pointer;
}

.field-plane--knowledge {
  background: var(--ds-surface, #071018);
  border: 1px solid var(--ds-color-border);
  box-shadow: var(--ds-elevation-1);
}
.field-plane--knowledge:hover {
  border-color: var(--ds-color-border-strong);
  box-shadow: var(--ds-elevation-2);
}
.fp-accent-top {
  height: 2px;
  background: var(--ds-accent, #7ad7f5);
  border-radius: var(--ds-radius-md) var(--ds-radius-md) 0 0;
}

.field-plane--insight {
  background: transparent;
  border: 1px solid transparent;
}
.fp-canopy-top {
  height: 1px;
  background: rgba(159,190,207,.18);
  margin-bottom: 4px;
}

.field-plane--hit {
  border-color: var(--ds-focus-ring-color, #7ad7f5);
  box-shadow: 0 0 0 1px var(--ds-focus-ring-color, rgba(122,215,245,.35));
}
.field-plane--focus {
  border-color: var(--ds-focus-ring-color, #7ad7f5);
  box-shadow: var(--ds-elevation-3, 0 8px 24px rgba(0,0,0,.4));
  outline: 2px solid var(--ds-focus-ring-color, #7ad7f5);
  outline-offset: 1px;
}

.fp-body {
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  overflow: hidden;
}

.fp-title {
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1.35;
  color: var(--ds-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.fp-summary {
  font-size: 11.5px;
  line-height: 1.45;
  color: var(--ds-color-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.fp-type-chip {
  align-self: flex-start;
  font-size: 10px;
  letter-spacing: .04em;
  padding: 2px 5px;
  border: 1px solid var(--ds-hairline);
  border-radius: var(--ds-radius-sm);
  color: var(--ds-semantic-neutral);
  font-family: var(--ds-font-mono);
  white-space: nowrap;
}

.field-plane--mid .fp-body { gap: 3px; }
.field-plane--mid .fp-summary { display: none; }
</style>
