/**
 * 骨骼手势动作库（纯数据，一次性叠加动作）。
 *
 * 与 7 状态的关系：状态是「长期姿态」（personaStates 的姿态增量 + 节奏），
 * 手势是「一次性动作」（挥手、点头、摇头、鞠躬、大笑、歪头、伸懒腰、打瞌睡、
 * 加油、害羞、思考、生气、鼓掌、无奈、敬礼、指向、点赞、比心、发抖、扶额、
 * 凑近、后仰、张望、摇摆、打响指、深鞠躬、抱臂、叉腰、指天、张开双臂、
 * 通讯、停止手势、压低手势），
 * 叠加在状态姿态之上、播完自动归零，不打断呼吸/眨眼，也不改变当前状态。
 *
 * 来源说明（2026-11-16）：抱臂/叉腰/指天/张开双臂借鉴王者荣耀「我的名片·元流之子」
 * 的展示动作语义，通讯/停止/压低借用三角洲行动的战术手语语义；
 * 仅借鉴动作设计，不提取任何游戏资产（商业素材不可用、骨骼也不兼容），
 * 全部按本项目 VRM 骨骼（无手指/无腿部）重新编排为关键帧。
 *
 * 为什么是代码内关键帧而不是外部 .vrma 资产：
 *  - 项目硬约束要求动作映射为纯数据配置表（相对基准姿态的增量），本文件延续该约定；
 *  - 公开渠道可直接取用的 VRMA 仅 pixiv/three-vrm(MIT) 的 test.vrma——只有 hips 3 通道
 *    的管线自检动画，无手势语义，不引入；
 *  - 纯数据零许可风险、零下载失败风险、零新依赖（不引入 @pixiv/three-vrm-animation）。
 *
 * 关键帧约定：
 *  - t 为归一化时间 [0,1]，按 gesture.duration 秒展开；
 *  - pose 为相对 PERSONA_POSE_BASE 的骨骼旋转增量（弧度），只写有增量的骨骼；
 *  - 首尾关键帧增量必须为空（从零出发、回零收尾），保证无跳变；
 *  - 关键帧间用 smoothstep 缓动，逐帧对位采样。
 */

/**
 * 挥手：右臂抬起过肩，前臂左右摆两拍。
 * 骨骼方向约定（three-vrm 归一化骨骼）：手势 pose 是**叠加在 PERSONA_POSE_BASE
 * （双臂 base z=∓1.15 下垂）之上的增量**，不是相对 T-pose 的绝对角。
 * 右臂上举（外展）= z 正增量；前臂 z 负值 = 向身体外侧弯。
 * 2026-11-16 修正 wave/greet：旧值按 T-pose 绝对角设计，叠加 base 后手臂转过头顶（诡异敬礼）。
 */
