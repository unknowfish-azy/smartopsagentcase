/* 证据完整性横幅（EvidenceBanner）的纯函数逻辑。
 * DESIGN §8.3 — 四个后端标志位任意一个为 true 就显示横幅；合并成一条琥珀色横幅。
 */

const FLAG_MAP = Object.freeze([
  { key: 'permissionDenied',
    text: '权限不足，部分检查没有执行',
    why: '换用带该能力的账号或管理员目标；这不代表目标服务不健康' },
  { key: 'dataMissing',
    text: '部分数据缺失，结论基于不完整的数据',
    why: '补采集或放宽采集范围' },
  { key: 'unverified',
    text: '未验证：结果只反映采集到的部分',
    why: '看待结论时保留余地' },
  { key: 'truncated',
    text: '输出被截断（超过 256 KB 上限）',
    why: '缩小查询范围后重跑' }
])

export function bannerFlags(evidence) {
  if (!evidence || typeof evidence !== 'object') return []
  return FLAG_MAP.filter(f => Boolean(evidence[f.key]))
}

export function hasIncompleteEvidence(evidence) {
  return bannerFlags(evidence).length > 0
}

export const EVIDENCE_DISCLAIMER = '这不代表目标服务不健康'
