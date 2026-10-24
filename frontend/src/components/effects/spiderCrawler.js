// 蜘蛛巡网引擎（哨兵 CRAWLER 面板的氛围动效）。
// 全部纯函数、确定性 RNG：同 seed 同画面，刷新不跳变；物理步进与绘制分离，可单测。
// 设计对齐 MASTER.md：单霓虹青、直线段蛛网（几何锐利，不做下垂弧线）、蜘蛛为拓扑巡检意象。

// mulberry32：32 位确定性 RNG（与 milestoneRain 同源）
export function createRng(seed) {
  let a = seed >>> 0
  return function next() {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const TAU = Math.PI * 2

function nodeKey(spoke, ring) { return `${spoke}:${ring}` }

// 几何蛛网：中心 + spokes 根辐条 + rings 层多边形环，全部直线段。
// 网随宿主面板自适应为椭圆（宽面板横向铺满，参考图的满幅构图）；蜘蛛行走逻辑与形状无关。
// 返回 segments（可绘制、可行走）与 adjacency（节点 → 相邻段），蜘蛛在节点处择路。
export function createWeb({ width, height, seed = 7, spokes = 10, rings = 4, margin = 18 }) {
  const rng = createRng(seed * 7919 + 13)
  const cx = width / 2
  const cy = height / 2
  const rx = Math.max(40, width / 2 - margin)
  const ry = Math.max(40, height / 2 - margin)
  const maxRadius = Math.min(rx, ry)
  const spokeCount = Math.max(6, spokes)
  const ringCount = Math.max(2, rings)

  // 节点坐标：辐条角 + 环半径都带小幅抖动，破除机械对称（星海/蛛网的 topology flow 语言）
  const nodeX = new Map()
  const nodeY = new Map()
  const spokeAngle = []
  for (let s = 0; s < spokeCount; s += 1) {
    const angle = (s / spokeCount) * TAU + (rng() - 0.5) * 0.12
    spokeAngle.push(angle)
  }
  const ringRadius = []
  for (let r = 0; r < ringCount; r += 1) {
    ringRadius.push(0.93 + rng() * 0.06) // 与 (r+1)/ringCount 相乘；抖动上限保证外环节点不溢出画布
  }
  for (let s = 0; s < spokeCount; s += 1) {
    for (let r = 0; r < ringCount; r += 1) {
      const rr = ringRadius[r] * (0.99 + rng() * 0.015)
      nodeX.set(nodeKey(s, r), cx + Math.cos(spokeAngle[s]) * rx * ((r + 1) / ringCount) * rr)
      nodeY.set(nodeKey(s, r), cy + Math.sin(spokeAngle[s]) * ry * ((r + 1) / ringCount) * rr)
    }
  }

  const segments = []
  const adjacency = new Map() // key → [{ seg, other }] other='center' | nodeKey
  const link = (keyA, keyB) => {
    const ax = keyA === 'center' ? cx : nodeX.get(keyA)
    const ay = keyA === 'center' ? cy : nodeY.get(keyA)
    const bx = keyB === 'center' ? cx : nodeX.get(keyB)
    const by = keyB === 'center' ? cy : nodeY.get(keyB)
    const length = Math.hypot(bx - ax, by - ay)
    if (length < 1) return
    const seg = { index: segments.length, ax, ay, bx, by, length }
    segments.push(seg)
    if (!adjacency.has(keyA)) adjacency.set(keyA, [])
    if (!adjacency.has(keyB)) adjacency.set(keyB, [])
    adjacency.get(keyA).push({ seg, other: keyB })
    adjacency.get(keyB).push({ seg, other: keyA })
  }

  // 辐条：中心 → 内环 → … → 外环
  for (let s = 0; s < spokeCount; s += 1) {
    let from = 'center'
    for (let r = 0; r < ringCount; r += 1) {
      const to = nodeKey(s, r)
      link(from, to)
      from = to
    }
  }
  // 环线：相邻辐条之间的多边形边
  for (let r = 0; r < ringCount; r += 1) {
    for (let s = 0; s < spokeCount; s += 1) {
      link(nodeKey(s, r), nodeKey((s + 1) % spokeCount, r))
    }
  }

  return { width, height, cx, cy, maxRadius, spokeCount, ringCount, nodeX, nodeY, segments, adjacency }
}

// 蜘蛛：随机落在一条外圈段上，8 条腿按左右各 4 只排布。
// scale 随网面尺寸自适应（大网蜘蛛等比放大，保持参考图里的醒目比例）。
// 腿 = { side, index, group, hipAngle, hipDist, footX, footY, stepping, fromX, fromY, toX, toY, progress }
export function createSpider(web, rng, scale = 1) {
  // 优先落在最外圈环线上（参考图的蜘蛛沿外网巡爬）
  const outerRingStart = web.segments.findIndex(seg => {
    return Math.hypot((seg.ax + seg.bx) / 2 - web.cx, (seg.ay + seg.by) / 2 - web.cy) > web.maxRadius * 0.8
  })
  const pool = outerRingStart >= 0 ? web.segments.slice(outerRingStart) : web.segments
  const seg = pool[Math.floor(rng() * pool.length)] || web.segments[0]
  const spider = {
    segIndex: seg.index,
    t: 0.2 + rng() * 0.6,
    dir: rng() > 0.5 ? 1 : -1,
    speed: 34 * Math.sqrt(scale), // 大网等比提速（sqrt 保持巡检节奏感），px/s
    scale,
    bodyX: 0, bodyY: 0, heading: 0, bodyAngle: 0,
    bob: 0, clock: 0, lastNodeKey: '',
    legs: []
  }
  const pairs = [0.42, 0.72, 1.02, 1.32] // 髋角（相对垂直躯干轴，弧度），前两对偏前、后两对偏后
  for (let side = -1; side <= 1; side += 2) {
    for (let i = 0; i < 4; i += 1) {
      spider.legs.push({
        side,
        index: (side + 1) / 2 * 4 + i,
        group: (i + (side > 0 ? 1 : 0)) % 2, // 四足两组交替：对角步态
        hipAngle: pairs[i] * side,
        hipDist: (7 + (i === 0 || i === 3 ? 1.5 : 0)) * scale,
        reach: (15 + (i === 1 || i === 2 ? 2 : 0)) * scale,
        footX: 0, footY: 0,
        stepping: false, fromX: 0, fromY: 0, toX: 0, toY: 0, progress: 0
      })
    }
  }
  placeBody(spider, web)
  // 初始足位直接落在理想位置（静态帧即成立姿态）
  for (const leg of spider.legs) {
    const ideal = idealFoot(spider, leg)
    leg.footX = ideal.x
    leg.footY = ideal.y
  }
  return spider
}

function placeBody(spider, web) {
  const seg = web.segments[spider.segIndex]
  spider.bodyX = seg.ax + (seg.bx - seg.ax) * spider.t
  spider.bodyY = seg.ay + (seg.by - seg.ay) * spider.t
  // 行进方向朝向段的前进侧
  spider.heading = spider.dir > 0
    ? Math.atan2(seg.by - seg.ay, seg.bx - seg.ax)
    : Math.atan2(seg.ay - seg.by, seg.ax - seg.bx)
}

function idealFoot(spider, leg) {
  // 理想足位：躯干侧面 hip 横向偏移 + 沿行进方向的前后跨距（髋角决定前腿/后腿）
  const base = spider.heading + Math.PI / 2 * leg.side
  const stride = Math.sin(leg.hipAngle) * leg.reach * 0.55
  const lateral = leg.hipDist
  return {
    x: spider.bodyX + Math.cos(base) * lateral + Math.cos(spider.heading) * stride,
    y: spider.bodyY + Math.sin(base) * lateral + Math.sin(spider.heading) * stride
  }
}

// 在节点处选下一段：优先直行（出段方向与前行方向点积最大），小幅随机避免路线机械重复；
// 排除当前段（原路返回），死路才折返
export function chooseNextSegment(web, spider, rng) {
  const seg = web.segments[spider.segIndex]
  const arrivedEnd = spider.dir > 0 ? 'b' : 'a'
  const key = nodeKeyForSegmentEnd(web, seg, arrivedEnd)
  const options = (web.adjacency.get(key) || []).filter(entry => entry.seg.index !== seg.index)
  if (options.length === 0) return { segIndex: seg.index, dir: -spider.dir } // 死路：原段折返
  const forwardX = arrivedEnd === 'b' ? seg.bx - seg.ax : seg.ax - seg.bx
  const forwardY = arrivedEnd === 'b' ? seg.by - seg.ay : seg.ay - seg.by
  const anchorX = arrivedEnd === 'b' ? seg.bx : seg.ax
  const anchorY = arrivedEnd === 'b' ? seg.by : seg.ay
  let best = null
  let bestScore = Infinity
  for (const option of options) {
    const exitX = exitPointX(web, option, key) - anchorX
    const exitY = exitPointY(web, option, key) - anchorY
    const denom = (option.seg.length * seg.length) || 1
    const dot = (forwardX * exitX + forwardY * exitY) / denom
    const score = -dot + rng() * 0.35
    if (score < bestScore) { bestScore = score; best = option }
  }
  const startAtB = endMatches(web, best, key) // 到达节点在 best 的 b 端 → 从 b 端走向 a 端
  return { segIndex: best.seg.index, dir: startAtB ? -1 : 1 }
}

function nodeKeyForSegmentEnd(web, seg, end) {
  // 由端点坐标反查节点 key（中心节点或环节点）
  const x = end === 'b' ? seg.bx : seg.ax
  const y = end === 'b' ? seg.by : seg.ay
  if (Math.hypot(x - web.cx, y - web.cy) < 0.75) return 'center'
  for (const [key, nx] of web.nodeX) {
    if (Math.abs(nx - x) < 0.75 && Math.abs(web.nodeY.get(key) - y) < 0.75) return key
  }
  return 'center'
}

function endMatches(web, entry, key) {
  // 该段的哪一端连接 key 节点
  const ax = entry.seg.ax, ay = entry.seg.ay
  const bx = entry.seg.bx, by = entry.seg.by
  const px = key === 'center' ? web.cx : web.nodeX.get(key)
  const py = key === 'center' ? web.cy : web.nodeY.get(key)
  const dA = Math.hypot(ax - px, ay - py)
  const dB = Math.hypot(bx - px, by - py)
  return dB < dA ? true : false // true = key 在 b 端
}

function exitPointX(web, entry, key) {
  const atB = endMatches(web, entry, key)
  return atB ? entry.seg.ax : entry.seg.bx
}
function exitPointY(web, entry, key) {
  const atB = endMatches(web, entry, key)
  return atB ? entry.seg.ay : entry.seg.by
}

// 物理步进：沿段行走 → 节点择路 → 躯干微俯仰 → 步态换脚
export function stepSpider(spider, web, dt, rng) {
  if (!(dt > 0)) return
  spider.clock += dt
  const seg = web.segments[spider.segIndex]
  spider.t += (spider.dir * spider.speed * dt) / Math.max(8, seg.length)
  if (spider.t > 1 || spider.t < 0) {
    const next = chooseNextSegment(web, spider, rng)
    spider.segIndex = next.segIndex
    spider.dir = next.dir
    spider.t = spider.dir > 0 ? 0 : 1
  }
  placeBody(spider, web)
  // 躯干垂直于网面的微颤（活物感，幅度随体型缩放）
  spider.bob = Math.sin(spider.clock * 9.5) * 1.2 * spider.scale

  // 步态：交替组允许迈步；超阈值立即起步（速度优先于步态整齐）
  const groupActive = Math.floor(spider.clock * 2.6) % 2
  for (const leg of spider.legs) {
    if (leg.stepping) {
      leg.progress += dt / 0.14 // 单步 140ms
      const p = Math.min(1, leg.progress)
      const ease = p * p * (3 - 2 * p)
      leg.footX = leg.fromX + (leg.toX - leg.fromX) * ease
      leg.footY = leg.fromY + (leg.toY - leg.fromY) * ease
      if (p >= 1) { leg.stepping = false; leg.progress = 0 }
      continue
    }
    const ideal = idealFoot(spider, leg)
    const dist = Math.hypot(leg.footX - ideal.x, leg.footY - ideal.y)
    if (dist > leg.reach * 0.85 && leg.group === groupActive) {
      leg.stepping = true
      leg.progress = 0
      leg.fromX = leg.footX; leg.fromY = leg.footY
      // 落足点带 2px 前探过冲：落定后立即又会被拉回，形成持续迈步节奏
      leg.toX = ideal.x + Math.cos(spider.heading) * 2
      leg.toY = ideal.y + Math.sin(spider.heading) * 2
    }
  }
}

// 静态姿态（reduced-motion）：不迈步，只复位到理想足位
export function restPose(spider, web) {
  placeBody(spider, web)
  spider.bob = 0
  for (const leg of spider.legs) {
    const ideal = idealFoot(spider, leg)
    leg.footX = ideal.x
    leg.footY = ideal.y
    leg.stepping = false
  }
}

export function legsStepping(spider) {
  return spider.legs.filter(leg => leg.stepping).length
}
