/**
 * 步态解算角（gait.js）→ 宇树官方 MJCF 关节角 的纯函数映射（无 three 依赖，node --test 可覆盖）。
 *
 * 原则：以官方 home 站立姿态为零点，只叠加「gait 输出 − gait 站立值」的增量；
 * 真机绝对关节角不经过本模块（unitreeGlbRig 直接按关节名覆盖）。
 *
 * 符号推导（MJCF：+X 前、+Y 左、+Z 上；gait.js：thigh>0 足前摆、calf>0 屈膝回折、hip>0 外展）：
 * - thigh/knee/shoulder/elbow 轴 = 0 1 0：绕 +Y 正旋使下垂的腿/臂向后（-X）摆，
 *   故「前摆为正」的 gait 角映射为负增量，「回折为正」映射为正增量；
 * - Go2 abduction 轴 = 1 0 0：左腿（+Y 侧）q>0 外展，右腿相反，左右异号；
 * - Go2 官方 home：thigh=0.9 / calf=-1.8（keyframe），gait 站立值 thigh=-0.18 / calf=0.62；
 * - G1 官方 home 全 0（直腿站立），gait 站立值 calf=0.06 / fore=0.3，增量归零后直腿。
 */

import { QUADRUPED_LEGS, QUADRUPED_STAND_POSE } from './gait.js'

/** 人形 gait 站立值（humanoidPose speed=0 时的输出）。 */
export const HUMANOID_STAND = Object.freeze({ thigh: 0, calf: 0.06, foot: 0, upper: 0, fore: 0.3 })

function homeOf(jointsMeta, name) {
  return Number(jointsMeta?.[name]?.home) || 0
}

/**
 * Go2 四足：quadrupedPose 输出 → 12 个 MJCF 关节目标角。
 * @param {ReturnType<import('./gait.js').quadrupedPose>} pose
 * @param {Record<string, {home?: number}>} jointsMeta go2.rig.json 的 joints
 */
export function go2JointTargets(pose, jointsMeta = {}) {
  const targets = {}
  for (const leg of QUADRUPED_LEGS) {
    const lp = pose?.legs?.[leg]
    if (!lp) continue
    const hipName = `${leg}_hip_joint`
    const thighName = `${leg}_thigh_joint`
    const calfName = `${leg}_calf_joint`
    /* 左腿外展为正，右腿镜像取负 */
    const abductionSign = leg.endsWith('L') ? 1 : -1
    targets[hipName] = homeOf(jointsMeta, hipName) + abductionSign * ((lp.hip ?? 0) - QUADRUPED_STAND_POSE.hip)
    targets[thighName] = homeOf(jointsMeta, thighName) - ((lp.thigh ?? 0) - QUADRUPED_STAND_POSE.thigh)
    targets[calfName] = homeOf(jointsMeta, calfName) - ((lp.calf ?? 0) - QUADRUPED_STAND_POSE.calf)
  }
  return targets
}

/**
 * G1 人形：humanoidPose 输出 → 11 个受步态驱动的关节目标角（其余关节保持 home）。
 * @param {ReturnType<import('./gait.js').humanoidPose>} pose
 * @param {Record<string, {home?: number}>} jointsMeta g1.rig.json 的 joints
 */
export function g1JointTargets(pose, jointsMeta = {}) {
  const targets = {}
  const sides = { L: 'left', R: 'right' }
  for (const [side, prefix] of Object.entries(sides)) {
    const lp = pose?.legs?.[side]
    if (lp) {
      const hip = `${prefix}_hip_pitch_joint`
      const knee = `${prefix}_knee_joint`
      const ankle = `${prefix}_ankle_pitch_joint`
      targets[hip] = homeOf(jointsMeta, hip) - ((lp.thigh ?? 0) - HUMANOID_STAND.thigh)
      targets[knee] = homeOf(jointsMeta, knee) + ((lp.calf ?? 0) - HUMANOID_STAND.calf)
      targets[ankle] = homeOf(jointsMeta, ankle) - ((lp.foot ?? 0) - HUMANOID_STAND.foot)
    }
    const ap = pose?.arms?.[side]
    if (ap) {
      const shoulder = `${prefix}_shoulder_pitch_joint`
      const elbow = `${prefix}_elbow_joint`
      targets[shoulder] = homeOf(jointsMeta, shoulder) - ((ap.upper ?? 0) - HUMANOID_STAND.upper)
      targets[elbow] = homeOf(jointsMeta, elbow) + ((ap.fore ?? 0) - HUMANOID_STAND.fore)
    }
  }
  if (pose?.torso) {
    targets.waist_yaw_joint = homeOf(jointsMeta, 'waist_yaw_joint') + (pose.torso.yaw || 0)
  }
  return targets
}
