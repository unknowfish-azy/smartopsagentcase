// Ansible 自动化知识包：对应 RH294（Red Hat System Administration III）课程目标，
// 并参考 Ansible 官方文档（docs.ansible.com）与 ansible/ansible-examples 仓库。
// 教学示例中的密码、密钥与生产主机不得直接复用。
export const ansibleProvenance = Object.freeze({
  source: '开源参考资料：Ansible 官方文档、RH294 课程目标、ansible/ansible-examples',
  references: ['Ansible Core Documentation', 'Ansible Galaxy', 'RH294 Red Hat System Administration III'],
  verification: '未在本项目真实主机上逐条执行，使用前需在实验环境验证'
})

const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: 'ansible.' + id,
  domain: 'linux', platform: 'Ansible Core / ansible-navigator', service: 'ansible',
  type: 'ANSIBLE AUTOMATION', title, section, summary, content,
  tags: ['Ansible', '自动化', 'YAML', ...tags],
  source: ansibleProvenance.source,
  version: 'ansible-core 2.14+ / RHEL 9 教学场景', risk, executionAllowed: false
})

export const ansibleEntries = [
  entry('architecture', 'Ansible 架构、无代理模型与幂等性', '01 / 基础',
    '控制节点通过 SSH 推送模块到受管节点；无 Agent、幂等和声明式 YAML 是三个基本前提。',
    '[SRC] Ansible 由控制节点（control node）和受管节点（managed node）组成，使用 SSH 和 Python 执行模块，不需要在受管节点常驻 Agent。Playbook 是 YAML 描述的期望状态，任务按顺序执行。\n[VERIFY] 幂等性指同一任务重复执行不重复产生副作用；changed 表示该次执行发生了变更，并不等于失败。\n[OPS] 排查自动化问题时先区分控制节点环境、连接与认证、受管节点 Python、模块参数和任务结果，不要把所有失败都归因于 Playbook 写错。默认先 --check 与 --diff 观察，再决定是否真实执行。',
    ['control node', 'managed node', 'SSH', 'Agentless', 'idempotency', 'changed']),
  entry('inventory', 'Inventory 分组、主机变量与匹配模式', '02 / Inventory',
    'Inventory 定义受管节点与分组；主机变量、组变量和匹配模式决定任务作用范围。',
    '[SRC] 静态 inventory 可用 INI 或 YAML，主机可写在 [web] 等组下；group_vars/ 与 host_vars/ 按组名、主机名加载变量。ansible-inventory --graph 可查看分组结构，--host <host> 查看变量。\n[OPS] 执行前用 ansible-inventory -i <inventory> --graph 核对目标，避免把测试机混入生产组。临时覆盖用 --limit <pattern> 限制范围；children、vars、ansible_host、ansible_port 等字段要确认缩进和层级。动态 inventory 脚本必须可执行并输出 JSON，先单独运行验证。',
    ['inventory', 'INI', 'YAML', 'group_vars', 'host_vars', 'ansible-inventory', '--limit'], 'APPROVAL_REQUIRED'),
  entry('configuration', 'ansible.cfg 查找顺序与连接参数', '03 / 配置',
    '配置查找顺序、remote_user、forks 和 SSH 参数决定 Ansible 如何连接与并发。',
    '[SRC] ansible.cfg 可按当前目录、ANSIBLE_CONFIG、~/.ansible.cfg、/etc/ansible/ansible.cfg 的顺序查找；常见项为 inventory、remote_user、host_key_checking、forks、timeout、collections_paths、stdout_callback。\n[OPS] 先用 ansible --version 查看实际加载的配置文件，再确认 ansible.cfg、环境变量和命令行参数谁生效。host_key_checking=False 会降低中间人防护，只适合受控实验环境；生产优先预置 known_hosts。并发 forks 过大可能压垮目标或触发连接限制，应结合窗口和回滚评估。',
    ['ansible.cfg', 'ANSIBLE_CONFIG', 'remote_user', 'forks', 'host_key_checking', 'timeout'], 'APPROVAL_REQUIRED'),
  entry('ad-hoc', 'Ad-hoc 命令、模块选择与 command/shell 边界', '04 / Ad-hoc',
    '临时任务用 ansible -m 调用模块；command 不经过 Shell，shell 才解析管道与重定向。',
    '[SRC] 示例：ansible all -m ping；ansible web -m command -a "uptime"；ansible web -m shell -a "df -h | tail -1"；使用 -b 提权、-u 指定用户、--limit 限制主机。\n[VERIFY] command 模块不执行 Shell 元字符，管道、重定向、变量展开需要 shell 模块；shell 模块风险更高，必须确认参数来源可信。\n[OPS] 只读巡检优先 command 或专用模块；执行变更前先 --check（模块支持时）并核对目标清单。禁止把未脱敏的密码放在 -a 参数中，命令历史与日志可能保留明文。',
    ['ansible', '-m ping', 'command', 'shell', '-b', 'become'], 'APPROVAL_REQUIRED'),
  entry('playbook', 'Playbook 结构、语法检查与执行边界', '05 / Playbook',
    'Playbook 由 plays、tasks 和模块组成；执行前做语法检查、目标核对和试运行。',
    '[SRC] 典型结构为 hosts、become、vars、tasks，每个 task 指定 name 与模块参数。常用命令：ansible-playbook --syntax-check site.yml；--check 只预演；--diff 显示文件差异；--limit 限制主机；--tags 选择任务。\n[OPS] name 必须可读，便于审计与定位失败任务。先 --syntax-check，再 --check --diff，确认影响范围后执行。生产执行要保留运行输出、目标清单、变更前后差异和回滚方式。不要用 serial 一次性推到全部主机，除非已验证失败处理。',
    ['playbook', 'plays', 'tasks', '--syntax-check', '--check', '--diff', '--tags'], 'APPROVAL_REQUIRED'),
  entry('facts-variables', '变量优先级、Facts、register 与 when', '06 / 变量与条件',
    '变量来源有优先级；Facts 是受管节点采集事实，register 保存任务结果，when 决定是否执行。',
    '[SRC] 常见变量来源包括 role defaults、inventory group_vars/host_vars、play vars、task vars、命令行 -e；优先级大致从低到高，命令行 extra vars 最高。gather_facts 采集 ansible_facts（如 ansible_os_family、ansible_default_ipv4）。register 将结果存入变量，可用 result.rc、result.stdout、result.changed 判断。\n[OPS] 变量同名时先确认来源，避免“改了没生效”。when 条件应基于 Facts 或 register 结果，不要依赖未定义变量；访问嵌套字段使用默认值过滤，避免 undefined 中断。敏感变量用 Vault 或外部凭据管理，不写入明文 group_vars。',
    ['variables precedence', 'gather_facts', 'ansible_facts', 'register', 'when', 'extra vars']),
  entry('loops-handlers', '循环、Handlers、block/rescue/always', '07 / 流程控制',
    '循环展开重复任务，Handlers 只在 changed 时触发，block/rescue/always 提供失败处理。',
    '[SRC] loop 遍历列表，item 为当前元素；notify 触发 handler，handler 默认在 play 结束时执行，多次 notify 只执行一次。block 包裹任务，rescue 捕获失败，always 始终执行。\n[VERIFY] handler 未被触发通常是没有 changed，或被 failed 任务中断；可用 --force-handlers 强制执行，但要评估副作用。\n[OPS] 失败处理要明确“失败后停在哪、是否回滚、是否继续其他主机”。max_fail_percentage、any_errors_fatal、ignore_errors 都会改变失败语义，使用前写清理由。清理动作放 always，但不能掩盖原始失败。',
    ['loop', 'with_items', 'handlers', 'notify', 'block', 'rescue', 'always', 'ignore_errors'], 'APPROVAL_REQUIRED'),
  entry('templates', 'Jinja2 模板、template 模块与校验', '08 / 模板',
    'template 模块渲染 Jinja2 模板到目标主机；变量、过滤器和 validate 决定安全落地。',
    '[SRC] templates/ 下的 .j2 文件通过 template: src=... dest=... owner=... mode=... 渲染；常用过滤器 default、join、upper、to_yaml；循环可生成多行配置。validate 可在替换前校验生成文件，backup 保留原文件。\n[OPS] 模板变更属于配置文件变更：先确认变量来源、渲染结果和差异，再决定执行。模板中的密码、Token 必须来自 Vault 或外部凭据；不要把密钥渲染进日志。执行后验证服务配置语法与业务健康，保留回滚文件。',
    ['template', 'Jinja2', 'filters', 'default', 'validate', 'backup', 'mode'], 'APPROVAL_REQUIRED'),
  entry('roles-collections', 'Role 目录结构、Galaxy 与 Collections', '09 / 复用',
    'Role 通过固定目录组织任务、变量、模板和处理器；Collections 打包模块与插件。',
    '[SRC] Role 目录含 tasks、defaults、vars、handlers、templates、files、meta；ansible-galaxy init <role> 生成骨架。requirements.yml 可声明 role 与 collection 版本，ansible-galaxy install -r requirements.yml 安装。FQCN（如 ansible.builtin.copy）可避免模块来源歧义。\n[OPS] 版本必须锁定，避免上游更新导致不可复现。第三方 Role/Collection 属于供应链依赖，安装前确认来源、许可证与维护状态；生产仓库优先私有 Galaxy 或内部镜像。不要直接使用来源不明的 playbook 执行生产变更。',
    ['role', 'tasks', 'defaults', 'handlers', 'meta', 'ansible-galaxy', 'requirements.yml', 'FQCN', 'collection'], 'APPROVAL_REQUIRED'),
  entry('vault-secrets', 'Ansible Vault、no_log 与凭据边界', '10 / 凭据安全',
    'Vault 加密敏感变量；no_log 防止输出泄露，但两者都不能替代最小权限与密钥管理。',
    '[SRC] ansible-vault create/edit/encrypt/decrypt 管理加密文件；ansible-playbook --vault-id <id>@<source> 提供解密凭据。no_log: true 隐藏任务输出，loop 中需按字段处理。\n[VERIFY] Vault 密码或密钥文件本身仍是敏感资产，不能提交到 Git 或写入镜像。\n[OPS] 生产使用独立 vault-id、权限受控的凭据来源和轮换机制。日志、CI 输出、失败回显都可能泄露变量，敏感任务必须 no_log 并限制 debug 输出。任何解密、导出或轮换操作都需要审批和审计记录。',
    ['ansible-vault', 'vault-id', 'no_log', 'secrets', 'credential rotation'], 'HIGH'),
  entry('diagnosis', '自动化失败证据链与幂等性排查', '11 / 故障诊断',
    '按连接、解释器、权限、模块参数、变量、幂等性逐层定位，保留失败任务与原始输出。',
    '[OPS] 常见分类：UNREACHABLE 查网络、SSH 端口、密钥、known_hosts；Permission denied 查 remote_user、become、sudoers；python interpreter 缺失查受管节点 Python 路径；模块参数错误查 FQCN 与必填参数；undefined variable 查变量来源与优先级；changed 反复出现查任务是否幂等（如 shell 命令未加 creates/changed_when）。\n证据顺序：失败任务名与主机 → 原始错误输出 → -vvv 连接细节（脱敏）→ inventory/变量 → 目标主机状态。修复后先 --check 验证，再小范围 --limit 执行，最后全量与业务复验。生产变更必须保留回滚与审计记录。',
    ['UNREACHABLE', 'Permission denied', 'python interpreter', 'undefined variable', 'changed', '-vvv', 'evidence chain'], 'APPROVAL_REQUIRED')
]

export const ansibleFacts = Object.freeze({
  controlNode: '安装 ansible-core 的主机，负责编排与推送模块',
  managedNode: '被 SSH 连接并执行模块的目标主机，需要 Python 解释器',
  idempotency: '重复执行不重复改变系统状态；changed 只表示本次发生变更'
})
