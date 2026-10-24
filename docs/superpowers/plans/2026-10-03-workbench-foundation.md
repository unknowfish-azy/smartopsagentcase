# Workbench Foundation Implementation Plan

> 执行方式：使用 executing-plans 按任务完成，先写失败测试再实现，不委派子代理。

**Goal:** 完成三工作台第一阶段可信基础，不开放生产写操作。

**Architecture:** 复用现有 Spring Boot 只读服务、Vue 路由及本地知识索引。知识快照由当前内容源确定性生成，前端和 Mini 使用一致的条目身份。

**Tech Stack:** Vue 3、Node 内置测试、Java 17、JUnit、Playwright；不增加依赖。

**Spec:** `docs/superpowers/specs/2026-10-03-workbench-foundation-design.md`

## Global Constraints

- 不更改真实账号、数据库、Harbor 地址/凭据或诊断白名单。
- 不新增生产写操作、自动轮询、外部模型调用或通用 Shell 入口。
- 保留现有工作区，所有文件使用 apply_patch 修改。

## Review Focus

- 配置存在但上游拒绝认证：不得显示为连接健康。
- 嵌套仓库名和非法路径：正确编码合法路径，拒绝路径穿越。
- 快速切换目标：晚返回的数据不得污染新目标。
- 资料未核验或索引缺失：不得声称已审核或 AI 完整可用。
- 环境意图与真实会话不一致：显示上下文提示，仍需人工核对执行目标。

## Task 1: Harbor 可信状态与制品浏览

- [x] 为 `HarborCatalogServiceTest.java` 增加状态、制品路径/字段、错误分类与脱敏测试并验证失败。
- [x] 扩展 `HarborCatalogService.java`、`HarborCatalogController.java`，保留旧接口兼容。
- [x] 扩展 `HarborBrowser.vue` 和前端状态辅助模块，覆盖分页、筛选、过期和请求隔离。
- [x] 运行后端定向测试及前端状态测试。

## Task 2: 统一知识模型与基础检索

- [x] 新建规范化/多词排名测试，验证失败。
- [x] 增加共享知识投影、确定性快照生成和一致性检查；接入目录与 Mini。
- [x] 更新知识页显示来源、未核验状态、命中依据和真实条目数。
- [x] 运行目录回归、快照一致性和 Mini 引用测试。

## Task 3: 云原生上下文与单层详情

- [x] 编写上下文白名单、URL 参数和隔离行为测试并验证失败。
- [x] 添加环境意图表单与路由恢复，替换嵌套弹窗、通用伪命令及重复 Markdown 渲染。
- [x] 工具入口显示目标提示但不自动执行；浅深色及小屏统一。
- [x] 运行上下文测试和既有工具回归。

## Task 4: 综合验收与文档

- [x] 浏览器模拟服务验收 375/1440px 浅深色、失败与切换竞态。
- [x] 运行前端测试、构建与相关后端测试，记录原有警告和未完成项。
- [x] 更新操作文档及验收记录；明确真实服务验证边界。
