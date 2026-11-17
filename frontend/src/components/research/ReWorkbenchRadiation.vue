<template>
  <section
    class="rewb-radia"
    :class="{ 'rewb-radia--live': activeCount > 0 }"
    aria-label="REA 工具辐射图"
  >
    <div class="rewb-radia__head">
      <h2>REA 工具辐射图</h2>
      <span class="rewb-radia__hint">{{ hint }}</span>
    </div>

    <!-- 横向滚动区必须可键盘聚焦，否则 axe scrollable-region-focusable serious -->
    <div
      class="rewb-radia__scroll"
      role="region"
      aria-label="REA 工具辐射图（可横向滚动）"
      tabindex="0"
    >
      <svg
        class="rewb-radia__svg"
        viewBox="0 0 900 380"
        role="img"
        :aria-label="ariaLabel"
      >
        <!-- 中心圆环：6 段弧对应 6 个逆向阶段，颜色为阶段语义色（非装饰霓虹） -->
        <g aria-hidden="true">
          <circle
            v-for="arc in arcs"
            :key="arc.stage.id"
            :cx="CX" :cy="CY" :r="arc.r"
            fill="none"
            :stroke="arc.color"
            :stroke-dasharray="arc.dash"
            :stroke-dashoffset="arc.offset"
            stroke-width="4"
            stroke-linecap="round"
            opacity=".72"
          />
          <!-- 强效果层：中心能量核，仅在命中管线时运转（无事件静默） -->
          <circle class="rewb-radia__core-halo" :cx="CX" :cy="CY" r="50" fill="none" stroke="rgba(94,203,200,.34)" stroke-width="1" />
          <circle class="rewb-radia__core-scan" :cx="CX" :cy="CY" r="66" fill="none" stroke="rgba(231,183,99,.9)" stroke-width="3" stroke-linecap="round" stroke-dasharray="34 380" />
          <circle :cx="CX" :cy="CY" :r="72" fill="none" stroke="rgba(138,160,180,.34)" stroke-width="1" />
          <circle :cx="CX" :cy="CY" :r="57" fill="none" stroke="rgba(138,160,180,.22)" stroke-width="1" stroke-dasharray="2 6" />
          <text class="rewb-radia__brand" :x="CX" :y="CY - 4" text-anchor="middle">REA</text>
          <text class="rewb-radia__count" :x="CX" :y="CY + 15" text-anchor="middle">{{ tools.length }} TOOLS</text>
        </g>

        <!-- 15 条流线：起点同为圆环右缘，终点为真实工具；只有命中当前管线才点亮 -->
        <g v-for="(ray, index) in rays" :key="ray.tool.id" class="rewb-ray-group" :class="{ 'rewb-ray--on': ray.active }">
          <path
            class="rewb-ray"
            :class="{ 'rewb-ray--active': ray.active }"
            :d="ray.d"
            :stroke="ray.color"
          />
          <!-- 强效果层：流光点沿路径传导 + 端点扩散环，按真实管线顺序错峰 -->
          <path
            class="rewb-ray__spark"
            :d="ray.d"
            :stroke="ray.color"
            :style="{ '--ray-order': ray.order }"
          />
          <circle
            class="rewb-ray__pulse"
            :cx="END_X" :cy="ray.y" r="4"
            :stroke="ray.color"
            :style="{ '--ray-order': ray.order }"
          />
          <circle class="rewb-ray__halo" :cx="END_X" :cy="ray.y" r="7" :stroke="ray.color" />
          <circle class="rewb-ray__dot" :cx="END_X" :cy="ray.y" r="3" :fill="ray.color" />
          <text class="rewb-ray__label" :x="END_X + 13" :y="ray.y + 4">[{{ pad(index + 1) }}] {{ ray.tool.name }}</text>
        </g>
      </svg>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import {
  CX,
  CY,
  END_X,
  buildArcs,
  buildRays,
  radiationAriaLabel,
  radiationHint
} from '../../domain/research/reWorkbenchRadiation.js'

/**
 * REA 工具辐射图（强效果档）：把参考内容里「圆环 + 多彩流线」的视觉语义
 * 改造成真实数据可视化 + 分级渲染。
 *
 * 红线：
 * - 流线不是装饰——只有命中当前目标管线的工具才点亮/流动；未选目标时全部静默（禁假繁忙）。
 * - 零新数据契约：工具、阶段、命中集合、管线顺序全部由宿主传现有目录数据。
 * - 强渲染只在 visualMode === 'balanced' 生效；轻量/减少动态/系统减少动态/掉帧/窄屏全部退静态。
 * - 纯 SVG + CSS，无 canvas / three.js / blur 滤镜 / 新增依赖。
 * - 几何与颜色逻辑在 domain/research/reWorkbenchRadiation.js（纯函数，已配单测）。
 */
const props = defineProps({
  tools: { type: Array, required: true },
  stages: { type: Array, required: true },
  activeIds: { type: [Set, Array], default: () => new Set() },
  activeOrder: { type: Array, default: () => [] },
  activeLabel: { type: String, default: '' }
})

const pad = n => String(n).padStart(2, '0')

const activeSet = computed(() => props.activeIds instanceof Set ? props.activeIds : new Set(props.activeIds))
const activeCount = computed(() => activeSet.value.size)

const hint = computed(() => radiationHint(props.tools.length, activeCount.value, props.activeLabel))
const ariaLabel = computed(() => radiationAriaLabel(props.tools.length, activeCount.value, props.activeLabel))

const arcs = computed(() => buildArcs(props.stages))
const rays = computed(() => buildRays(props.tools, activeSet.value, props.activeOrder))
</script>

