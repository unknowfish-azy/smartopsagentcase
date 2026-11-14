# INTAKE · 合规与选型结论（阶段 1）

> 核查日期：**2026-11-14**　取证脚本：`acquire.mjs`　取证记录：`manifest.generated.json`（generatedAt `2026-11-14T01:47:30Z`）
> 本文回答一个问题：**哪些来源能用、以什么身份用、哪些一律不碰**。不通过本表，不写业务代码。

## 0. 结论先行

1. **形象走「CC0 占位先跑通，自建作为 v2」**。理由不是省钱，是解耦：加载/表情/口型/降级四条链路的正确性，与「脸好不好看」无关；形象单独迭代，避免返工锁死。
2. **方法走「读 MIT 源码，自己重写」**：`three-vrm`（运行时依赖）+ `ChatVRM`（只读参考）。代码思路可学，示例模型资产一律不落地。
3. **占位模型已落地并取证**：`vroid-sendagaya-shino`（CC0，15,074,328 B，sha256 `1e177c1a…`）已下到 `inbox/`，许可快照为**人工转录**（官方 FAQ 页对脚本返回 403），并已在 manifest 里标 `manual: true`。阶段 2 可以开工；但这个模型超体积与 draw call 预算，只当占位，阶段 2 结束后必须替换。

## 1. 分级标准（引用 PLAN §3）

| 级别 | 条件 | 允许的动作 |
| --- | --- | --- |
| **A** | MIT / Apache-2.0 / CC0 / CC-BY（保留署名） | 可进仓库；须记录 SPDX + 核查日期 + 原始 URL |
| **B** | GPL / AGPL / LGPL | 只作**离线工具**；不进前端运行时、不与前端代码链接 |
| **C** | 保留所有权利 / 无许可证 / 条款含糊 | **禁止落地**；方案里可引用 URL，不下载资产 |

## 2. 逐条结论

证据列 = `manifest.generated.json` 中的 `commit` + `license.sha256` 前 16 位；完整值见 manifest 与 `license-snapshots/`。

| # | 来源 | 类型 | 清单声明 SPDX | 仓库实际 | 固定 commit | 许可快照 sha256(前16) | 级别 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `pixiv/three-vrm` | reference-code / **runtime** | MIT | MIT | `3caf7a21` | `279ec82987aec7e7` | A | ✅ 可进 `package.json`（`@pixiv/three-vrm`）；唯一允许的 3D 运行时依赖 |
| 2 | `pixiv/ChatVRM` | reference-code | MIT | MIT | `b542aa00` | `8f2598cf184ec846` | A | ✅ 只读源码；仓库已归档，无维护风险但有「不更新」风险 |
| 3 | `sh-akira/VirtualMotionCapture` | reference-code | MIT | MIT | `8508e712` | `ed6388e44b121de9` | A | ✅ 仅作技术参考；**本项目默认不启用摄像头**，启用需显式授权 |
| 4 | `makehumancommunity/mpfb2` | offline-tool | `GPL-3.0-only AND CC0-1.0` | `NOASSERTION` | `9de0707f` | `5cefb60680cb9efd` | **B** | ✅ 只在本地/CI 的 Blender 里用；产物（.vrm）属 A 级可入库，addon 代码本身不得进仓库 |
| 5 | `makehumancommunity/makehuman` | rejected | `NOASSERTION` | — | — | — | C | ❌ 不落地。代码 AGPL 系、资产边界靠 MPFB2 的 LICENSE 才说清，没有必要绕 |
| 6 | `microsoft/Microsoft-Rocketbox` | rejected | MIT | — | — | — | C | ❌ 不落地。仓库 2022 年归档；MIT 覆盖的是脚本工具，模型资产授权需逐项确认，不适合当基础形象 |
| 7 | `vrm-c/vrm-specification` | reference-doc | 无 | — | — | — | C（仅阅读） | ❌ 不落地代码/示例资产。只读规范理解 VRM 1.0 结构 |
| 8 | `vroid-sendagaya-shino`（Sendagaya Shino） | model-asset | `CC0-1.0` | 非仓库来源，靠 `licenseUrl` 取证 | 直链 SHA256 固定 | `e8d31f57c92c6d7f`（人工转录） | A（带条件） | ✅ 占位可用：官方 FAQ 明确 CC0 + 文件内 VRM meta 自证 `licenseName=CC0`；仅作占位，超体积预算（见 §4） |

