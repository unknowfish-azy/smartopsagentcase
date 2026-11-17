/**
 * 遥控能力模型（纯数据 + 纯函数）。
 *
 * 设计契约：**UI 由能力清单驱动，不按设备类型写 if-else**。
 * 四类设备的运动学差异在这里声明一次，摇杆面板只读 axes/maxSpeed/gaits。
 *
 * 轴命名与后端命令参数一一对应：
 *   forward → x（纵向，[-1,1]）
 *   lateral → y（横向平移，[-1,1]）
 *   yaw     → theta（自转，[-1,1]）
 *   gait    → gait（步态枚举，仅四足有）
 *
 * 不支持的轴一律钳到 0 并记入 unsupportedAxes，绝不「猜一个合理值」。
 */

/** 全部可声明轴（顺序即 UI 展示顺序）。 */
export const TELEOP_AXES = Object.freeze(['forward', 'lateral', 'yaw', 'gait'])

/**
 * 形态 → 能力清单（**兜底副本**）。
 *
 * 权威表在后端 RobotTeleopProfiles，随 GET /api/robot/devices 的 `teleop` 下发；
 * 这里只在后端未下发或字段不合法时使用（离线演示、旧版后端），
 * 改动能力表请改后端，不要只改这里。
 *
 * - CAR     差速车：只能前进 + 自转，横向平移无执行器
 * - DOG     四足：可横移、可自转，另有步态档位
 * - SPIDER  全向轮/麦轮：可横移、可自转
 * - ROBOT   通用巡检机器人：保守按差速处理（宁可少给一个轴）
 */
export const TELEOP_PROFILES = Object.freeze({
  CAR: Object.freeze({
    formFactor: 'CAR',
    label: '巡逻车',
    kinematics: 'differential',
    axes: Object.freeze(['forward', 'yaw']),
    maxSpeed: Object.freeze({ linear: 0.6, angular: 0.85 }),
    gaits: Object.freeze([]),
    maxSpeedNote: '差速：前进 + 自转，无横移执行器'
  }),
  DOG: Object.freeze({
    formFactor: 'DOG',
    label: '机器狗',
    kinematics: 'quadruped',
    axes: Object.freeze(['forward', 'lateral', 'yaw', 'gait']),
    maxSpeed: Object.freeze({ linear: 0.35, angular: 0.7 }),
    gaits: Object.freeze(['TROT', 'WALK', 'STAND']),
    maxSpeedNote: '四足：可横移，限速低于轮式以免失稳'
  }),
  SPIDER: Object.freeze({
    formFactor: 'SPIDER',
    label: '蜘蛛机器人',
    kinematics: 'omnidirectional',
    axes: Object.freeze(['forward', 'lateral', 'yaw']),
    maxSpeed: Object.freeze({ linear: 0.45, angular: 0.8 }),
    gaits: Object.freeze([]),
    maxSpeedNote: '全向：三轴独立，可原地横移'
  }),
  ROBOT: Object.freeze({
    formFactor: 'ROBOT',
    label: '巡检机器人',
    kinematics: 'differential',
    axes: Object.freeze(['forward', 'yaw']),
    maxSpeed: Object.freeze({ linear: 0.5, angular: 0.8 }),
    gaits: Object.freeze([]),
    maxSpeedNote: '通用形态：保守按差速处理'
  })
})

/** 未识别形态的兜底：只给最保守的两轴，并标记 known=false 让 UI 如实提示。 */
const UNKNOWN_PROFILE = Object.freeze({
  formFactor: 'UNKNOWN',
  label: '未知形态',
  kinematics: 'differential',
  axes: Object.freeze(['forward', 'yaw']),
  maxSpeed: Object.freeze({ linear: 0.3, angular: 0.5 }),
  gaits: Object.freeze([]),
  maxSpeedNote: '形态未登记：按差速最低限速运行'
})

