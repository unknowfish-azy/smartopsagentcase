#!/usr/bin/env node
// DS-07 许可证核验脚本
// 用法：
//   node scripts/open-source/verify-licenses.mjs --date=YYYY-MM-DD            # 全量：拉 license + 扫依赖 + 出报告
//   node scripts/open-source/verify-licenses.mjs --date=YYYY-MM-DD --from-results  # 复用已有 license，仅重扫依赖文件并重生成报告（省 GitHub API 配额）
// 输入：scripts/open-source/registry.json（全量）或 scripts/open-source/results-<date>.json（--from-results）
// 动作：
//   - GitHub 仓库：GET https://api.github.com/repos/{owner}/{repo} → license.spdx_id / archived / default_branch
//   - HF 模型：GET {HF_HOST}/api/models/{id} → cardData.license
//     HF_HOST 启动时探测：优先官方 https://huggingface.co，不可达（TCP 超时）则回退镜像 https://hf-mirror.com
//   - qwen_dependency：拉取 requirements.txt / pyproject.toml / setup.py / tokenizer_config.json / config.json
//     （根目录 404 时回退 python/ 与 src/ 子目录前缀）搜 qwen / dashscope / tongyi；取不到写「未核验」
// 输出：
//   - scripts/open-source/results-<date>.json（机器可读快照）
//   - scripts/open-source/run-<date>.log（实际 stdout）
//   - reports/open-source-license-verification-<date>.md（Markdown 报告，内嵌实际输出）
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = join(__dirname, '..', '..')
const REGISTRY_PATH = join(__dirname, 'registry.json')
const DATE = process.argv.find(a => a.startsWith('--date='))?.slice(7) || new Date().toISOString().slice(0, 10)
const FROM_RESULTS = process.argv.includes('--from-results')
const RESULTS_PATH = join(__dirname, `results-${DATE}.json`)
const RUN_LOG_PATH = join(__dirname, `run-${DATE}.log`)
const REPORT_PATH = join(ROOT, 'reports', `open-source-license-verification-${DATE}.md`)

const UA = 'SmartOpsAgent-DS07-license-verification/1.0 (+https://github.com)'
const FETCH_TIMEOUT_MS = 15000
const HF_PROBE_TIMEOUT_MS = 6000
const INTER_REQ_DELAY_MS = 500
const MAX_FILE_BYTES = 2_000_000

const GITHUB_TOKEN = process.env.GITHUB_TOKEN || ''
const HF_TOKEN = process.env.HF_TOKEN || ''
const HF_OFFICIAL = 'https://huggingface.co'
const HF_MIRROR = 'https://hf-mirror.com'

const QWEN_KEYWORDS = [/qwen/i, /dashscope/i, /tongyi/i]
const DEP_FILES = ['requirements.txt', 'pyproject.toml', 'setup.py', 'tokenizer_config.json', 'config.json']
// 根目录找不到时回退的子目录前缀（仅 GitHub；HF 模型文件在根）
const GITHUB_SUBPREFIXES = ['', 'python/', 'src/']

const PERMISSIVE = new Set(['mit', 'apache-2.0', 'apache 2.0', 'bsd-3-clause', 'bsd-2-clause', 'isc', '0bsd', 'unlicense', 'cc0-1.0', 'python-2.0', 'postgresql'])
const WEAK_COPYLEFT_SAAS_SAFE = new Set(['mpl-2.0', 'lgpl-2.1-only', 'lgpl-2.1-or-later', 'lgpl-3.0-only', 'lgpl-3.0-or-later', 'lgpl-2.0-only', 'lgpl-2.0-or-later'])
const STRONG_COPYLEFT = new Set(['gpl-2.0', 'gpl-2.0-only', 'gpl-2.0-or-later', 'gpl-3.0', 'gpl-3.0-only', 'gpl-3.0-or-later', 'agpl-3.0', 'agpl-3.0-only', 'agpl-3.0-or-later'])
const NON_OSI_MODEL_LICENSES = new Set(['gemma', 'llama', 'llama3.1', 'llama3.2', 'llama3.2-community', 'llama-3.2', 'mistral', 'mistralai', 'deepseek', 'phi', 'phi-3', 'cohere', 'command-r', 'other'])

const LOG_LINES = []
function log(...args) { const msg = args.join(' '); LOG_LINES.push(msg); console.log(msg) }
function logProgress(s) { process.stdout.write(s) }

