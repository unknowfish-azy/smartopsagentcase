// 逆向研究工作台目录：15 套开源工具的静态策展快照。
//
// 诚实边界：
// - 清单按参考内容标题语义（"15套开源工具，搭建本地逆向研究工作台 · REA 生态"）
//   与公开常识策展，未与原文逐条核对；页面必须如实声明这一点。
// - 仓库链接全部指向官方 repo；本页只做导览，不打包、不执行任何工具。
// - 纯静态数据 + 纯函数（管线推导），无框架依赖，供视图与单元测试共用。

export const RE_STAGES = Object.freeze([
  { id: 'recon', label: 'RECON', cn: '侦察识别', hint: '先弄清目标是什么：格式、打包器、入口' },
  { id: 'static', label: 'STATIC', cn: '静态分析', hint: '不运行目标，直接读结构与反编译' },
  { id: 'dynamic', label: 'DYNAMIC', cn: '动态调试', hint: '让目标跑起来，断点、hook、跟踪' },
  { id: 'network', label: 'NETWORK', cn: '网络观测', hint: '抓包与代理，看协议与远端交互' },
  { id: 'memory', label: 'MEMORY / MOBILE', cn: '记忆与移动', hint: '内存取证与安卓目标拆解' },
  { id: 'report', label: 'REPORT', cn: '证据沉淀', hint: '把结论固化为规则与可复现笔记' }
])

export const RE_TOOLS = Object.freeze([
  // ── 侦察识别 ──
  {
    id: 'die', name: 'Detect It Easy', stage: 'recon',
    repo: 'https://github.com/horsicq/DIE-engine',
    blurb: '文件类型 / 编译器 / 打包器 / 加密壳识别，拖入即出结论。',
    useWhen: '拿到任何陌生样本的第一步：先问"这是什么"。'
  },
  {
    id: 'binwalk', name: 'binwalk', stage: 'recon',
    repo: 'https://github.com/ReFirmLabs/binwalk',
    blurb: '固件镜像里扫描嵌入文件系统与可提取段，一键 carve。',
    useWhen: '分析路由器 / IoT 固件，先把镜像拆开看层次。'
  },
  {
    id: 'upx', name: 'UPX', stage: 'recon',
    repo: 'https://github.com/upx/upx',
    blurb: '常见可执行压缩壳，本身可加壳也可解壳（-d）。',
    useWhen: 'DIE 报 UPX 时先脱壳，再进静态分析，避免反编译出一堆乱码。'
  },
  // ── 静态分析 ──
  {
    id: 'ghidra', name: 'Ghidra', stage: 'static',
    repo: 'https://github.com/NationalSecurityAgency/ghidra',
    blurb: 'NSA 开源反编译套件，多架构反汇编 + 反编译 + 脚本生态。',
    useWhen: '需要跨架构深度反编译时的默认主力。'
  },
  {
    id: 'cutter', name: 'Cutter', stage: 'static',
    repo: 'https://github.com/rizinorg/cutter',
    blurb: 'rizin 的图形前端，反汇编 / 图视图 / 调试一体，上手比命令行快。',
    useWhen: '想要 rizin 内核但不想全程敲命令。'
  },
  {
    id: 'imhex', name: 'ImHex', stage: 'static',
    repo: 'https://github.com/WerWolv/ImHex',
    blurb: '面向模式匹配的十六进制编辑器，用 DSL 写文件结构解析模板。',
    useWhen: '逆向私有文件格式 / 网络包结构时做字节级拆解。'
  },
  // ── 动态调试 ──
  {
    id: 'x64dbg', name: 'x64dbg', stage: 'dynamic',
    repo: 'https://github.com/x64dbg/x64dbg',
    blurb: 'Windows 用户态调试器，断点 / 补丁 / 脚本插件齐全。',
    useWhen: 'Windows 目标需要单步跟、改寄存器、下条件断点。'
  },
  {
    id: 'frida', name: 'Frida', stage: 'dynamic',
    repo: 'https://github.com/frida/frida',
    blurb: '跨平台动态插桩：JS 脚本注入 hook 函数、改返回值、追踪调用。',
    useWhen: '不想改二进制，想在运行时"动手脚"——安卓 / iOS / 桌面通用。'
  },
  {
    id: 'qemu', name: 'QEMU', stage: 'dynamic',
    repo: 'https://github.com/qemu/qemu',
    blurb: '全系统模拟器，固件与怪架构二进制的沙箱运行环境。',
    useWhen: '目标不能在自己机器上直接跑（ARM 固件 / MIPS 样本）。'
  },
  // ── 网络观测 ──
  {
    id: 'wireshark', name: 'Wireshark', stage: 'network',
    repo: 'https://gitlab.com/wireshark/wireshark',
    blurb: '最主流的抓包与协议分析器，解码器覆盖数百种协议。',
    useWhen: '被动观测目标的所有进出流量，还原协议字段。'
  },
  {
    id: 'mitmproxy', name: 'mitmproxy', stage: 'network',
    repo: 'https://github.com/mitmproxy/mitmproxy',
    blurb: '可编程 HTTPS 中间人代理，实时查看 / 改写请求响应。',
    useWhen: '目标是 App 或客户端，需要主动拦截改包看反应。'
  },
  // ── 记忆与移动 ──
  {
    id: 'volatility', name: 'Volatility 3', stage: 'memory',
    repo: 'https://github.com/volatilityfoundation/volatility3',
    blurb: '内存取证框架：从内存转储里挖进程、连接、注入痕迹。',
    useWhen: '分析恶意样本行为或做事件响应，内存不会说谎。'
  },
  {
    id: 'jadx', name: 'jadx', stage: 'memory',
    repo: 'https://github.com/skylot/jadx',
    blurb: 'APK / dex 转 Java 源码，带 GUI 搜索与交叉引用。',
    useWhen: '安卓逆向第一步：先读懂它的 Java 层逻辑。'
  },
  {
    id: 'apktool', name: 'Apktool', stage: 'memory',
    repo: 'https://github.com/iBotPeaches/Apktool',
    blurb: 'APK 资源与 smali 级拆包 / 回包，重打包改行为的标配。',
    useWhen: 'jadx 只读不够，需要改 smali 重打包验证假设。'
  },
  // ── 证据沉淀 ──
  {
    id: 'yara', name: 'YARA', stage: 'report',
    repo: 'https://github.com/VirusTotal/yara',
    blurb: '样本特征规则语言，把"我认出了它"固化成可复用的规则。',
    useWhen: '研究收尾：给目标家族写规则，下次秒识别；配合 notebook 记录结论，过程可复现。'
  }
])

