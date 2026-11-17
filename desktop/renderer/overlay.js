/**
 * 圈选遮罩：暗色蒙层 + 拖框选区（选区内提亮），松开即提交 DIP 坐标，ESC 取消。
 */
const canvas = document.getElementById('mask');
const hint = document.getElementById('hint');
const sizeLabel = document.getElementById('size');
const api = window.smartops.overlay;

const ctx = canvas.getContext('2d');
const dpr = window.devicePixelRatio || 1;

function fitCanvas() {
  canvas.width = Math.round(window.innerWidth * dpr);
  canvas.height = Math.round(window.innerHeight * dpr);
  draw();
}

let start = null;
let current = null;

function rect() {
  if (!start || !current) return null;
  return {
    x: Math.min(start.x, current.x),
    y: Math.min(start.y, current.y),
    w: Math.abs(current.x - start.x),
    h: Math.abs(current.y - start.y),
  };
}

function draw() {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = window.innerWidth;
  const h = window.innerHeight;
  // 蒙层：半透明暗色
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = 'rgba(8, 12, 22, 0.35)';
  ctx.fillRect(0, 0, w, h);
  const r = rect();
  if (r) {
    // 选区内抠亮
    ctx.save();
    ctx.globalCompositeOperation = 'destination-out';
    ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
    ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.restore();
    ctx.strokeStyle = '#5b8cff';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(r.x + .5, r.y + .5, r.w, r.h);
    ctx.setLineDash([]);
    sizeLabel.hidden = false;
    sizeLabel.textContent = `${Math.round(r.w)} × ${Math.round(r.h)}`;
    sizeLabel.style.left = `${r.x}px`;
    sizeLabel.style.top = `${Math.max(2, r.y - 26)}px`;
  } else {
    sizeLabel.hidden = true;
  }
}

window.addEventListener('resize', fitCanvas);

window.addEventListener('mousedown', (e) => {
  if (e.button !== 0) return;
  start = { x: e.clientX, y: e.clientY };
  current = { ...start };
  hint.style.display = 'none';
  draw();
});

window.addEventListener('mousemove', (e) => {
  if (!start) return;
  current = { x: e.clientX, y: e.clientY };
  draw();
});

window.addEventListener('mouseup', () => {
  if (!start) return;
  const r = rect();
  start = null;
  current = null;
  api.done(r); // <10px 由主进程判为无效并取消
});

window.addEventListener('keyup', (e) => {
  if (e.key === 'Escape') api.cancel();
});

fitCanvas();