const WAVE = Object.freeze({
  label: '挥手',
  duration: 1.5,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      // 2026-11-16 修复"直臂举过头顶"诡异挥手：手势增量叠加在 PERSONA_POSE_BASE
      // （右臂 base z=-1.15 下垂）之上。总角 z = -1.15 + 1.85 = +0.7 → 侧上约 40°，
      // 挥动主体由前臂（lowerArm z 摆动）+ 手腕完成，肘部保持明显弯曲。
      t: 0.18,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ z: 1.85, x: -0.1 }),
        rightLowerArm: Object.freeze({ z: -0.55, y: -0.2 }),
        rightHand: Object.freeze({ z: -0.1 }),
        head: Object.freeze({ z: -0.06 })
      })
    },
    {
      t: 0.38,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ z: 1.85, x: -0.1 }),
        rightLowerArm: Object.freeze({ z: -0.95, y: 0.15 }),
        rightHand: Object.freeze({ z: 0.15 })
      })
    },
    {
      t: 0.58,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ z: 1.85, x: -0.1 }),
        rightLowerArm: Object.freeze({ z: -0.4, y: -0.2 }),
        rightHand: Object.freeze({ z: -0.15 })
      })
    },
    {
      t: 0.78,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ z: 1.85, x: -0.1 }),
        rightLowerArm: Object.freeze({ z: -0.95, y: 0.15 }),
        rightHand: Object.freeze({ z: 0.15 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/** 点头：低头一拍再回正，比状态里的节律 nod 幅度大一档，表示「明白了」。 */
const NOD = Object.freeze({
  label: '点头',
  duration: 0.9,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    { t: 0.35, pose: Object.freeze({ head: Object.freeze({ x: 0.32 }), neck: Object.freeze({ x: 0.12 }) }) },
    { t: 0.55, pose: Object.freeze({ head: Object.freeze({ x: 0.04 }) }) },
    { t: 0.75, pose: Object.freeze({ head: Object.freeze({ x: 0.24 }), neck: Object.freeze({ x: 0.08 }) }) },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/** 摇头：左右转头各一拍，表示「不对 / 拒绝」。 */
const SHAKE = Object.freeze({
  label: '摇头',
  duration: 1.1,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    { t: 0.3, pose: Object.freeze({ head: Object.freeze({ y: 0.38 }) }) },
    { t: 0.65, pose: Object.freeze({ head: Object.freeze({ y: -0.38 }) }) },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/** 鞠躬：15° 前倾停顿半拍再起身，配合表达感谢/歉意。 */
const BOW = Object.freeze({
  label: '鞠躬',
  duration: 1.6,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.3,
      pose: Object.freeze({
        chest: Object.freeze({ x: 0.26 }),
        head: Object.freeze({ x: 0.14 }),
        neck: Object.freeze({ x: 0.08 }),
        leftUpperArm: Object.freeze({ x: 0.08 }),
        rightUpperArm: Object.freeze({ x: 0.08 })
      })
    },
    { t: 0.7, pose: Object.freeze({ chest: Object.freeze({ x: 0.26 }), head: Object.freeze({ x: 0.14 }), neck: Object.freeze({ x: 0.08 }) }) },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/** 开场问候：右手抚胸微点头，比单纯点头更有「在听」的礼仪感。 */
const GREET = Object.freeze({
  label: '致意',
  duration: 1.2,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      // 2026-11-16 修复：z 增量 -1.5 叠加 base -1.15 后总 -2.65 rad 会把臂转到头顶对侧；
      // 改为 +1.0 → 总 z = -0.15 ≈ 侧平举略下 9°，配合前臂前伸（x -0.9）为自然致意。
      t: 0.3,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.55, z: 1.0 }),
        rightLowerArm: Object.freeze({ x: -0.9, y: 0.5 }),
        rightHand: Object.freeze({ x: -0.2 }),
        head: Object.freeze({ x: 0.12 })
      })
    },
    { t: 0.72, pose: Object.freeze({ rightUpperArm: Object.freeze({ x: -0.55, z: 1.0 }), rightLowerArm: Object.freeze({ x: -0.9, y: 0.5 }), rightHand: Object.freeze({ x: -0.2 }) }) },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 大笑（厘米秀式"摸头开心"反馈）：头后仰 + 双肩耸动两拍。
 * 耸肩用双上臂小幅外展（left 负增量 / right 正增量，叠加 base 后仍远在肩线内）。
 */
const LAUGH = Object.freeze({
  label: '大笑',
  duration: 1.6,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.2,
      pose: Object.freeze({
        head: Object.freeze({ x: -0.26, z: -0.04 }),
        neck: Object.freeze({ x: -0.08 }),
        chest: Object.freeze({ x: -0.08 }),
        leftUpperArm: Object.freeze({ z: -0.2, x: 0.08 }),
        rightUpperArm: Object.freeze({ z: 0.2, x: 0.08 }),
        leftLowerArm: Object.freeze({ z: -0.15 }),
        rightLowerArm: Object.freeze({ z: 0.15 })
      })
    },
    {
      t: 0.4,
      pose: Object.freeze({
        head: Object.freeze({ x: -0.12 }),
        leftUpperArm: Object.freeze({ z: -0.08, x: 0.04 }),
        rightUpperArm: Object.freeze({ z: 0.08, x: 0.04 })
      })
    },
    {
      t: 0.6,
      pose: Object.freeze({
        head: Object.freeze({ x: -0.2, z: -0.03 }),
        chest: Object.freeze({ x: -0.05 }),
        leftUpperArm: Object.freeze({ z: -0.16, x: 0.06 }),
        rightUpperArm: Object.freeze({ z: 0.16, x: 0.06 }),
        leftLowerArm: Object.freeze({ z: -0.12 }),
        rightLowerArm: Object.freeze({ z: 0.12 })
      })
    },
    {
      t: 0.8,
      pose: Object.freeze({
        head: Object.freeze({ x: -0.08 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 歪头疑惑（厘米秀式长按反馈）：头侧歪一拍、停顿、轻摆回正，
 * 双肩微耸表示"怎么了？"。
 */
const TILT = Object.freeze({
  label: '歪头',
  duration: 1.4,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.25,
      pose: Object.freeze({
        head: Object.freeze({ z: 0.28, x: -0.05 }),
        neck: Object.freeze({ z: 0.1 }),
        leftUpperArm: Object.freeze({ z: -0.14, x: 0.06 }),
        rightUpperArm: Object.freeze({ z: 0.14, x: 0.06 })
      })
    },
    {
      t: 0.7,
      pose: Object.freeze({
        head: Object.freeze({ z: 0.24, x: -0.04 }),
        neck: Object.freeze({ z: 0.08 }),
        leftUpperArm: Object.freeze({ z: -0.12, x: 0.05 }),
        rightUpperArm: Object.freeze({ z: 0.12, x: 0.05 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 伸懒腰（idle 彩蛋第一段）：双臂前伸上举（x 负增量 = 前举，z 增量极小
 * 叠加 base 后总外展约 1.05 rad，仍在护栏肩线内）+ 躯干后仰，保持一拍呼吸。
 */
const STRETCH = Object.freeze({
  label: '伸懒腰',
  duration: 2.2,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.2,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.9, z: -0.06 }),
        rightUpperArm: Object.freeze({ x: -0.9, z: 0.06 }),
        leftLowerArm: Object.freeze({ x: -0.2 }),
        rightLowerArm: Object.freeze({ x: -0.2 }),
        chest: Object.freeze({ x: -0.12 }),
        head: Object.freeze({ x: -0.1 })
      })
    },
    {
      t: 0.55,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -1.2, z: -0.06 }),
        rightUpperArm: Object.freeze({ x: -1.2, z: 0.06 }),
        leftLowerArm: Object.freeze({ x: -0.3 }),
        rightLowerArm: Object.freeze({ x: -0.3 }),
        chest: Object.freeze({ x: -0.18 }),
        head: Object.freeze({ x: -0.15 })
      })
    },
    {
      t: 0.85,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -1.1, z: -0.05 }),
        rightUpperArm: Object.freeze({ x: -1.1, z: 0.05 }),
        chest: Object.freeze({ x: -0.14 }),
        head: Object.freeze({ x: -0.1 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 打瞌睡（idle 彩蛋第二段）：躯干微前倾，头一点一点三拍渐弱。
 * 末帧回零 = "被唤醒抬起头"，配合组件的唤醒逻辑使用。
 */
const SLEEP = Object.freeze({
  label: '打瞌睡',
  duration: 4.2,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.1,
      pose: Object.freeze({
        chest: Object.freeze({ x: 0.12 }),
        neck: Object.freeze({ x: 0.06 }),
        head: Object.freeze({ x: 0.06 })
      })
    },
    { t: 0.22, pose: Object.freeze({ chest: Object.freeze({ x: 0.12 }), neck: Object.freeze({ x: 0.08 }), head: Object.freeze({ x: 0.34 }) }) },
    { t: 0.34, pose: Object.freeze({ chest: Object.freeze({ x: 0.12 }), neck: Object.freeze({ x: 0.06 }), head: Object.freeze({ x: 0.1 }) }) },
    { t: 0.48, pose: Object.freeze({ chest: Object.freeze({ x: 0.14 }), neck: Object.freeze({ x: 0.08 }), head: Object.freeze({ x: 0.28 }) }) },
    { t: 0.62, pose: Object.freeze({ chest: Object.freeze({ x: 0.14 }), neck: Object.freeze({ x: 0.06 }), head: Object.freeze({ x: 0.12 }) }) },
    { t: 0.78, pose: Object.freeze({ chest: Object.freeze({ x: 0.14 }), neck: Object.freeze({ x: 0.08 }), head: Object.freeze({ x: 0.22 }) }) },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 加油/庆祝：双臂前举，前臂上下挥两拍打气。
 * 挥动主体是 lowerArm x（肘部前抬往复），上臂保持前举不动，z 增量极小。
 */
const CHEER = Object.freeze({
  label: '加油',
  duration: 1.4,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.15,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.85, z: -0.08 }),
        rightUpperArm: Object.freeze({ x: -0.85, z: 0.08 }),
        leftLowerArm: Object.freeze({ x: -1.2 }),
        rightLowerArm: Object.freeze({ x: -1.2 }),
        leftHand: Object.freeze({ x: -0.1 }),
        rightHand: Object.freeze({ x: -0.1 }),
        chest: Object.freeze({ x: -0.05 }),
        head: Object.freeze({ x: -0.08 })
      })
    },
    {
      t: 0.35,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.8, z: -0.08 }),
        rightUpperArm: Object.freeze({ x: -0.8, z: 0.08 }),
        leftLowerArm: Object.freeze({ x: -0.75 }),
        rightLowerArm: Object.freeze({ x: -0.75 })
      })
    },
    {
      t: 0.55,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.85, z: -0.08 }),
        rightUpperArm: Object.freeze({ x: -0.85, z: 0.08 }),
        leftLowerArm: Object.freeze({ x: -1.3 }),
        rightLowerArm: Object.freeze({ x: -1.3 }),
        head: Object.freeze({ x: -0.06 })
      })
    },
    {
      t: 0.8,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.75, z: -0.06 }),
        rightUpperArm: Object.freeze({ x: -0.75, z: 0.06 }),
        leftLowerArm: Object.freeze({ x: -0.85 }),
        rightLowerArm: Object.freeze({ x: -0.85 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 害羞：双手抬到脸旁假装掩面，头微低左右轻摇（厘米秀式"摸头后"的娇羞反馈）。
 * 肘部大弯（lowerArm x ≈ -1.9）把手带到脸侧，视线避开镜头。
 */
const SHY = Object.freeze({
  label: '害羞',
  duration: 1.6,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.2,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.55, z: -0.06 }),
        rightUpperArm: Object.freeze({ x: -0.55, z: 0.06 }),
        leftLowerArm: Object.freeze({ x: -1.9, z: -0.1 }),
        rightLowerArm: Object.freeze({ x: -1.9, z: 0.1 }),
        leftHand: Object.freeze({ x: -0.3 }),
        rightHand: Object.freeze({ x: -0.3 }),
        head: Object.freeze({ x: 0.18 }),
        chest: Object.freeze({ x: 0.05 })
      })
    },
    {
      t: 0.45,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.55, z: -0.06 }),
        rightUpperArm: Object.freeze({ x: -0.55, z: 0.06 }),
        leftLowerArm: Object.freeze({ x: -1.9, z: -0.1 }),
        rightLowerArm: Object.freeze({ x: -1.9, z: 0.1 }),
        leftHand: Object.freeze({ x: -0.3 }),
        rightHand: Object.freeze({ x: -0.3 }),
        head: Object.freeze({ x: 0.2, y: 0.08 })
      })
    },
    {
      t: 0.7,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.52, z: -0.05 }),
        rightUpperArm: Object.freeze({ x: -0.52, z: 0.05 }),
        leftLowerArm: Object.freeze({ x: -1.85, z: -0.1 }),
        rightLowerArm: Object.freeze({ x: -1.85, z: 0.1 }),
        head: Object.freeze({ x: 0.18, y: -0.08 })
      })
    },
    {
      t: 0.9,
      pose: Object.freeze({
        head: Object.freeze({ x: 0.1 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 思考：右手托腮，头微歪（与语音"思考中"的状态姿态互补的一次性强调动作）。
 */
const THINK = Object.freeze({
  label: '思考',
  duration: 2.0,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.25,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.45, z: 0.15 }),
        rightLowerArm: Object.freeze({ x: -2.0, z: -0.05 }),
        rightHand: Object.freeze({ x: -0.35 }),
        head: Object.freeze({ x: 0.12, z: 0.16 }),
        neck: Object.freeze({ z: 0.06 })
      })
    },
    {
      t: 0.55,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.45, z: 0.15 }),
        rightLowerArm: Object.freeze({ x: -2.05, z: -0.05 }),
        rightHand: Object.freeze({ x: -0.35 }),
        head: Object.freeze({ x: 0.14, z: 0.14 })
      })
    },
    {
      t: 0.85,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.4, z: 0.12 }),
        rightLowerArm: Object.freeze({ x: -1.8, z: -0.05 }),
        head: Object.freeze({ x: 0.08, z: 0.1 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 生气：双臂内收叉腰 + 胸前倾 + 头左右摇两下（"哼！"）。
 * 内收方向 left 为 z 正增量 / right 为 z 负增量，叠加 base 后 ±1.27 rad，
 * 贴着护栏肩线（|总角| < 1.3）但不越线。
 */
const ANGRY = Object.freeze({
  label: '生气',
  duration: 1.5,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.2,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: 0.1, z: 0.12 }),
        rightUpperArm: Object.freeze({ x: 0.1, z: -0.12 }),
        leftLowerArm: Object.freeze({ x: -1.1, z: 0.05 }),
        rightLowerArm: Object.freeze({ x: -1.1, z: -0.05 }),
        chest: Object.freeze({ x: 0.14 }),
        head: Object.freeze({ x: 0.08 })
      })
    },
    {
      t: 0.45,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: 0.1, z: 0.12 }),
        rightUpperArm: Object.freeze({ x: 0.1, z: -0.12 }),
        leftLowerArm: Object.freeze({ x: -1.1, z: 0.05 }),
        rightLowerArm: Object.freeze({ x: -1.1, z: -0.05 }),
        chest: Object.freeze({ x: 0.14 }),
        head: Object.freeze({ x: 0.08, y: 0.14 })
      })
    },
    {
      t: 0.65,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: 0.1, z: 0.12 }),
        rightUpperArm: Object.freeze({ x: 0.1, z: -0.12 }),
        leftLowerArm: Object.freeze({ x: -1.1, z: 0.05 }),
        rightLowerArm: Object.freeze({ x: -1.1, z: -0.05 }),
        chest: Object.freeze({ x: 0.14 }),
        head: Object.freeze({ x: 0.08, y: -0.14 })
      })
    },
    {
      t: 0.85,
      pose: Object.freeze({
        chest: Object.freeze({ x: 0.08 }),
        head: Object.freeze({ x: 0.05 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 鼓掌：双臂前伸，双手向中线互拍两拍（拍合瞬间 hands z 相向收拢）。
 */
const APPLAUD = Object.freeze({
  label: '鼓掌',
  duration: 1.8,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.15,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.55 }),
        rightUpperArm: Object.freeze({ x: -0.55 }),
        leftLowerArm: Object.freeze({ x: -1.5 }),
        rightLowerArm: Object.freeze({ x: -1.5 }),
        leftHand: Object.freeze({ z: 0.3 }),
        rightHand: Object.freeze({ z: -0.3 }),
        head: Object.freeze({ x: -0.06 })
      })
    },
    {
      t: 0.3,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.55 }),
        rightUpperArm: Object.freeze({ x: -0.55 }),
        leftLowerArm: Object.freeze({ x: -1.5 }),
        rightLowerArm: Object.freeze({ x: -1.5 }),
        leftHand: Object.freeze({ z: 0.05 }),
        rightHand: Object.freeze({ z: -0.05 })
      })
    },
    {
      t: 0.5,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.55 }),
        rightUpperArm: Object.freeze({ x: -0.55 }),
        leftLowerArm: Object.freeze({ x: -1.5 }),
        rightLowerArm: Object.freeze({ x: -1.5 }),
        leftHand: Object.freeze({ z: 0.3 }),
        rightHand: Object.freeze({ z: -0.3 })
      })
    },
    {
      t: 0.65,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.55 }),
        rightUpperArm: Object.freeze({ x: -0.55 }),
        leftLowerArm: Object.freeze({ x: -1.5 }),
        rightLowerArm: Object.freeze({ x: -1.5 }),
        leftHand: Object.freeze({ z: 0.05 }),
        rightHand: Object.freeze({ z: -0.05 })
      })
    },
    {
      t: 0.9,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.4 }),
        rightUpperArm: Object.freeze({ x: -0.4 }),
        leftLowerArm: Object.freeze({ x: -1.0 }),
        rightLowerArm: Object.freeze({ x: -1.0 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 无奈耸肩：双肩外展上耸 + 双手摊开 + 头侧歪（"我也没办法～"）。
 */
const SHRUG = Object.freeze({
  label: '无奈',
  duration: 1.5,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.2,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ z: -0.18, x: 0.06 }),
        rightUpperArm: Object.freeze({ z: 0.18, x: 0.06 }),
        leftLowerArm: Object.freeze({ x: -0.9 }),
        rightLowerArm: Object.freeze({ x: -0.9 }),
        leftHand: Object.freeze({ x: 0.2 }),
        rightHand: Object.freeze({ x: 0.2 }),
        head: Object.freeze({ z: -0.14 }),
        chest: Object.freeze({ x: -0.04 })
      })
    },
    {
      t: 0.6,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ z: -0.16, x: 0.05 }),
        rightUpperArm: Object.freeze({ z: 0.16, x: 0.05 }),
        leftLowerArm: Object.freeze({ x: -0.85 }),
        rightLowerArm: Object.freeze({ x: -0.85 }),
        leftHand: Object.freeze({ x: 0.15 }),
        rightHand: Object.freeze({ x: 0.15 }),
        head: Object.freeze({ z: -0.12 })
      })
    },
    {
      t: 0.9,
      pose: Object.freeze({
        head: Object.freeze({ z: -0.06 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 敬礼/收到：右手抬到额侧，头正微抬（"收到，马上执行"）。
 * 右臂外展增量 +1.0，叠加 base 后总角 -0.15 ≈ 侧平举略下，靠前臂大弯把手带到头侧。
 */
const SALUTE = Object.freeze({
  label: '敬礼',
  duration: 1.2,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.22,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.5, z: 1.0 }),
        rightLowerArm: Object.freeze({ x: -2.2, y: -0.3 }),
        rightHand: Object.freeze({ z: -0.2 }),
        head: Object.freeze({ x: -0.06 }),
        chest: Object.freeze({ x: -0.04 })
      })
    },
    {
      t: 0.68,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.48, z: 0.95 }),
        rightLowerArm: Object.freeze({ x: -2.15, y: -0.28 }),
        rightHand: Object.freeze({ z: -0.18 }),
        head: Object.freeze({ x: -0.04 })
      })
    },
    { t: 0.85, pose: Object.freeze({ rightUpperArm: Object.freeze({ z: 0.5 }), rightLowerArm: Object.freeze({ x: -1.0 }) }) },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 指向：右臂前伸指向侧前方，头随视线同向转（"看这里"）。
 * 臂不下垂也不上举，靠 x 前举 + 肘部伸直表达"指向"。
 */
