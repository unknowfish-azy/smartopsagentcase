# Linux Shell 知识资料实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. If the user chooses subagent-driven execution, use `superpowers:subagent-driven-development` instead. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Linux Shell 输入输出与管道内容作为可搜索、可查阅、可前后导航的简易中文知识资料加入 SmartOpsAgent。

**Architecture:** 保留现有本地知识目录及详情页结构。新增 Markdown 知识源和稳定目录条目；复用当前搜索与详情导航，以过滤后的结果作为上一条/下一条的范围，不新增数据库表或通用 Markdown 导入器。

**Tech Stack:** Vue 3、Vite、Node.js 内置 `node:test`、Markdown。

**Spec:** `docs/superpowers/specs/2026-09-23-linux-shell-knowledge-remote-diagnostics-design.md`

## Global Constraints

- 知识源路径为 `knowledge/linux/shell_io_pipeline.md`。
- 用户界面资料使用简易中文，命令和必要技术术语保留原文。
- 首期不新增数据库表或通用 Markdown 导入解析器。
- 相邻文章按当前搜索/筛选结果排序，没有相邻条目时禁用对应箭头。
- 保留开始实施时工作区内已有改动；特别是 `knowledgeCatalog.js` 与相关测试，只增量修改。

## Review Focus

- 中文关键词可能只出现在正文：测试正文关键词可命中条目。
- 过滤结果可能改变相邻顺序：测试上一条/下一条只在当前过滤列表内移动。
- 首尾条目没有相邻项：测试导航返回 `null`，页面禁用对应按钮。
- 搜索结果正文作为纯文本显示：检查页面使用文本插值而不是把知识内容当 HTML 执行。
- 文档和目录摘要可能不一致：测试 Markdown 源与目录记录都包含主要概念和安全提醒。

---

### Task 1: 建立目录条目与检索回归测试

**Files:**
- Modify: `frontend/test/knowledge-catalog.test.mjs`
- Modify: `frontend/src/views/knowledge/knowledgeCatalog.js`

**Interfaces:**
- Produces: 稳定条目 ID `linux-shell-io-pipeline`；条目字段遵守当前 catalog 结构：`id`、`domain`、`platform`、`service`、`type`、`title`、`summary`、`content`、`source`、`section`、`version`、`risk`、`tags`。
- Produces: `knowledgeDomains` 中新增 `linux` 分类，并更新既有顺序测试而不删除用户已经增加的断言。

- [ ] **Step 1: 写失败测试**

```js
test('indexes the Linux Shell I/O knowledge entry and searches its body', () => {
  const results = searchKnowledgeEntries({ query: '标准错误 pipefail' })
  const entry = results.find(item => item.id === 'linux-shell-io-pipeline')

  assert.ok(entry)
  assert.equal(entry.platform, 'Linux')
  assert.match(entry.content, /标准错误/)
  assert.ok(entry.tags.includes('Shell'))
})
```

- [ ] **Step 2: 运行单测确认失败**

Run: `node --test test/knowledge-catalog.test.mjs`（工作目录 `frontend`）  
Expected: FAIL，当前 catalog 没有 `linux-shell-io-pipeline`。

- [ ] **Step 3: 加入最小 catalog 条目**

在 `knowledgeDomains` 中追加简易中文 Linux 分类，在目录中追加 `linux-shell-io-pipeline` 条目，简述覆盖 FD、重定向、管道、`tee`、`xargs`、`wc` 和退出状态；正文首版可先放简短摘要，后续 Task 2 扩充。同步调整域顺序测试，保留文件中与本任务无关的现存断言。

- [ ] **Step 4: 运行单测确认通过**

Run: `node --test test/knowledge-catalog.test.mjs`（工作目录 `frontend`）  
Expected: PASS，正文、标签和平台均能搜索到。

- [ ] **Step 5: 提交本任务**

```bash
git add frontend/test/knowledge-catalog.test.mjs frontend/src/views/knowledge/knowledgeCatalog.js
git commit -m "feat: index Linux shell I/O knowledge"
```

### Task 2: 编写安全准确的 Shell I/O Markdown 资料