## 3. mpfb2 的 `NOASSERTION` 怎么解释（容易被误判成 C 级）

GitHub API 报 `NOASSERTION`，不是「无许可」，而是许可被拆成多份文件、识别器给不出单一 SPDX。快照实测（`license-snapshots/mpfb2.LICENSE.txt`）：

- 第 60–62 行：assets 以 **CC0 1.0 Universal** 发布；
- 第 69–79 行：明确 **output 归使用者**，MakeHuman 团队不作任何主张；
- 代码部分为 GPLv3（`LICENSE.CODE.md`）。

因此判定：**B 级工具 + A 级产物**。这也是本轮唯一一个「清单声明与 API 报值不一致」的条目，脚本已把它写进 manifest 的 `warnings`，属预期行为，不是漏审。

> 旁证：把来源从 `cfcohen/mpfb2`（fork，2022-11 停更、0 star）改指正仓 `makehumancommunity/mpfb2`（701 star）后，`LICENSE.md` 的 sha256 与旧快照完全一致 → 两仓许可原文同源，结论不因换仓而变。

## 4. 占位模型：已解除，附条件

| 项 | 现状 |
| --- | --- |
| 直链 | ✅ `https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/beta/Sendagaya_Shino.vrm` |
| 许可 | ✅ 官方 FAQ 明确 CC0；文件内 VRM meta 自证 `licenseName=CC0`、`allowedUserName=Everyone`、`commercialUssageName=Allow`、`title=Sendagaya Shino` |
| 哈希 | ✅ sha256 `1e177c1a7b14f783a9c48395831db8616260d3bddd4154cb2784b779adca49b5`，15,074,328 B，与预检一致；`inbox/…/Sendagaya_Shino.vrm.SOURCE.txt` 为出处回执 |
| 许可快照 | ⚠️ **人工转录**（`license-snapshots/vroid-sendagaya-shino.LICENSE.txt`）：官方 FAQ 页对脚本请求返回 403，manifest 标 `status=license-captured-manual` + `manual: true`，不冒充自动抓取 |
| 入库策略 | ✅ `docs/design/agent-avatar-3d-v1/inbox/` 已进 `.gitignore`：证据靠 manifest + 直链 + SHA256 复现，不把 15MB 提交进库 |

**已知预算例外（必须显式记账，不能静默接受）**：15MB（预算 ≤6MB）、17 材质（draw call 预算 ≤12）、VRM 0.x（加载后需 `VRMUtils.rotateVRM0`）。

处置：阶段 2 可以带着它打通「加载 → 站立 → 眨眼/呼吸 → 释放」；**阶段 5 的性能数字不得用占位模型的数据交差**，必须在替换后的模型（自建 VRM 1.0 或压缩后的成品）上重测。

## 5. 阶段 1 自检

- [x] 每个 `allow=true` 来源都有 SPDX、核查日期、许可快照与 SHA256（模型类另加直链 SHA256）
- [x] `allow=false` 的三条（makehuman / rocketbox / vrm-spec）一条请求都没发（dry-run 输出 `SKIP`）
- [x] 表内没有任何「许可未确认」的资产被标为可用；唯一人工转录的快照已标 `manual: true`
- [x] `AvatarSample_A/B/C` 在全部交付物里只以禁止性表述出现
- [x] 运行时依赖只有 `@pixiv/three-vrm`（MIT），`three@^0.186.0` 为既有依赖

## 6. 资产入库前的硬门槛（阶段 2 起生效）

1. 每个模型目录须有 `<name>.LICENSE.txt` + `<name>.SOURCE.txt`（原始 URL、抓取时间、SHA256）。
2. `manifest.generated.json` 里的 SHA256 与实际文件一致；不一致即视为未取证。
3. glTF/VRM 结构校验通过（`gltf-validator`），且不含外部贴图引用。
4. 体积超预算（单模型 ≤ 6MB）先压缩再入库，不把「未压缩」写进仓库。