const POINT = Object.freeze({
  label: '指向',
  duration: 1.6,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.2,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -1.25, z: 0.75 }),
        rightLowerArm: Object.freeze({ x: -0.15, y: 0.1 }),
        rightHand: Object.freeze({ x: -0.1 }),
        head: Object.freeze({ y: 0.22, x: -0.04 }),
        neck: Object.freeze({ y: 0.1 }),
        chest: Object.freeze({ y: 0.08 })
      })
    },
    {
      t: 0.62,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -1.2, z: 0.72 }),
        rightLowerArm: Object.freeze({ x: -0.12, y: 0.08 }),
        rightHand: Object.freeze({ x: -0.08 }),
        head: Object.freeze({ y: 0.2, x: -0.03 }),
        neck: Object.freeze({ y: 0.09 })
      })
    },
    {
      t: 0.82,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.7, z: 0.35 }),
        head: Object.freeze({ y: 0.08 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 点赞：右臂前举竖起大拇指，头轻点一下（"干得漂亮"）。
 * 前臂前抬 + 手腕外旋是"竖拇指"的可辨识特征，不依赖手指骨骼。
 */
const THUMB_UP = Object.freeze({
  label: '点赞',
  duration: 1.5,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.22,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -1.0, z: 0.35 }),
        rightLowerArm: Object.freeze({ x: -1.35, y: -0.25 }),
        rightHand: Object.freeze({ z: -0.35, x: -0.15 }),
        head: Object.freeze({ x: 0.1 }),
        chest: Object.freeze({ x: -0.03 })
      })
    },
    {
      t: 0.45,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.96, z: 0.34 }),
        rightLowerArm: Object.freeze({ x: -1.3, y: -0.24 }),
        rightHand: Object.freeze({ z: -0.33, x: -0.14 }),
        head: Object.freeze({ x: -0.02 })
      })
    },
    {
      t: 0.8,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.9, z: 0.3 }),
        rightLowerArm: Object.freeze({ x: -1.2, y: -0.2 }),
        rightHand: Object.freeze({ z: -0.3 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 比心：双臂在胸前合拢、双手扣成心形，头微低（亲昵反馈）。
 * 内收方向 left 为 z 正增量（限 < 0.15）、right 为 z 负增量，均在肩线护栏内。
 */
const HEART = Object.freeze({
  label: '比心',
  duration: 1.8,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.22,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.5, z: 0.12 }),
        rightUpperArm: Object.freeze({ x: -0.5, z: -0.12 }),
        leftLowerArm: Object.freeze({ x: -1.85, y: 0.35 }),
        rightLowerArm: Object.freeze({ x: -1.85, y: -0.35 }),
        leftHand: Object.freeze({ y: 0.3, z: 0.2 }),
        rightHand: Object.freeze({ y: -0.3, z: -0.2 }),
        head: Object.freeze({ x: 0.12 }),
        chest: Object.freeze({ x: 0.04 })
      })
    },
    {
      t: 0.62,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.48, z: 0.12 }),
        rightUpperArm: Object.freeze({ x: -0.48, z: -0.12 }),
        leftLowerArm: Object.freeze({ x: -1.8, y: 0.33 }),
        rightLowerArm: Object.freeze({ x: -1.8, y: -0.33 }),
        leftHand: Object.freeze({ y: 0.28, z: 0.18 }),
        rightHand: Object.freeze({ y: -0.28, z: -0.18 }),
        head: Object.freeze({ x: 0.1, z: 0.06 })
      })
    },
    {
      t: 0.85,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.3, z: 0.06 }),
        rightUpperArm: Object.freeze({ x: -0.3, z: -0.06 }),
        leftLowerArm: Object.freeze({ x: -1.2 }),
        rightLowerArm: Object.freeze({ x: -1.2 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 发抖/紧张：双肩内收上耸、缩脖，头小幅高频抖动（告警/被吓到）。
 * 用短周期多关键帧表达"高频"，比拉长单次幅度更自然。
 */
const SHIVER = Object.freeze({
  label: '发抖',
  duration: 1.3,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.12,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: 0.12, z: 0.1 }),
        rightUpperArm: Object.freeze({ x: 0.12, z: -0.1 }),
        leftLowerArm: Object.freeze({ x: -0.6 }),
        rightLowerArm: Object.freeze({ x: -0.6 }),
        neck: Object.freeze({ x: 0.1 }),
        head: Object.freeze({ x: 0.12, z: 0.05 }),
        chest: Object.freeze({ x: 0.08 })
      })
    },
    { t: 0.26, pose: Object.freeze({ leftUpperArm: Object.freeze({ x: 0.12, z: 0.1 }), rightUpperArm: Object.freeze({ x: 0.12, z: -0.1 }), leftLowerArm: Object.freeze({ x: -0.6 }), rightLowerArm: Object.freeze({ x: -0.6 }), neck: Object.freeze({ x: 0.1 }), head: Object.freeze({ x: 0.12, z: -0.05 }), chest: Object.freeze({ x: 0.08 }) }) },
    { t: 0.4, pose: Object.freeze({ leftUpperArm: Object.freeze({ x: 0.11, z: 0.09 }), rightUpperArm: Object.freeze({ x: 0.11, z: -0.09 }), leftLowerArm: Object.freeze({ x: -0.58 }), rightLowerArm: Object.freeze({ x: -0.58 }), neck: Object.freeze({ x: 0.09 }), head: Object.freeze({ x: 0.11, z: 0.05 }), chest: Object.freeze({ x: 0.07 }) }) },
    { t: 0.54, pose: Object.freeze({ leftUpperArm: Object.freeze({ x: 0.1, z: 0.08 }), rightUpperArm: Object.freeze({ x: 0.1, z: -0.08 }), leftLowerArm: Object.freeze({ x: -0.55 }), rightLowerArm: Object.freeze({ x: -0.55 }), neck: Object.freeze({ x: 0.08 }), head: Object.freeze({ x: 0.1, z: -0.05 }), chest: Object.freeze({ x: 0.06 }) }) },
    { t: 0.7, pose: Object.freeze({ leftUpperArm: Object.freeze({ x: 0.08, z: 0.06 }), rightUpperArm: Object.freeze({ x: 0.08, z: -0.06 }), leftLowerArm: Object.freeze({ x: -0.4 }), rightLowerArm: Object.freeze({ x: -0.4 }), neck: Object.freeze({ x: 0.05 }), head: Object.freeze({ x: 0.06, z: 0.04 }), chest: Object.freeze({ x: 0.04 }) }) },
    { t: 0.86, pose: Object.freeze({ chest: Object.freeze({ x: 0.02 }), head: Object.freeze({ x: 0.02 }) }) },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 扶额（"我的锅…"）：右手抬到额头，头低下、肩下沉。
 * 肘部极限弯曲（lowerArm x -2.45）把手带到前额，额头与手的贴合靠上臂前举补足。
 */
