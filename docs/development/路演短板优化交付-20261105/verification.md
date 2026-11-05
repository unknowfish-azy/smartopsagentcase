# 路演优化任务书交付验证记录

验证时间：2026-11-05T15:50:21+08:00（北京时间）

本轮只整理 Markdown 与交付证据；业务实现、数据库迁移、服务启动、模型评测和产品测试均未执行。

## 产物

- 主文件：`docs/development/路演短板优化与多模型实施任务书-20261105.md`
- SHA256：`38e9ab83f7572c349e0b1219782d09cb6e8ecc02758403ca62930da613dcac96`
- 内容：287行，13张任务卡，含优先级、既有任务映射、实施规格、验收、依赖、回滚边界和可复制接单提示词。
- 差分：`taskbook.patch`，相对不存在的前像新增主文件。
- 回滚：`rollback.ps1`；默认只读预检，显式 `-Apply` 才移除哈希匹配的新增主文件。交付证据目录保留。

## 实际验证结果

| 检查 | 结果 | 证据 |
|---|---|---|
| UTF-8、替换字符、代码围栏配对 | PASS | Python只读校验，exit 0 |
| 13个任务标题唯一及关键语义 | PASS | Python只读校验，exit 0 |
| 15个本地Markdown链接存在 | PASS | Python路径校验，exit 0 |
| 精确差分匹配 | PASS | `git apply --reverse --check -- docs/development/路演短板优化交付-20261105/taskbook.patch`，exit 0；未应用差分 |
| PowerShell语法 | PASS | Language.Parser解析rollback.ps1，0个错误 |
| 实际文件回滚预检 | PASS | 默认DRY_RUN，主文件保留 |
| 副本默认预检 | PASS | exit 0，副本保留 |
| 副本被修改后拒绝回滚 | PASS | 返回非0，副本内容完整保留 |
| 精确副本显式回滚 | PASS | exit 0，仅移除副本任务书 |
| 重复回滚 | PASS | exit 0，NOOP |
| 独立模型只读审阅 | PASS | 核对10项事实纠正、任务依赖和已做/待做边界；反馈“可交接”，未修改文件 |

回滚副本原始命令、stdout/stderr与退出码：`.runtime/taskbook-delivery-qa-20261105-0a40098e/rollback-cases.json`。

上述PASS仅针对这次文档及回滚工具，不代表任务书中的业务方案已经实现、测试通过或已有生产效果。

## 使用

转发主Markdown即可；能访问仓库的接单者再读取参考索引。主文件基于上一轮审阅与本轮源码核对，未重新联网调研GitHub。

回滚预检命令（仓库根目录）：

```powershell
pwsh -NoProfile -File 'docs/development/路演短板优化交付-20261105/rollback.ps1'
```

确认要撤销新增任务书时，在同一命令末尾增加 `-Apply`。若主文件已被后续修改，脚本拒绝删除。副本演练不会改动真实主文件。
