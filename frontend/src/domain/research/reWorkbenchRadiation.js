/**
 * REA 工具辐射图——纯几何 / 布局函数。
 *
 * 从 ReWorkbenchRadiation.vue 抽出，保持零依赖（不 import Vue），
 * 便于单元测试覆盖：弧段均分、流线 y 分布、贝塞尔路径、命中点亮与管线错峰序号。
 *
 * 红线（与组件注释一致）：
 * - 流线不是装饰——只有命中当前目标管线的工具才点亮；未选目标时全部静默。
 * - 颜色是阶段语义色（非装饰霓虹），未知阶段走 FALLBACK_COLOR。
 */

export const STAGE_COLORS = Object.freeze({
  recon: '#5ECBC8',
  static: '#6EA8FE',
  dynamic: '#E7B763',
  network: '#A78BFA',
  memory: '#F08A8A',
  report: '#78C679'
})
export const FALLBACK_COLOR = '#8AA0B4'

export const CX = 112
export const CY = 190
export const R = 72
export const START_X = CX + R + 6
export const END_X = 742
export const TOP_Y = 24
export const BOTTOM_Y = 356
/** 阶段弧半径（比中心环大 12，避免重叠）。 */
export const ARC_R = 84
/** 弧段间隙（SVG 单位）。 */
export const ARC_GAP = 8

export const stageColor = stageId => STAGE_COLORS[stageId] || FALLBACK_COLOR

/**
 * 6 段阶段弧：按阶段顺序均分圆周，段间留 ARC_GAP 间隙。
 * @returns {{stage: object, r: number, color: string, dash: string, offset: number}[]}
 */
export function buildArcs(stages) {
  const list = Array.isArray(stages) ? stages : []
  const circumference = 2 * Math.PI * ARC_R
  const step = circumference / Math.max(list.length, 1)
  const seg = Math.max(step - ARC_GAP, 4)
  return list.map((stage, i) => ({
    stage,
    r: ARC_R,
    color: stageColor(stage.id),
    dash: `${seg} ${circumference - seg}`,
    offset: -step * i
  }))
}

/**
 * 15 条贝塞尔流线：起点同为圆环右缘，终点按工具序均分布满上下界。
 * @param {object[]} tools 工具目录（须含 id / stage）
 * @param {Set|Array} activeIds 当前目标管线命中的工具 id 集合
 * @param {Array} activeOrder 命中工具按真实 pipeline 顺序排列的 id 数组
 * @returns {{tool: object, y: number, d: string, color: string, active: boolean, order: number}[]}
 */
export function buildRays(tools, activeIds, activeOrder) {
  const list = Array.isArray(tools) ? tools : []
  const active = activeIds instanceof Set ? activeIds : new Set(Array.isArray(activeIds) ? activeIds : [])
  const orderSource = Array.isArray(activeOrder) ? activeOrder : []
  const orderMap = new Map(orderSource.map((id, i) => [id, i]))
  const count = list.length
  return list.map((tool, i) => {
    const y = count === 1
      ? (TOP_Y + BOTTOM_Y) / 2
      : TOP_Y + (BOTTOM_Y - TOP_Y) * (i / (count - 1))
    return {
      tool,
      y,
      d: `M ${START_X} ${CY} C 360 ${CY}, 520 ${y}, ${END_X} ${y}`,
      color: stageColor(tool.stage),
      active: active.has(tool.id),
      // 命中工具按真实管线顺序错峰；未命中（或顺序表缺项）退回卡片序号，保证渲染稳定
      order: orderMap.has(tool.id) ? orderMap.get(tool.id) : i
    }
  })
}

export function radiationHint(toolsCount, activeCount, label) {
  const total = Number(toolsCount) || 0
  const hit = Number(activeCount) || 0
  return hit
    ? `已按「${label || '当前目标'}」点亮 ${hit} / ${total} 条工具管线`
    : '未选目标：全部静默，无事件不绘制流线'
}

export function radiationAriaLabel(toolsCount, activeCount, label) {
  const total = Number(toolsCount) || 0
  const hit = Number(activeCount) || 0
  return hit
    ? `REA 工具辐射图，共 ${total} 个工具，当前目标 ${label || '未命名'} 命中 ${hit} 个`
    : `REA 工具辐射图，共 ${total} 个工具，尚未选择目标，全部静默`
}
