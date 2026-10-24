// 里程碑庆祝粒子引擎：纯函数、无 DOM/框架依赖，可单测（node --test）。
// 视觉来源：「量化机器人麻袋装钱」类展示的金币雨 + 钱袋填充动效。
// 落地约束（design-system/MASTER.md + 合规结论）：
// - 只作真实里程碑的庆祝动效，绝不绑定虚构收益/回撤（证据优先红线）；
// - 几何锐利：金币一律旋转菱形，不用正圆；
// - 单强调色 + 受控庆祝金：gold 调色板仅存在于本特效画布，不进入状态色/数据色；
// - 袋容量有上限：满了溢出逃逸，不无限堆叠——画面不撒谎。

// mulberry32：小巧确定性 PRNG，同种子同序列（测试可复现、静态帧可重绘）
export function createRng(seed = 1) {
  let a = seed >>> 0
  return function rng() {
    a |= 0
    a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export const GRAVITY = 1500 // px/s²，屏幕空间常数（组件按容器尺寸换算由调用方决定）

// 麻袋几何：以容器尺寸推导，袋口略窄于袋身；columns/capacity 决定堆叠上限
export function vesselGeometry(width, height) {
  const bagWidth = Math.min(300, Math.max(170, width * 0.42))
  const bagHeight = Math.min(230, Math.max(140, height * 0.5))
  const floorY = height - Math.max(16, height * 0.07)
  const left = width / 2 - bagWidth / 2
  const topY = floorY - bagHeight
  const inset = bagWidth * 0.13
  const mouthWidth = bagWidth - inset * 2
  return {
    left,
    right: left + bagWidth,
    topY,
    floorY,
    mouthLeft: left + inset,
    mouthRight: left + bagWidth - inset,
    mouthWidth,
    mouthY: topY + bagHeight * 0.06,
    columns: 7,
    capacity: 8
  }
}

export function createWorld({ width, height, vessel = null, floorY = height - 6, reducedMotion = false }) {
  return {
    width,
    height,
    floorY,
    reducedMotion,
    vessel: vessel ? { ...vessel, pile: new Array(vessel.columns).fill(0) } : null
  }
}

// 生成一枚金币。funnel 模式从袋口上方撒入（初速略向袋口汇聚，仍有少量自然脱靶）；
// rain 模式全宽上方撒入。
export function createCoin(rng, world, mode = 'rain') {
  const size = 7 + rng() * 7
  const coin = {
    x: 0,
    y: 0,
    vx: (rng() - 0.5) * 90,
    vy: 40 + rng() * 120,
    rot: rng() * Math.PI * 2,
    vr: (rng() - 0.5) * 6,
    size,
    state: 'falling', // falling → captured | settled | escape → dead
    life: 1,
    alpha: 1,
    resting: false,
    column: -1
  }
  if (mode === 'funnel' && world.vessel) {
    const v = world.vessel
    const mouth = (v.mouthLeft + v.mouthRight) / 2
    coin.x = mouth + (rng() - 0.5) * v.mouthWidth * 1.7
    coin.y = v.mouthY - 24 - rng() * 90
    coin.vx = (mouth - coin.x) * 0.4 + (rng() - 0.5) * 50
    coin.vy = 60 + rng() * 140
  } else {
    coin.x = world.width * (0.06 + rng() * 0.88)
    coin.y = -coin.size - rng() * world.height * 0.35
  }
  return coin
}

// 单步积分。dt 单位秒（调用方负责 clamp，防后台标签页长帧炸穿物理）。
export function stepCoin(coin, dt, world) {
  if (coin.state === 'dead') return coin
  if (coin.state === 'escape') {
    coin.life -= dt
    coin.alpha = Math.max(0, coin.life)
    if (coin.life <= 0) { coin.state = 'dead'; return coin }
    if (coin.resting) return coin // 躺平的金币只淡出，不再受力
  }
  if (coin.state === 'captured' || coin.state === 'settled') return coin
  if (world.reducedMotion) {
    // 降低动效：不积分，直接落定（组件据此只画一帧静态画面）
    coin.state = 'settled'
    coin.resting = true
    coin.rot = Math.round(coin.rot / 0.12) * 0.12
    return coin
  }

  coin.vy += GRAVITY * dt
  const drag = Math.max(0, 1 - 0.6 * dt)
  coin.vx *= drag
  coin.x += coin.vx * dt
  coin.y += coin.vy * dt
  coin.rot += coin.vr * dt

  const v = world.vessel
  // 袋口捕获：越过袋口水平线且 x 落在袋口内 → 收入堆叠列
  if (v && coin.state === 'falling' && coin.y >= v.mouthY && coin.x >= v.mouthLeft && coin.x <= v.mouthRight) {
    const columnWidth = v.mouthWidth / v.columns
    const column = Math.min(v.columns - 1, Math.max(0, Math.floor((coin.x - v.mouthLeft) / columnWidth)))
    if (v.pile[column] < v.capacity) {
      coin.state = 'captured'
      coin.column = column
      coin.x = v.mouthLeft + (column + 0.5) * columnWidth + (coin.vx > 0 ? coin.size * 0.18 : -coin.size * 0.18)
      coin.y = v.floorY - v.pile[column] * coin.size * 1.05 - coin.size * 0.6
      coin.rot = (column % 2 === 0 ? 1 : -1) * 0.12
      coin.vr = 0
      v.pile[column] += 1
      return coin
    }
    // 袋满：溢出逃逸（向上弹出口），不无限堆叠
    coin.state = 'escape'
    coin.vy = -220
    coin.vx = (coin.x < (v.mouthLeft + v.mouthRight) / 2 ? -1 : 1) * (60 + Math.abs(coin.vx))
    return coin
  }

  // 落地弹跳：袋身覆盖区用袋底，其余用世界地板（funnel 模式世界地板在画布外，脱靶金币直接落死）
  const floorY = v && coin.x >= v.left && coin.x <= v.right ? v.floorY : world.floorY
  if (coin.y + coin.size >= floorY) {
    coin.y = floorY - coin.size
    if (Math.abs(coin.vy) > 90) {
      coin.vy *= -0.32
      coin.vx *= 0.72
      coin.vr *= 0.6
    } else {
      coin.vy = 0
      coin.vx = 0
      coin.vr = 0
      // 淡出中的金币落地后保持 escape（只淡出），不能被改写成 settled——
      // settled 会跳过 escape 的寿命递减，导致庆祝结束后金币永死不了、finished 事件不发
      if (coin.state !== 'escape') coin.state = 'settled'
      coin.resting = true
      coin.rot = Math.round(coin.rot / 0.12) * 0.12 // 对齐到少量倾角，保持几何感
    }
  }
  if (coin.y - coin.size > world.height + 60 || coin.x < -coin.size * 3 || coin.x > world.width + coin.size * 3) {
    coin.state = 'dead'
  }
  return coin
}

// 到时长：全部未死金币转为淡出（已躺平的只淡出不再受力）
export function fadeCoins(coins) {
  for (const coin of coins) {
    if (coin.state === 'dead') continue
    coin.state = 'escape'
    coin.life = Math.min(coin.life, 0.5)
  }
  return coins
}

export function liveCoinCount(coins) {
  return coins.reduce((count, coin) => (coin.state === 'dead' ? count : count + 1), 0)
}

// 里程碑档位推导：value 未知（null/非数字）时 progress=0 且不猜方向；超过最高档 next=null、progress=1
export function milestoneProgress(value, thresholds) {
  const list = Array.isArray(thresholds)
    ? thresholds.filter(t => typeof t === 'number' && Number.isFinite(t) && t > 0).sort((a, b) => a - b)
    : []
  if (!list.length) return { reached: null, next: null, progress: 0 }
  const safe = typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null
  if (safe === null) return { reached: null, next: list[0], progress: 0 }
  const reached = list.filter(t => t <= safe).pop() ?? null
  const next = list.find(t => t > safe) ?? null
  return { reached, next, progress: next === null ? 1 : Math.min(1, safe / next) }
}

// ── 持续动态演示（ambient）用微尘粒子：袋内/袋口缓慢上浮的星尘，纯装饰不承载数据 ──

// 确定性生成：同 seed 同分布，刷新不跳变
export function createMotes(rng, count, width, height) {
  const safeCount = Math.max(0, Math.min(64, Math.floor(count)))
  const motes = []
  for (let i = 0; i < safeCount; i += 1) {
    motes.push({
      x: rng() * width,
      y: rng() * height,
      size: 1 + rng() * 1.6,
      vy: 6 + rng() * 14, // px/s，缓慢上浮
      sway: 4 + rng() * 10, // 横向摆幅
      phase: rng() * Math.PI * 2
    })
  }
  return motes
}

// 步进：上浮 + 正弦横摆；浮出顶部后从底部重生（y 取模回卷，天然确定）
export function stepMotes(motes, dt, height, time = 0) {
  if (!(dt > 0)) return
  for (const mote of motes) {
    mote.y -= mote.vy * dt
    if (mote.y < -4) mote.y += height + 8
    mote.phase += dt * 1.6
  }
  void time
}
