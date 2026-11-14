/* 泳道图的视口数学：只做缩放与横向平移，不碰行模型。
   内容宽度始终等于视口宽度，所以放大后左右可拖，缩小后居中且不可拖。 */

export const ZOOM_MIN = 0.5
export const ZOOM_MAX = 2
export const ZOOM_STEP = 0.1

export function clampZoom(value) {
  if (!Number.isFinite(value)) return 1
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Number(value.toFixed(2))))
}

export function stepZoom(current, direction) {
  return clampZoom(current + direction * ZOOM_STEP)
}

export function panBounds(viewportWidth, zoom) {
  const width = Number.isFinite(viewportWidth) ? viewportWidth : 0
  const scaled = width * zoom
  if (scaled <= width) {
    const centered = (width - scaled) / 2
    return { min: centered, max: centered }
  }
  return { min: width - scaled, max: 0 }
}

export function clampPan(panX, viewportWidth, zoom) {
  const { min, max } = panBounds(viewportWidth, zoom)
  if (!Number.isFinite(panX)) return min
  return Math.min(max, Math.max(min, panX))
}

/* 以指针位置为中心缩放：缩放前后指针下面的内容坐标保持不变。 */
export function zoomAt({ zoom, panX, viewportWidth, pointerX, nextZoom }) {
  const target = clampZoom(nextZoom)
  const contentX = (pointerX - panX) / zoom
  return { zoom: target, panX: clampPan(pointerX - contentX * target, viewportWidth, target) }
}

export function zoomPercent(zoom) {
  return `${Math.round(zoom * 100)}%`
}