const FACEPALM = Object.freeze({
  label: '扶额',
  duration: 1.7,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.25,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.75, z: 0.85 }),
        rightLowerArm: Object.freeze({ x: -2.45, y: -0.2 }),
        rightHand: Object.freeze({ x: -0.25 }),
        head: Object.freeze({ x: 0.3, z: 0.08 }),
        neck: Object.freeze({ x: 0.1 }),
        chest: Object.freeze({ x: 0.1 }),
        leftUpperArm: Object.freeze({ z: -0.08 })
      })
    },
    {
      t: 0.72,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.72, z: 0.82 }),
        rightLowerArm: Object.freeze({ x: -2.42, y: -0.18 }),
        rightHand: Object.freeze({ x: -0.22 }),
        head: Object.freeze({ x: 0.32, z: 0.06 }),
        neck: Object.freeze({ x: 0.1 }),
        chest: Object.freeze({ x: 0.1 })
      })
    },
    {
      t: 0.88,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ z: 0.4 }),
        rightLowerArm: Object.freeze({ x: -1.2 }),
        head: Object.freeze({ x: 0.12 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 凑近细看：躯干前倾、颈前探、头微抬（"我看看…"）。
 * 纯躯干+颈部动作，肩臂保持基准，用于"聆听/查看"这类专注语义。
 */
const LEAN_IN = Object.freeze({
  label: '凑近',
  duration: 1.9,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.3,
      pose: Object.freeze({
        chest: Object.freeze({ x: 0.2 }),
        neck: Object.freeze({ x: 0.14 }),
        head: Object.freeze({ x: 0.2 }),
        leftUpperArm: Object.freeze({ x: 0.06 }),
        rightUpperArm: Object.freeze({ x: 0.06 })
      })
    },
    {
      t: 0.72,
      pose: Object.freeze({
        chest: Object.freeze({ x: 0.22 }),
        neck: Object.freeze({ x: 0.15 }),
        head: Object.freeze({ x: 0.22, z: 0.04 })
      })
    },
    {
      t: 0.9,
      pose: Object.freeze({
        chest: Object.freeze({ x: 0.06 }),
        head: Object.freeze({ x: 0.05 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 惊讶后仰：躯干快速后仰、头抬起，双臂微微张开（"啊？"）。
 * 与 leanIn 形成一对相反的"接近/退避"语义。
 */
const LEAN_BACK = Object.freeze({
  label: '后仰',
  duration: 1.3,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.15,
      pose: Object.freeze({
        chest: Object.freeze({ x: -0.3 }),
        neck: Object.freeze({ x: -0.1 }),
        head: Object.freeze({ x: -0.22 }),
        leftUpperArm: Object.freeze({ z: -0.1, x: 0.05 }),
        rightUpperArm: Object.freeze({ z: 0.1, x: 0.05 }),
        leftLowerArm: Object.freeze({ x: -0.3 }),
        rightLowerArm: Object.freeze({ x: -0.3 })
      })
    },
    {
      t: 0.55,
      pose: Object.freeze({
        chest: Object.freeze({ x: -0.26 }),
        neck: Object.freeze({ x: -0.08 }),
        head: Object.freeze({ x: -0.18 }),
        leftUpperArm: Object.freeze({ z: -0.08 }),
        rightUpperArm: Object.freeze({ z: 0.08 }),
        leftLowerArm: Object.freeze({ x: -0.25 }),
        rightLowerArm: Object.freeze({ x: -0.25 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 东张西望：头左右转两拍、躯干轻微跟随（"人呢？"）。
 * 纯头颈+躯干 y 轴旋转，幅度递减收尾。
 */
const LOOK_AROUND = Object.freeze({
  label: '张望',
  duration: 2.2,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    { t: 0.18, pose: Object.freeze({ head: Object.freeze({ y: 0.35 }), neck: Object.freeze({ y: 0.12 }), chest: Object.freeze({ y: 0.08 }) }) },
    { t: 0.42, pose: Object.freeze({ head: Object.freeze({ y: -0.38 }), neck: Object.freeze({ y: -0.13 }), chest: Object.freeze({ y: -0.09 }) }) },
    { t: 0.66, pose: Object.freeze({ head: Object.freeze({ y: 0.24 }), neck: Object.freeze({ y: 0.08 }), chest: Object.freeze({ y: 0.05 }) }) },
    { t: 0.85, pose: Object.freeze({ head: Object.freeze({ y: -0.1 }) }) },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 轻松摇摆：重心左右轻摆两拍，头随摆动微倾（待机时的"闲适"表现）。
 * 用 chest y + head z 的短句组合模拟身体重心移动，不涉及腿骨。
 */
const SWAY = Object.freeze({
  label: '摇摆',
  duration: 2.4,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.2,
      pose: Object.freeze({
        chest: Object.freeze({ y: 0.07, z: 0.03 }),
        head: Object.freeze({ z: 0.08 }),
        leftUpperArm: Object.freeze({ z: -0.06 }),
        rightUpperArm: Object.freeze({ z: 0.06 })
      })
    },
    {
      t: 0.5,
      pose: Object.freeze({
        chest: Object.freeze({ y: -0.07, z: -0.03 }),
        head: Object.freeze({ z: -0.08 }),
        leftUpperArm: Object.freeze({ z: -0.06 }),
        rightUpperArm: Object.freeze({ z: 0.06 })
      })
    },
    {
      t: 0.78,
      pose: Object.freeze({
        chest: Object.freeze({ y: 0.04 }),
        head: Object.freeze({ z: 0.04 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 打响指：右臂前举，前臂快速内收一拍后放松（"有了！"）。
 * 无手指骨骼，靠手腕快速外旋 + 前臂瞬间回收表达"打响指"。
 */
const SNAP = Object.freeze({
  label: '打响指',
  duration: 1.1,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.18,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.85, z: 0.3 }),
        rightLowerArm: Object.freeze({ x: -1.25, y: -0.2 }),
        rightHand: Object.freeze({ z: -0.45 }),
        head: Object.freeze({ x: -0.05 })
      })
    },
    {
      t: 0.32,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.8, z: 0.28 }),
        rightLowerArm: Object.freeze({ x: -0.95, y: -0.1 }),
        rightHand: Object.freeze({ z: 0.2 }),
        head: Object.freeze({ x: -0.1 })
      })
    },
    {
      t: 0.6,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.6, z: 0.2 }),
        rightLowerArm: Object.freeze({ x: -0.7 }),
        rightHand: Object.freeze({ z: -0.1 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 深鞠躬：躯干前倾约 32°、头随之下垂并停顿一拍（郑重致谢/致歉）。
 * 与 15° 的浅鞠躬 bow 区分：幅度约两倍，双臂自然前垂。
 */
const DEEP_BOW = Object.freeze({
  label: '深鞠躬',
  duration: 2.0,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.28,
      pose: Object.freeze({
        chest: Object.freeze({ x: 0.55 }),
        neck: Object.freeze({ x: 0.14 }),
        head: Object.freeze({ x: 0.2 }),
        leftUpperArm: Object.freeze({ x: 0.14 }),
        rightUpperArm: Object.freeze({ x: 0.14 })
      })
    },
    {
      t: 0.7,
      pose: Object.freeze({
        chest: Object.freeze({ x: 0.55 }),
        neck: Object.freeze({ x: 0.14 }),
        head: Object.freeze({ x: 0.2 })
      })
    },
    {
      t: 0.88,
      pose: Object.freeze({
        chest: Object.freeze({ x: 0.2 }),
        head: Object.freeze({ x: 0.08 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 抱臂（借鉴王者「我的名片·元流之子」招牌站姿）：双臂交叉胸前、下巴微抬，审视感。
 * 内收方向 left 为 z 正增量（限 < 0.15）、right 为 z 负增量，均在护栏内；
 * 交叉靠两侧前臂大弯（-1.9）在中线叠合，不依赖手指骨骼。
 */
const ARMS_CROSSED = Object.freeze({
  label: '抱臂',
  duration: 2.2,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.24,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: 0.1, z: 0.12 }),
        rightUpperArm: Object.freeze({ x: 0.1, z: -0.12 }),
        leftLowerArm: Object.freeze({ x: -1.9, y: 0.35 }),
        rightLowerArm: Object.freeze({ x: -1.9, y: -0.35 }),
        leftHand: Object.freeze({ y: 0.2 }),
        rightHand: Object.freeze({ y: -0.2 }),
        chest: Object.freeze({ x: -0.04 }),
        head: Object.freeze({ x: -0.08 })
      })
    },
    {
      t: 0.72,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: 0.1, z: 0.12 }),
        rightUpperArm: Object.freeze({ x: 0.1, z: -0.12 }),
        leftLowerArm: Object.freeze({ x: -1.86, y: 0.33 }),
        rightLowerArm: Object.freeze({ x: -1.86, y: -0.33 }),
        head: Object.freeze({ x: -0.06, z: 0.03 })
      })
    },
    {
      t: 0.9,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: 0.05, z: 0.06 }),
        rightUpperArm: Object.freeze({ x: 0.05, z: -0.06 }),
        leftLowerArm: Object.freeze({ x: -0.9 }),
        rightLowerArm: Object.freeze({ x: -0.9 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 单手叉腰（耍帅站姿）：右臂外展后内收、肘部向后弯，手贴腰侧；头微侧。
 * 左臂保持基准，形成"半边耍帅"的松弛感。
 */
const HAND_ON_HIP = Object.freeze({
  label: '叉腰',
  duration: 2.0,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.22,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: 0.12, z: 0.15 }),
        rightLowerArm: Object.freeze({ x: -1.55, y: -0.5 }),
        rightHand: Object.freeze({ x: -0.1 }),
        chest: Object.freeze({ y: 0.05 }),
        head: Object.freeze({ z: -0.06 })
      })
    },
    {
      t: 0.7,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: 0.12, z: 0.14 }),
        rightLowerArm: Object.freeze({ x: -1.5, y: -0.48 }),
        rightHand: Object.freeze({ x: -0.08 }),
        chest: Object.freeze({ y: 0.05 }),
        head: Object.freeze({ z: -0.05 })
      })
    },
    {
      t: 0.9,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: 0.06, z: 0.07 }),
        rightLowerArm: Object.freeze({ x: -0.8 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 单臂指天（名片展示式宣言）：右臂前上举（x 轴主导，避免越过肩线护栏）、
 * 手指向上，头随之上抬。前举而非外展，绕开 base z=∓1.15 的肩线限制。
 */
const POINT_UP = Object.freeze({
  label: '指天',
  duration: 1.9,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.22,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -1.55, z: 0.2 }),
        rightLowerArm: Object.freeze({ x: 0.05 }),
        rightHand: Object.freeze({ x: -0.15 }),
        leftUpperArm: Object.freeze({ z: -0.08 }),
        chest: Object.freeze({ x: -0.06 }),
        head: Object.freeze({ x: -0.14 })
      })
    },
    {
      t: 0.62,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -1.6, z: 0.2 }),
        rightLowerArm: Object.freeze({ x: 0.02 }),
        rightHand: Object.freeze({ x: -0.12 }),
        chest: Object.freeze({ x: -0.05 }),
        head: Object.freeze({ x: -0.12, z: 0.04 })
      })
    },
    {
      t: 0.86,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.8, z: 0.1 }),
        head: Object.freeze({ x: -0.04 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 张开双臂（名片欢迎式）：双臂侧平举略前，掌心向上，头微抬。
 * 侧平举是肩线护栏允许的上限（left z -1.2 → 总角 -0.05），视觉接近水平张臂。
 */
const OPEN_ARMS = Object.freeze({
  label: '张开双臂',
  duration: 2.0,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.24,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.25, z: -1.2 }),
        rightUpperArm: Object.freeze({ x: -0.25, z: 1.2 }),
        leftLowerArm: Object.freeze({ x: -0.35 }),
        rightLowerArm: Object.freeze({ x: -0.35 }),
        leftHand: Object.freeze({ x: -0.1 }),
        rightHand: Object.freeze({ x: -0.1 }),
        chest: Object.freeze({ x: -0.08 }),
        head: Object.freeze({ x: -0.06 })
      })
    },
    {
      t: 0.72,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ x: -0.22, z: -1.15 }),
        rightUpperArm: Object.freeze({ x: -0.22, z: 1.15 }),
        leftLowerArm: Object.freeze({ x: -0.3 }),
        rightLowerArm: Object.freeze({ x: -0.3 }),
        head: Object.freeze({ x: -0.05, z: 0.04 })
      })
    },
    {
      t: 0.9,
      pose: Object.freeze({
        leftUpperArm: Object.freeze({ z: -0.45 }),
        rightUpperArm: Object.freeze({ z: 0.45 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 贴耳通讯（借用三角洲行动的无线电手势）：右手抬到耳侧、头微侧，
 * 与 salute 的区别在于手停点更低更靠耳、且身体不前倾。
 */
const RADIO_CALL = Object.freeze({
  label: '通讯',
  duration: 2.0,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.2,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.45, z: 0.95 }),
        rightLowerArm: Object.freeze({ x: -2.25, y: -0.25 }),
        rightHand: Object.freeze({ z: -0.2 }),
        neck: Object.freeze({ z: -0.03 }),
        head: Object.freeze({ z: -0.05 })
      })
    },
    {
      t: 0.55,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.43, z: 0.92 }),
        rightLowerArm: Object.freeze({ x: -2.2, y: -0.23 }),
        rightHand: Object.freeze({ z: -0.18 }),
        head: Object.freeze({ z: -0.04, x: 0.03 })
      })
    },
    {
      t: 0.86,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.3, z: 0.5 }),
        rightLowerArm: Object.freeze({ x: -1.2 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 停止手势（三角洲行动战术手语「停止」）：右臂前举、掌心朝前，停顿一拍。
 * 前臂几乎伸直（x -0.55）表示"挡住/停下"，与 point 的肘部伸直指向区分。
 */
const SIGNAL_STOP = Object.freeze({
  label: '停止手势',
  duration: 1.6,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.18,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -1.3, z: 0.28 }),
        rightLowerArm: Object.freeze({ x: -0.55 }),
        rightHand: Object.freeze({ x: -0.25 }),
        chest: Object.freeze({ x: -0.05 }),
        head: Object.freeze({ x: -0.04 })
      })
    },
    {
      t: 0.6,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -1.26, z: 0.26 }),
        rightLowerArm: Object.freeze({ x: -0.5 }),
        rightHand: Object.freeze({ x: -0.22 }),
        head: Object.freeze({ x: -0.03 })
      })
    },
    {
      t: 0.84,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.6, z: 0.12 }),
        rightLowerArm: Object.freeze({ x: -0.25 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 压低/稳住手势（三角洲行动战术手语「掩护/压低」）：右臂前举后掌心下压两拍，
 * 头随之下低——用于"稍等、稳住"这类节奏控制语义。
 */
const SIGNAL_COVER = Object.freeze({
  label: '压低手势',
  duration: 1.8,
  keys: Object.freeze([
    { t: 0, pose: Object.freeze({}) },
    {
      t: 0.16,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -1.2, z: 0.2 }),
        rightLowerArm: Object.freeze({ x: -1.1 }),
        rightHand: Object.freeze({ x: -0.2 }),
        chest: Object.freeze({ x: 0.05 }),
        head: Object.freeze({ x: 0.06 })
      })
    },
    {
      t: 0.34,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.85, z: 0.18 }),
        rightLowerArm: Object.freeze({ x: -0.75 }),
        rightHand: Object.freeze({ x: 0.05 }),
        chest: Object.freeze({ x: 0.07 }),
        head: Object.freeze({ x: 0.1 })
      })
    },
    {
      t: 0.54,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -1.15, z: 0.2 }),
        rightLowerArm: Object.freeze({ x: -1.05 }),
        rightHand: Object.freeze({ x: -0.15 }),
        chest: Object.freeze({ x: 0.05 }),
        head: Object.freeze({ x: 0.07 })
      })
    },
    {
      t: 0.72,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.9, z: 0.18 }),
        rightLowerArm: Object.freeze({ x: -0.8 }),
        head: Object.freeze({ x: 0.09 })
      })
    },
    {
      t: 0.88,
      pose: Object.freeze({
        rightUpperArm: Object.freeze({ x: -0.5, z: 0.1 }),
        rightLowerArm: Object.freeze({ x: -0.4 })
      })
    },
    { t: 1, pose: Object.freeze({}) }
  ])
})

