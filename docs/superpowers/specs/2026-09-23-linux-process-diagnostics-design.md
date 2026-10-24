# Linux Process Diagnostics Design

## Goal

把 Linux 进程管理知识加入 SmartOpsAgent 知识中心，并将现有“进程管理器”工具优化为知识驱动的只读诊断工作区。

## Scope

本阶段只处理本地知识、前端索引、诊断规则和命令预览。系统不读取本机或 SSH 的真实进程数据，不执行命令，不执行 `kill`、`renice`、重启或配置修改。

## Architecture

`knowledge/linux/process_management.md` 是完整知识源；`knowledgeCatalog.js` 提供现有离线搜索和详情页面使用的索引；`processDiagnostics.js` 提供纯数据诊断规则；`ToolsView.vue` 根据 `/tools/processes` 展示规则、证据、只读命令预览、风险和验证步骤。知识详情通过路由查询参数打开工具，并保留现有上一条/下一条资料导航。

## Diagnostic Rules

至少提供四种只读场景：服务器卡顿、CPU 高使用率、D 状态进程、Z 状态进程。每种场景包含症状、需要确认的证据、只读命令预览、风险说明、验证方式和升级条件。

## Safety Boundary

命令预览仅供学习和人工复制。Bridge 离线或在线都不触发执行；工具页不显示“执行”按钮，不调用 Operations Bridge，不写入远程系统。

## Acceptance Criteria

1. 搜索 `LINUX-PROCESS-001`、`D state`、`zombie`、`ps aux` 能找到进程管理知识。
2. 进程工具能展示四类诊断场景，并明确证据优先和风险。
3. 知识详情可打开进程工具，并能返回知识详情。
4. 现有知识详情的上一条/下一条、域筛选、既有工具导航不回归。
5. 只读安全边界有自动化测试覆盖。
