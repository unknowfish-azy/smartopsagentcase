<!--
  FieldStage.vue — CSS 3D 空间场 stage（DESIGN §7 CSS 3D 方案）。

  结构：
    .field-stage                ← perspective: 1400px（子元素透视投影）
      .field-world              ← preserve-3d + 世界变换（translate3d / rotateX / rotateY）
        [FieldPlane × N]        ← 知识/洞察平面（DOM，3D 定位）
        EvidenceBed             ← Canvas2D 证据层（translateZ 最底层）
        ThreadLayer             ← SVG 线程层（屏幕空间叠加，不 preserve-3d）

  相机状态由父组件注入（useFieldCamera），本组件只负责把状态批量写入 transform。
  遵循 DESIGN §6.2 预算：单次相机变更批量写一次 transform，不在 rAF 里逐元素 setState。
-->
<script setup>
import { computed } from 'vue'

const props = defineProps({
  camera: { type: Object, required: true },  // useFieldCamera() 返回值
  worldSize: { type: Object, default: () => ({ w: 7200, h: 660, d: 2000 }) },
})

// 世界变换矩阵（球坐标 → 平移 + 旋转 + 缩放）
const worldTransform = computed(() => {
  const cx = props.camera.target.x
  const cy = props.camera.target.y
  const cz = props.camera.target.z
  // 先把世界中心移到原点，再应用 yaw（绕 Y）和 pitch（绕 X），最后把中心拉回 target
  // 注意：CSS 3D 的 rotateY 正值是顺时针（从上方看），这里 yaw 正值 = 向右看 → 等价 rotateY(-yaw)
  return [
    `translate3d(${-cx}px, ${-cy}px, ${-cz}px)`,
    `rotateX(${-props.camera.pitch.value}deg)`,   // pitch 正 = 向上抬 → 旋转视角朝下看世界
    `rotateY(${-props.camera.yaw.value}deg)`,     // yaw 正 = 向右转 → 世界向左转
    `translate3d(${cx}px, ${cy}px, ${cz}px)`,
  ].join(' ')
})

// stage 的 perspective 值：相机 dist 越大 → 透视影响越小 → perspective 值越大
const perspective = computed(() => {
  // perspective ≈ dist × 1.2，clamp 到合理范围
  const d = props.camera.dist.value
  return `${Math.round(d * 1.2)}px`
})

defineSlots()
</script>

<template>
  <div class="field-stage" :style="{ perspective }">
    <div class="field-world" :style="{ transform: worldTransform }">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.field-stage {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--ds-surface-base);
  transform-style: preserve-3d;
  will-change: perspective;
  cursor: grab;
}
.field-stage:active { cursor: grabbing; }

.field-world {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 1px;
  height: 1px;
  transform-style: preserve-3d;
  will-change: transform;
}
</style>
