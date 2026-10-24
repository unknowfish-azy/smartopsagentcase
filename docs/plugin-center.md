# 智维插件中心

入口：主菜单「插件中心」，路由 `/plugins`。

本次借鉴可组合插件与依赖管理的组织方式，实现当前浏览器的功能入口工作区，不是 DeepSeek Harness 运行时兼容层。内置八项能力入口；JSON 自定义清单支持名称、分类、描述、版本、现有入口标识与依赖。没有硬编码清单数量上限，实际受浏览器存储容量限制。

支持搜索、分类、仅看已添加、分页、添加/启停/移出工作区、自定义清单导入与删除、依赖校验和浏览器持久化。启停仅影响插件中心内的入口可用性，不改变后端服务，也不禁止从原菜单访问业务功能。添加入口不会自动运行命令、调用模型或连接主机。

清单导入不加载 npm 包、脚本、外部地址或 MCP 服务；远程市场、服务端插件执行器和跨设备同步尚未实现。页面明确展示此边界。默认工作区预置知识、连接、模型三个入口。存储键 `smartops_plugin_workspace_v1`，写入失败保留旧状态；清单错误提供反馈。

## 结构

- `frontend/src/components/ui/radial-orbital-timeline.vue`：参考轨道组件的 Vue 适配，暂停、悬停/键盘暂停、减少动态效果、隐藏标签页暂停，显示六个节点，更多能力在下方分页目录。
- `frontend/src/views/plugins/PluginCenterView.vue`：插件工作区。
- `frontend/src/domain/plugins/{catalog,workspace}.js`：目录、状态转换、清单校验。
- 全局样式沿用 `frontend/src/assets/styles`，轨道动画使用组件局部 CSS，避免覆盖现有动画类。

项目实际是 Vue 3 + JavaScript + Element Plus，未引入 React/shadcn/Tailwind 运行时或复制无法直接运行的 TSX。UI 组件集中于 `frontend/src/components/ui`，图标复用 Element Plus；无新增依赖或远程图片。独立 React + TypeScript + Tailwind/shadcn 初始化步骤见 `docs/model-analytics.md`，不要在此 Vue 项目目录直接初始化 React。

## 验证

`npm test`、`npm run build`、`node test/plugin-center.browser.mjs`。浏览器测试覆盖 1440px/375px、主题、减少动态效果、依赖阻止、非法 JSON、自定义导入、刷新保留、移除删除、分页与手机主菜单。
