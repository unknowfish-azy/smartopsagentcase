/**
 * sceneReconstruction — 真实场景还原的数据层（纯函数）
 *
 * 第一版只做「素材接入 + 流程编排」：识别扫描件类型、校验大小、生成还原流水线阶段。
 * 真实还原引擎尚未接入，因此任何阶段都不会被伪造为「已完成」——点击开始只会进入
 * BLOCKED 并说明依赖缺失，页面同时展示后续技术路线。
 */

/** 单文件上限 512MB，超出大概率是未分块的原始点云，需要离线预处理。 */
export const MAX_ASSET_BYTES = 512 * 1024 * 1024

export const ASSET_KINDS = Object.freeze({
  'point-cloud': '点云',
  mesh: '网格模型',
  'image-set': '实景影像',
  archive: '压缩包',
  unknown: '未识别'
})

const EXT_KIND = {
  ply: 'point-cloud',
  pcd: 'point-cloud',
  las: 'point-cloud',
  laz: 'point-cloud',
  e57: 'point-cloud',
  xyz: 'point-cloud',
  glb: 'mesh',
  gltf: 'mesh',
  obj: 'mesh',
  fbx: 'mesh',
  stl: 'mesh',
  jpg: 'image-set',
  jpeg: 'image-set',
  png: 'image-set',
  tif: 'image-set',
  tiff: 'image-set',
  dng: 'image-set',
  zip: 'archive',
  '7z': 'archive',
  tar: 'archive',
  gz: 'archive'
}

/** 还原流水线阶段：与后续引擎实现一一对应，禁止跳过。 */
export const RECONSTRUCTION_STAGES = Object.freeze([
  { key: 'align', label: '点云 / 影像配准', detail: '把多站点云统一到同一坐标系' },
  { key: 'mesh', label: '网格重建', detail: '生成可渲染的厂房与机柜几何体' },
  { key: 'semantic', label: '语义标注', detail: '标注机柜、冷通道、机器人停放位' },
  { key: 'sensor', label: '传感器绑定', detail: '把温度/湿度/功率点位绑到几何体' },
  { key: 'publish', label: '发布孪生场景', detail: '发布后由 3D 机房页面消费' }
])

/** 取小写扩展名，无扩展名返回空串。 */
export function fileExtension(name) {
  const text = String(name || '')
  const dot = text.lastIndexOf('.')
  if (dot < 0 || dot === text.length - 1) return ''
  return text.slice(dot + 1).toLowerCase()
}

/** 识别单个扫描件；无法识别时给出可执行的原因。 */
export function classifyScanAsset(name) {
  const ext = fileExtension(name)
  if (!ext) return { ok: false, ext: '', kind: 'unknown', reason: '缺少扩展名，无法判断素材类型' }
  const kind = EXT_KIND[ext]
  if (!kind) {
    return {
      ok: false,
      ext,
      kind: 'unknown',
      reason: `不支持 .${ext}：请上传点云（ply/pcd/las）、网格（glb/gltf/obj）或实景影像`
    }
  }
  return { ok: true, ext, kind, label: ASSET_KINDS[kind], reason: '' }
}

export function formatBytes(bytes) {
  const value = Number(bytes)
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size >= 100 || unit === 0 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`
}

/**
 * 汇总素材覆盖度：还原至少需要点云或网格之一，只有影像时只能做纹理贴图。
 */
export function summariseCoverage(assets) {
  const kinds = new Set((assets || []).map(asset => asset.kind))
  const pointCloud = kinds.has('point-cloud')
  const mesh = kinds.has('mesh')
  const imagery = kinds.has('image-set') || kinds.has('archive')
  return {
    pointCloud,
    mesh,
    imagery,
    ready: pointCloud || mesh,
    reason: pointCloud || mesh
      ? ''
      : imagery
        ? '只有影像素材：可用于贴图，但缺少几何来源，需要补充点云或网格'
        : '还没有可用的扫描素材'
  }
}

/**
 * 由文件列表创建还原任务（不落盘、不上传，只做本地编排）。
 * @returns {{assets:Array, rejected:Array, totalBytes:number, coverage:object, stages:Array, status:string}}
 */
export function createReconstructionJob(fileList) {
  const assets = []
  const rejected = []
  for (const file of fileList || []) {
    const name = file?.name ?? ''
    const size = Number(file?.size) || 0
    const info = classifyScanAsset(name)
    if (!info.ok) {
      rejected.push({ name, reason: info.reason })
      continue
    }
    if (size > MAX_ASSET_BYTES) {
      rejected.push({ name, reason: `超过单文件上限 ${formatBytes(MAX_ASSET_BYTES)}，请先分块或抽稀` })
      continue
    }
    assets.push({ name, size, kind: info.kind, kindLabel: info.label, ext: info.ext })
  }
  const totalBytes = assets.reduce((sum, asset) => sum + asset.size, 0)
  return {
    assets,
    rejected,
    totalBytes,
    coverage: summariseCoverage(assets),
    stages: RECONSTRUCTION_STAGES.map(stage => ({ ...stage, status: 'pending' })),
    status: assets.length ? 'READY' : 'EMPTY'
  }
}

/**
 * 启动还原：引擎未接入，如实返回 BLOCKED 并指出缺失依赖，绝不伪造进度。
 */
export function startReconstruction(job) {
  if (!job || !job.assets?.length) {
    return { ...job, status: 'EMPTY', notice: '请先上传点云或网格素材' }
  }
  if (!job.coverage?.ready) {
    return { ...job, status: 'BLOCKED', notice: job.coverage?.reason || '素材不足，无法开始还原' }
  }
  return {
    ...job,
    status: 'BLOCKED',
    notice: '还原引擎尚未接入：当前仅完成素材接入与流程编排，点击下方技术路线可查看接入顺序',
    stages: job.stages.map((stage, index) => ({ ...stage, status: index === 0 ? 'blocked' : 'pending' }))
  }
}