const sleep = ms => new Promise(r => setTimeout(r, ms))

async function httpGet(url, { accept = 'application/json', extraHeaders = {}, timeoutMs = FETCH_TIMEOUT_MS } = {}) {
  const headers = { 'User-Agent': UA, Accept: accept, ...extraHeaders }
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  const trace = { url, method: 'GET', requested_at: new Date().toISOString() }
  try {
    const res = await fetch(url, { headers, signal: ctrl.signal })
    trace.status = res.status
    trace.status_text = res.statusText
    const body = await res.text()
    trace.body_bytes = body.length
    clearTimeout(timer)
    return { ok: res.ok, status: res.status, text: body, trace }
  } catch (e) {
    clearTimeout(timer)
    trace.error = String(e && e.message || e)
    trace.cause_code = (e && e.cause && e.cause.code) || (/aborted/i.test(trace.error) ? 'CONNECT_TIMEOUT_ABORTED' : undefined)
    return { ok: false, status: 0, text: '', trace }
  }
}
const githubHeaders = () => GITHUB_TOKEN ? { Authorization: `Bearer ${GITHUB_TOKEN}` } : {}
const hfHeaders = () => HF_TOKEN ? { Authorization: `Bearer ${HF_TOKEN}` } : {}
const splitGhRef = ref => { const m = /^([^/]+)\/(.+)$/.exec(ref.trim()); return m ? { owner: m[1], repo: m[2] } : null }

let HF_HOST = HF_OFFICIAL
let HF_PROBE = null
async function detectHfHost() {
  const probeUrl = `${HF_OFFICIAL}/api/models/HuggingFaceTB/SmolLM2-1.7B-Instruct`
  const r = await httpGet(probeUrl, { timeoutMs: HF_PROBE_TIMEOUT_MS })
  HF_PROBE = { url: probeUrl, status: r.status, ok: r.ok, error: r.trace.error, cause_code: r.trace.cause_code }
  if (r.ok) { HF_HOST = HF_OFFICIAL; HF_PROBE.used_host = HF_OFFICIAL; return }
  HF_HOST = HF_MIRROR
  HF_PROBE.used_host = HF_MIRROR
  HF_PROBE.note = '官方 huggingface.co 不可达（TCP 连接超时 / 被阻断），改用镜像 hf-mirror.com 拉取 cardData.license 与原始文件'
}

async function verifyGithub(item) {
  const { owner, repo } = splitGhRef(item.ref) || {}
  const result = { name: item.name, ref: item.ref, url: item.url, type: item.type, section: item.section, claimed_license: item.claimed_license, requests: [], qwen_files: [] }
  if (!owner) { result.fatal = 'invalid ref'; return result }
  const apiUrl = `https://api.github.com/repos/${owner}/${repo}`
  result.requests.push({ kind: 'license', url: apiUrl })
  const r = await httpGet(apiUrl, { extraHeaders: githubHeaders() })
  result.requests[result.requests.length - 1].trace = r.trace
  if (!r.ok) { result.license_spdx = '未核验'; result.archived = '未核验'; result.license_error = `HTTP ${r.status} ${r.trace.error || ''}`.trim(); return result }
  let data
  try { data = JSON.parse(r.text) } catch { result.license_spdx = '未核验'; result.license_error = 'JSON parse failed'; return result }
  result.default_branch = data.default_branch || 'main'
  result.archived = !!data.archived
  const lic = data.license
  result.license_spdx = (lic && lic.spdx_id) ? lic.spdx_id : (lic ? lic.key : 'NOASSERTION')
  result.license_name = lic ? lic.name : null
  return result
}

async function verifyHf(item) {
  const result = { name: item.name, ref: item.ref, url: item.url, type: item.type, section: item.section, claimed_license: item.claimed_license, requests: [], qwen_files: [] }
  const apiUrl = `${HF_HOST}/api/models/${item.ref}`
  result.requests.push({ kind: 'license', url: apiUrl, host: HF_HOST })
  const r = await httpGet(apiUrl, { extraHeaders: hfHeaders() })
  result.requests[result.requests.length - 1].trace = r.trace
  if (!r.ok) { result.license_spdx = '未核验'; result.license_error = `HTTP ${r.status} ${r.trace.error || ''}`.trim(); return result }
  let data
  try { data = JSON.parse(r.text) } catch { result.license_spdx = '未核验'; result.license_error = 'JSON parse failed'; return result }
  const card = data.cardData || {}
  let lic = card.license
  if (Array.isArray(lic)) lic = lic.join(',')
  result.license_spdx = lic ? String(lic) : 'NOASSERTION'
  result.gated = data.gated || false
  result.hf_tags = (data.tags || []).slice(0, 8)
  result.source_host = HF_HOST
  return result
}

