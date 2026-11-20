/**
 * 3D 场景级电影感氛围层（纯装饰，不参与业务判定）。
 *
 * 组成：
 * - 地面科技光晕盘：同心环 + 辐射刻度 + 中心柔光，缓慢自转；
 * - 雷达扫描扇面：绕地图中心低速旋转的扇形扫描光；
 * - 巡检视野扇面：随本体朝向转动的传感器视野锥；
 * - 环境浮尘：稀疏光点上浮，增加空气感与景深；
 * - 运动拖尾：本体移动时向后喷出并衰减的光尘（速度越快越密）；
 * - 路线流光：沿真实任务路线流动的光点，绕行点段自动变为琥珀色；
 * - 路线方向箭头：沿路线同向推进的三角箭头，强化前进方向；
 * - 任务目标：下一个未完成路点上方的全息光柱 + 双环 + 文字标签；
 * - 设备全息扫描：本体腰部双向旋转弧环、自下而上升起的扫描光面、环绕轨道光点；
 * - 全息扫描幕：整场横移的竖直光幕，周期性扫过全部设备与路线；
 * - 视野激光扫掠：巡检视野扇面内左右摆动的窄扫描光束；
 * - 模式基座光环：本体脚下的光环颜色随运行模式变化；
 * - 目标锁定框：面向镜头的四角括号 + 旋转菱形，强化「选中并锁定」的观感；
 * - 告警警戒圈：告警时本体周围旋转的虚线警戒环；
 * - 全息数据碎片：远景缓慢翻转漂浮的六边形线框，制造数字孪生空气感；
 * - 全息防护罩：本体外的半球线框与纬度扫描环，随模式/告警变色；
 * - 障碍测距：按真实 obstacleDistance 在本体前方生成距离弧与外发脉冲；
 * - 电量全息环：按真实电量点亮地面分段弧，低电量自动转为红色脉冲；
 * - 遥测上行：心跳正常时，从本体向上升起的数据粒子流；
 * - 终点任务进度：终点处分段进度环，全部完成后显示全息徽章与完成脉冲；
 * - 运动光刃：真实速度超过阈值时，在本体后方生成流线型速度光迹；
 * - 空间数据雨：远景稀疏垂直光线缓慢下落，增加持续环境动态；
 * - 悬浮状态标签：本体上方 Sprite 显示真实模式与电量，心跳中断自动转红；
 * - 螺旋能量链：环绕本体盘旋上升的光链，随自主/遥控模式换色；
 * - 头顶警示标：低电量或告警时出现的脉冲警示三角；
 * - 路点完成爆发：路点由未完成变为完成时，原地扩散能量环；
 * - 声呐波纹：本体脚下周期性扩散的扫描圈，强化「活场景」感；
 * - 告警浮标：设备上方悬浮环 + 光柱 + 下指箭头，由真实告警等级驱动；
 * - 交互脉冲：点击设备时从地面扩散的能量环。
 *
 * 所有尺寸/透明度都按「地图 15m 量级」设计；调用方在 SVG 软件渲染后端不应构建本层。
 */

import {
  AdditiveBlending, BufferAttribute, BufferGeometry, CanvasTexture, CircleGeometry, Color,
  ConeGeometry, CylinderGeometry, DoubleSide, Group, Line, LineBasicMaterial, LineSegments, Mesh,
  MeshBasicMaterial, NormalBlending, PlaneGeometry, Points, PointsMaterial, RingGeometry,
  SphereGeometry, Sprite, SpriteMaterial, SRGBColorSpace, TorusGeometry
} from 'three'

const WARN_COLOR = 0xe3a008
const DANGER_COLOR = 0xe5484d
/** 路线光点数量：足够形成连续光流，又不至于每帧产生明显开销 */
const FLOW_COUNT = 64
/** 浮尘数量：低多边形光点，主要贡献景深 */
const DUST_COUNT = 120
/** 拖尾光尘池大小：循环复用，避免运行时创建对象 */
const EMBER_COUNT = 56
/** 路线光流速度（米/秒） */
const FLOW_SPEED = 1.7
/** 路线方向箭头数量 */
const CHEVRON_COUNT = 5
/** 遥测上行粒子数量 */
const UPLINK_COUNT = 18
/** 电量环分段数量 */
const BATTERY_SEGMENTS = 36
/** 终点任务进度环分段数量 */
const MISSION_SEGMENTS = 24
/** 高速运动光刃数量 */
const SPEED_BLADE_COUNT = 8
/** 空间数据雨线条数量 */
const DATA_RAIN_COUNT = 18
/** 螺旋能量链节点数 */
const HELIX_POINTS = 56
/** 运行模式中文标签 */
const MODE_LABELS = {
  AUTONOMOUS: '自主巡检',
  HUMAN_CONTROL: '人工遥控',
  IDLE: '待机',
  E_STOP: '急停',
  FAULT: '故障',
  OFFLINE: '离线'
}

/** 柔和光点贴图（白色径向渐变，材质 color 负责染色）。 */
function makeSpriteTexture() {
  const size = 64
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  gradient.addColorStop(0, 'rgba(255,255,255,1)')
  gradient.addColorStop(0.4, 'rgba(255,255,255,0.55)')
  gradient.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, size, size)
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