**Files:**
- Create: `knowledge/linux/shell_io_pipeline.md`
- Modify: `frontend/test/knowledge-catalog.test.mjs`
- Modify: `frontend/src/views/knowledge/knowledgeCatalog.js`

**Interfaces:**
- Consumes: Task 1 的 `linux-shell-io-pipeline` 目录条目。
- Produces: 可在知识详情页阅读的完整简易中文正文，以及可验证的关键概念。

- [ ] **Step 1: 写资料内容测试**

用 `node:fs` 读取 Markdown，断言包含以下准确要点：`command >file 2>&1`、`command 2>&1 >file` 的区别、`&>` 是 Bash 扩展、`set -o pipefail`、`xargs` 删除风险、换行/空格文件名处理和 `tee`。

- [ ] **Step 2: 运行测试确认失败**

Run: `node --test test/knowledge-catalog.test.mjs`（工作目录 `frontend`）  
Expected: FAIL，知识源文件尚不存在。

- [ ] **Step 3: 编写 Markdown 知识源**

按 FD 与标准流、重定向及顺序、管道与退出码、`tee`、安全使用 `xargs`、`wc`、生产收集示例、常见误区组织章节。明确 `>` 会覆盖文件；用 `find ... -print0 | xargs -0` 处理特殊文件名；不把 `xargs rm -rf` 作为推荐示范；解释 `ps | grep` 自匹配并提供更合适的查询方式。命令示例应说明适用 Shell、权限和风险。

- [ ] **Step 4: 在知识条目中展示同一主题正文**

将资料精简正文登记在 catalog `content` 中，保留 Markdown 文件为可导出的完整知识资源；用测试断言目录正文和 Markdown 均包含标准流、重定向、管道、安全提醒等主题，避免只登记标题而详情为空。

- [ ] **Step 5: 运行资料测试确认通过**

Run: `node --test test/knowledge-catalog.test.mjs`（工作目录 `frontend`）  
Expected: PASS，所有安全和语法要点均存在。

- [ ] **Step 6: 提交本任务**

```bash
git add knowledge/linux/shell_io_pipeline.md frontend/test/knowledge-catalog.test.mjs frontend/src/views/knowledge/knowledgeCatalog.js
git commit -m "docs: add Linux shell I/O pipeline knowledge"
```

### Task 3: 验证详情展示与过滤导航

**Files:**
- Modify: `frontend/test/knowledge-library.test.mjs`
- Modify: `frontend/src/views/knowledge/knowledgeLibrary.js`
- Verify: `frontend/src/views/knowledge/KnowledgeView.vue`

**Interfaces:**
- Consumes: 现有 `knowledgeEntryView(entryId, entries)`。
- Produces: 基于传入结果列表的前后条目；边界返回 `null`，页面禁用对应按钮。

- [ ] **Step 1: 补充过滤列表与边界测试**

测试只有 Shell 条目时前后均为 `null`；测试传入 `[a, shell, c]` 时 Shell 的 `previous.id === 'a'` 且 `next.id === 'c'`；未知 ID 返回 `null`。不改写已有知识域顺序测试或用户新增断言。

- [ ] **Step 2: 运行单测确认行为**

Run: `node --test test/knowledge-library.test.mjs`（工作目录 `frontend`）  
Expected: PASS；如失败，只修复详情导航本身，不重排全局 catalog。

- [ ] **Step 3: 检查详情正文安全呈现和控件状态**

确认 `KnowledgeView.vue` 以 Vue 文本插值展示 `content`，保留 `white-space: pre-wrap`，上一条/下一条按钮由 `disabled` 状态控制；只在测试发现缺口时做最小修改。

- [ ] **Step 4: 运行知识相关测试和构建**

Run: `npm test` 和 `npm run build`（工作目录 `frontend`）  
Expected: 知识目录、资料详情和现有前端构建均通过。

- [ ] **Step 5: 提交本任务**

```bash
git add frontend/test/knowledge-library.test.mjs frontend/src/views/knowledge/knowledgeLibrary.js frontend/src/views/knowledge/KnowledgeView.vue
git commit -m "test: verify filtered knowledge navigation"
```