/** 后端 MOVE 的 ttlMs 合法区间（与 RobotCommandPolicy 保持一致）。 */
export const TELEOP_TTL_MS = 200
/** 20Hz 上限下留出的安全间隔：后端硬限 20 条/秒，80ms ≈ 12.5Hz。 */
export const TELEOP_INTERVAL_MS = 80

export const DEFAULT_GAIT = 'TROT'

/**
 * 由台账设备解出遥控能力。
 *
 * **权威来源是后端 `device.teleop`**（RobotTeleopProfiles）；本地 TELEOP_PROFILES
 * 只在后端未下发/字段不合法时兜底（离线演示、旧版后端），并用 `source` 如实标注。
 *
 * @param {object|null} device 后端 GET /api/robot/devices 的单条记录
 * @returns {object} profile（含 deviceKey / known / teleopCapable / source / reason）
 */
export function resolveTeleopProfile(device) {
  if (!device || typeof device !== 'object') {
    return {
      ...UNKNOWN_PROFILE,
      deviceKey: '',
      known: false,
      teleopCapable: false,
      source: 'local',
      reason: '未选择设备'
    }
  }

  // 台账 capabilities 是「整机能力」清单；没有 MOVE 就是不可遥控（例如只读占位设备）
  const declared = normalizeCapabilities(device.capabilities)
  const lacksMove = declared !== null && !declared.includes('MOVE')

  const raw = typeof device.formFactor === 'string' ? device.formFactor.trim().toUpperCase() : ''
  const local = TELEOP_PROFILES[raw]
  const remote = normalizeRemoteProfile(device.teleop)
  const base = remote || local || UNKNOWN_PROFILE

  return {
    ...base,
    axes: [...base.axes],
    gaits: [...base.gaits],
    deviceKey: typeof device.deviceKey === 'string' ? device.deviceKey : '',
    known: remote ? remote.known !== false : Boolean(local),
    teleopCapable: !lacksMove,
    source: remote ? 'backend' : 'local',
    reason: lacksMove ? '该设备未声明 MOVE 能力，仅可查看不可遥控' : ''
  }
}

/** 远端能力清单的字段校验：任何关键字段不合法就整体弃用，绝不半信半疑地部分采信。 */
function normalizeRemoteProfile(remote) {
  if (!remote || typeof remote !== 'object') return null
  const axes = Array.isArray(remote.axes)
    ? remote.axes.filter((axis) => TELEOP_AXES.includes(axis))
    : []
  if (!axes.includes('forward')) return null

  const maxSpeed = remote.maxSpeed && typeof remote.maxSpeed === 'object' ? remote.maxSpeed : {}
  const linear = Number(maxSpeed.linear)
  const angular = Number(maxSpeed.angular)
  if (!Number.isFinite(linear) || !Number.isFinite(angular)) return null

  return {
    formFactor: typeof remote.formFactor === 'string' ? remote.formFactor : 'UNKNOWN',
    label: typeof remote.label === 'string' && remote.label ? remote.label : '未知形态',
    kinematics: typeof remote.kinematics === 'string' ? remote.kinematics : 'differential',
    axes,
    maxSpeed: { linear, angular },
    gaits: Array.isArray(remote.gaits) ? remote.gaits.filter((gait) => typeof gait === 'string') : [],
    maxSpeedNote: typeof remote.maxSpeedNote === 'string' ? remote.maxSpeedNote : '',
    known: remote.known !== false
  }
}

/** capabilities 可能是数组，也可能是后端未解析的 JSON 字符串。 */
function normalizeCapabilities(raw) {
  if (Array.isArray(raw)) return raw.filter((item) => typeof item === 'string')
  if (typeof raw === 'string' && raw.trim()) {
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed.filter((item) => typeof item === 'string') : null
    } catch {
      return null
    }
  }
  return null
}

/**
 * 摇杆二维向量 → 各轴意图。
 *
 * 规则（唯一的分支点，按能力而非类型）：
 * - 有 lateral 轴：摇杆 X 直接映射横移（全向/四足）
 * - 无 lateral 轴：摇杆 X 映射自转（差速车的天然手感）
 *
 * @param {object} profile resolveTeleopProfile 的返回值
 * @param {{x:number,y:number}} vector 归一化摇杆向量（x=右, y=前）
 * @returns {{forward:number, lateral:number, yaw:number}}
 */
