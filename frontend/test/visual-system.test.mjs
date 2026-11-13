import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

test('visual system exposes semantic elevation and signal tokens', async () => {
 const source = await readFile(new URL('../src/assets/styles/variables.css', import.meta.url), 'utf8')
 assert.match(source, /--smart-surface-ghost:/)
 assert.match(source, /--smart-signal-running:/)
 assert.match(source, /--smart-focus-ring:/)
})

test('dashboard uses Bento enterprise layout (T19, 2026-11-13 D1 裁决变更为采纳 Bento)', async () => {
 const source = await readFile(new URL('../src/views/dashboard/DashboardView.vue', import.meta.url), 'utf8')
 assert.match(source, /DashboardBento/)
 const bentoSource = await readFile(new URL('../src/components/dashboard/DashboardBento.vue', import.meta.url), 'utf8')
 assert.match(bentoSource, /bento-briefing/)          /* §3.5 AI 情境简报层 */
 assert.match(bentoSource, /bento-kpi/)                /* KPI 带 */
 assert.match(bentoSource, /bento-status/)            /* 态势总览 */
 assert.match(bentoSource, /bento-activity/)          /* 活动流 */
 assert.match(bentoSource, /--ds-surface-raised/)     /* 新令牌 */
})
