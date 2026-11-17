/**
 * 圈选截屏模块（P0）。
 *
 * 流程：全屏透明遮罩窗口（覆盖悬浮球所在显示器）→ 用户拖框圈选 →
 * 关闭遮罩 → desktopCapturer 取整屏物理像素帧 → 按选区×scaleFactor 裁剪 → PNG dataURL。
 */

const { BrowserWindow, ipcMain, desktopCapturer, screen } = require('electron');
const path = require('node:path');

let overlayWin = null;
let pendingDone = null;       // (rectDip | null) => void
let lastSelectionDisplay = null; // 创建遮罩时锁定的显示器（选区坐标以此为参照）

function getSelectionDisplay() {
  return lastSelectionDisplay;
}

function startSelection(anchorWin, { onDone } = {}) {
  if (overlayWin && !overlayWin.isDestroyed()) return; // 已在选区中
  pendingDone = typeof onDone === 'function' ? onDone : null;

  const anchorBounds = anchorWin && !anchorWin.isDestroyed() ? anchorWin.getBounds() : null;
  const display = screen.getDisplayNearestPoint(
    anchorBounds ? { x: anchorBounds.x, y: anchorBounds.y } : screen.getCursorScreenPoint(),
  );
  lastSelectionDisplay = display;

  overlayWin = new BrowserWindow({
    x: display.bounds.x,
    y: display.bounds.y,
    width: display.bounds.width,
    height: display.bounds.height,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    hasShadow: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    fullscreen: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  overlayWin.setAlwaysOnTop(true, 'screen-saver');
  overlayWin.loadFile(path.join(__dirname, 'renderer', 'overlay.html'));
  overlayWin.show();
  overlayWin.focus();
}

function cancelSelection() {
  if (overlayWin && !overlayWin.isDestroyed()) overlayWin.close();
  overlayWin = null;
  const done = pendingDone;
  pendingDone = null;
  if (done) done(null);
}

/** 选区完成（DIP 坐标）：先关遮罩再截屏，避免把遮罩拍进去。 */
function finishSelection(rectDip) {
  if (overlayWin && !overlayWin.isDestroyed()) overlayWin.close();
  overlayWin = null;
  const done = pendingDone;
  pendingDone = null;
  if (!done) return;
  if (!rectDip || rectDip.w < 10 || rectDip.h < 10) {
    done(null);
    return;
  }
  done(rectDip);
}

/** 按选区截屏并裁剪，返回 PNG dataURL；失败抛错由调用方如实提示。 */
async function captureRegion(rectDip, display) {
  const dpr = display.scaleFactor || 1;
  const sources = await desktopCapturer.getSources({
    types: ['screen'],
    thumbnailSize: {
      width: Math.round(display.size.width * dpr),
      height: Math.round(display.size.height * dpr),
    },
  });
  const wanted = String(display.id);
  const source =
    sources.find((s) => String(s.display_id) === wanted) ||
    sources.find((s) => s.thumbnail && !s.thumbnail.isEmpty());
  if (!source || !source.thumbnail || source.thumbnail.isEmpty()) {
    throw new Error('未能获取屏幕画面（desktopCapturer 无可用源）');
  }
  const physical = {
    x: Math.max(0, Math.round(rectDip.x * dpr)),
    y: Math.max(0, Math.round(rectDip.y * dpr)),
    width: Math.max(1, Math.round(rectDip.w * dpr)),
    height: Math.max(1, Math.round(rectDip.h * dpr)),
  };
  // 夹紧到整屏物理尺寸内
  const size = source.thumbnail.getSize();
  physical.x = Math.min(physical.x, size.width - 1);
  physical.y = Math.min(physical.y, size.height - 1);
  physical.width = Math.min(physical.width, size.width - physical.x);
  physical.height = Math.min(physical.height, size.height - physical.y);

  const cropped = source.thumbnail.crop(physical);
  return cropped.toDataURL('image/png');
}

module.exports = { startSelection, cancelSelection, finishSelection, captureRegion, getSelectionDisplay };