/** 目标类型 → 推荐工具管线（阶段顺序）。工具 id 必须存在于 RE_TOOLS。 */
export const RE_TARGETS = Object.freeze([
  {
    id: 'native', label: '本机二进制', cn: 'EXE / ELF / Mach-O',
    pipeline: ['die', 'upx', 'ghidra', 'cutter', 'x64dbg', 'frida', 'yara'],
    note: '先识别与脱壳，静态反编译读逻辑，动态调试验证，最后写 YARA 规则沉淀。'
  },
  {
    id: 'firmware', label: '固件 / IoT', cn: '路由器 / 嵌入式镜像',
    pipeline: ['binwalk', 'ghidra', 'imhex', 'qemu', 'yara'],
    note: 'binwalk 拆镜像，Ghidra 啃怪架构，ImHex 固化格式，QEMU 模拟跑起来，结论写 YARA 规则。'
  },
  {
    id: 'mobile', label: '安卓应用', cn: 'APK / dex',
    pipeline: ['frida', 'mitmproxy', 'jadx', 'apktool', 'yara'],
    note: 'Frida 运行时插桩，mitmproxy 看网络行为，jadx 读 Java 层，apktool 动 smali，结论写 YARA 规则。'
  },
  {
    id: 'protocol', label: '私有协议', cn: '客户端 ↔ 服务端',
    pipeline: ['imhex', 'frida', 'wireshark', 'mitmproxy'],
    note: 'ImHex 模板固化字段结构，Frida 钩加解密函数，先被动抓包（Wireshark），再主动改包探测边界（mitmproxy）。'
  },
  {
    id: 'memory', label: '内存样本', cn: 'dump / 事件响应',
    pipeline: ['binwalk', 'volatility', 'yara'],
    note: 'binwalk 辅助 carve 出嵌入对象，Volatility 挖进程与注入痕迹，YARA 扫特征收尾。'
  }
])

const toolIndex = new Map(RE_TOOLS.map(tool => [tool.id, tool]))

/** 管线推导：目标 id → [{ stage, tools[] }]，阶段保序、缺阶段不出现。 */
export function pipelineForTarget(targetId) {
  const target = RE_TARGETS.find(item => item.id === targetId)
  if (!target) return []
  const stageOrder = RE_STAGES.map(stage => stage.id)
  const groups = []
  for (const toolId of target.pipeline) {
    const tool = toolIndex.get(toolId)
    if (!tool) continue
    let group = groups.find(item => item.stage === tool.stage)
    if (!group) {
      group = { stage: tool.stage, tools: [] }
      const at = groups.findIndex(item => stageOrder.indexOf(item.stage) > stageOrder.indexOf(tool.stage))
      if (at === -1) groups.push(group)
      else groups.splice(at, 0, group)
    }
    group.tools.push(tool)
  }
  return groups
}

/** 工具卡片按阶段聚合：[{ stage, tools[] }]，目录顺序即展示顺序。 */
export function toolsByStage() {
  return RE_STAGES
    .map(stage => ({ stage, tools: RE_TOOLS.filter(tool => tool.stage === stage.id) }))
    .filter(group => group.tools.length > 0)
}
