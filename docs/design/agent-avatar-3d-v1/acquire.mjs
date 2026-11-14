#!/usr/bin/env node
/**
 * acquire.mjs —— 可审计的资产/来源抓取器
 *
 * 只做三件事：
 *   1. 读 sources.json（人工审核过的清单），allow=false 的一律不碰
 *   2. 抓 GitHub 仓库元数据（SPDX、实际 commit sha）+ 许可原文快照
 *   3. 对显式列出 url 的资产做下载 + SHA256，落到 inbox/
 *
 * 不做：不放宽 allow、不下载整仓、不给资产"自动判定许可"。
 * 重定向：逐跳校验，每跳都必须落在白名单域名内，最多 3 跳，否则直接报错。
 *
 * 用法：
 *   node acquire.mjs --dry-run        # 只打印计划，不发请求
 *   node acquire.mjs                  # 抓元数据 + 许可快照（默认，轻量）
 *   node acquire.mjs --assets         # 额外抓 urls 里列出的资产文件
 *
 * 产物：
 *   manifest.generated.json           # 机器可读的取证记录
 *   license-snapshots/<id>.LICENSE.txt
 *   inbox/<id>/<file>                 # 仅 --assets
 */
import { mkdir, readFile, writeFile, stat } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { dirname, join, basename } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const args = new Set(process.argv.slice(2))
const DRY = args.has('--dry-run')
const WITH_ASSETS = args.has('--assets')
const TOKEN = process.env.GITHUB_TOKEN || ''
const UA = 'smartops-agent-intake/1.0 (+local audit script)'

const sha256 = buf => createHash('sha256').update(buf).digest('hex')
const log = (...a) => console.log(...a)

async function gh(path) {
  const res = await fetch(`https://api.github.com${path}`, {
    headers: { 'user-agent': UA, accept: 'application/vnd.github+json', ...(TOKEN ? { authorization: `Bearer ${TOKEN}` } : {}) }
  })
  if (!res.ok) throw new Error(`GitHub API ${res.status} ${path}`)
  return res.json()
}

const GITHUB_HOSTS = new Set(['raw.githubusercontent.com', 'github.com', 'objects.githubusercontent.com', 'codeload.github.com'])
const TEXT_HOSTS = GITHUB_HOSTS
const ASSET_HOSTS = GITHUB_HOSTS

/** 手动跟随重定向：每一跳都校验域名白名单，最多 3 跳 */
async function fetchGuarded(url, allowedHosts) {
  let current = url
  for (let hop = 0; hop <= 3; hop++) {
    const res = await fetch(current, { headers: { 'user-agent': UA }, redirect: 'manual' })
    if (res.status >= 300 && res.status < 400) {
      const target = new URL(res.headers.get('location') ?? '', current)
      if (!allowedHosts.has(target.host)) throw new Error(`重定向目标不在白名单：${target.host}`)
      current = target.toString()
      continue
    }
    if (!res.ok) {
      const err = new Error(`HTTP ${res.status} ${current}`)
      err.status = res.status
      throw err
    }
    return res
  }
  throw new Error(`重定向超过 3 跳，拒绝继续：${url}`)
}

async function getText(url) {
  try {
    const res = await fetchGuarded(url, TEXT_HOSTS)
    return await res.text()
  } catch (err) {
    if (err.status === 404) return null
    throw err
  }
}

/** 许可原文可能存在的位置，按顺序试。拆分许可的仓库常见 LICENSE.CODE.md / LICENSE.ASSETS.md */
const LICENSE_CANDIDATES = [
  'LICENSE',
  'LICENSE.md',
  'LICENSE.txt',
  'LICENSE.CODE.md',
  'LICENSE-CODE.md',
  'LICENSE.ASSETS.md',
  'LICENSE-ASSETS.md',
  'COPYING'
]

async function snapshotLicense(repo, defaultBranch, id) {
  for (const name of LICENSE_CANDIDATES) {
    const url = `https://raw.githubusercontent.com/${repo}/${defaultBranch}/${name}`
    const text = await getText(url)
    if (text && text.length > 80) {
      const dir = join(HERE, 'license-snapshots')
      await mkdir(dir, { recursive: true })
      const file = join(dir, `${id}.LICENSE.txt`)
      await writeFile(file, text, 'utf8')
      return { file: `license-snapshots/${id}.LICENSE.txt`, source: url, bytes: Buffer.byteLength(text), sha256: sha256(Buffer.from(text)) }
    }
  }
  return null
}

/** 非仓库型来源：许可写在官方 FAQ / 条款页里，直接把页面原文落盘 */
async function snapshotExternalLicense(id, url) {
  const host = new URL(url).host
  const res = await fetchGuarded(url, new Set([host]))
  const text = await res.text()
  const dir = join(HERE, 'license-snapshots')
  await mkdir(dir, { recursive: true })
  const file = join(dir, `${id}.LICENSE.html`)
  await writeFile(file, text, 'utf8')
  return { file: `license-snapshots/${id}.LICENSE.html`, source: url, bytes: Buffer.byteLength(text), sha256: sha256(Buffer.from(text)) }
}

async function acquireAsset(id, url) {
  const host = new URL(url).host
  if (!ASSET_HOSTS.has(host)) throw new Error(`资产直链不在允许的域名白名单内：${host}`)
  const res = await fetchGuarded(url, ASSET_HOSTS)
  if (!res.ok) throw new Error(`asset ${res.status} ${url}`)
  const buf = Buffer.from(await res.arrayBuffer())
  const dir = join(HERE, 'inbox', id)
  await mkdir(dir, { recursive: true })
  const name = basename(new URL(url).pathname) || 'asset.bin'
  const file = join(dir, name)
  await writeFile(file, buf)
  const digest = sha256(buf)
  const sidecar = [
    `source: ${url}`,
    `fetchedAt: ${new Date().toISOString()}`,
    `bytes: ${buf.length}`,
    `sha256: ${digest}`,
    'license: 见 manifest.generated.json 与 license-snapshots/（本文件只是出处回执）'
  ].join('\n') + '\n'
  await writeFile(join(dir, `${name}.SOURCE.txt`), sidecar, 'utf8')
  return { file: `inbox/${id}/${name}`, source: url, bytes: buf.length, sha256: digest }
}

