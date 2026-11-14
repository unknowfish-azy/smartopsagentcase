# agent-avatar-3d-v1 · 智能体 3D 数字人

给 SmartOpsAgent 的 Agent 加一个 3D 数字人形象：合规取资产、逆向取方法、按项目约束集成。

| 文件 | 是什么 | 给谁看 |
| --- | --- | --- |
| [PLAN.md](PLAN.md) | 全案：合规门、选型（含许可核查结论）、爬取管线、逆向管线、集成规格、性能预算、验收清单、红线 | 你 / 评审 |
| [PROMPT.md](PROMPT.md) | 可直接发给 Trae 或其他执行模型的提示词，5 阶段 + 自检 + 交付格式 | 执行模型 |
| [sources.json](sources.json) | 人工审核过的来源清单，`allow` 开关就是权限 | 维护者 |
| [INTAKE.md](INTAKE.md) | 阶段 1 结论：逐条许可判定、分级、阻塞项与解除条件 | 评审 / 执行模型 |
| [acquire.mjs](acquire.mjs) | 可审计抓取脚本：只抓清单里 `allow=true` 的，留许可原文 + commit sha + SHA256 | 维护者 / CI |
| [manifest.generated.json](manifest.generated.json) | 上一次真实运行的取证记录 | 审计 |
| [license-snapshots/](license-snapshots/) | 抓到的许可原文（证据，不要删） | 审计 |

## 跑一次

```bash
node acquire.mjs --dry-run     # 只看计划
node acquire.mjs               # 抓元数据 + 许可原文快照
node acquire.mjs --assets      # 额外下载 urls 里显式列出的资产（域名白名单）
```

设 `GITHUB_TOKEN` 可避开匿名限流。脚本**不会**下载整仓、不会自动判定许可、拒绝跟随到非白名单域名。

## 本次运行的实际发现（不是理论风险）

`mpfb2` 的 GitHub 元数据报 `NOASSERTION`，但仓库里是**拆分许可**：`LICENSE.md` + `LICENSE.CODE.md`（GPLv3）+ `LICENSE.ASSETS.md`（CC0）。脚本按「清单声明 vs 仓库实际」比出了这条不一致并写进 manifest 的 `warnings`——这就是为什么清单要人工写、脚本只负责对账。

结论不变：MPFB2 的**资产 CC0、导出物归使用者**，是自建形象最干净的路径；但不要把「GitHub 上显示的 license 徽章」当作授权依据。

## 底线（一句话）

仓库里只允许出现 CC0 / MIT / Apache-2.0 的资产；`AvatarSample_A/B/C` 这类「保留版权 + 使用条款」的模型一律不落地。形象自己造，方法可以学。
