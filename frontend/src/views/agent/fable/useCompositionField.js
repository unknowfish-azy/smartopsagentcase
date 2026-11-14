/**
 * useCompositionField.js
 *
 * 把后端数据映射为构成场的八个视觉参数。
 * 纯函数 —— 不 import Vue、不碰 DOM，可用 Node 直接跑单测。
 *
 * @param {Object} loops    GET /api/agent/loops   闭环数组（最多 30 条）
 * @param {Object} stats    GET /api/agent/loops/stats  { total, reviewed, resolved, learnedCount, byStage, resolveRate }
 * @param {Object} summary  GET /api/inspector/summary  { total, pass, warning, high, critical }
 * @param {Object} companion useCompanionStore()         { states: { whale } }
 *
 * @returns {{
 *   aperture: number,   // 孔径     0.40 – 1.20    来自 high + critical
 *   tilt:     number,   // 倾角    −34° – −6°     来自 byStage 主导相位
 *   volume:   number,   // 体积     0.85 – 1.15    来自 total（log 压缩）
 *   spin:     number,   // 环速     0 – 1          来自 warning
 *   groove:   number,   // 刻线     8 – 48（整数） 来自 learnedCount
 *   grain:    number,   // 噪声     0 – 1          来自 1 − resolveRate
 *   gaze:     { x:number, y:number },   // 瞳孔 来自焦点对象方向
 *   pulse:    number    // 心跳周期  2.4 – 6.0 s   来自闭环时长均值
 * }}
 */

/* ---------------------------- 通用工具 ---------------------------- */

/** 归一化：把 value 从 [lo, hi] 映射到 [0, 1]，超出范围则钳制 */
function norm(value, lo, hi) {
  const n = hi - lo
  if (n <= 0) return 0
  const v = (Number(value) || 0) - lo
  if (v < 0) return 0
  if (v > n) return 1
  return v / n
}

/** 数值钳制到 [lo, hi] */
function clamp(value, lo, hi) {
  const v = Number(value) || 0
  return v < lo ? lo : v > hi ? hi : v
}

/* ---------------------------- 阶段相位表 ---------------------------- */

/**
 * byStage 的每个 stage 映射到一个"目标倾角"。
 *
 * 真实后端 stage 流转顺序（DecisionLoopService.STAGES）：
 *   ANALYZE → MEMORIZE → DECIDE → REVIEW → LEARNED
 *   分析  →  记忆召回 → 决策  →  核查 → 学习完成
 *
 * 倾角形成 V 型：从分析到决策收拢（越决策越"聚焦"），
 *               再到学习完成重新展开回到中性。
 * 未知 stage（后端新增）一律归为 ANALYZE，不抛错。
 */
const STAGE_TILT_TARGET = {
  ANALYZE: -21,    // 分析：目光开始切片
  MEMORIZE: -18,   // 记忆：略收拢
  DECIDE: -7,      // 决策：孔径最窄，倾角最平
  REVIEW: -16,     // 核查：重新展开
  LEARNED: -12,    // 学习完成：回到中性
  DEFAULT: -21     // 兜底：未知值 → 按 ANALYZE 处理
}

/* ---------------------------- 主函数 ---------------------------- */