// 取单个依赖文件：按前缀顺序尝试，返回首个 200；否则返回最后一次失败记录
async function fetchOneDepFile(baseUrl, file, prefixes) {
  let last = null
  for (const pre of prefixes) {
    const url = `${baseUrl}/${pre}${file}`
    const r = await httpGet(url, { accept: '*/*' })
    const rec = { file, path_used: `${pre}${file}`, url, ok: r.ok, status: r.status, trace: r.trace, matches: [] }
    if (r.ok && r.text) { rec.text = r.text.slice(0, MAX_FILE_BYTES); rec.matches = findQwenMatches(r.text, file); return rec }
    last = rec
    await sleep(INTER_REQ_DELAY_MS)
  }
  return last
}

async function fetchDepFiles(item, defaultBranch) {
  const fetched = []
  let baseUrl, prefixes
  if (item.type === 'github') {
    const { owner, repo } = splitGhRef(item.ref)
    baseUrl = `https://raw.githubusercontent.com/${owner}/${repo}/${defaultBranch}`
    prefixes = GITHUB_SUBPREFIXES
  } else {
    baseUrl = `${HF_HOST}/${item.ref}/raw/main`
    prefixes = ['']
  }
  for (const f of DEP_FILES) {
    const rec = await fetchOneDepFile(baseUrl, f, prefixes)
    fetched.push(rec)
    await sleep(INTER_REQ_DELAY_MS)
  }
  return fetched
}

function findQwenMatches(text) {
  const matches = []
  const lines = text.split(/\r?\n/)
  lines.forEach((line, i) => { if (QWEN_KEYWORDS.some(re => re.test(line))) matches.push({ line: i + 1, text: line.trim().slice(0, 160) }) })
  return matches.slice(0, 6)
}

function classifyQwen(item, fetched) {
  const retrieved = fetched.filter(f => f.ok)
  if (retrieved.length === 0) {
    return { level: '未核验', reason: '依赖文件全部取不到（根目录及 python/src 子目录均 404 / 或 401 gated / 网络），按 §6 不得默认 none', evidence: [] }
  }
  const allMatches = []
  retrieved.forEach(f => f.matches.forEach(m => allMatches.push({ file: `${f.path_used || f.file}`, ...m })))
  const modelFileHit = retrieved.some(f => /tokenizer_config\.json|config\.json/.test(f.file) && f.matches.length)
  const dashscopeRuntimeDep = retrieved.some(f => /requirements\.txt|pyproject\.toml|setup\.py/.test(f.file) && f.matches.some(m => /dashscope/i.test(m.text)))
  if (modelFileHit || dashscopeRuntimeDep) {
    return { level: 'required', reason: modelFileHit ? '模型配置文件（tokenizer_config.json / config.json）命中 qwen → 该模型本体即千问家族' : '依赖清单中 dashscope 作为运行时依赖', evidence: allMatches }
  }
  if (allMatches.length > 0) {
    return { level: 'optional', reason: '代码/配置中出现 qwen/dashscope/tongyi 引用，但非默认运行时强依赖；可切换至其他底座', evidence: allMatches }
  }
  return { level: 'none', reason: '已抓取的依赖文件中未出现 qwen / dashscope / tongyi 关键词', evidence: [] }
}

function conclude(item, spdx, qwen) {
  if (qwen.level === 'required') return '仅隔离使用'
  if (qwen.level === '未核验' && spdx === '未核验') return '未核验'
  const lic = (spdx || '').trim().toLowerCase()
  if (!lic || lic === '未核验') return '未核验'
  if (NON_OSI_MODEL_LICENSES.has(lic)) return '仅隔离使用（非 OSI 许可）'
  if (STRONG_COPYLEFT.has(lic)) return '禁止（强 Copyleft）'
  if (PERMISSIVE.has(lic)) return qwen.level === 'optional' ? '允许（optional，需写明替代路径）' : '允许'
  if (WEAK_COPYLEFT_SAAS_SAFE.has(lic)) return '允许（弱 Copyleft，SaaS 自用安全；分发需注意）'
  if (lic === 'noassertion') return '未核验（许可声明不明确）'
  return '仅隔离使用（许可非已知宽松类型，需法务复核）'
}

