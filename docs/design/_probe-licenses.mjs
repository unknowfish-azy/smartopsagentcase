const repos = [
  'rive-app/rive-wasm', 'juliangarnier/anime', 'motiondivision/motion', 'airbnb/lottie-web',
  'metafizzy/zdog', 'oframe/ogl', 'pixijs/pixijs', 'statelyai/xstate',
  'theatre-js/theatre', 'vueuse/motion', 'patriciogonzalezvivo/lygia', 'greensock/GSAP'
]
const pick = t => {
  const m = t.match(/(MIT License|Apache License|ISC License|Mozilla Public License|GNU GENERAL PUBLIC LICENSE|BSD 3-Clause|GNU AFFERO)/i)
  return m ? m[1] : '?'
}
for (const r of repos) {
  let lic = '?', stars = '?', pushed = '?'
  try {
    const h = await (await fetch('https://github.com/' + r, { headers: { 'user-agent': 'dsh' } })).text()
    const s = h.match(/id="repo-stars-counter-star"[^>]*title="([\d,]+)"/)
    if (s) stars = s[1]
    const t = h.match(/<relative-time[^>]*datetime="([^"]+)"/)
    if (t) pushed = t[1].slice(0, 10)
  } catch (e) { stars = 'html-fail' }
  for (const n of ['LICENSE', 'LICENSE.md', 'license', 'LICENSE.txt', 'COPYING']) {
    try {
      const res = await fetch('https://raw.githubusercontent.com/' + r + '/HEAD/' + n)
      if (res.ok) { lic = pick(await res.text()); break }
    } catch (e) {}
  }
  console.log(r.padEnd(32), ('lic=' + lic).padEnd(24), ('stars=' + stars).padEnd(14), 'pushed=' + pushed)
}
