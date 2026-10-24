const LABELS = Object.freeze({ SCREENSHOT: '截屏', CAMERA: '拍照', CLIPBOARD: '剪贴板', FILE: '文件', DRAG_DROP: '拖拽' })

export function sourceLabel(source) { return LABELS[source] || '视觉附件' }

export function stopMediaStream(stream) {
  for (const track of stream?.getTracks?.() || []) track.stop()
}

function mediaError(error, fallback) {
  if (error?.name === 'NotAllowedError' || error?.name === 'PermissionDeniedError') return new Error('VISUAL_PERMISSION_DENIED')
  return new Error(fallback)
}

async function frameToFile(video, source, { documentRef = globalThis.document } = {}) {
  const canvas = documentRef.createElement('canvas')
  canvas.width = video.videoWidth || 1280
  canvas.height = video.videoHeight || 720
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'))
  if (!blob) throw new Error('VISUAL_CAPTURE_EMPTY')
  return new File([blob], `${source.toLowerCase()}-${Date.now()}.png`, { type: 'image/png', lastModified: Date.now() })
}

async function capture(kind, { mediaDevices = globalThis.navigator?.mediaDevices, documentRef = globalThis.document } = {}) {
  const getter = kind === 'SCREENSHOT' ? mediaDevices?.getDisplayMedia?.bind(mediaDevices) : mediaDevices?.getUserMedia?.bind(mediaDevices)
  if (!getter) throw new Error(kind === 'SCREENSHOT' ? 'SCREEN_CAPTURE_UNAVAILABLE' : 'CAMERA_UNAVAILABLE')
  let stream
  try { stream = await getter(kind === 'SCREENSHOT' ? { video: true, audio: false } : { video: { facingMode: 'environment' }, audio: false })
    const video = documentRef.createElement('video'); video.muted = true; video.playsInline = true; video.srcObject = stream
    await video.play?.()
    return await frameToFile(video, kind, { documentRef })
  } catch (error) { throw error?.message?.startsWith('VISUAL_') || error?.message?.includes('UNAVAILABLE') ? error : mediaError(error, 'VISUAL_CAPTURE_FAILED') }
  finally { stopMediaStream(stream) }
}

export function captureScreen(options) { return capture('SCREENSHOT', options) }
export function captureCamera(options) { return capture('CAMERA', options) }