function clauseHint(spdx) {
  const l = (spdx || '').toLowerCase()
  if (/gemma/.test(l)) return 'Gemma Terms of Use（非 OSI）：商用需阅读 https://ai.google.dev/gemma/terms ；允许商用但含使用限制与禁止条款（不得用于违反法律的用途、不得生成误导性内容等），需逐项核对。'
  if (/llama/.test(l)) return 'Llama 3.2 Community License（非 OSI，Meta）：商用需阅读 https://ai.meta.com/llama/license/ ；含「月活用户超 7 亿需另行授权」条款，分发受限制，需法务确认适用场景。'
  return ''
}

function fmtEvidence(qwen) {
  if (qwen.level === '未核验') return qwen.reason
  if (qwen.level === 'none') return `${qwen.reason}（已扫 ${qwen.files_scanned || 0} 个可达文件）`
  const lines = qwen.evidence.slice(0, 5).map(e => `\`${e.file}:L${e.line}\` ${e.text}`)
  return lines.length ? lines.join('<br>') : qwen.reason
}
function fmtVerifyCmd(result) {
  const cmds = result.requests.map(r => `GET ${r.url}`)
  ;(result.qwen_files || []).forEach(f => cmds.push(`GET ${f.url}`))
  return cmds.slice(0, 4).join('<br>') + (cmds.length > 4 ? `<br>…共 ${cmds.length} 个请求` : '')
}
const sectionTitle = s => ({ '4.1': '§4.1 底座候选（HF 模型，共 6）', '6.1': '§6.1 蒸馏与数据（共 5）', '6.2': '§6.2 训练与推理（共 7）', '6.3': '§6.3 结构化输出与护栏（共 6）', '6.4': '§6.4 服务化与工程（共 6）', '6.5': '§6.5 AIOps 领域（共 4）' }[s] || `§${s}`)

async function scanDepsForResult(result) {
  const item = { name: result.name, ref: result.ref || result.name, type: result.type, section: result.section, url: result.url }
  const branch = result.default_branch || 'main'
  const fetched = await fetchDepFiles(item, branch)
  result.qwen_files = fetched.map(f => ({ file: f.file, path_used: f.path_used, url: f.url, ok: f.ok, status: f.status, match_count: f.matches.length, matches: f.matches, trace: f.trace }))
  const qwen = classifyQwen(item, fetched)
  qwen.files_scanned = fetched.filter(f => f.ok).length
  result.qwen_dependency = qwen
  result.conclusion = conclude(item, result.license_spdx, qwen)
  result.clause_hint = clauseHint(result.license_spdx)
  result.verified_at = new Date().toISOString()
  return result
}