/**
 * 手势口播文案：每个手势配一句 TTS 播报词（不依赖动作，只描述语义）。
 *
 * 约定：
 *  - 一律短句（≤ 20 字），spoken 时不会盖住用户正在等的 AI 回答；
 *  - 用口语而非书面语（"咦/呼/哎呀"），与态度手势的情绪一致；
 *  - 与气泡文案解耦：气泡是随机反应，口播是动作语义，两者可同时出现。
 *
 * 与 PERSONA_GESTURES 的关系由测试保证一一对应（不在这里 import 动作库，
 * 避免循环引用：动作库只依赖本表做播报，不做动作定义）。
 */
export const PERSONA_GESTURE_VOICES = Object.freeze({
  // 社交礼仪
  wave: '你好呀，我是小鱼。',
  greet: '我是小鱼，随时待命。',
  bow: '多谢关照。',
  deepBow: '郑重感谢你的信任。',
  salute: '收到，马上执行！',
  // 应答态度
  nod: '嗯，明白了。',
  shake: '这样不太行哦。',
  thumbUp: '干得漂亮！',
  point: '看这里，请注意。',
  heart: '给你比个心。',
  // 情绪反应
  laugh: '哈哈，真让人开心。',
  shy: '哎呀，别这样夸我。',
  angry: '哼，别戳我啦！',
  tilt: '咦，怎么啦？',
  shrug: '这个我也没办法呀。',
  shiver: '哇，吓我一跳。',
  facepalm: '哎，这个我搞砸了。',
  leanBack: '啊？出什么事了？',
  // 工作状态
  think: '让我想一想。',
  leanIn: '我凑近看看。',
  snap: '有了，想到办法了！',
  lookAround: '咦，人去哪儿了？',
  applaud: '漂亮，值得鼓掌！',
  cheer: '加油，你可以的！',
  // 待机闲适
  stretch: '呼——伸个懒腰。',
  sleep: '呼……好困呀。',
  sway: '嗯～今天心情不错。',
  // 名片展示（借鉴王者「我的名片·元流之子」的耍帅站姿）
  armsCrossed: '嗯哼，你说吧。',
  handOnHip: '放心，交给我。',
  pointUp: '目标就在前方！',
  openArms: '欢迎来到智维平台。',
  // 战术手语（借用三角洲行动的无线电/停止/压低手势）
  radioCall: '收到呼叫，正在接入。',
  signalStop: '先停一下。',
  signalCover: '稍等，稳住。'
})