<style scoped>
.rewb-radia {
  border: 1px solid var(--smart-border, #e5e7eb);
  border-radius: 12px;
  background: var(--smart-surface, #fff);
  padding: 12px 14px;
  display: grid;
  gap: 8px;
}
.rewb-radia__head { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.rewb-radia__head h2 { margin: 0; font-size: 15px; }
.rewb-radia__hint { color: var(--smart-muted, #6b7280); font-size: 12px; }
.rewb-radia__scroll { overflow-x: auto; }
.rewb-radia__svg { display: block; width: 100%; min-width: 680px; height: auto; }

.rewb-radia__brand { fill: var(--smart-text, #1f2937); font: 700 22px var(--font-mono, Consolas, monospace); letter-spacing: .12em; }
.rewb-radia__count { fill: var(--smart-muted, #6b7280); font: 10px var(--font-mono, Consolas, monospace); letter-spacing: .16em; }

/* ---------- 基线：低透明度静态细线，无事件静默 ---------- */
.rewb-ray { fill: none; stroke-width: 1.6; stroke-opacity: .10; stroke-linecap: round; transition: stroke-opacity .25s ease, stroke-width .25s ease; }
.rewb-ray--active { stroke-width: 2; stroke-opacity: .85; stroke-dasharray: 8 14; animation: rewb-ray-flow 1.6s linear infinite; }
@keyframes rewb-ray-flow { to { stroke-dashoffset: -44; } }
.rewb-ray__halo { fill: none; stroke-width: 1; opacity: 0; }
.rewb-ray__dot { opacity: .25; transition: opacity .25s ease; }
.rewb-ray--on .rewb-ray__halo { opacity: .55; }
.rewb-ray--on .rewb-ray__dot { opacity: 1; }
.rewb-ray__label { fill: var(--smart-muted, #6b7280); font: 11px var(--font-mono, Consolas, monospace); opacity: .32; }
.rewb-ray--on .rewb-ray__label { fill: var(--smart-text, #1f2937); opacity: 1; font-weight: 700; }

/* ---------- 强效果层：只在 balanced 档 + 命中管线时运行 ----------
   与 motion-strong.css 同规矩：强效果档仅 visualMode === 'balanced' 生效。
   三层增强：中心扫描核 / 沿路径流光点 / 端点扩散环；均按真实管线顺序错峰。 */
.rewb-radia__core-halo,
.rewb-radia__core-scan,
.rewb-ray__spark,
.rewb-ray__pulse { opacity: 0; pointer-events: none; }
.rewb-radia__core-halo,
.rewb-radia__core-scan { transform-box: fill-box; transform-origin: center; }
.rewb-ray__pulse { transform-box: fill-box; transform-origin: center; }
.rewb-ray__spark { fill: none; stroke-width: 3; stroke-linecap: round; stroke-dasharray: 10 1000; stroke-dashoffset: 1000; }

.app-layout[data-visual-mode='balanced'] .rewb-radia--live .rewb-radia__core-halo {
  opacity: 1;
  animation: rewb-core-breathe 2.8s ease-in-out infinite;
}
.app-layout[data-visual-mode='balanced'] .rewb-radia--live .rewb-radia__core-scan {
  opacity: .9;
  animation: rewb-core-spin 5s linear infinite;
}
@keyframes rewb-core-breathe { 0%, 100% { opacity: .45; transform: scale(1); } 50% { opacity: 1; transform: scale(1.14); } }
@keyframes rewb-core-spin { to { transform: rotate(360deg); } }

.app-layout[data-visual-mode='balanced'] .rewb-ray--on .rewb-ray__spark {
  opacity: 1;
  animation: rewb-ray-spark 1.9s linear infinite;
  animation-delay: calc(var(--ray-order, 0) * 80ms);
}
@keyframes rewb-ray-spark { from { stroke-dashoffset: 1000; } to { stroke-dashoffset: -10; } }

.app-layout[data-visual-mode='balanced'] .rewb-ray--on .rewb-ray__pulse {
  animation: rewb-ray-pulse 2.4s ease-out infinite;
  animation-delay: calc(var(--ray-order, 0) * 80ms);
}
@keyframes rewb-ray-pulse { 0% { transform: scale(1); opacity: .75; } 70%, 100% { transform: scale(3.2); opacity: 0; } }

/* ---------- 四重降级：强效果层全部退场，静态连线与文字保留 ---------- */
@media (prefers-reduced-motion: reduce) {
  .rewb-ray, .rewb-ray__dot { transition: none; }
  .rewb-ray--active { animation: none; stroke-dasharray: none; stroke-opacity: .7; }
  .rewb-radia__core-halo, .rewb-radia__core-scan, .rewb-ray__spark, .rewb-ray__pulse { animation: none !important; opacity: 0 !important; }
}
.app-layout[data-visual-mode='lightweight'] .rewb-ray--active,
.app-layout[data-visual-mode='reduced-motion'] .rewb-ray--active,
[data-motion-degraded='true'] .rewb-ray--active {
  animation: none;
  stroke-dasharray: none;
  stroke-opacity: .7;
}
[data-motion-degraded='true'] .rewb-radia__core-halo,
[data-motion-degraded='true'] .rewb-radia__core-scan,
[data-motion-degraded='true'] .rewb-ray__spark,
[data-motion-degraded='true'] .rewb-ray__pulse { animation: none !important; opacity: 0 !important; }
@media (max-width: 768px) {
  .rewb-radia { padding: 10px; }
  .rewb-radia__svg { min-width: 620px; }
  .rewb-radia__hint { font-size: 11px; }
  .rewb-radia__core-halo, .rewb-radia__core-scan, .rewb-ray__spark, .rewb-ray__pulse { animation: none !important; opacity: 0 !important; }
}
</style>
