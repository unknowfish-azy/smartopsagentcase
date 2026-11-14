<template>
  <div class="comp" aria-hidden="true">
    <span class="comp-diag"></span>
    <span class="comp-diag comp-diag--soft"></span>

    <span class="comp-frame"></span>

    <svg class="comp-arc" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <path d="M0 100A100 100 0 0 1 100 0" class="arc-line arc-line--outer" />
      <path d="M28 100A72 72 0 0 1 100 28" class="arc-line" />
      <path d="M52 100A48 48 0 0 1 100 52" class="arc-line arc-line--inner" />
    </svg>

    <span class="comp-bar"></span>

    <span class="comp-measure">
      <i
        v-for="tick in 11"
        :key="tick"
        :class="{ major: tick % 5 === 1 }"
        :style="{ top: `${(tick - 1) * 10}%` }"
      ></i>
      <b>α</b>
    </span>

    <span class="comp-plate">
      <i></i><i></i><i></i>
    </span>
  </div>
</template>

<script setup>
defineProps({
  state: { type: String, default: 'idle' }
})
</script>

<style scoped>
.comp {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

/* 斜规：贯穿舞台的两条对角线，斜率随状态改变 */
.comp-diag {
  position: absolute;
  top: 50%;
  left: -14%;
  width: 128%;
  height: 1px;
  background: var(--fab-rule-2);
  transform: rotate(var(--fab-diag-rot, -12deg));
  transition: transform 1000ms var(--fab-ease);
}

.comp-diag--soft {
  top: 28%;
  height: 1px;
  background: var(--fab-rule);
  opacity: .7;
  transform: rotate(calc(var(--fab-diag-rot, -12deg) * -0.45));
}

/* 方框：右半区的取景框 */
.comp-frame {
  position: absolute;
  top: 9%;
  left: 43%;
  width: 44%;
  aspect-ratio: 1;
  border: 1px solid var(--fab-rule-2);
  transform: rotate(var(--fab-square-rot, 6deg)) scale(var(--fab-square-scale, .9));
  transition: transform 1200ms var(--fab-ease), border-color 600ms var(--fab-ease-io);
}

/* 弧规：右下的四分之一圆规，构图的重量与留白的边界 */
.comp-arc {
  position: absolute;
  top: var(--fab-arc-y, 56%);
  left: var(--fab-arc-x, 50%);
  width: 44%;
  height: 44%;
  overflow: visible;
  transform: rotate(var(--fab-arc-rot, 0deg)) scale(var(--fab-arc-scale, 1));
  transform-origin: 100% 100%;
  transition: top 1000ms var(--fab-ease), left 1000ms var(--fab-ease), transform 1000ms var(--fab-ease);
}

.arc-line {
  fill: none;
  stroke: var(--fab-paper);
  stroke-opacity: .16;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
  transition: stroke-opacity 700ms var(--fab-ease-io);
}

.arc-line--outer {
  stroke-opacity: .3;
}

.arc-line--inner {
  stroke: var(--fab-clay);
  stroke-opacity: .46;
}

.fable[data-state='decide'] .arc-line--inner { stroke-opacity: .68; }
.fable[data-state='execute'] .arc-line--inner { stroke-opacity: .55; }
.fable[data-state='reflect'] .arc-line--inner { stroke-opacity: .3; }

/* 地尺：肥波脚下的黄油色量杆，长度随状态伸缩 */
.comp-bar {
  position: absolute;
  top: 78.6%;
  left: 25%;
  width: 34%;
  height: 3px;
  background: var(--fab-butter);
  opacity: .78;
  transform-origin: 0 50%;
  transform: scaleX(var(--fab-bar-scale, .34));
  transition: transform 1000ms var(--fab-ease), opacity 700ms var(--fab-ease-io);
}

.fable[data-state='execute'] .comp-bar { opacity: .8; }

/* 量规：竖向刻度尺 */
.comp-measure {
  position: absolute;
  top: 15%;
  bottom: 14%;
  left: var(--fab-measure-x, 16%);
  width: 1px;
  background: var(--fab-rule-2);
  transition: left 1000ms var(--fab-ease);
}

.comp-measure i {
  position: absolute;
  left: 0;
  width: 7px;
  height: 1px;
  background: var(--fab-paper-26);
}

.comp-measure i.major {
  width: 13px;
  background: var(--fab-paper-46);
}

.comp-measure b {
  position: absolute;
  bottom: -18px;
  left: 0;
  color: var(--fab-paper-26);
  font: 8px/1 var(--fab-mono, monospace);
  letter-spacing: .2em;
}

/* 版号牌：右下角的图版信息 */
.comp-plate {
  position: absolute;
  right: 6%;
  bottom: 9%;
  display: grid;
  gap: 4px;
  width: 46px;
  opacity: .7;
}

.comp-plate i {
  display: block;
  height: 1px;
  background: var(--fab-paper-26);
}

.comp-plate i:nth-child(2) { width: 70%; }
.comp-plate i:nth-child(3) { width: 40%; }

@media (prefers-reduced-motion: reduce) {
  .comp * { transition: none !important; }
}
</style>