/**
 * 新增手势的多句口播变体（2026-11-16）：同一动作在不同情境下换种说法，
 * 由 gestureVoice 随机取一句，避免反复点击/反复触发时听到完全相同的台词。
 *
 * 约定：
 *  - 键必须是 PERSONA_GESTURE_VOICES 已登记的手势；
 *  - 第一句与 PERSONA_GESTURE_VOICES 的主文案保持一致（主文案仍是"最通用的一句"）；
 *  - 每句同样 ≤20 字，全部变体之间不重复。
 */
export const PERSONA_GESTURE_VOICE_VARIANTS = Object.freeze({
  // 社交礼仪
  wave: Object.freeze(['你好呀，我是小鱼。', '嗨，又见面啦。', '我在这儿呢，挥个手。']),
  greet: Object.freeze(['我是小鱼，随时待命。', '有事随时叫我。', '我盯着集群呢。']),
  bow: Object.freeze(['多谢关照。', '谢谢你的信任。', '辛苦你啦。']),
  deepBow: Object.freeze(['郑重感谢你的信任。', '这份信任我记下了。', '由衷感谢你的支持。']),
  salute: Object.freeze(['收到，马上执行！', '命令收到，立刻办。', '明白，这就去办。']),
  // 应答态度
  nod: Object.freeze(['嗯，明白了。', '好的，我记下了。', '收到，就这样办。']),
  shake: Object.freeze(['这样不太行哦。', '这个方案还得再想想。', '别急，先别这么做。']),
  thumbUp: Object.freeze(['干得漂亮！', '这波操作很稳。', '不错，值得表扬。']),
  point: Object.freeze(['看这里，请注意。', '这儿有个问题。', '重点在这儿。']),
  heart: Object.freeze(['给你比个心。', '有你在真好。', '谢谢你陪着我。']),
  // 情绪反应
  laugh: Object.freeze(['哈哈，真让人开心。', '太逗了，哈哈哈。', '这可太有意思了。']),
  shy: Object.freeze(['哎呀，别这样夸我。', '不好意思啦。', '别看了，我会害羞。']),
  angry: Object.freeze(['哼，别戳我啦！', '再戳我要生气了。', '住手，我可不是玩具。']),
  tilt: Object.freeze(['咦，怎么啦？', '有事吗？', '嗯？你在看我？']),
  shrug: Object.freeze(['这个我也没办法呀。', '我也很为难。', '这个真不归我管。']),
  shiver: Object.freeze(['哇，吓我一跳。', '别突然冒出来呀。', '刚才那下真吓人。']),
  facepalm: Object.freeze(['哎，这个我搞砸了。', '唉，是我疏忽了。', '抱歉，这个没做好。']),
  leanBack: Object.freeze(['啊？出什么事了？', '等等，什么情况？', '这变化有点突然。']),
  // 工作状态
  think: Object.freeze(['让我想一想。', '我在推理，稍等。', '这个问题得算一下。']),
  leanIn: Object.freeze(['我凑近看看。', '仔细查一下日志。', '让我看仔细点。']),
  snap: Object.freeze(['有了，想到办法了！', '找到原因了！', '思路通了！']),
  lookAround: Object.freeze(['咦，人去哪儿了？', '刚才还在的呀。', '有人在吗？']),
  applaud: Object.freeze(['漂亮，值得鼓掌！', '这波必须鼓掌。', '干得好，鼓掌！']),
  cheer: Object.freeze(['加油，你可以的！', '稳住，能搞定。', '再加把劲！']),
  // 待机闲适
  stretch: Object.freeze(['呼——伸个懒腰。', '坐久了，活动一下。', '啊——舒服多了。']),
  sleep: Object.freeze(['呼……好困呀。', '让我眯一会儿。', '困得睁不开眼了。']),
  sway: Object.freeze(['嗯～今天心情不错。', '这会儿挺轻松的。', '一切都在正轨上。']),
  // 名片展示类
  armsCrossed: Object.freeze(['嗯哼，你说吧。', '我在这儿听着呢。', '说吧，我等着。']),
  handOnHip: Object.freeze(['放心，交给我。', '这点事包在我身上。', '看我的吧。']),
  pointUp: Object.freeze(['目标就在前方！', '看那儿，就是它。', '方向已经锁定。']),
  openArms: Object.freeze(['欢迎来到智维平台。', '来吧，随便问。', '我随时都在。']),
  // 战术手语类
  radioCall: Object.freeze(['收到呼叫，正在接入。', '信号收到，开始处理。', '接到指令，马上跟进。']),
  signalStop: Object.freeze(['先停一下。', '等一下，别急。', '暂停，听我说。']),
  signalCover: Object.freeze(['稍等，稳住。', '别慌，交给我。', '放轻松，一步一步来。'])
})