/** 地面科技盘贴图：同心环 + 辐射线 + 外圈刻度，白色描边由材质染色。 */
function makeGroundTexture() {
  const size = 512
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  const c = size / 2
  const maxR = size / 2 - 4

  /* 中心柔光：让地面整体有一层淡淡能量底 */
  const glow = ctx.createRadialGradient(c, c, 0, c, c, maxR)
  glow.addColorStop(0, 'rgba(255,255,255,0.30)')
  glow.addColorStop(0.5, 'rgba(255,255,255,0.08)')
  glow.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = glow
  ctx.fillRect(0, 0, size, size)

  /* 同心环 */
  ctx.lineWidth = 1
  for (let radius = 36; radius < maxR; radius += 34) {
    ctx.strokeStyle = radius % 102 === 0 ? 'rgba(255,255,255,0.55)' : 'rgba(255,255,255,0.22)'
    ctx.beginPath()
    ctx.arc(c, c, radius, 0, Math.PI * 2)
    ctx.stroke()
  }

  /* 辐射线：24 等分，长短交错 */
  for (let i = 0; i < 24; i += 1) {
    const angle = (i / 24) * Math.PI * 2
    const inner = i % 2 === 0 ? 48 : 120
    ctx.strokeStyle = i % 2 === 0 ? 'rgba(255,255,255,0.24)' : 'rgba(255,255,255,0.12)'
    ctx.beginPath()
    ctx.moveTo(c + Math.cos(angle) * inner, c + Math.sin(angle) * inner)
    ctx.lineTo(c + Math.cos(angle) * maxR, c + Math.sin(angle) * maxR)
    ctx.stroke()
  }

  /* 外圈刻度：小段弧线强化「雷达盘」观感 */
  ctx.lineWidth = 3
  ctx.strokeStyle = 'rgba(255,255,255,0.45)'
  for (let i = 0; i < 12; i += 1) {
    const start = (i / 12) * Math.PI * 2
    ctx.beginPath()
    ctx.arc(c, c, maxR - 6, start, start + 0.11)
    ctx.stroke()
  }

  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

/** 视野扇面贴图：径向渐隐（中心亮、边缘完全透明），避免地面出现生硬的扇形色块。 */
function makeVisionTexture() {
  const size = 256
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  const c = size / 2
  const gradient = ctx.createRadialGradient(c, c, 0, c, c, c)
  gradient.addColorStop(0, 'rgba(255,255,255,0.9)')
  gradient.addColorStop(0.55, 'rgba(255,255,255,0.38)')
  gradient.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, size, size)
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

/** 目标光柱贴图：柱底亮、柱顶完全透明（Cylinder 的 UV 顶部对应画布顶部）。 */
function makeBeamTexture() {
  const width = 8
  const height = 128
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  const gradient = ctx.createLinearGradient(0, 0, 0, height)
  gradient.addColorStop(0, 'rgba(255,255,255,0)')
  gradient.addColorStop(0.55, 'rgba(255,255,255,0.35)')
  gradient.addColorStop(1, 'rgba(255,255,255,0.9)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, width, height)
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

/** 目标点文字标签：圆角暗底 + 主题色描边，Sprite 始终面向相机。 */
function makeLabelTexture(text, color) {
  const width = 256
  const height = 72
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  ctx.beginPath()
  if (ctx.roundRect) ctx.roundRect(10, 10, width - 20, height - 20, 12)
  else ctx.rect(10, 10, width - 20, height - 20)
  ctx.fillStyle = 'rgba(8, 14, 26, 0.78)'
  ctx.fill()
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  ctx.stroke()
  ctx.font = '600 30px "Microsoft YaHei", "PingFang SC", sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = color
  ctx.fillText(text, width / 2, height / 2 + 1)
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

/** 扫描幕贴图：底部亮、顶部淡出，左右边缘用 destination-in 羽化，避免出现硬边光板。 */
function makeCurtainTexture() {
  const width = 128
  const height = 64
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  const vertical = ctx.createLinearGradient(0, 0, 0, height)
  vertical.addColorStop(0, 'rgba(255,255,255,0)')
  vertical.addColorStop(0.6, 'rgba(255,255,255,0.5)')
  vertical.addColorStop(1, 'rgba(255,255,255,0.95)')
  ctx.fillStyle = vertical
  ctx.fillRect(0, 0, width, height)
  const horizontal = ctx.createLinearGradient(0, 0, width, 0)
  horizontal.addColorStop(0, 'rgba(0,0,0,0)')
  horizontal.addColorStop(0.5, 'rgba(0,0,0,1)')
  horizontal.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.globalCompositeOperation = 'destination-in'
  ctx.fillStyle = horizontal
  ctx.fillRect(0, 0, width, height)
  ctx.globalCompositeOperation = 'source-over'
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

/** 目标锁定括号贴图：四个 L 形角标 + 柔光，白色描边由 Sprite 材质染色。 */
function makeReticleTexture() {
  const size = 256
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  const inset = 30
  const arm = 56
  ctx.lineWidth = 8
  ctx.lineCap = 'round'
  ctx.strokeStyle = 'rgba(255,255,255,0.95)'
  ctx.shadowColor = 'rgba(190,225,255,0.9)'
  ctx.shadowBlur = 14
  const corners = [
    [inset, inset, 1, 1],
    [size - inset, inset, -1, 1],
    [inset, size - inset, 1, -1],
    [size - inset, size - inset, -1, -1]
  ]
  corners.forEach(([x, y, dx, dy]) => {
    ctx.beginPath()
    ctx.moveTo(x + dx * arm, y)
    ctx.lineTo(x, y)
    ctx.lineTo(x, y + dy * arm)
    ctx.stroke()
  })
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

/** 目标锁定菱形贴图：旋转的菱形轮廓 + 中心点。 */
function makeDiamondTexture() {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  const c = size / 2
  const r = 44
  ctx.lineWidth = 6
  ctx.lineJoin = 'round'
  ctx.strokeStyle = 'rgba(255,255,255,0.95)'
  ctx.shadowColor = 'rgba(150,200,255,0.9)'
  ctx.shadowBlur = 12
  ctx.beginPath()
  ctx.moveTo(c, c - r)
  ctx.lineTo(c + r, c)
  ctx.lineTo(c, c + r)
  ctx.lineTo(c - r, c)
  ctx.closePath()
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(c, c, 5, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255,255,255,0.95)'
  ctx.fill()
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

/** 任务完成徽章：双圈全息边框 + 对勾，白色描边由 Sprite 材质染色。 */
function makeMissionBadgeTexture() {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  const c = size / 2
  ctx.strokeStyle = 'rgba(255,255,255,0.9)'
  ctx.shadowColor = 'rgba(160,255,210,0.9)'
  ctx.shadowBlur = 12
  ctx.lineWidth = 4
  ctx.beginPath()
  ctx.arc(c, c, 48, 0, Math.PI * 2)
  ctx.stroke()
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.arc(c, c, 39, 0, Math.PI * 2)
  ctx.stroke()
  ctx.lineWidth = 8
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.beginPath()
  ctx.moveTo(38, 65)
  ctx.lineTo(56, 83)
  ctx.lineTo(92, 43)
  ctx.stroke()
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

/** 头顶警示标：圆角三角 + 感叹号，白色描边由 Sprite 材质染色。 */
function makeWarningTexture() {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  const c = size / 2
  ctx.strokeStyle = 'rgba(255,255,255,0.95)'
  ctx.shadowColor = 'rgba(255,200,140,0.9)'
  ctx.shadowBlur = 12
  ctx.lineWidth = 6
  ctx.lineJoin = 'round'
  ctx.beginPath()
  ctx.moveTo(c, 20)
  ctx.lineTo(112, 104)
  ctx.lineTo(16, 104)
  ctx.closePath()
  ctx.stroke()
  ctx.lineWidth = 8
  ctx.lineCap = 'round'
  ctx.beginPath()
  ctx.moveTo(c, 52)
  ctx.lineTo(c, 80)
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(c, 93, 4.5, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255,255,255,0.95)'
  ctx.fill()
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

/**
 * 构建电影感氛围层。
 * @param {{accentHex?: number, theme?: string, lowDetail?: boolean}} options
 */
export function buildCinematicLayer({ accentHex = 0x5b8cff, theme = 'light', lowDetail = false } = {}) {
  const group = new Group()
  group.name = 'cinematic-layer'

  const disposables = []
  const spriteTexture = makeSpriteTexture()
  const groundTexture = makeGroundTexture()
  disposables.push(spriteTexture, groundTexture)

  const accent = new Color(accentHex)
  const warn = new Color(WARN_COLOR)

  /* ---------- 地面科技光晕盘 ---------- */
  const groundSpin = new Group()
  groundSpin.position.set(2.5, 0, 0)
  group.add(groundSpin)

  const groundMat = new MeshBasicMaterial({
    map: groundTexture, color: accentHex, transparent: true, opacity: 0.5,
    depthWrite: false, side: DoubleSide
  })
  const ground = new Mesh(new PlaneGeometry(20, 20), groundMat)
  ground.rotation.x = -Math.PI / 2
  ground.position.y = 0.004
  groundSpin.add(ground)
  disposables.push(groundMat)

  /* ---------- 雷达扫描扇面 ---------- */
  const radarSpin = new Group()
  radarSpin.position.set(2.5, 0, 0)
  group.add(radarSpin)

  const radarMat = new MeshBasicMaterial({
    color: accentHex, transparent: true, opacity: 0.12, depthWrite: false,
    side: DoubleSide, blending: AdditiveBlending
  })
  const radar = new Mesh(new CircleGeometry(8.2, 48, 0, Math.PI / 7), radarMat)
  radar.rotation.x = -Math.PI / 2
  radar.position.y = 0.012
  radarSpin.add(radar)
  disposables.push(radarMat)

  /* ---------- 环境浮尘 ---------- */
  const dustPositions = new Float32Array(DUST_COUNT * 3)
  for (let i = 0; i < DUST_COUNT; i += 1) {
    dustPositions[i * 3] = -5 + Math.random() * 15
    dustPositions[i * 3 + 1] = 0.15 + Math.random() * 3.2
    dustPositions[i * 3 + 2] = -4 + Math.random() * 12
  }
  const dustGeo = new BufferGeometry()
  dustGeo.setAttribute('position', new BufferAttribute(dustPositions, 3))
  const dustMat = new PointsMaterial({
    size: 0.07, map: spriteTexture, color: accentHex, transparent: true, opacity: 0.42,
    depthWrite: false, sizeAttenuation: true, blending: AdditiveBlending
  })
  const dust = new Points(dustGeo, dustMat)
  group.add(dust)
  disposables.push(dustGeo, dustMat)

  /* ---------- 巡检视野扇面（随本体朝向转动） ---------- */
  const VISION_FOV = Math.PI / 3
  const visionSpin = new Group()
  visionSpin.visible = false
  group.add(visionSpin)

  const visionMat = new MeshBasicMaterial({
    map: makeVisionTexture(), color: accentHex, transparent: true, opacity: 0.2, depthWrite: false,
    side: DoubleSide, blending: AdditiveBlending
  })
  const vision = new Mesh(new CircleGeometry(2.4, 36, -VISION_FOV / 2, VISION_FOV), visionMat)
  vision.rotation.x = -Math.PI / 2
  visionSpin.add(vision)
  disposables.push(visionMat)
  disposables.push(visionMat.map)

  /* 视野内的激光扫掠线：在扇面内左右摆动，模拟主动探测 */
  const visionScanMat = new MeshBasicMaterial({
    color: 0xdcefff, transparent: true, opacity: 0.4, depthWrite: false,
    side: DoubleSide, blending: AdditiveBlending
  })
  const visionScan = new Mesh(new CircleGeometry(2.35, 14, -0.045, 0.09), visionScanMat)
  visionScan.rotation.x = -Math.PI / 2
  visionScan.position.y = 0.008
  visionSpin.add(visionScan)
  disposables.push(visionScanMat, visionScan.geometry)

  /* ---------- 运动拖尾光尘（速度驱动，循环池） ---------- */
  const emberPositions = new Float32Array(EMBER_COUNT * 3)
  const emberColors = new Float32Array(EMBER_COUNT * 3)
  const emberLife = new Float32Array(EMBER_COUNT)
  emberPositions.fill(-100) /* 初始放到场景外，避免地面出现未点亮的原点 */
  const emberGeo = new BufferGeometry()
  emberGeo.setAttribute('position', new BufferAttribute(emberPositions, 3))
  emberGeo.setAttribute('color', new BufferAttribute(emberColors, 3))
  const emberMat = new PointsMaterial({
    size: lowDetail ? 0.07 : 0.095, map: spriteTexture, transparent: true, opacity: 0.95,
    depthWrite: false, sizeAttenuation: true, blending: AdditiveBlending, vertexColors: true
  })
  const embers = new Points(emberGeo, emberMat)
  embers.frustumCulled = false
  group.add(embers)
  disposables.push(emberGeo, emberMat)
  let emberCursor = 0
  let emberClock = 0
  const emberTint = new Color()

  /* ---------- 交互脉冲（点击设备时扩散的能量环） ---------- */
  const bursts = []
  function burstAt(x, z, hex = 0x9fc2ff, size = 1) {
    const mat = new MeshBasicMaterial({
      color: hex, transparent: true, opacity: 0.9, side: DoubleSide,
      depthWrite: false, blending: AdditiveBlending
    })
    const ring = new Mesh(new RingGeometry(0.82, 1, 48), mat)
    ring.rotation.x = -Math.PI / 2
    ring.position.set(x, 0.06, z)
    group.add(ring)
    bursts.push({ ring, mat, age: 0, size })
  }

  /* ---------- 路线光流 ---------- */
  let routePoints = []
  let cumulative = []
  let totalLength = 0

  const flowPositions = new Float32Array(FLOW_COUNT * 3)
  const flowColors = new Float32Array(FLOW_COUNT * 3)
  const flowGeo = new BufferGeometry()
  flowGeo.setAttribute('position', new BufferAttribute(flowPositions, 3))
  flowGeo.setAttribute('color', new BufferAttribute(flowColors, 3))
  const flowMat = new PointsMaterial({
    size: lowDetail ? 0.09 : 0.11, map: spriteTexture, transparent: true, opacity: 0.95,
    depthWrite: false, sizeAttenuation: true, blending: AdditiveBlending, vertexColors: true
  })
  const flow = new Points(flowGeo, flowMat)
  flow.visible = false
  /* 位置逐帧变化，关闭视锥裁剪避免每帧重算包围球 */
  flow.frustumCulled = false
  group.add(flow)
  disposables.push(flowGeo, flowMat)

  /* ---------- 路线方向箭头（沿路线流动，强化前进方向） ---------- */
  const chevronGeo = new ConeGeometry(0.085, 0.22, 3)
  chevronGeo.rotateZ(-Math.PI / 2) /* 锥尖朝 +X，配合 rotation.y 指向路段方向 */
  const directionChevrons = []
  for (let i = 0; i < CHEVRON_COUNT; i += 1) {
    const mat = new MeshBasicMaterial({
      color: accentHex, transparent: true, opacity: 0.75, depthWrite: false, blending: AdditiveBlending
    })
    const mesh = new Mesh(chevronGeo, mat)
    mesh.position.y = 0.07
    mesh.visible = false
    group.add(mesh)
    directionChevrons.push({ mesh, mat })
    disposables.push(mat)
  }
  disposables.push(chevronGeo)

  /** 采样路线上的距离 d 对应的世界坐标与所属路段颜色。 */
  function sampleRoute(distance) {
    let lo = 0
    let hi = cumulative.length - 1
    while (lo < hi - 1) {
      const mid = (lo + hi) >> 1
      if (cumulative[mid] <= distance) lo = mid
      else hi = mid
    }
    const a = routePoints[lo]
    const b = routePoints[Math.min(lo + 1, routePoints.length - 1)]
    const segStart = cumulative[lo] ?? 0
    const segEnd = cumulative[lo + 1] ?? segStart
    const segLength = segEnd - segStart
    const t = segLength > 1e-6 ? Math.min(1, Math.max(0, (distance - segStart) / segLength)) : 0
    return {
      x: a.x + (b.x - a.x) * t,
      y: a.y + (b.y - a.y) * t,
      z: a.z + (b.z - a.z) * t,
      detour: b.detour,
      dirX: b.x - a.x,
      dirZ: b.z - a.z
    }
  }

  /**
   * 写入真实路线（世界坐标：x, y=0.045, z=-mapY）。
   * @param {Array<{x:number, y:number, detour?:boolean}>} points
   */
  function setRoute(points) {
    const previous = routePoints
    routePoints = Array.isArray(points)
      ? points.map((p) => ({
        x: Number(p.x) || 0,
        y: 0.045,
        z: -(Number(p.y) || 0),
        detour: Boolean(p.detour),
        done: Boolean(p.done),
        label: String(p.label || '')
      }))
      : []
    cumulative = [0]
    totalLength = 0
    for (let i = 0; i < routePoints.length - 1; i += 1) {
      const a = routePoints[i]
      const b = routePoints[i + 1]
      totalLength += Math.hypot(b.x - a.x, b.z - a.z)
      cumulative.push(totalLength)
    }
    const valid = routePoints.length >= 2 && totalLength > 1e-3
    flow.visible = valid
    flowGeo.setDrawRange(0, valid ? FLOW_COUNT : 0)
    if (!valid) {
      directionChevrons.forEach((arrow) => { arrow.mesh.visible = false })
    }
    if (valid) updateFlow(0)

    /* 路点完成瞬间：同一序号由未完成变为完成时，在原地扩散一圈能量环 */
    routePoints.forEach((p, i) => {
      if (p.done && previous[i] && previous[i].done === false) {
        burstAt(p.x, p.z, 0x6ef0c0, 1.6)
      }
    })

    /* 目标光柱：指向下一个未完成路点；全部完成时隐藏 */
    const targetIndex = routePoints.findIndex((p) => !p.done)
    const next = targetIndex >= 0 ? routePoints[targetIndex] : null
    targetGroup.visible = Boolean(next)
    if (next) {
      targetGroup.position.set(next.x, 0, next.z)
      const hex = next.detour ? WARN_COLOR : 0x9fc2ff
      targetBeamMat.color.setHex(hex)
      targetRingMat.color.setHex(hex)
      setTargetLabel(next.label || `P${targetIndex + 1}`, next.detour ? '#ffd27a' : '#cfe2ff')
    } else {
      setTargetLabel('', '')
    }

    /* 终点进度：在路线末端显示完成比例；全部完成时点亮徽章与持续脉冲 */
    missionGroup.visible = valid
    missionBadge.visible = false
    missionPulse.visible = false
    if (valid) {
      const end = routePoints[routePoints.length - 1]
      const doneCount = routePoints.reduce((count, point) => count + (point.done ? 1 : 0), 0)
      const complete = doneCount === routePoints.length
      const activeCount = Math.round(doneCount / routePoints.length * MISSION_SEGMENTS)
      missionGroup.position.set(end.x, 0, end.z)
      missionActiveMat.color.setHex(complete ? 0x63d6a4 : accentHex)
      for (let i = 0; i < MISSION_SEGMENTS; i += 1) {
        missionSegments[i].material = i < activeCount ? missionActiveMat : missionInactiveMat
      }
      missionBadge.visible = complete
      missionPulse.visible = complete
    }
  }

  /** 按累计距离推进光点；颜色取该路段是否是绕行段。 */
  function updateFlow(elapsed) {
    if (!flow.visible || totalLength <= 0) return
    const spacing = totalLength / FLOW_COUNT
    for (let i = 0; i < FLOW_COUNT; i += 1) {
      const d = (elapsed * FLOW_SPEED + i * spacing) % totalLength
      const p = sampleRoute(d)
      flowPositions[i * 3] = p.x
      flowPositions[i * 3 + 1] = p.y
      flowPositions[i * 3 + 2] = p.z
      const color = p.detour ? warn : accent
      flowColors[i * 3] = color.r
      flowColors[i * 3 + 1] = color.g
      flowColors[i * 3 + 2] = color.b
    }
    flowGeo.attributes.position.needsUpdate = true
    flowGeo.attributes.color.needsUpdate = true

    /* 方向箭头：比光点更慢、更亮，沿路段朝向放置 */
    const arrowSpacing = totalLength / CHEVRON_COUNT
    for (let i = 0; i < CHEVRON_COUNT; i += 1) {
      const arrow = directionChevrons[i]
      const d = (elapsed * FLOW_SPEED * 0.7 + i * arrowSpacing) % totalLength
      const p = sampleRoute(d)
      arrow.mesh.position.set(p.x, 0.07, p.z)
      arrow.mesh.rotation.y = -Math.atan2(p.dirZ, p.dirX)
      arrow.mesh.visible = true
      arrow.mat.color.copy(p.detour ? warn : accent)
      arrow.mat.opacity = 0.55 + 0.3 * (0.5 + 0.5 * Math.sin(elapsed * 3 + i))
    }
  }

  /* ---------- 告警浮标 ---------- */
  const alarmGroup = new Group()
  alarmGroup.visible = false
  group.add(alarmGroup)

  const alarmMat = new MeshBasicMaterial({
    color: WARN_COLOR, transparent: true, opacity: 0.85, depthWrite: false, blending: AdditiveBlending
  })
  const alarmGlowMat = new MeshBasicMaterial({
    color: WARN_COLOR, transparent: true, opacity: 0.28, depthWrite: false, depthTest: false, blending: AdditiveBlending
  })
  const alarmRing = new Mesh(new TorusGeometry(0.34, 0.018, 8, 40), alarmMat)
  alarmRing.rotation.x = Math.PI / 2
  alarmRing.position.y = 1.28
  alarmGroup.add(alarmRing)

  const alarmHalo = new Mesh(new SphereGeometry(0.075, 14, 12), alarmGlowMat)
  alarmHalo.position.y = 1.28
  alarmHalo.renderOrder = 3
  alarmGroup.add(alarmHalo)

  const beamGeo = new CylinderGeometry(0.006, 0.02, 1.1, 8, 1, true)
  const beamMat = new MeshBasicMaterial({
    color: WARN_COLOR, transparent: true, opacity: 0.42, depthWrite: false, side: DoubleSide, blending: AdditiveBlending
  })
  const alarmBeam = new Mesh(beamGeo, beamMat)
  alarmBeam.position.y = 0.62
  alarmGroup.add(alarmBeam)

  const chevron = new Mesh(new ConeGeometry(0.075, 0.14, 4), alarmMat)
  chevron.rotation.x = Math.PI
  chevron.position.y = 1.56
  alarmGroup.add(chevron)

  disposables.push(alarmMat, alarmGlowMat, beamGeo, beamMat, alarmRing.geometry, alarmHalo.geometry, chevron.geometry)

  /* ---------- 下一个任务目标：全息光柱 + 双环 + 文字标签 ---------- */
  const targetGroup = new Group()
  targetGroup.visible = false
  group.add(targetGroup)

  const beamTexture = makeBeamTexture()
  const targetBeamMat = new MeshBasicMaterial({
    map: beamTexture, color: 0x9fc2ff, transparent: true, opacity: 0.55,
    depthWrite: false, side: DoubleSide, blending: AdditiveBlending
  })
  const targetBeam = new Mesh(new CylinderGeometry(0.07, 0.22, 1.7, 14, 1, true), targetBeamMat)
  targetBeam.position.y = 0.85
  targetGroup.add(targetBeam)

  const targetRingMat = new MeshBasicMaterial({
    color: 0x9fc2ff, transparent: true, opacity: 0.75, depthWrite: false, blending: AdditiveBlending
  })
  const targetRingGeo = new TorusGeometry(0.34, 0.016, 8, 40)
  const targetRingBase = new Mesh(targetRingGeo, targetRingMat)
  targetRingBase.rotation.x = Math.PI / 2
  targetRingBase.position.y = 0.22
  targetGroup.add(targetRingBase)
  const targetRingTop = new Mesh(targetRingGeo, targetRingMat)
  targetRingTop.rotation.x = Math.PI / 2
  targetRingTop.position.y = 1.55
  targetGroup.add(targetRingTop)
  disposables.push(beamTexture, targetBeamMat, targetRingMat, targetBeam.geometry, targetRingGeo)

  let targetLabel = null
  let targetLabelKey = ''
  /** 目标标签按文本+颜色缓存，避免每 5 秒任务刷新都重建贴图。 */
  function setTargetLabel(text, color) {
    const key = text ? `${text}|${color}` : ''
    if (key === targetLabelKey) return
    targetLabelKey = key
    if (targetLabel) {
      targetGroup.remove(targetLabel)
      targetLabel.material.map?.dispose()
      targetLabel.material.dispose()
      targetLabel = null
    }
    if (!text) return
    const material = new SpriteMaterial({
      map: makeLabelTexture(text, color), transparent: true, depthWrite: false, opacity: 0.96
    })
    targetLabel = new Sprite(material)
    targetLabel.scale.set(1.15, 0.3, 1)
    targetLabel.position.y = 2
    targetGroup.add(targetLabel)
  }

  /* ---------- 设备全息扫描：双向旋转弧环 + 上升扫描光面 + 环绕轨道光点 ---------- */
  const holoGroup = new Group()
  holoGroup.visible = false
  group.add(holoGroup)

  const HOLO_COLOR = 0x9fc2ff
  const holoRingMatA = new MeshBasicMaterial({
    color: HOLO_COLOR, transparent: true, opacity: 0.34, depthWrite: false, blending: AdditiveBlending
  })
  const holoRingGeoA = new TorusGeometry(0.56, 0.006, 6, 64, Math.PI * 1.55)
  const holoRingA = new Mesh(holoRingGeoA, holoRingMatA)
  holoRingA.rotation.x = Math.PI / 2
  holoRingA.position.y = 0.52
  holoGroup.add(holoRingA)

  const holoRingMatB = new MeshBasicMaterial({
    color: HOLO_COLOR, transparent: true, opacity: 0.26, depthWrite: false, blending: AdditiveBlending
  })
  const holoRingGeoB = new TorusGeometry(0.44, 0.005, 6, 56, Math.PI * 1.4)
  const holoRingB = new Mesh(holoRingGeoB, holoRingMatB)
  holoRingB.rotation.x = Math.PI / 2
  holoRingB.position.y = 1.02
  holoGroup.add(holoRingB)

  /* 扫描光面：水平薄环自下而上扫过本体，循环周期 2.6s */
  const scanMat = new MeshBasicMaterial({
    color: 0xbfe0ff, transparent: true, opacity: 0, side: DoubleSide,
    depthWrite: false, blending: AdditiveBlending
  })
  const scanGeo = new RingGeometry(0.2, 0.62, 48)
  const scanSweep = new Mesh(scanGeo, scanMat)
  scanSweep.rotation.x = -Math.PI / 2
  holoGroup.add(scanSweep)

  /* 环绕轨道光点：4 颗微光绕本体做椭圆轨道运动 */
  const orbitGroup = new Group()
  holoGroup.add(orbitGroup)
  const orbitMat = new MeshBasicMaterial({
    color: HOLO_COLOR, transparent: true, opacity: 0.85, depthWrite: false, blending: AdditiveBlending
  })
  const orbitGeo = new SphereGeometry(0.022, 8, 8)
  const orbitSparks = []
  for (let i = 0; i < 4; i += 1) {
    const spark = new Mesh(orbitGeo, orbitMat)
    orbitSparks.push(spark)
    orbitGroup.add(spark)
  }
  disposables.push(
    holoRingMatA, holoRingGeoA, holoRingMatB, holoRingGeoB, scanMat, scanGeo, orbitMat, orbitGeo
  )

  /* ---------- 全场全息扫描幕：每 7 秒沿 Z 轴横移扫过全部设备与路线 ---------- */
  const curtainTexture = makeCurtainTexture()
  const curtainMat = new MeshBasicMaterial({
    map: curtainTexture, color: 0x9fc2ff, transparent: true, opacity: 0,
    depthWrite: false, side: DoubleSide, blending: AdditiveBlending
  })
  const curtain = new Mesh(new PlaneGeometry(18, 3.4), curtainMat)
  curtain.visible = false
  group.add(curtain)
  disposables.push(curtainTexture, curtainMat, curtain.geometry)

  /* ---------- 模式基座光环：颜色随运行模式变化 ---------- */
  const baseHaloMat = new MeshBasicMaterial({
    color: accentHex, transparent: true, opacity: 0.2, depthWrite: false,
    side: DoubleSide, blending: AdditiveBlending
  })
  const baseHalo = new Mesh(new RingGeometry(0.34, 0.62, 40), baseHaloMat)
  baseHalo.rotation.x = -Math.PI / 2
  baseHalo.visible = false
  group.add(baseHalo)
  disposables.push(baseHaloMat, baseHalo.geometry)

  /* ---------- 目标锁定框：四角括号 + 旋转菱形（Sprite 天然面向镜头） ---------- */
  const reticleGroup = new Group()
  reticleGroup.visible = false
  group.add(reticleGroup)

  const reticleBracketMat = new SpriteMaterial({
    map: makeReticleTexture(), color: 0xdcecff, transparent: true,
    depthWrite: false, depthTest: false, opacity: 0.6
  })
  const reticleBrackets = new Sprite(reticleBracketMat)
  reticleBrackets.scale.set(1.45, 1.45, 1)
  reticleBrackets.renderOrder = 4
  reticleGroup.add(reticleBrackets)

  const diamondMat = new SpriteMaterial({
    map: makeDiamondTexture(), color: 0x9fc2ff, transparent: true,
    depthWrite: false, depthTest: false, opacity: 0.7
  })
  const diamond = new Sprite(diamondMat)
  diamond.scale.set(0.46, 0.46, 1)
  diamond.renderOrder = 5
  reticleGroup.add(diamond)
  disposables.push(reticleBracketMat, reticleBracketMat.map, diamondMat, diamondMat.map)

  /* ---------- 告警警戒圈：告警时本体周围旋转的虚线环 ---------- */
  const alarmZone = new Group()
  alarmZone.visible = false
  group.add(alarmZone)

  const alarmZoneMat = new MeshBasicMaterial({
    color: WARN_COLOR, transparent: true, opacity: 0.4, side: DoubleSide,
    depthWrite: false, blending: AdditiveBlending
  })
  const zoneSegmentGeo = new RingGeometry(0.86, 0.94, 6, 1, 0, 0.16)
  for (let i = 0; i < 12; i += 1) {
    const segment = new Mesh(zoneSegmentGeo, alarmZoneMat)
    segment.rotation.x = -Math.PI / 2
    segment.rotation.z = (i / 12) * Math.PI * 2
    segment.position.y = 0.028
    alarmZone.add(segment)
  }
  disposables.push(alarmZoneMat, zoneSegmentGeo)

  /* ---------- 全息数据碎片：远景缓慢翻转的六边形线框 ---------- */
  const shards = []
  const shardMat = new MeshBasicMaterial({
    color: 0x9fc2ff, transparent: true, opacity: 0.14, wireframe: true,
    depthWrite: false, blending: AdditiveBlending
  })
  const shardGeo = new CircleGeometry(0.34, 6)
  const SHARD_COUNT = lowDetail ? 4 : 7
  for (let i = 0; i < SHARD_COUNT; i += 1) {
    const shard = new Mesh(shardGeo, shardMat)
    const angle = (i / SHARD_COUNT) * Math.PI * 2 + 0.4
    const radius = 4.6 + (i % 3) * 1.6
    shard.position.set(
      2.5 + Math.cos(angle) * radius,
      1.3 + (i % 4) * 0.45,
      Math.sin(angle) * radius * 0.8
    )
    shard.rotation.set(i * 0.7, i * 1.1, i * 0.5)
    shards.push({ mesh: shard, baseY: shard.position.y, phase: i * 1.3, spin: 0.12 + (i % 3) * 0.06 })
    group.add(shard)
  }
  disposables.push(shardMat, shardGeo)

  /* ---------- 全息防护罩：半球线框 + 沿球面升降的纬度扫描环 ---------- */
  const domeGroup = new Group()
  domeGroup.visible = false
  group.add(domeGroup)

  const domeMat = new MeshBasicMaterial({
    color: 0x9fc2ff, wireframe: true, transparent: true, opacity: 0.06,
    depthWrite: false, blending: AdditiveBlending
  })
  const domeGeo = new SphereGeometry(0.96, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2)
  const dome = new Mesh(domeGeo, domeMat)
  dome.position.y = 0.05
  domeGroup.add(dome)

  const domeRingMat = new MeshBasicMaterial({
    color: 0x9fc2ff, transparent: true, opacity: 0.3,
    depthWrite: false, blending: AdditiveBlending
  })
  const domeRingGeo = new TorusGeometry(1, 0.006, 6, 64)
  const domeScanRing = new Mesh(domeRingGeo, domeRingMat)
  domeScanRing.rotation.x = Math.PI / 2
  domeGroup.add(domeScanRing)
  disposables.push(domeMat, domeGeo, domeRingMat, domeRingGeo)

  /* ---------- 障碍测距：真实距离弧 + 从本体向外传播的探测脉冲 ---------- */
  const rangeGroup = new Group()
  rangeGroup.visible = false
  group.add(rangeGroup)

  const rangeMat = new MeshBasicMaterial({
    color: 0x74d7ff, transparent: true, opacity: 0.5, side: DoubleSide,
    depthWrite: false, blending: AdditiveBlending
  })
  const rangePulseMat = new MeshBasicMaterial({
    color: 0x74d7ff, transparent: true, opacity: 0.4, side: DoubleSide,
    depthWrite: false, blending: AdditiveBlending
  })
  const rangeArcGeo = new RingGeometry(0.965, 1, 40, 1, -0.48, 0.96)
  const rangeArc = new Mesh(rangeArcGeo, rangeMat)
  rangeArc.rotation.x = -Math.PI / 2
  rangeArc.position.y = 0.065
  rangeGroup.add(rangeArc)
  const rangePulse = new Mesh(rangeArcGeo, rangePulseMat)
  rangePulse.rotation.x = -Math.PI / 2
  rangePulse.position.y = 0.07
  rangeGroup.add(rangePulse)
  disposables.push(rangeMat, rangePulseMat, rangeArcGeo)

  /* ---------- 电量全息环：36 段地面弧按真实电量点亮 ---------- */
  const batteryGroup = new Group()
  batteryGroup.visible = false
  group.add(batteryGroup)

  const batteryActiveMat = new MeshBasicMaterial({
    color: 0x63d6a4, transparent: true, opacity: 0.55, side: DoubleSide,
    depthWrite: false, blending: AdditiveBlending
  })
  const batteryInactiveMat = new MeshBasicMaterial({
    color: 0x3a5870, transparent: true, opacity: 0.16, side: DoubleSide,
    depthWrite: false, blending: AdditiveBlending
  })
  const batteryStep = Math.PI * 2 / BATTERY_SEGMENTS
  const batterySegmentGeo = new RingGeometry(0.68, 0.735, 4, 1, 0, batteryStep * 0.68)
  const batterySegments = []
  for (let i = 0; i < BATTERY_SEGMENTS; i += 1) {
    const segment = new Mesh(batterySegmentGeo, batteryInactiveMat)
    segment.rotation.x = -Math.PI / 2
    segment.rotation.z = i * batteryStep
    segment.position.y = 0.04
    batterySegments.push(segment)
    batteryGroup.add(segment)
  }
  disposables.push(batteryActiveMat, batteryInactiveMat, batterySegmentGeo)

  /* ---------- 遥测上行：心跳正常时，从本体升起的数据粒子流 ---------- */
  const uplinkPositions = new Float32Array(UPLINK_COUNT * 3)
  const uplinkColors = new Float32Array(UPLINK_COUNT * 3)
  uplinkPositions.fill(-100)
  const uplinkGeo = new BufferGeometry()
  uplinkGeo.setAttribute('position', new BufferAttribute(uplinkPositions, 3))
  uplinkGeo.setAttribute('color', new BufferAttribute(uplinkColors, 3))
  const uplinkMat = new PointsMaterial({
    size: 0.065, map: spriteTexture, transparent: true, opacity: 0.85,
    depthWrite: false, sizeAttenuation: true, blending: AdditiveBlending, vertexColors: true
  })
  const uplink = new Points(uplinkGeo, uplinkMat)
  uplink.frustumCulled = false
  uplink.visible = false
  group.add(uplink)
  const uplinkColor = new Color(0x8fd8ff)
  const uplinkTint = new Color()
  disposables.push(uplinkGeo, uplinkMat)

  /* ---------- 终点任务进度：分段进度环 + 全部完成后的全息徽章 ---------- */
  const missionGroup = new Group()
  missionGroup.visible = false
  group.add(missionGroup)

  const missionActiveMat = new MeshBasicMaterial({
    color: accentHex, transparent: true, opacity: 0.55, side: DoubleSide,
    depthWrite: false, blending: AdditiveBlending
  })
  const missionInactiveMat = new MeshBasicMaterial({
    color: 0x3a5870, transparent: true, opacity: 0.16, side: DoubleSide,
    depthWrite: false, blending: AdditiveBlending
  })
  const missionStep = Math.PI * 2 / MISSION_SEGMENTS
  const missionSegmentGeo = new RingGeometry(0.48, 0.53, 4, 1, 0, missionStep * 0.68)
  const missionSegments = []
  for (let i = 0; i < MISSION_SEGMENTS; i += 1) {
    const segment = new Mesh(missionSegmentGeo, missionInactiveMat)
    segment.rotation.x = -Math.PI / 2
    segment.rotation.z = i * missionStep
    segment.position.y = 0.052
    missionSegments.push(segment)
    missionGroup.add(segment)
  }

  const missionBadgeMat = new SpriteMaterial({
    map: makeMissionBadgeTexture(), color: 0x7cf0b6, transparent: true,
    depthWrite: false, depthTest: false, opacity: 0.9
  })
  const missionBadge = new Sprite(missionBadgeMat)
  missionBadge.position.y = 0.86
  missionBadge.scale.set(0.52, 0.52, 1)
  missionBadge.renderOrder = 3
  missionBadge.visible = false
  missionGroup.add(missionBadge)

  const missionPulseMat = new MeshBasicMaterial({
    color: 0x63d6a4, transparent: true, opacity: 0, side: DoubleSide,
    depthWrite: false, blending: AdditiveBlending
  })
  const missionPulseGeo = new RingGeometry(0.36, 0.4, 48)
  const missionPulse = new Mesh(missionPulseGeo, missionPulseMat)
  missionPulse.rotation.x = -Math.PI / 2
  missionPulse.position.y = 0.058
  missionPulse.visible = false
  missionGroup.add(missionPulse)
  disposables.push(
    missionActiveMat, missionInactiveMat, missionSegmentGeo,
    missionBadgeMat, missionBadgeMat.map, missionPulseMat, missionPulseGeo
  )

  /* ---------- 运动光刃：高速时在本体后方生成流线型速度光迹 ---------- */
  const speedBladeMat = new MeshBasicMaterial({
    color: accentHex, transparent: true, opacity: 0.45, side: DoubleSide,
    depthWrite: false, blending: AdditiveBlending
  })
  const speedBladeGeo = new PlaneGeometry(1, 0.028)
  speedBladeGeo.rotateX(-Math.PI / 2)
  const speedBlades = []
  for (let i = 0; i < SPEED_BLADE_COUNT; i += 1) {
    const blade = new Mesh(speedBladeGeo, speedBladeMat)
    blade.visible = false
    speedBlades.push(blade)
    group.add(blade)
  }
  disposables.push(speedBladeMat, speedBladeGeo)

  /* ---------- 空间数据雨：远景稀疏垂直光线，持续缓慢下落 ---------- */
  const dataRainPositions = new Float32Array(DATA_RAIN_COUNT * 6)
  const dataRainDrops = []
  for (let i = 0; i < DATA_RAIN_COUNT; i += 1) {
    const angle = (i / DATA_RAIN_COUNT) * Math.PI * 2 + 0.2
    const radius = 4.2 + (i % 4) * 1.1
    dataRainDrops.push({
      x: 2.5 + Math.cos(angle) * radius,
      z: Math.sin(angle) * radius * 0.8,
      offset: (i * 0.37) % 3,
      speed: 0.22 + (i % 3) * 0.06,
      length: 0.18 + (i % 4) * 0.06
    })
  }
  const dataRainGeo = new BufferGeometry()
  dataRainGeo.setAttribute('position', new BufferAttribute(dataRainPositions, 3))
  const dataRainMat = new LineBasicMaterial({
    color: 0x77baff, transparent: true, opacity: 0.16,
    depthWrite: false, blending: AdditiveBlending
  })
  const dataRain = new LineSegments(dataRainGeo, dataRainMat)
  dataRain.frustumCulled = false
  dataRain.visible = false
  group.add(dataRain)
  disposables.push(dataRainGeo, dataRainMat)

  /* ---------- 悬浮状态标签：本体上方的 3D 模式/电量标签 ---------- */
  const statusTagMat = new SpriteMaterial({
    map: makeLabelTexture('待机', '#9fc2ff'), color: 0xffffff, transparent: true,
    depthWrite: false, depthTest: false, opacity: 0.92
  })
  const statusTag = new Sprite(statusTagMat)
  statusTag.scale.set(1.3, 0.364, 1)
  statusTag.renderOrder = 3
  statusTag.visible = false
  group.add(statusTag)
  let statusTagKey = ''
  disposables.push(statusTagMat)

  /* ---------- 螺旋能量链：环绕本体盘旋上升的光链 ---------- */
  const helixPositions = new Float32Array(HELIX_POINTS * 3)
  const helixColors = new Float32Array(HELIX_POINTS * 3)
  const helixGeo = new BufferGeometry()
  helixGeo.setAttribute('position', new BufferAttribute(helixPositions, 3))
  helixGeo.setAttribute('color', new BufferAttribute(helixColors, 3))
  const helixMat = new LineBasicMaterial({
    vertexColors: true, transparent: true, opacity: 0.55,
    depthWrite: false, blending: AdditiveBlending
  })
  const helix = new Line(helixGeo, helixMat)
  helix.frustumCulled = false
  helix.visible = false
  group.add(helix)
  disposables.push(helixGeo, helixMat)

  /* ---------- 头顶警示标：低电量/告警时出现的脉冲三角 ---------- */
  const warnMarkerMat = new SpriteMaterial({
    map: makeWarningTexture(), color: DANGER_COLOR, transparent: true,
    depthWrite: false, depthTest: false, opacity: 0.9
  })
  const warnMarker = new Sprite(warnMarkerMat)
  warnMarker.scale.set(0.36, 0.36, 1)
  warnMarker.renderOrder = 5
  warnMarker.visible = false
  group.add(warnMarker)
  disposables.push(warnMarkerMat, warnMarkerMat.map)

  /* ---------- 声呐扫描波纹：闲置时也保持周期性扩散，增强“活场景”感 ---------- */
  const pingMat = new MeshBasicMaterial({
    color: accentHex, transparent: true, opacity: 0, side: DoubleSide,
    depthWrite: false, blending: AdditiveBlending
  })
  const pingGeo = new RingGeometry(0.9, 1, 64)
  const ping = new Mesh(pingGeo, pingMat)
  ping.rotation.x = -Math.PI / 2
  ping.visible = false
  group.add(ping)
  disposables.push(pingMat, pingGeo)
  let pingAge = 2.2

  let appliedAlarm = -1
  let isDark = theme === 'dark'

  /** 告警等级：0 无、1 警示（琥珀）、2 危险（红）。 */
  function setAlarm(level) {
    const next = Math.max(0, Math.min(2, Number(level) || 0))
    if (next === appliedAlarm) return
    appliedAlarm = next
    alarmGroup.visible = next > 0
    const color = next === 2 ? DANGER_COLOR : WARN_COLOR
    alarmMat.color.setHex(color)
    alarmGlowMat.color.setHex(color)
    beamMat.color.setHex(color)
    alarmZoneMat.color.setHex(color)
  }

  /** 主题切换：浅色卡片上用常态混合避免加色被白底吃掉；深色保留加色辉光。 */
  function setTheme(next) {
    const dark = next === 'dark'
    isDark = dark
    const blend = dark ? AdditiveBlending : NormalBlending
    groundMat.blending = blend
    groundMat.opacity = dark ? 0.72 : 0.5
    groundMat.color.setHex(dark ? 0x9fc2ff : accentHex)
    radarMat.blending = blend
    radarMat.opacity = dark ? 0.16 : 0.06
    dustMat.blending = blend
    dustMat.opacity = dark ? 0.5 : 0.3
    flowMat.blending = dark ? AdditiveBlending : NormalBlending
    flowMat.opacity = dark ? 0.95 : 0.8
    visionMat.blending = blend
    visionScanMat.blending = blend
    curtainMat.blending = blend
    baseHaloMat.blending = blend
    reticleBracketMat.blending = blend
    diamondMat.blending = blend
    alarmZoneMat.blending = blend
    shardMat.blending = blend
    domeMat.blending = blend
    domeRingMat.blending = blend
    rangeMat.blending = blend
    rangePulseMat.blending = blend
    batteryActiveMat.blending = blend
    batteryInactiveMat.blending = blend
    uplinkMat.blending = blend
    missionActiveMat.blending = blend
    missionInactiveMat.blending = blend
    missionPulseMat.blending = blend
    speedBladeMat.blending = blend
    dataRainMat.blending = blend
    helixMat.blending = blend
  }

  setTheme(theme)
  setAlarm(0)

  /**
   * 逐帧更新。
   * @param {{dt?:number, elapsed?:number, robot?:import('three').Object3D|null,
   *   alarmLevel?:number, degraded?:boolean, speed?:number, mode?:string, stale?:boolean,
   *   battery?:number|null, obstacleDistance?:number|null}} input
   */
  function update({
    dt = 0.016, elapsed = 0, robot = null, alarmLevel = 0, degraded = false,
    speed = 0, mode = '', stale = false, battery = null, obstacleDistance = null
  } = {}) {
    /* 地面盘与雷达扇面：低速自转，降级时停转（仍保留静态装饰） */
    if (!degraded) {
      groundSpin.rotation.y = elapsed * 0.028
      radarSpin.rotation.y = elapsed * 0.42
      dust.rotation.y = elapsed * 0.012
      dust.position.y = Math.sin(elapsed * 0.4) * 0.07
      for (let i = 0; i < shards.length; i += 1) {
        const shard = shards[i]
        shard.mesh.rotation.x += dt * shard.spin
        shard.mesh.rotation.y += dt * shard.spin * 0.7
        shard.mesh.position.y = shard.baseY + Math.sin(elapsed * 0.7 + shard.phase) * 0.12
      }
    }
    setAlarm(alarmLevel)
    if (!degraded) updateFlow(elapsed)

    /* 巡检视野扇面：跟随本体朝向；自主态最亮，离线/心跳超时隐藏 */
    const showVision = Boolean(robot) && !stale && !degraded
    visionSpin.visible = showVision
    if (showVision) {
      visionSpin.position.set(robot.position.x, 0.03, robot.position.z)
      visionSpin.rotation.y = robot.rotation.y
      const wave = 0.5 + 0.5 * Math.sin(elapsed * 2.4)
      const base = mode === 'AUTONOMOUS' ? 0.22 : mode === 'HUMAN_CONTROL' ? 0.16 : 0.1
      visionMat.opacity = base + wave * 0.06
      visionMat.color.setHex(mode === 'HUMAN_CONTROL' ? 0x57c8d8 : mode === 'AUTONOMOUS' ? accentHex : 0x9fc2ff)
      visionScan.rotation.z = Math.sin(elapsed * 2.2) * (VISION_FOV / 2 - 0.12)
      visionScanMat.opacity = 0.2 + (0.5 + 0.5 * Math.sin(elapsed * 4.4)) * 0.2
    }

    /* 目标光柱：双环呼吸 + 光柱脉动（目标位置由 setRoute 决定，不随时间漂移） */
    if (targetGroup.visible) {
      const targetWave = 0.5 + 0.5 * Math.sin(elapsed * 3)
      targetRingBase.scale.setScalar(1 + targetWave * 0.18)
      targetRingTop.scale.setScalar(1.25 - targetWave * 0.25)
      targetBeamMat.opacity = 0.32 + targetWave * 0.26
      targetRingMat.opacity = 0.5 + targetWave * 0.3
    }

    /* 设备全息扫描：双向弧环自转 + 扫描光面自下而上 + 轨道光点环绕 */
    const showHolo = Boolean(robot) && !stale && !degraded
    holoGroup.visible = showHolo
    if (showHolo) {
      holoGroup.position.set(robot.position.x, 0, robot.position.z)
      const holoWave = 0.5 + 0.5 * Math.sin(elapsed * 2)
      holoRingA.rotation.z = elapsed * 1.1
      holoRingB.rotation.z = -elapsed * 1.7
      holoRingMatA.opacity = 0.24 + holoWave * 0.18
      holoRingMatB.opacity = 0.18 + (1 - holoWave) * 0.16

      const scanCycle = (elapsed % 2.6) / 2.6
      scanSweep.position.y = 0.06 + scanCycle * 1.5
      scanMat.opacity = 0.34 * Math.sin(Math.PI * scanCycle)

      for (let i = 0; i < orbitSparks.length; i += 1) {
        const angle = (i / orbitSparks.length) * Math.PI * 2 + elapsed * 0.9
        orbitSparks[i].position.set(
          Math.cos(angle) * 0.64,
          0.62 + Math.sin(elapsed * 1.8 + i * 1.7) * 0.34,
          Math.sin(angle) * 0.64
        )
      }
    }

    /* 全息扫描幕：整场横移，作为周期性全场景扫描 */
    if (!degraded) {
      const curtainCycle = (elapsed % 7) / 7
      curtain.visible = true
      curtain.position.set(2.5, 1.7, -10 + curtainCycle * 20)
      curtainMat.opacity = (isDark ? 0.16 : 0.1) * Math.sin(Math.PI * curtainCycle)
    } else {
      curtain.visible = false
    }

    /* 模式基座光环：自主蓝 / 遥控青 / 急停故障红 / 待机淡蓝（单环开销极低，降级时也保留） */
    if (robot) {
      baseHalo.visible = true
      baseHalo.position.set(robot.position.x, 0.025, robot.position.z)
      const haloHex = mode === 'E_STOP' || mode === 'FAULT' ? DANGER_COLOR
        : mode === 'AUTONOMOUS' ? accentHex
          : mode === 'HUMAN_CONTROL' ? 0x57c8d8 : 0x9fc2ff
      baseHaloMat.color.setHex(haloHex)
      const haloWave = 0.5 + 0.5 * Math.sin(elapsed * 2.6)
      baseHalo.scale.setScalar(1 + haloWave * 0.08)
      baseHaloMat.opacity = 0.12 + haloWave * 0.1
    } else {
      baseHalo.visible = false
    }

    /* 目标锁定框：Sprite 自动面向镜头，括号呼吸缩放 + 菱形旋转（HUD 级元素，降级时也保留） */
    if (robot) {
      reticleGroup.visible = true
      reticleGroup.position.set(robot.position.x, 0.62 + Math.sin(elapsed * 1.6) * 0.03, robot.position.z)
      const lockWave = 0.5 + 0.5 * Math.sin(elapsed * 2.8)
      reticleGroup.scale.setScalar(1 + lockWave * 0.05)
      reticleBracketMat.opacity = 0.4 + lockWave * 0.24
      diamondMat.rotation = elapsed * 0.9
      diamondMat.opacity = 0.5 + lockWave * 0.3
    } else {
      reticleGroup.visible = false
    }

    /* 告警警戒圈：告警时地面虚线环旋转并呼吸 */
    if (alarmGroup.visible && robot) {
      alarmZone.visible = true
      alarmZone.position.set(robot.position.x, 0, robot.position.z)
      alarmZone.rotation.y = elapsed * 0.5
      const zoneWave = 0.5 + 0.5 * Math.sin(elapsed * 3.4)
      alarmZone.scale.setScalar(1 + zoneWave * 0.16)
      alarmZoneMat.opacity = 0.2 + zoneWave * 0.26
    } else {
      alarmZone.visible = false
    }

    /* 全息防护罩：半球线框缓慢旋转，纬度环沿球面往复扫描 */
    const showDome = Boolean(robot) && !stale && !degraded
    domeGroup.visible = showDome
    if (showDome) {
      domeGroup.position.set(robot.position.x, 0, robot.position.z)
      dome.rotation.y = elapsed * 0.16
      const domeHex = alarmLevel === 2 || mode === 'E_STOP' || mode === 'FAULT' ? DANGER_COLOR
        : alarmLevel === 1 ? WARN_COLOR
          : mode === 'AUTONOMOUS' ? accentHex
            : mode === 'HUMAN_CONTROL' ? 0x57c8d8 : 0x9fc2ff
      domeMat.color.setHex(domeHex)
      domeRingMat.color.setHex(domeHex)
      const domeWave = 0.5 + 0.5 * Math.sin(elapsed * 2.1)
      domeMat.opacity = (mode === 'AUTONOMOUS' ? 0.085 : 0.045) + domeWave * 0.025
      const domePhase = (elapsed % 3.2) / 3.2
      const ringY = 0.08 + domePhase * 0.82
      const ringRadius = Math.sqrt(Math.max(0.01, 0.96 * 0.96 - (ringY - 0.05) ** 2))
      domeScanRing.position.y = ringY
      domeScanRing.scale.setScalar(ringRadius)
      domeRingMat.opacity = 0.34 * Math.sin(Math.PI * domePhase)
    }

    /* 障碍测距：距离弧位置严格使用真实 obstacleDistance，近距自动变色 */
    const distance = Number(obstacleDistance)
    const showRange = Boolean(robot) && !stale && obstacleDistance !== null
      && obstacleDistance !== undefined && Number.isFinite(distance) && distance >= 0.08 && distance <= 8
    rangeGroup.visible = showRange
    if (showRange) {
      rangeGroup.position.set(robot.position.x, 0, robot.position.z)
      rangeGroup.rotation.y = robot.rotation.y
      const rangeHex = distance < 0.5 ? DANGER_COLOR : distance < 1.2 ? WARN_COLOR : 0x74d7ff
      rangeMat.color.setHex(rangeHex)
      rangePulseMat.color.setHex(rangeHex)
      rangeArc.scale.setScalar(distance)
      rangeMat.opacity = 0.34 + (0.5 + 0.5 * Math.sin(elapsed * 3.2)) * 0.18
      rangePulse.visible = !degraded
      if (!degraded) {
        const rangePhase = (elapsed % 1.5) / 1.5
        const pulseDistance = Math.max(0.1, 0.3 + (distance - 0.3) * rangePhase)
        rangePulse.scale.setScalar(pulseDistance)
        rangePulseMat.opacity = 0.42 * (1 - rangePhase)
      }
    }

    /* 电量全息环：按真实百分比点亮分段，低电量红色/琥珀色脉冲 */
    const hasBattery = battery !== null && battery !== undefined && battery !== ''
      && Number.isFinite(Number(battery))
    const showBattery = Boolean(robot) && !stale && hasBattery
    batteryGroup.visible = showBattery
    if (showBattery) {
      const level = Math.max(0, Math.min(100, Number(battery)))
      batteryGroup.position.set(robot.position.x, 0, robot.position.z)
      const activeCount = Math.round(level / 100 * BATTERY_SEGMENTS)
      for (let i = 0; i < BATTERY_SEGMENTS; i += 1) {
        batterySegments[i].material = i < activeCount ? batteryActiveMat : batteryInactiveMat
      }
      batteryActiveMat.color.setHex(level < 15 ? DANGER_COLOR : level < 30 ? WARN_COLOR : 0x63d6a4)
      const batteryWave = 0.5 + 0.5 * Math.sin(elapsed * (level < 30 ? 5 : 2))
      batteryActiveMat.opacity = level < 30 ? 0.35 + batteryWave * 0.35 : 0.42 + batteryWave * 0.14
    }

    /* 遥测上行：粒子位置与颜色写入预分配缓冲，心跳异常立即隐藏 */
    const showUplink = Boolean(robot) && !stale && !degraded
    uplink.visible = showUplink
    if (showUplink) {
      for (let i = 0; i < UPLINK_COUNT; i += 1) {
        const phase = (elapsed * (0.28 + (i % 4) * 0.035) + i / UPLINK_COUNT) % 1
        const angle = i * 2.399 + elapsed * 0.25
        const radius = 0.16 + (i % 3) * 0.07
        uplinkPositions[i * 3] = robot.position.x + Math.cos(angle) * radius
        uplinkPositions[i * 3 + 1] = 0.5 + phase * 1.75
        uplinkPositions[i * 3 + 2] = robot.position.z + Math.sin(angle) * radius
        uplinkTint.copy(uplinkColor).multiplyScalar(Math.sin(Math.PI * phase))
        uplinkColors[i * 3] = uplinkTint.r
        uplinkColors[i * 3 + 1] = uplinkTint.g
        uplinkColors[i * 3 + 2] = uplinkTint.b
      }
      uplinkGeo.attributes.position.needsUpdate = true
      uplinkGeo.attributes.color.needsUpdate = true
    }

    /* 悬浮状态标签：真实模式 + 5% 取整电量，心跳中断转红 */
    if (robot) {
      statusTag.visible = true
      statusTag.position.set(robot.position.x, 1.42 + Math.sin(elapsed * 1.3) * 0.03, robot.position.z)
      const modeLabel = MODE_LABELS[mode] || '离线'
      const hasTagBattery = battery !== null && battery !== undefined && battery !== ''
        && Number.isFinite(Number(battery))
      const batteryBucket = hasTagBattery ? Math.round(Number(battery) / 5) * 5 : null
      const tagHex = stale ? DANGER_COLOR
        : alarmLevel === 2 || mode === 'E_STOP' || mode === 'FAULT' ? DANGER_COLOR
          : alarmLevel === 1 ? WARN_COLOR : accentHex
      const tagKey = `${stale ? 'STALE' : modeLabel}|${batteryBucket === null ? '--' : batteryBucket}|${tagHex}`
      if (tagKey !== statusTagKey) {
        statusTagKey = tagKey
        const text = stale
          ? '心跳中断'
          : batteryBucket === null ? modeLabel : `${modeLabel} · ${batteryBucket}%`
        const nextMap = makeLabelTexture(text, `#${tagHex.toString(16).padStart(6, '0')}`)
        if (statusTagMat.map) statusTagMat.map.dispose()
        statusTagMat.map = nextMap
        statusTagMat.needsUpdate = true
      }
    } else {
      statusTag.visible = false
    }

    /* 螺旋能量链：环绕本体盘旋上升，节点位置与亮度写入预分配缓冲 */
    const showHelix = Boolean(robot) && !stale && !degraded
    helix.visible = showHelix
    if (showHelix) {
      helixMat.color.setHex(mode === 'AUTONOMOUS' ? accentHex : 0x9fc2ff)
      for (let i = 0; i < HELIX_POINTS; i += 1) {
        const t = i / (HELIX_POINTS - 1)
        const angle = t * Math.PI * 4.4 + elapsed * 1.1
        const radius = 0.46 - t * 0.1
        helixPositions[i * 3] = robot.position.x + Math.cos(angle) * radius
        helixPositions[i * 3 + 1] = 0.12 + t * 1.2
        helixPositions[i * 3 + 2] = robot.position.z + Math.sin(angle) * radius
        const fade = Math.sin(Math.PI * t)
        helixColors[i * 3] = fade * 0.5
        helixColors[i * 3 + 1] = fade * 0.78
        helixColors[i * 3 + 2] = fade
      }
      helixGeo.attributes.position.needsUpdate = true
      helixGeo.attributes.color.needsUpdate = true
    }

    /* 头顶警示标：低电量或告警时脉冲显示，颜色随级别切换 */
    const warnBattery = battery !== null && battery !== undefined && battery !== ''
      && Number.isFinite(Number(battery)) && Number(battery) < 15
    const showWarnMarker = Boolean(robot) && (alarmLevel > 0 || warnBattery)
    warnMarker.visible = showWarnMarker
    if (showWarnMarker) {
      warnMarkerMat.color.setHex(alarmLevel >= 2 || warnBattery ? DANGER_COLOR : WARN_COLOR)
      const markerWave = 0.5 + 0.5 * Math.sin(elapsed * 4.2)
      warnMarker.position.set(robot.position.x, 1.82 + markerWave * 0.06, robot.position.z)
      warnMarkerMat.opacity = 0.5 + markerWave * 0.42
    }

    /* 终点任务进度：进度环呼吸；全部完成后徽章浮动并持续扩散完成脉冲 */
    if (missionGroup.visible) {
      const missionWave = 0.5 + 0.5 * Math.sin(elapsed * 2.6)
      missionActiveMat.opacity = 0.38 + missionWave * 0.2
      if (missionBadge.visible) {
        const badgeScale = 0.48 + missionWave * 0.08
        missionBadge.scale.set(badgeScale, badgeScale, 1)
        missionBadge.position.y = 0.84 + Math.sin(elapsed * 1.8) * 0.05
        missionBadgeMat.opacity = 0.7 + missionWave * 0.25
        const missionPhase = (elapsed % 2.2) / 2.2
        missionPulse.scale.setScalar(0.65 + missionPhase * 1.8)
        missionPulseMat.opacity = 0.4 * (1 - missionPhase)
      }
    }

    /* 运动光刃：按真实速度生成向后流动的光迹，低于阈值立即隐藏 */
    const showSpeedBlades = Boolean(robot) && !stale && !degraded && speed > 0.18
    speedBladeMat.color.setHex(mode === 'HUMAN_CONTROL' ? 0x57c8d8 : accentHex)
    speedBladeMat.opacity = Math.min(0.58, 0.22 + speed * 0.28)
    for (let i = 0; i < SPEED_BLADE_COUNT; i += 1) {
      const blade = speedBlades[i]
      blade.visible = showSpeedBlades
      if (!showSpeedBlades) continue
      const phase = (elapsed * (0.9 + speed * 0.6) + i / SPEED_BLADE_COUNT) % 1
      const behind = 0.35 + phase * 1.4
      const lateral = ((i % 4) - 1.5) * 0.14
      const yaw = robot.rotation.y
      blade.position.set(
        robot.position.x - Math.cos(yaw) * behind + Math.sin(yaw) * lateral,
        0.12 + (i % 3) * 0.06,
        robot.position.z + Math.sin(yaw) * behind + Math.cos(yaw) * lateral
      )
      blade.rotation.y = yaw
      blade.scale.set((0.35 + speed * 0.5) * (1 - phase * 0.45), 1, 1)
    }

    /* 空间数据雨：只更新预分配线段缓冲，降级时整体关闭 */
    dataRain.visible = !degraded
    if (!degraded) {
      for (let i = 0; i < DATA_RAIN_COUNT; i += 1) {
        const drop = dataRainDrops[i]
        const y = 0.35 + (((drop.offset - elapsed * drop.speed) % 3 + 3) % 3)
        dataRainPositions[i * 6] = drop.x
        dataRainPositions[i * 6 + 1] = y + drop.length
        dataRainPositions[i * 6 + 2] = drop.z
        dataRainPositions[i * 6 + 3] = drop.x
        dataRainPositions[i * 6 + 4] = y
        dataRainPositions[i * 6 + 5] = drop.z
      }
      dataRainGeo.attributes.position.needsUpdate = true
    }

    /* 声呐波纹：每 3 秒从本体脚下扩散一圈，最多扩散到 3.7m */
    if (robot && !stale && !degraded) {
      pingAge += dt
      if (pingAge > 3) pingAge = 0
      const k = pingAge / 1.7
      if (k < 1) {
        ping.visible = true
        ping.position.set(robot.position.x, 0.045, robot.position.z)
        ping.scale.setScalar(0.3 + k * 3.4)
        pingMat.opacity = 0.28 * (1 - k) * (1 - k)
      } else {
        ping.visible = false
      }
    } else {
      ping.visible = false
    }

    /* 运动拖尾：按真实速度向后喷出光尘，速度越快越密；停下即停止发射 */
    if (robot && !degraded && speed > 0.06) {
      emberClock += dt
      const interval = speed > 0.5 ? 0.045 : 0.09
      while (emberClock >= interval) {
        emberClock -= interval
        const yaw = robot.rotation.y
        const index = emberCursor % EMBER_COUNT
        emberCursor += 1
        emberPositions[index * 3] = robot.position.x - Math.cos(yaw) * 0.42 + (Math.random() - 0.5) * 0.16
        emberPositions[index * 3 + 1] = 0.08 + Math.random() * 0.12
        emberPositions[index * 3 + 2] = robot.position.z + Math.sin(yaw) * 0.42 + (Math.random() - 0.5) * 0.16
        emberLife[index] = 1
      }
    } else {
      emberClock = 0
    }
    let emberDirty = false
    for (let i = 0; i < EMBER_COUNT; i += 1) {
      if (emberLife[i] <= 0) continue
      emberLife[i] -= dt / 0.85
      emberDirty = true
      if (emberLife[i] <= 0) {
        emberLife[i] = 0
        emberPositions[i * 3 + 1] = -100
        emberColors[i * 3] = 0
        emberColors[i * 3 + 1] = 0
        emberColors[i * 3 + 2] = 0
        continue
      }
      emberPositions[i * 3 + 1] += dt * 0.34
      emberTint.copy(accent).multiplyScalar(emberLife[i])
      emberColors[i * 3] = emberTint.r
      emberColors[i * 3 + 1] = emberTint.g
      emberColors[i * 3 + 2] = emberTint.b
    }
    if (emberDirty) {
      emberGeo.attributes.position.needsUpdate = true
      emberGeo.attributes.color.needsUpdate = true
    }

    /* 交互脉冲：点击后 1 秒内扩散并淡出 */
    for (let i = bursts.length - 1; i >= 0; i -= 1) {
      const burst = bursts[i]
      burst.age += dt
      const k = burst.age / 1
      if (k >= 1) {
        group.remove(burst.ring)
        burst.ring.geometry.dispose()
        burst.mat.dispose()
        bursts.splice(i, 1)
        continue
      }
      burst.ring.scale.setScalar((0.25 + k * 2.6) * burst.size)
      burst.mat.opacity = 0.85 * (1 - k) * (1 - k)
    }

    if (!alarmGroup.visible || !robot) return
    /* 告警浮标跟随本体：位置在地面投影，光环呼吸 + 箭头旋转 */
    alarmGroup.position.set(robot.position.x, 0, robot.position.z)
    const wave = 0.5 + 0.5 * Math.sin(elapsed * 4.2)
    const pulse = 1 + wave * 0.35
    alarmRing.scale.setScalar(pulse)
    alarmMat.opacity = 0.5 + wave * 0.45
    alarmHalo.scale.setScalar(1 + wave * 0.5)
    alarmGlowMat.opacity = 0.16 + wave * 0.2
    chevron.position.y = 1.56 + Math.sin(elapsed * 3.2) * 0.06
    chevron.rotation.y = elapsed * 1.6
    beamMat.opacity = 0.28 + wave * 0.24
  }

  function dispose() {
    bursts.splice(0).forEach((burst) => {
      burst.ring.geometry.dispose()
      burst.mat.dispose()
    })
    if (targetLabel) {
      targetLabel.material.map?.dispose()
      targetLabel.material.dispose()
      targetLabel = null
    }
    statusTagMat.map?.dispose()
    disposables.forEach((item) => item.dispose?.())
    group.traverse((node) => {
      node.geometry?.dispose?.()
      node.material?.dispose?.()
    })
  }

  return { group, setRoute, setAlarm, setTheme, update, burstAt, dispose }
}
