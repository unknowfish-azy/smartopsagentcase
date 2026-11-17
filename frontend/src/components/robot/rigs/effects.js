/**
 * 3D 机器人状态灯 / LiDAR 扫描的动画参数（纯函数，无 three 依赖，可单测）。
 *
 * 状态灯：由真实业务状态（心跳、急停/故障、障碍距离、电量、运行模式）决定颜色与节奏；
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

/** 低电量阈值（0~1 比例或百分数均可，见 resolveBeaconStatus） */
export const LOW_BATTERY_RATIO = 0.2
/** 障碍距离告警阈值（米） */
export const NEAR_OBSTACLE_METERS = 0.5

/**
 * 状态灯预设：颜色 / 自发光 / 呼吸频率来源（idle 或 alarm 基准 × 倍率）/ 亮度区间 / 脉冲幅度。
 * source 指「用调节面板里的哪一档基准频率」，factor 是相对倍率，保证面板滑杆依然有效。
 */
export const BEACON_STATUS = Object.freeze({
  idle: { color: 0x5ad691, emissive: 0x1c5a37, source: 'idle', factor: 1, intensity: [0.9, 1.8], scaleAmp: 0.12 },
  running: { color: 0x5b8cff, emissive: 0x14336b, source: 'idle', factor: 1.6, intensity: [1.1, 2.1], scaleAmp: 0.14 },
  manual: { color: 0x57c8d8, emissive: 0x14505a, source: 'idle', factor: 1.2, intensity: [0.9, 1.7], scaleAmp: 0.1 },
  warn: { color: 0xe3a008, emissive: 0x5a3d00, source: 'alarm', factor: 0.5, intensity: [1, 2], scaleAmp: 0.16 },
  fault: { color: 0xe5484d, emissive: 0x7a1418, source: 'alarm', factor: 1, intensity: [1.2, 3.4], scaleAmp: 0.3 },
  offline: { color: 0x8a8f98, emissive: 0x2a2d33, source: 'idle', factor: 1, intensity: [0.35, 0.35], scaleAmp: 0 }
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

/** 数值安全转换：null / undefined / 空串视为「无数据」，避免被 Number 转成 0 造成误报。 */
function toNumber(value) {
  if (value === null || value === undefined || value === '') return NaN
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : NaN
}

/**
 * 由真实遥测/模式推导状态灯业务状态（优先级从高到低）。
 * @param {{mode?: string, battery?: number, stale?: boolean, obstacleDistance?: number}} [input]
 * @returns {{key: string} & typeof BEACON_STATUS.idle}
 */
export function resolveBeaconStatus({ mode, battery, stale = false, obstacleDistance } = {}) {
  const normalizedMode = String(mode || '').toUpperCase()
  /* 1. 心跳中断：离线灰，覆盖其他一切状态 */
  if (stale || normalizedMode === 'OFFLINE') return { key: 'offline', ...BEACON_STATUS.offline }
  /* 2. 急停 / 故障：红色快闪 */
  if (normalizedMode === 'E_STOP' || normalizedMode === 'FAULT') return { key: 'fault', ...BEACON_STATUS.fault }
  /* 3. 障碍过近：琥珀色警示 */
  const obstacle = toNumber(obstacleDistance)
  if (Number.isFinite(obstacle) && obstacle < NEAR_OBSTACLE_METERS) return { key: 'warn', ...BEACON_STATUS.warn }
  /* 4. 低电量：琥珀色警示（兼容 0~1 比例与 0~100 百分数） */
  const rawBattery = toNumber(battery)
  if (Number.isFinite(rawBattery)) {
    const ratio = rawBattery > 1 ? rawBattery / 100 : rawBattery
    if (ratio < LOW_BATTERY_RATIO) return { key: 'warn', ...BEACON_STATUS.warn }
  }
  /* 5. 运行中：自主巡检蓝色呼吸，人工接管青色呼吸 */
  if (normalizedMode === 'AUTONOMOUS') return { key: 'running', ...BEACON_STATUS.running }
  if (normalizedMode === 'HUMAN_CONTROL') return { key: 'manual', ...BEACON_STATUS.manual }
  /* 6. 其余（IDLE 等）：常态绿色呼吸 */
  return { key: 'idle', ...BEACON_STATUS.idle }
}

/**
 * 状态灯参数。
 *
 * 两种调用方式：
 * - 旧式：`beaconPulse(t, { alarm, stale })` → 绿色呼吸 / 红色告警闪烁；
 * - 业务态：`beaconPulse(t, { hz, intensity, scaleAmp, stale })` → 按状态预设的节奏与亮度。
 * @param {number} t 累计秒数
 * @param {{alarm?: boolean, stale?: boolean, idleHz?: number, alarmHz?: number, hz?: number,
 *   intensity?: [number, number], scaleAmp?: number}} options
 * @returns {{intensity: number, scale: number}} emissive 强度与缩放倍率
 */
export function beaconPulse(t, {
  alarm = false,
  stale = false,
  idleHz = DEFAULT_EFFECT_CONFIG.beaconIdleHz,
  alarmHz = DEFAULT_EFFECT_CONFIG.beaconAlarmHz,
  hz,
  intensity,
  scaleAmp
} = {}) {
  if (stale) return { intensity: 0.35, scale: 1 }
  const time = Number.isFinite(t) ? t : 0
  const frequency = Number.isFinite(hz) ? hz : (alarm ? alarmHz : idleHz)
  const wave = 0.5 + 0.5 * Math.sin(time * frequency * Math.PI * 2)
  const lo = Array.isArray(intensity) ? Number(intensity[0]) : NaN
  const hi = Array.isArray(intensity) ? Number(intensity[1]) : NaN
  if (Number.isFinite(lo) && Number.isFinite(hi)) {
    const amp = Number.isFinite(scaleAmp) ? scaleAmp : 0.14
    return { intensity: lo + (hi - lo) * wave, scale: 1 + amp * wave }
  }
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
