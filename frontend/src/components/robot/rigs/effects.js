/**
 * 3D 机器人状态灯 / LiDAR 扫描的动画参数（纯函数，无 three 依赖，可单测）。
 *
 * 状态灯：常态慢呼吸（绿），告警快闪（红），心跳超时压暗；
 * 扫描环：从本体向外扩散并淡出，循环播放；扫描扇面由 rig 自己按角度旋转。
 *
 * 所有可调参数集中在 DEFAULT_EFFECT_CONFIG，调用方可用 `effects` 选项局部覆盖。
 */

/** 可配置项默认值（全部为数字，单位见注释）。 */
export const DEFAULT_EFFECT_CONFIG = Object.freeze({
  /** 状态灯常态呼吸频率（Hz） */
  beaconIdleHz: 0.8,
  /** 状态灯告警闪烁频率（Hz） */
  beaconAlarmHz: 3,
  /** 地面扫描环扩张周期（秒） */
  scanPeriod: 2.4,
  /** LiDAR 常态转速（rad/s） */
  lidarSpeed: 3.2,
  /** LiDAR 告警转速（rad/s） */
  lidarAlarmSpeed: 6.4,
  /** 扫描环最高不透明度 */
  ringMaxOpacity: 0.34,
  /** 心跳超时时扫描环不透明度 */
  ringStaleOpacity: 0.1
})

/**
 * 合并调用方覆盖项：只接受非负有限数字，非法值回落到默认。
 * @param {Partial<typeof DEFAULT_EFFECT_CONFIG>} [partial]
 * @returns {typeof DEFAULT_EFFECT_CONFIG}
 */
export function resolveEffectConfig(partial) {
  const config = { ...DEFAULT_EFFECT_CONFIG }
  if (!partial || typeof partial !== 'object') return config
  for (const key of Object.keys(DEFAULT_EFFECT_CONFIG)) {
    const value = Number(partial[key])
    if (Number.isFinite(value) && value >= 0) config[key] = value
  }
  return config
}

/**
 * 状态灯参数。
 * @param {number} t 累计秒数
 * @param {{alarm?: boolean, stale?: boolean, idleHz?: number, alarmHz?: number}} options
 * @returns {{intensity: number, scale: number}} emissive 强度与缩放倍率
 */
export function beaconPulse(t, {
  alarm = false,
  stale = false,
  idleHz = DEFAULT_EFFECT_CONFIG.beaconIdleHz,
  alarmHz = DEFAULT_EFFECT_CONFIG.beaconAlarmHz
} = {}) {
  if (stale) return { intensity: 0.35, scale: 1 }
  const time = Number.isFinite(t) ? t : 0
  const hz = alarm ? alarmHz : idleHz
  /* 0→1 的呼吸波：正弦抬到正值区间，避免灯被压灭 */
  const wave = 0.5 + 0.5 * Math.sin(time * hz * Math.PI * 2)
  return {
    intensity: alarm ? 1.2 + 2.2 * wave : 0.9 + 0.9 * wave,
    scale: alarm ? 1 + 0.3 * wave : 1 + 0.12 * wave
  }
}

/**
 * 地面扫描环参数：progress 0→1 线性推进，半径由内向外扩张、透明度递减。
 * @param {number} t 累计秒数
 * @param {{period?: number, stale?: boolean, maxOpacity?: number, staleOpacity?: number}} options
 * @returns {{progress: number, scale: number, opacity: number}}
 */
export function scanRing(t, {
  period = DEFAULT_EFFECT_CONFIG.scanPeriod,
  stale = false,
  maxOpacity = DEFAULT_EFFECT_CONFIG.ringMaxOpacity,
  staleOpacity = DEFAULT_EFFECT_CONFIG.ringStaleOpacity
} = {}) {
  const time = Number.isFinite(t) ? t : 0
  const cycle = Number.isFinite(period) && period > 0 ? period : DEFAULT_EFFECT_CONFIG.scanPeriod
  const raw = (time % cycle) / cycle
  const progress = raw < 0 ? raw + 1 : raw
  return {
    progress,
    scale: 0.4 + progress * 0.9,
    opacity: (1 - progress) * (stale ? staleOpacity : maxOpacity)
  }
}