export function computeField(loops, stats, summary, companion) {
  // ---- null / 非法输入防护（默认值只防 undefined，null 要手动归一） ----
  loops = Array.isArray(loops) ? loops : []
  stats = (stats && typeof stats === 'object') ? stats : {}
  summary = (summary && typeof summary === 'object') ? summary : {}
  companion = (companion && typeof companion === 'object') ? companion : {}
  // ---- 输入归一化 ----
  const total = Number(stats.total ?? 0)
  const high = Number(summary.high ?? 0)
  const critical = Number(summary.critical ?? 0)
  const warning = Number(summary.warning ?? 0)
  const learnedCount = Number(stats.learnedCount ?? 0)
  const resolveRate = Number(stats.resolveRate ?? 0)

  // companion runtimeState
  const whaleState = companion?.states?.whale || ''
  const runtimeDegraded = whaleState === 'DEGRADED'

  // ---- 1. aperture 孔径 ----
  // 来源：inspector/summary → high + critical（上限 8）
  // 孔径越大越"睁着"；告警越多孔径越小越"眯着"
  const highCritical = high + critical
  const aperture = clamp(1.2 - 0.8 * norm(highCritical, 0, 8), 0.40, 1.20)

  // ---- 2. tilt 倾角 ----
  // 来源：loops/stats → byStage 主导相位
  // 按各 stage 的 count 加权，归为一个主导倾角
  const byStage = Array.isArray(stats.byStage) ? stats.byStage : []
  let tilt = -12 // IDLE 默认
  if (byStage.length > 0) {
    let totalCount = 0
    let weightedTilt = 0
    for (const entry of byStage) {
      const stage = (entry && entry.stage) ? String(entry.stage).toUpperCase() : 'ANALYZE'
      const count = Number(entry && entry.count ? entry.count : 0)
      if (count <= 0) continue
      const target = STAGE_TILT_TARGET[stage] ?? STAGE_TILT_TARGET.DEFAULT
      weightedTilt += target * count
      totalCount += count
    }
    if (totalCount > 0) {
      tilt = clamp(weightedTilt / totalCount, -34, -6)
    }
  } else if (runtimeDegraded) {
    // 没有 byStage 但 runtime 告警 → 用 DECIDE 倾角近似
    tilt = -7
  }

  // ---- 3. volume 体积 ----
  // 来源：loops/stats → total（log 压缩，上限 100）
  // 闭环越多体积越大，但用 log 压缩避免爆炸
  const volumeRatio = Math.log10(1 + total) / Math.log10(1 + 100)
  const volume = clamp(0.85 + 0.3 * volumeRatio, 0.85, 1.15)

  // ---- 4. spin 环速 ----
  // 来源：inspector/summary → warning（上限 5）
  const spin = norm(warning, 0, 5)

  // ---- 5. groove 刻线数 ----
  // 来源：loops/stats → learnedCount（上限 200）
  // 整数，8–48
  const groove = Math.round(clamp(8 + 40 * norm(learnedCount, 0, 200), 8, 48))

  // ---- 6. grain 噪声 ----
  // 来源：loops/stats → 1 − resolveRate
  // resolveRate 是 0..1 的浮点数；解决率越低，噪声越大
  const grain = clamp(1 - resolveRate, 0, 1)

  // ---- 7. gaze 瞳孔 ----
  // 来源：焦点对象方向 —— 最新 high 事件 / requiresHuman loop
  // 纯函数没有 UI 选中态，所以 gaze 只反映后端信号方向；
  // 组件层的指针跟随会叠加在这个基础上
  let gazeX = 0
  let gazeY = 0
  if (runtimeDegraded || highCritical > 0) {
    // 有告警 → 瞳孔往左偏 (-x)，幅度按严重度
    gazeX = -clamp(norm(highCritical, 0, 5) * 0.8, -0.8, 0.8)
  }
  // 看是否有需要人工审批的 loop
  const hasRequiresHuman = Array.isArray(loops) && loops.some(l => Boolean(l && l.requiresHuman))
  if (hasRequiresHuman) {
    // 需要审批 → 瞳孔往上偏移一些（y < 0），幅度 0.3
    gazeY = -0.3
  }
  const gaze = { x: clamp(gazeX, -1, 1), y: clamp(gazeY, -1, 1) }

  // ---- 8. pulse 心跳周期 ----
  // 来源：loops[] → 闭环时长均值（秒）
  // 数据库没有 started_at/ended_at，只有 created_at/updated_at/reviewed_at。
  // 优先用 reviewedAt - createdAt（走完核查阶段才有 reviewedAt，最接近"闭环时长"），
  // 其次 updatedAt - createdAt，都没有时退化为 4.0s 默认。
  let pulse = 4.0 // 中性默认
  const durations = []
  if (Array.isArray(loops)) {
    for (const loop of loops) {
      if (!loop) continue
      const created = loop.createdAt ? new Date(loop.createdAt).getTime() : null
      // 优先 reviewedAt，其次 updatedAt
      const ended = loop.reviewedAt
        ? new Date(loop.reviewedAt).getTime()
        : (loop.updatedAt ? new Date(loop.updatedAt).getTime() : null)
      if (created && ended && ended > created) {
        durations.push((ended - created) / 1000)
      }
    }
  }
  if (durations.length > 0) {
    // 取最近 5 条的均值，避免被很久以前的长闭环拖垮
    const recent = durations.slice(-5)
    const avg = recent.reduce((s, d) => s + d, 0) / recent.length
    // 均值可能是秒数，归一到 2.4–6.0s 区间：用 clamp 并按合理上限 600s 做比例
    pulse = clamp(2.4 + (avg / 600) * 3.6, 2.4, 6.0)
  }

  return {
    aperture,
    tilt,
    volume,
    spin,
    groove,
    grain,
    gaze,
    pulse
  }
}

/* ---------------------------- 边界场景专用 ---------------------------- */

/** 全零输入 —— 应该返回中性值（不是全 0） */
export function neutralField() {
  return computeField([], {}, {}, {})
}
