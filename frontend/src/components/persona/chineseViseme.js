/**
 * 中文拼音韵母 → 口型（viseme）映射表。
 *
 * 五个 viseme 与 VRM 预设、2D 嘴型共用：aa / oh / ih / ou / ee。
 * 第六类"闭口"不单开通道：闭口由振幅归零表达，鼻音韵尾用 nasal 标记，
 * 渲染端可以让口型多保持一帧，避免 an/ang 被读成纯 a。
 *
 * 输入允许带声调符号、数字声调、ü/u:、y/w 拼写和 j/q/x 后的省略 ü。
 */
const INITIALS = ['zh', 'ch', 'sh', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l', 'g', 'k', 'h', 'j', 'q', 'x', 'r', 'z', 'c', 's']

/** y/w 开头的拼写先还原成韵母本体，避免把 y 当声母后剩不下东西 */
const ZERO_INITIAL = {
  yi: 'i', yin: 'in', ying: 'ing',
  ya: 'ia', yao: 'iao', ye: 'ie', you: 'iou', yan: 'ian', yang: 'iang', yong: 'iong',
  yu: 'v', yue: 've', yuan: 'van', yun: 'vn',
  wu: 'u', wa: 'ua', wo: 'uo', wai: 'uai', wei: 'ei', wan: 'uan', wen: 'uen', wang: 'uang', weng: 'ueng'
}

/** 韵母 → viseme；键按最长前缀匹配使用 */
const FINAL_VISEME = {
  a: 'aa', ia: 'aa', ua: 'aa',
  ai: 'aa', uai: 'aa',
  ao: 'aa', iao: 'aa',
  an: 'aa', ian: 'aa', uan: 'aa', van: 'aa',
  ang: 'aa', iang: 'aa', uang: 'aa',
  o: 'oh', uo: 'oh',
  ou: 'ou', iou: 'ou', iu: 'ou', ong: 'ou', iong: 'ou',
  u: 'ou', v: 'ou', ve: 'ou', vn: 'ou',
  e: 'ee', ei: 'ee', uei: 'ee', ui: 'ee',
  en: 'ee', uen: 'ee', un: 'ee', eng: 'ee', ueng: 'ee', er: 'ee',
  i: 'ih', in: 'ih', ing: 'ih'
}

const NASAL_FINALS = new Set([
  'an', 'ian', 'uan', 'van', 'ang', 'iang', 'uang',
  'en', 'uen', 'un', 'vn', 'eng', 'ueng', 'in', 'ing', 'ong', 'iong'
])

const FINALS = Object.keys(FINAL_VISEME).sort((a, b) => b.length - a.length)

/** 去声调/数字/分隔符，并把 ü 统一成 v（含带调 ü，NFD 前先替换否则会退化成 u） */
export function stripTone(pinyin) {
  return String(pinyin ?? '')
    .trim()
    .toLowerCase()
    .replace(/ü/g, 'v')
    .replace(/[ǖǘǚǜ]/g, 'v')
    .replace(/u:/g, 'v')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[1-5]/g, '')
    .replace(/[^a-zv]/g, '')
}

/** 取韵母：处理零声母拼写、j/q/x 后的省略 ü，再去掉声母 */
export function finalOf(pinyin) {
  let text = stripTone(pinyin)
  if (!text) return ''

  if (ZERO_INITIAL[text]) return ZERO_INITIAL[text]

  // ju / jue / juan / jun 实际是 jü / jüe / jüan / jün
  if (/^[jqx]u/.test(text)) text = `${text[0]}v${text.slice(2)}`

  for (const initial of INITIALS) {
    if (text.startsWith(initial)) {
      return text.slice(initial.length)
    }
  }
  return text
}

/**
 * 拼音 → { final, viseme, nasal }。
 * 无法识别的韵母按首个元音兜底，保证一定返回一个口型，不让嘴停住。
 */
export function visemeFromPinyin(pinyin) {
  const final = finalOf(pinyin)
  if (!final) return null

  let viseme = FINAL_VISEME[final]
  if (!viseme) {
    const matched = FINALS.find((item) => final.endsWith(item))
    viseme = matched ? FINAL_VISEME[matched] : ''
  }
  if (!viseme) {
    const vowel = final.match(/[aoeiuv]/)?.[0] ?? 'a'
    viseme = { a: 'aa', o: 'oh', e: 'ee', i: 'ih', u: 'ou', v: 'ou' }[vowel]
  }

  return {
    final,
    viseme,
    nasal: NASAL_FINALS.has(final)
  }
}