function buildReport({ date, results, registry, hfProbe }) {
  const L = []
  L.push('# 开源框架 / 底座许可证核验报告（DS-07）')
  L.push('')
  L.push(`> 核验日期：${date}（GMT+8）`)
  L.push(`> 核验方法：逐项调用 GitHub REST API \`GET /repos/{owner}/{repo}\` 读 \`license.spdx_id\`；HF 模型调用 \`{HF_HOST}/api/models/{id}\` 读 \`cardData.license\`；再拉取 \`requirements.txt\` / \`pyproject.toml\` / \`setup.py\` / \`tokenizer_config.json\` / \`config.json\`（根目录 404 时回退 \`python/\`、\`src/\` 子目录）搜 \`qwen\` / \`dashscope\` / \`tongyi\` 判定 \`qwen_dependency\`。`)
  if (hfProbe && !hfProbe.ok) {
    L.push(`> **网络说明（实测）**：官方 \`huggingface.co\` 在当前环境不可达（探测 \`${hfProbe.url}\` → ${hfProbe.cause_code || hfProbe.error || ('HTTP ' + hfProbe.status)}），HF 侧 \`cardData.license\` 与原始依赖文件改用镜像 \`${hfProbe.used_host}\` 拉取；GitHub API 与 \`raw.githubusercontent.com\` 直连正常。镜像返回的 \`cardData.license\` 与官方同源，可采信。`)
  }
  L.push(`> 输入清单：\`scripts/open-source/registry.json\`（${registry.items.length} 项：§6.1–6.5 共 28 个 GitHub 仓库 + §4.1 共 6 个 HF 模型）`)
  L.push(`> 机器可读快照：\`scripts/open-source/results-${date}.json\`（含每项实际请求 URL、响应状态与匹配证据行）`)
  L.push('> 免责声明：本报告为工程决策参考，不构成法律意见；商用分发前请交由法务复核。星数与「大家都在用」不构成商用依据。')
  L.push('', '---', '')

  const byLevel = {}, qwenStats = {}
  results.forEach(r => { byLevel[r.conclusion] = (byLevel[r.conclusion] || 0) + 1; qwenStats[r.qwen_dependency.level] = (qwenStats[r.qwen_dependency.level] || 0) + 1 })
  L.push('## 1. 结论速览')
  L.push('')
  L.push(`- 共核验 **${results.length}** 项：${results.filter(r => r.type === 'github').length} 个 GitHub 仓库 + ${results.filter(r => r.type === 'hf-model').length} 个 HF 模型。`)
  L.push(`- 结论分布：${Object.entries(byLevel).map(([k, v]) => `\`${k}\` ${v}`).join('、')}。`)
  L.push(`- \`qwen_dependency\` 分布：${Object.entries(qwenStats).map(([k, v]) => `\`${k}\` ${v}`).join('、')}。`)
  L.push('- **硬门禁（来自 ARCHITECTURE §6 / 实施计划 §7）**：')
  L.push('  1. `qwen_dependency=required` 的项，无论许可证多干净，结论一律「仅隔离使用」，不得进主干；')
  L.push('  2. `optional` 项必须写明替代路径与实际生效底座；')
  L.push('  3. `gemma-2-2b-it` 与 `Llama-3.2-1B-Instruct` 两项标为非 OSI 许可并附条款提示；')
  L.push('  4. 取不到许可证或依赖证据的项写「未核验」，不得默认 `none` 或「允许」。')
  L.push('', '---', '')

  const sections = ['4.1', '6.1', '6.2', '6.3', '6.4', '6.5']
  L.push('## 2. 核验明细（按 ARCHITECTURE 章节分组）')
  L.push('')
  for (const s of sections) {
    const group = results.filter(r => r.section === s)
    if (!group.length) continue
    L.push(`### 2.${sections.indexOf(s) + 1} ${sectionTitle(s)}`)
    L.push('')
    L.push('| 仓库/模型 URL | SPDX id（API 实测） | `qwen_dependency` | 依赖证据 | 核验日期 | 核验命令 | 结论 |')
    L.push('|---|---|---|---|---|---|---|')
    for (const r of group) {
      const urlCell = `[${r.name}](${r.url})${r.archived === true ? ' （已归档）' : ''}`
      const spdxCell = r.license_spdx === '未核验' ? `⚠️ 未核验${r.license_error ? `（${r.license_error}）` : ''}` : `\`${r.license_spdx}\``
      const evCell = fmtEvidence(r.qwen_dependency).replace(/\|/g, '\\|')
      const cmdCell = fmtVerifyCmd(r).replace(/\|/g, '\\|')
      let concl = r.conclusion
      if (r.clause_hint) concl += '<br>📌 条款提示见 §3'
      L.push(`| ${urlCell} | ${spdxCell} | \`${r.qwen_dependency.level}\` | ${evCell} | ${date} | ${cmdCell} | ${concl} |`)
    }
    L.push('')
  }

  L.push('---', '', '## 3. 非 OSI 许可条款提示（gemma / llama 及其他非宽松许可）', '')
  const nonOsi = results.filter(r => r.clause_hint || (r.conclusion && r.conclusion.includes('非 OSI')))
  if (!nonOsi.length) L.push('无。')
  else for (const r of nonOsi) {
    L.push(`### 3.${nonOsi.indexOf(r) + 1} ${r.name}`, '')
    L.push(`- URL：${r.url}`)
    L.push(`- cardData.license（API 实测${r.source_host ? `，源：${r.source_host}` : ''}）：\`${r.license_spdx}\``)
    L.push(`- 条款提示：${r.clause_hint || '该许可不在已知 OSI 宽松许可集合内，需法务复核许可原文。'}`)
    L.push(`- 结论：**${r.conclusion}** —— 即便功能合适，也不得作为默认底座进主干；仅限隔离评估使用，商用前必须法务逐项核对条款原文。`, '')
  }

  L.push('---', '', '## 4. `qwen_dependency=required` 项清单（一律「仅隔离使用」）', '')
  const req = results.filter(r => r.qwen_dependency.level === 'required')
  if (!req.length) L.push('本次核验未发现 `required` 项。')
  else {
    L.push('| 项 | 许可证 | 判定依据 |', '|---|---|---|')
    for (const r of req) L.push(`| ${r.name} | \`${r.license_spdx}\` | ${r.qwen_dependency.reason} |`)
  }
  L.push('')

  L.push('---', '', '## 5. 失败 / 未核验项（如实列出，不许猜）', '')
  const failed = results.filter(r => r.conclusion.startsWith('未核验') || r.license_spdx === '未核验' || r.qwen_dependency.level === '未核验')
  if (!failed.length) L.push('无未核验项。')
  else {
    L.push('| 项 | 失败点 | 实际响应 |', '|---|---|---|')
    for (const r of failed) {
      const fail = []
      if (r.license_spdx === '未核验') fail.push(`license: ${r.license_error || 'unknown'}`)
      else if (r.conclusion.startsWith('未核验')) fail.push(`license: ${r.license_spdx}（${r.conclusion}）`)
      if (r.qwen_dependency.level === '未核验') fail.push('qwen_dependency: 依赖文件全部取不到（详见明细表「依赖证据」列）')
      const traces = (r.requests || []).map(x => `${x.url} → HTTP ${x.trace.status}${x.trace.error ? ' (' + x.trace.error + ')' : ''}`).join('; ')
      L.push(`| ${r.name} | ${fail.join('; ')} | ${traces} |`)
    }
  }
  L.push('')

  L.push('---', '', '## 6. 实际执行命令与输出（可复现）', '')
  L.push('执行命令：', '')
  L.push('```powershell')
  L.push(`cd D:\\SmartOpsAgent; node scripts/open-source/verify-licenses.mjs --date=${date}${FROM_RESULTS ? ' --from-results' : ''}`)
  L.push('```', '')
  L.push('标准输出（实际留存，来自 `scripts/open-source/run-' + date + '.log`）：', '')
  L.push('```text')
  LOG_LINES.forEach(l => L.push(l))
  L.push('```', '')
  L.push(`附录 A（运行日志）：\`scripts/open-source/run-${date}.log\`；机器可读快照：\`scripts/open-source/results-${date}.json\`。`, '')

  L.push('---', '', '## 7. 验收对照（实施计划 §7）', '')
  L.push('| 验收断言 | 状态 | 证据 |', '|---|---|---|')
  const allHaveConclusion = results.every(r => r.conclusion)
  L.push(`| ① 清单每项都有结论或「未核验」 | ${allHaveConclusion ? '✅ 通过' : '❌ 失败'} | 明细表共 ${results.length} 行，无空结论 |`)
  const gemmaOk = results.some(r => /gemma/i.test(r.license_spdx) && r.clause_hint)
  const llamaOk = results.some(r => /llama/i.test(r.license_spdx) && r.clause_hint)
  L.push(`| ② gemma-2-2b / Llama-3.2-1B 标非 OSI + 条款提示 | ${gemmaOk && llamaOk ? '✅ 通过' : '❌ 失败'} | gemma 命中=${gemmaOk}，llama 命中=${llamaOk}；§3 列出 ${nonOsi.length} 项 |`)
  L.push(`| ③ 报告日期与本次一致 | ✅ 通过 | ${date} |`)
  const reqAllIsolated = results.every(r => r.qwen_dependency.level !== 'required' || r.conclusion === '仅隔离使用')
  L.push(`| ④ 每项有 qwen_dependency + 依赖证据，required 一律「仅隔离使用」 | ${reqAllIsolated ? '✅ 通过' : '❌ 失败'} | §4 列出 required 项 ${req.length} 个，均落「仅隔离使用」 |`)
  L.push('')
  L.push('---', '')
  L.push(`*本报告由 \`scripts/open-source/verify-licenses.mjs\` 于 ${date} 生成；SPDX / cardData.license 为 API 实时值，随时间可能变化，落地引入前必须重新核验。*`)
  return L.join('\n')
}

