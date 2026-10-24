import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

test('visual system exposes semantic elevation and signal tokens', async () => {
 const source = await readFile(new URL('../src/assets/styles/variables.css', import.meta.url), 'utf8')
 assert.match(source, /--smart-surface-ghost:/)
 assert.match(source, /--smart-signal-running:/)
 assert.match(source, /--smart-focus-ring:/)
})

test('dashboard uses the visual system hero metadata and status rail', async () => {
 const source = await readFile(new URL('../src/views/dashboard/DashboardView.vue', import.meta.url), 'utf8')
 assert.match(source, /home-heading__signal/)
 assert.match(source, /home-heading__meta/)
 assert.match(source, /home-orbit-carousel/)
})
