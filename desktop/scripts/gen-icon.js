/**
 * 生成 assets/icon.png（64×64，蓝色圆 + 白色小鲸鱼轮廓，无第三方依赖）。
 * 运行：node scripts/gen-icon.js
 */
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const SIZE = 64;

// —— 画布：透明底，圆形渐变球体 ——
const pixels = Buffer.alloc(SIZE * SIZE * 4, 0);

function setPixel(x, y, [r, g, b, a]) {
  const i = (y * SIZE + x) * 4;
  pixels[i] = r; pixels[i + 1] = g; pixels[i + 2] = b; pixels[i + 3] = a;
}

const CX = 32, CY = 32, R = 29;
for (let y = 0; y < SIZE; y++) {
  for (let x = 0; x < SIZE; x++) {
    const d = Math.hypot(x - CX, y - CY);
    if (d > R + 1) continue;
    // 边缘 1px 抗锯齿
    const alpha = d > R ? Math.max(0, Math.round(255 * (R + 1 - d))) : 255;
    // 对角渐变：#5b8cff → #1e3aa8
    const t = Math.min(1, Math.max(0, ((x + y) / 2 - 6) / 52));
    const r = Math.round(0x5b + (0x1e - 0x5b) * t);
    const g = Math.round(0x8c + (0x3a - 0x8c) * t);
    const b = Math.round(0xff + (0xa8 - 0xff) * t);
    setPixel(x, y, [r, g, b, alpha]);
  }
}

// 白色小鲸鱼轮廓（与 ball.html 的 SVG 同形，简化为粗笔画）
const whale = [
  '................................',
  '.............#####..............',
  '...........#########............',
  '..........###########...........',
  '.........#############..........',
  '.........##############.........',
  '........################........',
  '........######..##########......',
  '........#####....###########....',
  '........##############......#...',
  '.........############....####...',
  '..........##########...####.....',
  '...........########...###.......',
  '............######..##..........',
  '.............####.#.............',
  '..............###...............',
].map((row) => row.split(''));

const WOX = 9, WOY = 15;
whale.forEach((row, ry) => {
  row.forEach((cell, rx) => {
    if (cell === '#' || cell === '.') {
      // 只画 # 为白色，小气泡点用深蓝
      if (cell !== '#') return;
      const x = WOX + rx, y = WOY + ry;
      if (x < 0 || x >= SIZE || y < 0 || y >= SIZE) return;
      setPixel(x, y, [255, 255, 255, 235]);
    }
  });
});

// —— 最小 PNG 编码器 ——
function crc32(buf) {
  let table = crc32.table;
  if (!table) {
    table = crc32.table = new Int32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c;
    }
  }
  let crc = -1;
  for (const byte of buf) crc = (crc >>> 8) ^ table[(crc ^ byte) & 0xff];
  return (crc ^ -1) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

const ihdr = Buffer.alloc(13);
ihdr.writeUInt32BE(SIZE, 0);
ihdr.writeUInt32BE(SIZE, 4);
ihdr[8] = 8;  // bit depth
ihdr[9] = 6;  // color type RGBA
// scanlines: filter byte 0 + RGBA
const raw = Buffer.alloc(SIZE * (1 + SIZE * 4));
for (let y = 0; y < SIZE; y++) {
  raw[y * (1 + SIZE * 4)] = 0;
  pixels.copy(raw, y * (1 + SIZE * 4) + 1, y * SIZE * 4, (y + 1) * SIZE * 4);
}
const png = Buffer.concat([
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  chunk('IHDR', ihdr),
  chunk('IDAT', zlib.deflateSync(raw, { level: 9 })),
  chunk('IEND', Buffer.alloc(0)),
]);

const out = path.join(__dirname, '..', 'assets', 'icon.png');
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, png);
console.log(`written ${out} (${png.length} bytes)`);