/**
 * 取手势的口播文案；未登记的返回空串（调用方静默，不抛错）。
 * 有变体时随机取一句（random 可注入以便测试）。
 * @param {string} name PERSONA_GESTURES 的键
 * @param {() => number} [random] 取值源，默认 Math.random
 * @returns {string}
 */
export function gestureVoice(name, random = Math.random) {
  const variants = PERSONA_GESTURE_VOICE_VARIANTS[name]
  if (variants?.length) {
    const index = Math.min(variants.length - 1, Math.floor(random() * variants.length))
    return variants[index] ?? variants[0]
  }
  return PERSONA_GESTURE_VOICES[name] ?? ''
}

export const PERSONA_GESTURES = Object.freeze({
  wave: WAVE,
  nod: NOD,
  shake: SHAKE,
  bow: BOW,
  greet: GREET,
  laugh: LAUGH,
  tilt: TILT,
  stretch: STRETCH,
  sleep: SLEEP,
  cheer: CHEER,
  shy: SHY,
  think: THINK,
  angry: ANGRY,
  applaud: APPLAUD,
  shrug: SHRUG,
  salute: SALUTE,
  point: POINT,
  thumbUp: THUMB_UP,
  heart: HEART,
  shiver: SHIVER,
  facepalm: FACEPALM,
  leanIn: LEAN_IN,
  leanBack: LEAN_BACK,
  lookAround: LOOK_AROUND,
  sway: SWAY,
  snap: SNAP,
  deepBow: DEEP_BOW,
  armsCrossed: ARMS_CROSSED,
  handOnHip: HAND_ON_HIP,
  pointUp: POINT_UP,
  openArms: OPEN_ARMS,
  radioCall: RADIO_CALL,
  signalStop: SIGNAL_STOP,
  signalCover: SIGNAL_COVER
})

export const PERSONA_GESTURE_NAMES = Object.freeze(Object.keys(PERSONA_GESTURES))

/**
 * 手势表情轨道（VRM blendshape 权重）。
 *
 * 为什么和骨骼关键帧分开：35 个手势的骨骼关键帧已经很密，把每个关键帧都改成
 * 「骨骼 + 表情」双通道，一是改动面巨大，二是大多数动作并不需要表情。
 * 这里单独维护 name → 表情关键帧，只有需要情绪的动作才登记，未登记 = 无表情增量。
 *
 * 约定与骨骼一致：t ∈ [0,1]，首尾必须为空权重（从零起、回零收），中间用 smoothstep 插值。
 * 权重是**叠加在状态表情之上的增量**，由渲染层 clamp 到 1：
 * 例如 idle 有 relaxed 0.25，laugh 再叠 happy 0.9，最终 happy=0.9、relaxed=0.25。
 *
 * blink 特殊：它不是情绪而是眼睑，渲染层用 max() 与自动眨眼合并，
 * 因此 sleep 这类"闭眼"动作可以安全地写 blink:1 而不会被自动眨眼打断。
 */
function expressionTrack(points) {
  return Object.freeze([
    Object.freeze({ t: 0, weights: Object.freeze({}) }),
    ...points.map(([t, weights]) => Object.freeze({ t, weights: Object.freeze(weights) })),
    Object.freeze({ t: 1, weights: Object.freeze({}) })
  ])
}

