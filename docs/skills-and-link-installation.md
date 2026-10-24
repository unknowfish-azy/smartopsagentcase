# Skill 与链接安装

主菜单 `/skills` 提供 SKILL.md 安装、启停、卸载、搜索、来源查看和任务目标设置。安装后默认停用。Agent 控制中心展示目标和已启用指令；模型接入页测试弹窗可勾选“应用已启用 Skill 和任务目标”，通过已有 systemPrompt 字段发送。不会自动启动后台任务或修改历史 Inspector 记录。

插件中心导入弹窗也支持链接读取，读取后预览 JSON，再确认导入。插件仍使用 SmartOps 清单格式和现有 entry 白名单，不支持任意 npm 包或第三方运行时插件格式。

## 支持链接

- GitHub blob 文件：转换为 raw.githubusercontent.com 原始文件地址。
- GitHub tree 目录：追加 SKILL.md 或 smartops-plugin.json。
- GitHub 仓库根：使用 HEAD 引用读取根目录对应文件。
- 其他公开 HTTPS 原始文件：需要源站允许浏览器跨域读取。

不携带 cookies、登录凭据或密钥，不跟随重定向。私有仓库、跨域受限站点、包含斜杠的复杂分支引用，可提供明确的原始文件地址或手动粘贴文件内容。读取限时 15 秒；Skill 下载上限 64 KiB，正文解析上限 60,000 字符；插件下载上限 20,000 字节。HTML 页面与错误响应不能作为安装文件。

Skill 解析 YAML frontmatter 的 name、description 和 Markdown 指令正文，使用 yaml 包处理多行描述。YAML 别名被限制，不执行脚本。只安装当前 Markdown 文件，不下载 scripts、references 等附属资源；页面提示依赖此类资源的技能需补充上下文。

安装数据在当前浏览器 localStorage：smartops_skills_v1 与 smartops_plugin_workspace_v1。来源保留为纯文本；手动修改远程内容会标注。相同 Skill 名称拒绝静默覆盖。已启用指令总长限制为 48,000 字符。模型调用仍遵循现有后端内部鉴权；没有将内部令牌放入前端。模拟测试不代表实际服务商调用已验证。

## 检查

- `npm.cmd test`：133 项测试，包括链接转换、非法地址、大小限制、YAML、重复安装与指令组装。
- `npm.cmd run build`：构建。
- `node test/skills.browser.mjs`：1440px / 375px 模拟网络验证 GitHub Skill/插件导入、持久化、目标、Agent 指令和模型请求负载。