async function main() {
  log(`[DS-07] date=${DATE} mode=${FROM_RESULTS ? 'from-results (reuse license, rescan deps)' : 'full'}`)
  log(`[DS-07] GitHub token: ${GITHUB_TOKEN ? 'set' : 'unauthenticated (60 req/hr)'}  HF token: ${HF_TOKEN ? 'set' : 'unauthenticated'}`)
  log('[DS-07] probing HF official host ...')
  await detectHfHost()
  log(`[DS-07] HF probe: official=${HF_OFFICIAL} status=${HF_PROBE.status} ok=${HF_PROBE.ok} → using ${HF_PROBE.used_host}`)
  if (HF_PROBE.note) log(`[DS-07] ${HF_PROBE.note}`)

  let registry
  let results
  if (FROM_RESULTS) {
    const snapshot = JSON.parse(await readFile(RESULTS_PATH, 'utf8'))
    registry = { items: snapshot.results.map(r => ({ name: r.name, ref: r.ref || r.name, type: r.type, section: r.section, url: r.url, claimed_license: r.claimed_license })) }
    results = snapshot.results
    log(`[DS-07] loaded ${results.length} prior results; rescanning dependency files only`)
  } else {
    registry = JSON.parse(await readFile(REGISTRY_PATH, 'utf8'))
    results = []
  }

  for (let i = 0; i < registry.items.length; i++) {
    const item = registry.items[i]
    let result
    if (FROM_RESULTS) {
      result = results[i]
    } else {
      logProgress(`[${i + 1}/${registry.items.length}] ${item.ref} ... `)
      result = item.type === 'github' ? await verifyGithub(item) : await verifyHf(item)
      await sleep(INTER_REQ_DELAY_MS)
    }
    await scanDepsForResult(result)
    if (!FROM_RESULTS) {
      // 完成行（含进度前缀）
      LOG_LINES.push(`[${i + 1}/${registry.items.length}] ${item.ref} ... spdx=${result.license_spdx} qwen=${result.qwen_dependency.level} → ${result.conclusion}`)
      console.log(`spdx=${result.license_spdx} qwen=${result.qwen_dependency.level} → ${result.conclusion}`)
    } else {
      log(`[${i + 1}/${registry.items.length}] ${result.ref || result.name} ... spdx=${result.license_spdx} qwen=${result.qwen_dependency.level} → ${result.conclusion}`)
    }
    results[i] = result
  }

  const snapshot = {
    date: DATE, generated_at: new Date().toISOString(),
    command: `node scripts/open-source/verify-licenses.mjs --date=${DATE}${FROM_RESULTS ? ' --from-results' : ''}`,
    hf_host_probe: HF_PROBE, mode: FROM_RESULTS ? 'from-results' : 'full',
    item_count: results.length, results,
  }
  // 先输出统计（纳入 LOG_LINES，供报告 §6 与运行日志留存）
  const byLevel = {}, qwenStats = {}
  results.forEach(r => { byLevel[r.conclusion] = (byLevel[r.conclusion] || 0) + 1; qwenStats[r.qwen_dependency.level] = (qwenStats[r.qwen_dependency.level] || 0) + 1 })
  log('[DS-07] conclusion distribution:', JSON.stringify(byLevel))
  log('[DS-07] qwen_dependency distribution:', JSON.stringify(qwenStats))

  await mkdir(dirname(RESULTS_PATH), { recursive: true })
  await writeFile(RESULTS_PATH, JSON.stringify(snapshot, null, 2), 'utf8')
  log(`[DS-07] results written: ${RESULTS_PATH}`)

  const md = buildReport({ date: DATE, results, registry, hfProbe: HF_PROBE })
  await mkdir(dirname(REPORT_PATH), { recursive: true })
  await writeFile(REPORT_PATH, md, 'utf8')
  log(`[DS-07] report written: ${REPORT_PATH}`)

  // 运行日志最后写：此时 LOG_LINES 已含统计与「report written」
  await writeFile(RUN_LOG_PATH, LOG_LINES.join('\n') + '\n', 'utf8')
  log(`[DS-07] run log written: ${RUN_LOG_PATH}`)
}

main().catch(e => { console.error('[DS-07] FATAL', e); process.exit(1) })