export const PERSONA_GESTURE_EXPRESSIONS = Object.freeze({
  // 社交礼仪
  wave: expressionTrack([[0.18, { happy: 0.5 }], [0.78, { happy: 0.5 }]]),
  greet: expressionTrack([[0.3, { happy: 0.55, relaxed: 0.2 }], [0.72, { happy: 0.5 }]]),
  bow: expressionTrack([[0.3, { relaxed: 0.35 }], [0.7, { relaxed: 0.35 }]]),
  deepBow: expressionTrack([[0.28, { relaxed: 0.5, happy: 0.2 }], [0.72, { relaxed: 0.45 }]]),
  salute: expressionTrack([[0.2, { happy: 0.35 }], [0.8, { happy: 0.3 }]]),
  // 应答态度
  nod: expressionTrack([[0.35, { relaxed: 0.3 }], [0.75, { relaxed: 0.25 }]]),
  shake: expressionTrack([[0.3, { sad: 0.2 }], [0.65, { sad: 0.2 }]]),
  thumbUp: expressionTrack([[0.2, { happy: 0.7 }], [0.8, { happy: 0.6 }]]),
  point: expressionTrack([[0.2, { relaxed: 0.3 }], [0.8, { relaxed: 0.25 }]]),
  heart: expressionTrack([[0.25, { happy: 0.75, relaxed: 0.3 }], [0.75, { happy: 0.7 }]]),
  // 情绪反应
  laugh: expressionTrack([[0.2, { happy: 0.9 }], [0.6, { happy: 0.8 }], [0.8, { happy: 0.6 }]]),
  shy: expressionTrack([[0.2, { happy: 0.6, relaxed: 0.4 }], [0.8, { happy: 0.55 }]]),
  angry: expressionTrack([[0.15, { angry: 0.75 }], [0.85, { angry: 0.6 }]]),
  tilt: expressionTrack([[0.25, { surprised: 0.3 }], [0.7, { surprised: 0.25 }]]),
  shrug: expressionTrack([[0.2, { sad: 0.25, relaxed: 0.3 }], [0.8, { sad: 0.2 }]]),
  shiver: expressionTrack([[0.1, { surprised: 0.7 }], [0.5, { surprised: 0.35 }]]),
  facepalm: expressionTrack([[0.2, { sad: 0.5 }], [0.7, { sad: 0.4 }]]),
  leanBack: expressionTrack([[0.15, { surprised: 0.6 }], [0.6, { surprised: 0.3 }]]),
  // 工作状态
  think: expressionTrack([[0.2, { relaxed: 0.2 }], [0.8, { relaxed: 0.2 }]]),
  leanIn: expressionTrack([[0.2, { relaxed: 0.2, surprised: 0.15 }], [0.8, { relaxed: 0.2 }]]),
  snap: expressionTrack([[0.1, { surprised: 0.6 }], [0.35, { happy: 0.85 }], [0.85, { happy: 0.7 }]]),
  lookAround: expressionTrack([[0.2, { surprised: 0.25 }], [0.8, { surprised: 0.2 }]]),
  applaud: expressionTrack([[0.15, { happy: 0.85 }], [0.85, { happy: 0.7 }]]),
  cheer: expressionTrack([[0.15, { happy: 0.9 }], [0.8, { happy: 0.75 }]]),
  // 待机闲适
  stretch: expressionTrack([[0.25, { relaxed: 0.45 }], [0.8, { relaxed: 0.3 }]]),
  // 打瞌睡闭眼：blink 由渲染层与自动眨眼取 max，不会被眨眼打断
  sleep: expressionTrack([[0.12, { blink: 1, relaxed: 0.6 }], [0.9, { blink: 1, relaxed: 0.6 }]]),
  sway: expressionTrack([[0.2, { happy: 0.35, relaxed: 0.35 }], [0.8, { happy: 0.3 }]]),
  // 名片展示
  armsCrossed: expressionTrack([[0.2, { relaxed: 0.35 }], [0.8, { relaxed: 0.3 }]]),
  handOnHip: expressionTrack([[0.2, { happy: 0.4, relaxed: 0.3 }], [0.8, { happy: 0.35 }]]),
  pointUp: expressionTrack([[0.15, { happy: 0.75 }], [0.8, { happy: 0.6 }]]),
  openArms: expressionTrack([[0.2, { happy: 0.6, relaxed: 0.3 }], [0.8, { happy: 0.5 }]]),
  // 战术手语（专注表情：不笑、略收）
  radioCall: expressionTrack([[0.15, { relaxed: 0.15 }], [0.8, { relaxed: 0.15 }]]),
  signalStop: expressionTrack([[0.1, { relaxed: 0.1 }], [0.7, { relaxed: 0.1 }]]),
  signalCover: expressionTrack([[0.1, { relaxed: 0.1 }], [0.7, { relaxed: 0.1 }]])
})

/**
 * 采样手势在时刻 t（秒）的表情增量。
 * @param {string} name 手势名
 * @param {number} seconds 已播放秒数
 * @returns {Record<string, number>} blendshape 名 → 权重增量（0~1）
 */
export function sampleGestureExpressions(name, seconds) {
  const track = PERSONA_GESTURE_EXPRESSIONS[name]
  const duration = PERSONA_GESTURES[name]?.duration ?? 0
  if (!track || !(duration > 0)) return {}
  const t = Math.min(1, Math.max(0, seconds / duration))
  if (t <= 0 || t >= 1) return {}
  let lo = 0
  for (let i = 0; i < track.length - 1; i += 1) {
    if (track[i].t <= t && t <= track[i + 1].t) {
      lo = i
      break
    }
  }
  const a = track[lo]
  const b = track[lo + 1] ?? track[lo]
  const k = smoothstep(a.t, b.t, t)
  const result = {}
  for (const name of new Set([...Object.keys(a.weights), ...Object.keys(b.weights)])) {
    const from = a.weights[name] ?? 0
    const to = b.weights[name] ?? 0
    const value = from + (to - from) * k
    if (value > 0.001) result[name] = value
  }
  return result
}

/** smoothstep：关键帧间缓动，比线性柔和，比弹簧便宜 */
function smoothstep(edge0, edge1, x) {
  const span = edge1 - edge0
  if (span <= 0) return x >= edge1 ? 1 : 0
  const t = Math.min(1, Math.max(0, (x - edge0) / span))
  return t * t * (3 - 2 * t)
}

/**
 * 采样手势在时刻 t（秒）的骨骼增量。
 * @returns {Record<string, {x:number, y:number, z:number}>} 骨骼名 → 旋转增量（该帧涉及的骨骼）
 */
export function sampleGesture(gesture, seconds) {
  const { keys, duration } = gesture
  if (!keys?.length || !(duration > 0)) return {}
  const t = Math.min(1, Math.max(0, seconds / duration))
  if (t <= 0 || t >= 1) return {}
  let lo = 0
  for (let i = 0; i < keys.length - 1; i += 1) {
    if (keys[i].t <= t && t <= keys[i + 1].t) {
      lo = i
      break
    }
  }
  const a = keys[lo]
  const b = keys[lo + 1] ?? keys[lo]
  const k = smoothstep(a.t, b.t, t)
  const result = {}
  const bones = new Set([...Object.keys(a.pose), ...Object.keys(b.pose)])
  for (const bone of bones) {
    const pa = a.pose[bone] ?? {}
    const pb = b.pose[bone] ?? {}
    result[bone] = {
      x: (pa.x ?? 0) + ((pb.x ?? 0) - (pa.x ?? 0)) * k,
      y: (pa.y ?? 0) + ((pb.y ?? 0) - (pa.y ?? 0)) * k,
      z: (pa.z ?? 0) + ((pb.z ?? 0) - (pa.z ?? 0)) * k
    }
  }
  return result
}

/** 手势合法性：骨骼名必须都在给定骨骼集合内，首尾关键帧必须为空增量 */
export function validateGestures(gestures, allowedBones) {
  const problems = []
  for (const [name, gesture] of Object.entries(gestures)) {
    const keys = gesture.keys ?? []
    if (!(gesture.duration > 0)) problems.push(`${name}: duration 必须为正`)
    if (keys.length < 2) problems.push(`${name}: 关键帧至少 2 个`)
    for (const key of keys) {
      for (const bone of Object.keys(key.pose ?? {})) {
        if (!allowedBones.includes(bone)) problems.push(`${name}: 骨骼 ${bone} 不在渲染层骨骼集合中`)
      }
    }
    const first = keys[0]
    const last = keys[keys.length - 1]
    if (first && Object.keys(first.pose ?? {}).length) problems.push(`${name}: 首关键帧必须为空增量`)
    if (last && (last.t !== 1 || Object.keys(last.pose ?? {}).length)) {
      problems.push(`${name}: 末关键帧必须 t=1 且为空增量（保证回零收尾）`)
    }
    for (const key of keys) {
      if (key.t < 0 || key.t > 1) problems.push(`${name}: 关键帧 t 越界`)
    }
    if (name === 'wave' && keys.length < 5) problems.push('wave: 需要至少两拍摆动（≥5 关键帧）')
  }
  return problems
}
