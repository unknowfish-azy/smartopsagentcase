/**
 * =========================================================
 * 本地图形点选人机验证（离线可用）
 * =========================================================
 *
 * 后端下发的是服务端生成的完整 SVG 场景（`scene`），前端只负责：
 *   1. 把场景原样注入展示；
 *   2. 把点击位置换算成 SVG viewBox 坐标（0..300 / 0..200）；
 *   3. 把坐标回传换一次性 token。
 *
 * 正确坐标从不下发到浏览器，几何判定只在服务端做，因此这里没有任何"答案"逻辑。
 * 纯函数集中在本文件，便于 node --test 直接测试。
 */

/** 与后端 `smartops.security.human-verification.min-response-ms` 无关的界面文案。 */
export const CLICK_HINT = '请在下方图形中按提示点选'

/** 色值 → 中文名，与后端 COLORS/HEX 一一对应，仅用于提示里的颜色序号解析。 */
const COLOR_NAMES = [
  ['红色', '#e2453c'],
  ['蓝色', '#2f6fe0'],
  ['绿色', '#2f9e5f'],
  ['橙色', '#e88b1f'],
  ['紫色', '#8b5cf6'],
  ['青色', '#0ea5b7']
]

/** 解析后端策略里与本地图形验证相关的字段，字段缺失/类型不对时返回 null（调用方按失败处理）。 */
export function localChallengeOf (policy) {
  if (!policy || policy.provider !== 'local') return null
  const { challenge, prompt, scene, targets, tolerance } = policy
  if (typeof challenge !== 'string' || !challenge || typeof scene !== 'string' || !scene.includes('<svg')) return null
  if (typeof targets !== 'number' || !Number.isInteger(targets) || targets < 1) return null
  if (typeof tolerance !== 'number' || tolerance <= 0) return null
  // provider 必须一起带出来：调用方（HumanVerification.vue 的 local 计算属性）用
  // challenge.provider === 'local' 判定是否渲染本地图形分支，丢掉它会让该分支永远不可达。
  return { provider: 'local', nonce: challenge, prompt: typeof prompt === 'string' ? prompt : '', scene, targets, tolerance }
}

/** 点击数量是否已经满足挑战要求的点击次数。 */
export function isComplete (state) {
  return Boolean(state) && state.pending.length === state.targets
}

/** 累加一次点击：超出目标数量时忽略，返回新的状态对象（不修改入参）。 */
export function addClick (state, point) {
  if (!state || !point) return state
  if (state.pending.length >= state.targets) return state
  return { ...state, pending: [...state.pending, point] }
}

/** 按顺序导出点击坐标数组，正好是提交给后端的 `clicks` 字段。 */
export function pendingClicks (state) {
  return state ? state.pending.map(click => ({ x: click.x, y: click.y })) : []
}

/** 生成进度文案：已点 / 需要点的数量。 */
export function progressLabel (state) {
  if (!state) return ''
  return `已点击 ${state.pending.length}/${state.targets}`
}

/** 复位点击进度（同一个挑战失败后允许继续作答）。 */
export function resetClicks (state) {
  return state ? { ...state, pending: [] } : state
}

/**
 * 把指针事件位置换算成 SVG viewBox 坐标。
 *
 * @param {{left:number, top:number, width:number, height:number}} box 画布的屏幕矩形
 * @param {{x:number, y:number}} point 指针在屏幕坐标系里的位置
 * @param {{width:number, height:number}} viewBox 服务端场景的 viewBox
 * @returns {{x:number, y:number}|null} 落在画布外时返回 null
 */
export function toViewBox (box, point, viewBox) {
  if (!box || !point || !viewBox) return null
  if (!(box.width > 0) || !(box.height > 0) || !(viewBox.width > 0) || !(viewBox.height > 0)) return null
  const x = (point.x - box.left) / box.width * viewBox.width
  const y = (point.y - box.top) / box.height * viewBox.height
  return { x: Math.round(x), y: Math.round(y) }
}

/**
 * 把服务端下发的 `<svg …>` 场景改造成自适应宽度的展示版本：
 * 只补一个合法 CSS 宽度，其余属性（viewBox、图形、颜色、字符）保持原样，不改动任何坐标。
 */
export function displayScene (scene) {
  if (typeof scene !== 'string' || !scene.startsWith('<svg')) return ''
  const head = scene.slice(0, scene.indexOf('>') + 1)
  if (head.includes('style=')) return scene
  return scene.replace('<svg', '<svg style="width:100%;height:100%;display:block"')
}

/** 依据提示算出服务端期望的点击顺序（仅测试与断言使用，不参与真实判定）。 */
export function solveForTest (prompt, shapes) {
  if (typeof prompt !== 'string' || !Array.isArray(shapes)) return []
  const colorToken = prompt.match(/#[0-9a-f]{6}/i)
  if (colorToken) {
    const expected = colorToken[0].toLowerCase()
    return shapes.filter(shape => shape.color.toLowerCase() === expected).map(shape => ({ x: shape.x, y: shape.y }))
  }
  const letters = []
  for (const char of prompt) {
    if (shapes.some(shape => shape.letter === char)) letters.push(char)
  }
  if (letters.length > 0) {
    return letters.map(letter => {
      const shape = shapes.find(candidate => candidate.letter === letter)
      return { x: shape.x, y: shape.y }
    })
  }
  const ordered = COLOR_NAMES
    .map(([name, color]) => ({ at: prompt.indexOf(name), color }))
    .filter(entry => entry.at >= 0)
    .sort((left, right) => left.at - right.at)
  const clicks = []
  for (const entry of ordered) {
    for (const shape of shapes) if (shape.color.toLowerCase() === entry.color) clicks.push({ x: shape.x, y: shape.y })
  }
  return clicks
}
