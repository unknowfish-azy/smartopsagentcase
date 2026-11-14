/**
 * SFC 编译检查：对主题二改动的 5 个 .vue 文件跑 parse + compileScript + compileTemplate，
 * 零错误才算通过。比 vite build（分钟级）快两个数量级，改动后即时验证。
 * 用法：node scripts/sfc-check.mjs [文件...]，不带参数则检查本清单。
 */
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const files = process.argv.slice(2).length
  ? process.argv.slice(2)
  : [
    'src/components/common/DecodeText.vue',
    'src/views/sentinel/SentinelDashboardView.vue',
    'src/views/agent/AgentCommandCenterView.vue',
    'src/views/operations/RunHistoryView.vue',
    'src/views/knowledge/KnowledgeCandidateReviewView.vue'
  ]

let failed = 0
for (const file of files) {
  const source = readFileSync(file, 'utf8')
  const { descriptor, errors } = parse(source, { filename: file })
  if (errors.length) {
    failed += 1
    console.error(`FAIL ${file}: parse errors ${errors.map(e => e.message).join('; ')}`)
    continue
  }
  try {
    const script = compileScript(descriptor, { id: file, genDefaultAs: '_sfc_main' })
    const template = compileTemplate({
      source: descriptor.template?.content ?? '',
      filename: file,
      id: file,
      compilerOptions: { bindingMetadata: script.bindings }
    })
    if (template.errors.length) throw new Error(`template: ${template.errors.map(e => e.message).join('; ')}`)
    console.log(`PASS ${file}`)
  } catch (cause) {
    failed += 1
    console.error(`FAIL ${file}: ${cause.message}`)
  }
}
console.log(failed ? `${failed} file(s) failed` : `all ${files.length} SFC compiled clean`)
process.exit(failed ? 1 : 0)