async function main() {
  const cfg = JSON.parse(await readFile(join(HERE, 'sources.json'), 'utf8'))

  // 清单里出现「有条件使用」的资产名时直接拒绝执行，防止有人手滑把它标成 allow=true
  const FORBIDDEN = /AvatarSample_[ABC]/i
  const offending = cfg.entries.filter(e => e.allow && FORBIDDEN.test(JSON.stringify(e)))
  if (offending.length) {
    console.error(`✗ 清单里有「有条件使用」的资产被标为 allow=true：${offending.map(e => e.id).join(', ')}`)
    process.exitCode = 1
    return
  }

  const manifest = { generatedAt: new Date().toISOString(), checkedAt: cfg.checkedAt, dryRun: DRY, withAssets: WITH_ASSETS, entries: [], summary: {} }
  let allowed = 0, blocked = 0, failed = 0

  for (const e of cfg.entries) {
    const row = { id: e.id, repo: e.repo ?? null, kind: e.kind, declaredSpdx: e.spdx ?? null, allow: Boolean(e.allow), use: e.use ?? '', note: e.note ?? '' }

    if (!e.allow) {
      blocked++
      row.status = 'blocked-by-policy'
      manifest.entries.push(row)
      log(`SKIP   ${e.id.padEnd(16)} ${e.kind}  (allow=false)`)
      continue
    }

    if (DRY) {
      allowed++
      row.status = 'planned'
      manifest.entries.push(row)
      log(`PLAN   ${e.id.padEnd(16)} ${e.kind}  spdx=${e.spdx}`)
      continue
    }

    try {
      if (e.repo) {
        const meta = await gh(`/repos/${e.repo}`)
        row.licenseSpdx = meta.license?.spdx_id ?? null
        row.archived = meta.archived
        row.stars = meta.stargazers_count
        row.defaultBranch = meta.default_branch
        row.commit = (await gh(`/repos/${e.repo}/commits/${meta.default_branch}`)).sha
        row.license = await snapshotLicense(e.repo, meta.default_branch, e.id)
        row.status = 'metadata-captured'
        if (!row.license) row.warnings = ['未找到许可原文，需人工补快照']
        if (e.allow && row.licenseSpdx && e.spdx && !row.licenseSpdx.startsWith(String(e.spdx).split(' ')[0])) {
          row.warnings = [...(row.warnings ?? []), `清单声明 ${e.spdx} 与仓库实际 ${row.licenseSpdx} 不一致`]
        }
      } else if (e.licenseUrl) {
        const manualFile = join(HERE, 'license-snapshots', `${e.id}.LICENSE.txt`)
        try {
          row.license = await snapshotExternalLicense(e.id, e.licenseUrl)
          row.status = 'license-captured'
        } catch (err) {
          // 站点常有 bot 防护（实测 vroid.pixiv.help 对脚本返回 403）→ 接受人工转录快照，但标记 manual
          const hasManual = await stat(manualFile).then(() => true).catch(() => false)
          if (hasManual) {
            const text = await readFile(manualFile, 'utf8')
            row.license = { file: `license-snapshots/${e.id}.LICENSE.txt`, source: e.licenseUrl, bytes: Buffer.byteLength(text), sha256: sha256(Buffer.from(text)), manual: true }
            row.status = 'license-captured-manual'
            row.warnings = [`许可页脚本抓取失败（${err.message}），使用人工转录快照`]
          } else {
            row.status = 'license-missing'
            row.warnings = [`许可页脚本抓取失败（${err.message}），且无人工快照，需补 license-snapshots/${e.id}.LICENSE.txt`]
          }
        }
      } else {
        row.status = 'no-repo'
        row.warnings = ['无 repo 也无 licenseUrl，许可无法取证']
      }

      if (WITH_ASSETS && Array.isArray(e.urls) && e.urls.length) {
        row.assets = []
        for (const url of e.urls) {
          try {
            row.assets.push(await acquireAsset(e.id, url))
          } catch (err) {
            row.assets.push({ source: url, error: String(err.message ?? err) })
            failed++
          }
        }
      }
      allowed++
      manifest.entries.push(row)
      log(`OK     ${e.id.padEnd(22)} ${row.licenseSpdx ?? '?'}  commit=${row.commit ? row.commit.slice(0, 8) : '-'}  license=${row.license ? 'saved' : 'MISSING'}`)
    } catch (err) {
      failed++
      row.status = 'error'
      row.error = String(err.message ?? err)
      manifest.entries.push(row)
      log(`FAIL   ${e.id.padEnd(16)} ${row.error}`)
    }
  }

  manifest.summary = { allowed, blocked, failed, total: cfg.entries.length }

  if (!DRY) {
    await writeFile(join(HERE, 'manifest.generated.json'), JSON.stringify(manifest, null, 2) + '\n', 'utf8')
    log(`\nmanifest.generated.json  allowed=${allowed} blocked=${blocked} failed=${failed}`)
  } else {
    log(`\n[dry-run] allowed=${allowed} blocked=${blocked} —— 未发请求、未写文件`)
  }
}

main().catch(err => { console.error(err); process.exitCode = 1 })