export function mapJoystickToAxes(profile, vector) {
  const axes = profile?.axes || []
  const x = clampUnit(vector?.x)
  const y = clampUnit(vector?.y)
  const strafes = axes.includes('lateral')
  return {
    forward: y,
    lateral: strafes ? x : 0,
    yaw: strafes ? 0 : x
  }
}

/**
 * 组装后端 MOVE 参数。不支持的轴强制为 0，并在 unsupportedAxes 里如实回报。
 *
 * @param {object} profile resolveTeleopProfile 的返回值
 * @param {{forward?:number,lateral?:number,yaw?:number}} intent 各轴意图 [-1,1]
 * @param {{speed?:number, ttlMs?:number, gait?:string}} options
 */
export function buildMoveParams(profile, intent, options = {}) {
  const axes = profile?.axes || []
  const forward = axes.includes('forward') ? clampUnit(intent?.forward) : 0
  const lateral = axes.includes('lateral') ? clampUnit(intent?.lateral) : 0
  const yaw = axes.includes('yaw') ? clampUnit(intent?.yaw) : 0

  const unsupportedAxes = []
  if (!axes.includes('lateral') && clampUnit(intent?.lateral) !== 0) unsupportedAxes.push('lateral')
  if (!axes.includes('yaw') && clampUnit(intent?.yaw) !== 0) unsupportedAxes.push('yaw')

  const maxLinear = Number(profile?.maxSpeed?.linear)
  const speed = Number.isFinite(options.speed)
    ? clamp01(options.speed)
    : clamp01(Number.isFinite(maxLinear) ? maxLinear : 0.3)

  const ttlMs = Number.isFinite(options.ttlMs) ? Math.round(options.ttlMs) : TELEOP_TTL_MS

  const params = {
    x: round3(forward),
    y: round3(lateral),
    theta: round3(yaw),
    speed: round3(speed),
    ttlMs
  }

  // 步态只在设备真的声明了 gait 轴时下发；否则连字段都不出现，避免误导桥端
  if (axes.includes('gait')) {
    const gaits = profile?.gaits || []
    params.gait = gaits.includes(options.gait) ? options.gait : (gaits[0] || DEFAULT_GAIT)
  }

  return { params, unsupportedAxes }
}

/**
 * 命令节流器：同一间隔内只放行第一条，返回是否放行。
 * 纯函数化（注入 now）便于单测，不依赖真实时钟。
 *
 * @param {number} intervalMs 最小间隔
 * @param {number} startAt 起始时间戳
 */
export function createCommandPacer(intervalMs = TELEOP_INTERVAL_MS, startAt = 0) {
  let lastAt = startAt - intervalMs
  return {
    /** @param {number} at 当前时间戳 */
    allow(at) {
      if (!Number.isFinite(at)) return false
      if (at - lastAt < intervalMs) return false
      lastAt = at
      return true
    },
    reset(at = 0) {
      lastAt = at - intervalMs
    },
    get lastAt() {
      return lastAt
    }
  }
}

/** 命令序号：桥端据此判丢包/乱序，必须严格递增。 */
export function createCommandSequence(start = 1) {
  let value = Number.isFinite(start) ? start : 1
  return {
    next() {
      const current = value
      value += 1
      return current
    },
    get current() {
      return value
    }
  }
}

/** 全零意图判定：用于「松手」与非零命令的分流。 */
export function isIdleIntent(intent) {
  return clampUnit(intent?.forward) === 0
    && clampUnit(intent?.lateral) === 0
    && clampUnit(intent?.yaw) === 0
}

function clampUnit(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return 0
  return Math.max(-1, Math.min(1, num))
}

function clamp01(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return 0
  return Math.max(0, Math.min(1, num))
}

function round3(value) {
  return Number(value.toFixed(3))
}
