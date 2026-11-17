# 知识蒸馏图谱使用指南

> 面向「知识蒸馏图谱」（`/atlas`，菜单 **KNOWLEDGE ATLAS / 知识蒸馏图谱**）的使用者文档。
> 该功能把 `knowledge/reference/ops-knowledge-rag` 语料库（Docker 运维课、云原生公开课、
> AI Infra 训练营、独立专题等 60 篇课程笔记）蒸馏成一张可探索的知识地图。
>
> 定位：**离线知识资产的地图**，不是实时监控面——页面所有数字来自蒸馏快照，
> 页头会标注快照生成时间。
>
> 截图统一存放于 `docs/images/atlas/`，标注「待补」的位置保存对应截图后删除占位块。

---

> 📷 **截图占位**：`docs/images/atlas/atlas-overview.png`（待补）
> 内容：`/atlas` 整页全景（1440 宽），包含页头声明、统计条、图谱主图、课程卡片与底部两栏。

---

## 一、页面导览

打开 `/atlas` 后从上到下有四个区块：

| 区块 | 内容 | 怎么用 |
| --- | --- | --- |
| 统计条 | 课程 / 文档 / 章节标题 / 代码块 / 字符量 | 一眼看语料库体量 |
| 知识图谱主图 | 内环课程枢纽 + 外环文档节点的旭日式布局 | 悬停、点击、聚焦（见下节） |
| 课程卡片侧栏 | 每个课程的文档数、体量、Top 命令 | 点击卡片聚焦该课程 |
| 底部两栏 | 高频命令 Top12 条形图 + 蒸馏说明 | 了解语料里最常出现的命令与快照来源 |

> 📷 **截图占位**：`docs/images/atlas/atlas-bottom-panels.png`（待补）
> 内容：页面底部两栏——高频命令 Top12 条形图与「这份快照怎么来的」说明卡。

## 二、图谱交互

- **悬停文档节点**：节点旁显示文档标题（超长截断），连线同色高亮；
- **点击文档节点**：主图下方展开详情面板——文档路径、体量、代码块数、
  蒸馏出的主题标签（1-3 级标题，最多 8 条）与命令清单（`docker ×12` 这种形式）；
- **点击课程枢纽 / 课程卡片**：聚焦该课程，图谱其余部分变暗；再次点击或点「显示全部」恢复；
- **布局是确定的**：课程按体量降序顺时针排扇区，文档在扇区内等分角度，
  节点大小 ∝ 字符量的平方根。没有物理模拟、没有动画循环——刷新后位置不变，方便对照。

> 📷 **截图占位**：`docs/images/atlas/atlas-graph-hover.png`（待补）
> 内容：悬停某个文档节点的瞬间——节点旁显示标题标签、连线同色高亮。

> 📷 **截图占位**：`docs/images/atlas/atlas-doc-detail.png`（待补）
> 内容：点击文档节点后，主图下方展开的详情面板（路径、主题标签、命令清单）。

> 📷 **截图占位**：`docs/images/atlas/atlas-course-focus.png`（待补）
> 内容：点击课程卡片聚焦后的状态——其余课程扇区变暗，顶部出现「已聚焦」提示与「显示全部」按钮。

## 三、蒸馏模型（快照里有什么）

蒸馏器输出 `frontend/src/views/atlas/atlasDistilled.json`，schemaVersion 1：

```
snapshot
├── schemaVersion / generatedAt / sourceRoot   ← 页头声明的来源与时间
├── totals                                     ← 统计条数据（courses/documents/headings/codeBlocks/chars）
├── courses[]                                  ← 课程：label、documentCount、chars、codeBlocks、topCommands(6)
├── documents[]                                ← 文档：id、courseId、title、path、chars、
│                                                 headingsCount、codeBlocks、commands(≤8)、headings(≤8)
└── topCommands[]                              ← 全库命令 Top24（条形图取前 12）
```

蒸馏规则要点：

1. **课程归属**：语料库一级目录；根目录散文件归入「独立专题」；
2. **主题骨架**：每篇取 1-3 级 markdown 标题（最多 8 条）；
3. **命令统计**：只统计 fenced code block 内、命中白名单的命令行；
   `sudo systemctl …` 记到 `systemctl` 头上；白名单外的 token 一律不收（宁漏勿错）；
4. **确定性**：文件按路径排序、id 稳定，同一语料两次蒸馏结果完全一致（有测试钉死）。

## 四、重新蒸馏

语料库更新后，在 `frontend` 目录执行：

```bash
npm run atlas:distill
```

会重新扫描 `knowledge/reference/ops-knowledge-rag` 并覆盖快照文件，
刷新页面即看到新的图谱。语料新增了课程目录时，在
`scripts/atlas/distill-atlas.mjs` 的 `COURSE_LABELS` 里补一条展示名（否则显示目录原名）。

## 五、边界与诚实声明

- 快照是**只读蒸馏**：蒸馏过程只读文件、统计结构，**不执行语料里的任何命令**；
- 页面不把快照冒充实时数据：页头标注生成时间，说明卡注明来源与 schema；
- 语料库目录缺失时蒸馏器直接报错；快照缺失时页面显示引导空态，不编造演示数据；
- 图谱布局无动画循环，天然满足项目 G5 降级要求（窄屏 340px 高、低视觉档无影响）。

> 📷 **截图占位**：`docs/images/atlas/atlas-empty-state.png`（可选）
> 内容：快照缺失时的引导空态（提示执行 `npm run atlas:distill`）——仅当希望文档覆盖异常场景时补。

## 六、相关代码与测试

| 内容 | 位置 |
| --- | --- |
| 蒸馏器（导出可测纯函数 + CLI） | `scripts/atlas/distill-atlas.mjs` |
| 蒸馏快照 | `frontend/src/views/atlas/atlasDistilled.json` |
| 图谱页面（canvas + 统计 + 命令条） | `frontend/src/views/atlas/KnowledgeAtlasView.vue` |
| 蒸馏器单元测试（7 项，含真实语料健康检查） | `frontend/test/atlas-distill.test.mjs` |
| 菜单注册 | `frontend/src/navigation/personalSystemNavigation.js`（`atlas` 组） |
| 路由 / 元数据 | `frontend/src/router/index.js`（`/atlas`）、`routeMetadata.js`（`KnowledgeAtlas`） |
