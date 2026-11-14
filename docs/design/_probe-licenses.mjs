const repos = [
  ['rive-app/rive-wasm', 'Rive 官方 WASM 运行时（state machine + inputs）'],
  ['juliangarnier/anime', 'anime.js v4 动画引擎（spring / 时间轴）'],
  ['motiondivision/motion', 'Motion（原 Framer Motion）vanilla 版'],
  ['airbnb/lottie-web', 'Lottie 运行时（AE 导出 JSON）'],
  ['metafizzy/zdog', 'Zdog 伪 3D 图形引擎（canvas / SVG）'],
  ['oframe/ogl', 'OGL 极简 WebGL 库'],
  ['pixijs/pixijs', 'PixiJS 2D WebGL 渲染器'],
  ['statelyai/xstate', 'XState 状态机（驱动动画输入）'],
  ['theatre-js/theatre', 'Theatre.js 动效编辑器 + 运行时'],
  ['vueuse/motion', 'Vue 声明式动效（spring）'],
  ['patriciogonzalezvivo/lygia', 'Lygia GLSL 着色器库'],
  ['d3/d3-interpolate', 'd3 插值/缓动（可手搓替代）']
]
const pick = t => {
  const m = t.match(/(MIT License|Apache License|ISC License|Mozilla Public License|GNU GENERAL PUBLIC LICENSE|BSD 3-Clause|GNU AFFERO)/i)
  return m ? m[1] : '?'
}
const withTimeout = (p, ms) => Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms))])

for (const [r, note] of repos) {
  let lic = '?', file = ''
  for (const n of ['LICENSE', 'LICENSE.md', 'license', 'LICENSE.txt', 'COPYING']) {
    try {
      const res = await withTimeout(fetch('https://raw.githubusercontent.com/' + r + '/HEAD/' + n), 8000)
      if (res.ok) { lic = pick(await res.text()); file = n; break }
    } catch (e) {}
  }
  console.log([r.padEnd(32), ('lic=' + lic).padEnd(20), ('file=' + file).padEnd(14), note].join(' '))
}
