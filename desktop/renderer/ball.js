/**
 * 悬浮球手势（对标大学搜题酱）：
 *   单击 → 展开/收起对话面板；双击 → 截屏提问（圈选）；长按 3s → 菜单；拖拽 → 移动。
 */
const ball = document.getElementById('ball');
const api = window.smartops.ball;

const LONG_PRESS_MS = 3000;
const DBL_CLICK_MS = 280;
const DRAG_THRESHOLD = 6;

let pressing = false;
let moved = false;
let longPressTimer = null;
let clickTimer = null;
let lastX = 0;
let lastY = 0;
let dragging = false;

function clearLongPress() {
  if (longPressTimer) {
    clearTimeout(longPressTimer);
    longPressTimer = null;
  }
}

ball.addEventListener('contextmenu', (e) => e.preventDefault());

ball.addEventListener('mousedown', (e) => {
  if (e.button !== 0) return;
  pressing = true;
  moved = false;
  lastX = e.screenX;
  lastY = e.screenY;
  clearLongPress();
  longPressTimer = setTimeout(() => {
    longPressTimer = null;
    pressing = false;
    api.menu(); // 长按 3s → 菜单
  }, LONG_PRESS_MS);
});

window.addEventListener('mousemove', (e) => {
  if (!pressing) return;
  const dx = e.screenX - lastX;
  const dy = e.screenY - lastY;
  if (!moved && Math.hypot(dx, dy) > DRAG_THRESHOLD) {
    moved = true;
    dragging = true;
    clearLongPress();
    api.moveStart();
  }
  if (dragging) {
    api.moveBy(0, 0); // 主进程按光标位置 + 按下偏移吸附，无需传增量
    lastX = e.screenX;
    lastY = e.screenY;
  }
});

window.addEventListener('mouseup', () => {
  if (!pressing) return;
  pressing = false;
  clearLongPress();
  if (dragging) {
    dragging = false;
    api.moveEnd();
    return;
  }
  // 单击/双击判别：第一击挂起 280ms，等待第二击
  if (clickTimer) {
    clearTimeout(clickTimer);
    clickTimer = null;
    api.capture(); // 双击 → 截屏提问
  } else {
    clickTimer = setTimeout(() => {
      clickTimer = null;
      api.togglePanel(); // 单击 → 面板
    }, DBL_CLICK_MS);
  }
});

// 状态动效：idle / thinking / error（主进程随 AI 流转发出）
api.onState((state) => {
  ball.className = `ball ball--${state === 'thinking' ? 'thinking' : state === 'error' ? 'error' : 'idle'}`;
});
