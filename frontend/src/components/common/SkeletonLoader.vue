<template>
  <div
    class="skeleton"
    :class="[
      `skeleton--${variant}`,
      { 'skeleton--animate': animate, 'skeleton--aria-pulse': ariaPulse }
    ]"
    :style="inlineStyle"
    :aria-hidden="ariaHidden"
    :role="ariaHidden ? undefined : 'status'"
    :aria-label="ariaHidden ? undefined : ariaLabel"
  ></div>
</template>

<script setup>

/**
 * Skeleton loading placeholder (T20, §3.3 微交互系统)
 *
 * @prop {'text' | 'circle' | 'rect' | 'bar'} variant - 骨架形状
 * @prop {string} width - 内联宽度（如 '100%' / '200px'）
 * @prop {string} height - 内联高度（如 '24px'）
 * @prop {string} radius - 圆角覆盖（如 '12px'）
 * @prop {string} inlineStyle - 自由内联样式 JSON string，覆盖 width/height/radius
 * @prop {boolean} animate - 是否做 shimmer 动画（默认 true；prefers-reduced-motion 自动禁用）
 * @prop {boolean} ariaPulse - 否，固定骨架不添加 role=status
 * @prop {boolean} ariaHidden - 是否 aria-hidden（默认 true；作为装饰使用）
 * @prop {string} ariaLabel - role=status 时的 aria-label
 */
defineProps({
  variant: { type: String, default: 'rect' },
  width: { type: String, default: '100%' },
  height: { type: String, default: '16px' },
  radius: { type: String, default: '' },
  inlineStyle: { type: String, default: '' },
  animate: { type: Boolean, default: true },
  ariaPulse: { type: Boolean, default: true },
  ariaHidden: { type: Boolean, default: true },
  ariaLabel: { type: String, default: '加载中' }
})

</script>

<style scoped>
.skeleton {
  position: relative;
  display: block;
  background: var(--ds-surface-overlay, var(--ds-color-surface-raised));
  border-radius: var(--ds-radius-sm, 4px);
  /* 基线：极柔 hairline + 微透明底色，不靠 blur */
  border: 1px solid var(--ds-hairline, rgba(255,255,255,.04));
  overflow: hidden;
}

.skeleton--circle { border-radius: 999px; }
.skeleton--rect { border-radius: var(--ds-radius-sm, 4px); }
.skeleton--text {
  height: 1em; width: 60%; max-width: 160px;
  border-radius: 3px;
}
.skeleton--bar {
  height: 24px; border-radius: var(--ds-radius-sm, 4px);
}

/* Shimmer 动画：150ms T18 令牌节奏 */
.skeleton--animate::after {
  content: '';
  position: absolute; inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(
    90deg,
    transparent 0%,
    color-mix(in srgb, var(--ds-color-primary, #2496ed) 10%, transparent) 45%,
    color-mix(in srgb, var(--ds-color-primary, #2496ed) 22%, transparent) 50%,
    color-mix(in srgb, var(--ds-color-primary, #2496ed) 10%, transparent) 55%,
    transparent 100%
  );
  animation: skeleton-shimmer 1.4s var(--ds-ease-out, cubic-bezier(.22,1,.36,1)) infinite;
}

@keyframes skeleton-shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

@media (prefers-reduced-motion: reduce) {
  .skeleton--animate::after { animation: none; }
}
</style>
