# 数字人形象方案 v2：程序化深海生物发光体

> 背景：sendagaya-shino 占位模型是校服棕发二次元，与项目深海/生物发光主题完全不搭。
> MPFB2 自建 VRM 需要 Blender（当前环境缺失）；现成 CC0 深海主题 VRM 人形不存在（搜遍 VRoid Hub/CC0 站）。
> 结论：用 three.js 原生几何体程序化构建一个抽象的深海生物发光数字人。

| 项 | 值 |
| --- | --- |
| 宿主 | 桌宠 PersonaPet（优先）+ /agent/persona 全页（后续） |
| 实现 | three.js 原生几何体 + MeshStandardMaterial/emissive + 自写动画 |
| 资产 | 零外部资产、零许可风险、体积 < 50KB |
| 主题 | 深海/生物发光：青蓝（#2496ED/#7AD7F5）+ 粉紫（#b48cf7，呼应登录水母） |
| 状态 | 复用 personaStates.js 七状态枚举 |
| 口型 | 复用 useLipSync（文字时间线），用发光弧线开合驱动 |

## 形象设计

```
       ◆ 光环 (torus, 发光, 慢旋)
      ╱ ╲
     ◯ 头部 (球体, 半透明青蓝发光, 内部脉冲核心)
    ◉  ◉ 眼部 (两个发光光点, 跟随视线)
     ╱│╲
    ◯ 身体 (胶囊体, 半透明, 外层发光壳)
    │ │ │
    ─ ─ ─ 口型 (发光弧线, 按 aa 权重开合)
   ╱  │  ╲
  光线/触须 (细长胶囊, 摆动, 末端发光)
```

| 部位 | 几何体 | 材质 | 动画 |
| --- | --- | --- | --- |
| 光环 | TorusGeometry | MeshBasicMaterial emissive 青蓝 | 慢旋 + 呼吸缩放 |
| 头部 | SphereGeometry | MeshStandardMaterial 半透明 + emissive | 呼吸脉动、点头 |
| 眼部 | SphereGeometry (小) | MeshBasicMaterial 强发光 | 跟随 lookTarget |
| 身体 | CapsuleGeometry | MeshStandardMaterial 半透明 + emissive | 呼吸起伏 |
| 口型 | RingGeometry/自定义 | MeshBasicMaterial | 按 aa 权重缩放 Y |
| 触须 | 3× CapsuleGeometry | MeshBasicMaterial 发光 | sin 摆动 |
| 核心光点 | SphereGeometry (极小) | MeshBasicMaterial 强发光 | 脉冲 |

## 状态映射（七状态）

| 状态 | 姿态 | 颜色 | 动效 |
| --- | --- | --- | --- |
| idle | 直立放松 | 青蓝基准 | 呼吸 |
| thinking | 微低头 | 青蓝 + 粉紫光点 | 头部左右轻摆 |
| observing | 微前倾 | 青蓝 | 眼随视线 |
| executing | 前倾 | 青蓝 + 白光 | 触须加速摆动 |
| alert | 后仰 | 琥珀 | 光环转快 |
| fault | 下垂 | 红色 | 触须静止、核心暗 |
| recovering | 渐直立 | 青蓝渐变恢复 | 光环转速渐回 |

## 技术实现

- 新建 `useProgrammaticAvatar.js`，暴露与 `useVrmModel.js` **相同的接口**：
  `setState / speakText / seekSpeech / stopSpeaking / resumeAudio / attachAudio / dispose`
- `AgentPersona.vue` 新增 `mode` prop：`'vrm'`（默认，全页用）/ `'programmatic'`（桌宠用）
- 桌宠 `<AgentPersona mode="programmatic" />`
- 动画复用 motionScheduler（30fps），性能预算沿用 frameBudget

## 验收清单

- [ ] 桌宠显示程序化深海发光体（非 sendagaya-shino 校服角色）
- [ ] 七状态在小窗内可辨识（颜色 + 姿态）
- [ ] 口型播报时弧线开合、结束归零
- [ ] reduced-motion 不加载 3D（静态 SVG 替身）
- [ ] 体积 < 50KB、draw call ≤ 6
- [ ] 无外部资产、无许可风险
