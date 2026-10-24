<template>
  <div class="home home-orbital">
    <header class="home-heading">
      <div class="home-heading__identity"><p>SMARTOPS / PERSONAL SYSTEM</p><h1>智维 Agent <span>个人运维空间</span></h1></div>
      <div class="home-heading__meta"><span class="home-heading__signal"><i aria-hidden="true"></i> SYSTEM READY</span><span>知识 · 系统 · 智能体 · 经验</span></div>
    </header>
    <HomeOrbitCarousel :slides="slides" />
  </div>
</template>

<script setup>
import HomeOrbitCarousel from '../../components/ui/home-orbit-carousel.vue'
import { personalSystemGroups } from '../../navigation/personalSystemNavigation'

function links(...ids) {
  return ids.flatMap(id => {
    const group = personalSystemGroups.find(item => item.id === id)
    return group.children.length
      ? [{ name: group.cn, to: group.to }, ...group.children.filter(child => child.to !== group.to).map(child => ({ name: child.cn, to: child.to }))]
      : [{ name: id === 'connections' ? '连接中心 / 远程运维' : group.cn, to: group.to }]
  })
}
const slides = [
  { label: '个人系统', eyebrow: 'PERSONAL / SYSTEM', kicker: '01 — 你的个人系统', title: '我的系统，\n始终保持运行', description: '记录系统、故障、运行手册与自动化过程中的关键上下文，让每一次操作都有迹可循。', words: ['OPERATE', 'LEARN', 'REMEMBER'], links: links('operations', 'knowledge', 'agent') },
  { label: '知识空间', eyebrow: 'KNOWLEDGE / RETAINED', kicker: '02 — 系统知识与运行手册', title: '系统教会我的\n一切', description: '知识按系统组织，而不是散落在彼此无关的文档中。从基础原理到故障排查，持续积累。', words: ['Linux', 'Docker', 'Kubernetes', '可观测性'], links: links('knowledge') },
  { label: '运维系统', eyebrow: 'SYSTEM / LEGIBLE', kicker: '03 — 连接现场，理解系统', title: '系统应当\n一目了然', description: '从服务器索引进入系统详情，连接远程环境，查阅日志、网络与运行上下文。', words: ['SSH', '网络诊断', '日志分析', '系统巡检'], links: links('connections', 'operations') },
  { label: '智能体', eyebrow: 'AGENT / SECOND CONSCIOUSNESS', kicker: '04 — 与智能体协作', title: '与系统一起\n思考', description: '明确任务目标，组织上下文与技能指引，在控制中心推进工作，在执行轨迹中回看过程。', words: ['目标', '上下文', '证据', '执行轨迹'], links: links('agent', 'skills') },
  { label: '运维记忆', eyebrow: 'MEMORY / EXPERIENCE', kicker: '05 — 经验成为下一次的起点', title: '留下真正\n重要的经验', description: '已解决的问题、已验证的证据与复盘结论，会在下一次故障到来时继续发挥作用。', words: ['故障复盘', '证据归档', '经验沉淀'], links: links('memory') },
  { label: '模型中心', eyebrow: 'MODELS / INSIGHT', kicker: '06 — 了解每一次调用', title: '让模型能力\n清晰可见', description: '管理模型接入，查看调用成功率、响应速度与测试趋势，追踪 Token 用量和额度。', words: ['成功率', '响应速度', '测试趋势', 'Token'], links: [{ name: '模型接入', to: '/model-settings' }, ...links('models').slice(1)] },
  { label: '插件与技能', eyebrow: 'EXTENSIONS / POSSIBILITIES', kicker: '07 — 扩展工具，明确目标', title: '用插件扩展，\n用技能指引', description: '通过链接安装插件与 Skill，组织功能入口与任务指引，为智能体准备明确的工作方向。', words: ['Plugins', 'Skills', 'GitHub', '任务指引'], links: links('plugins', 'skills') }
]
</script>

<style scoped>
.home-orbital { min-height: calc(100dvh - 112px); display: flex; flex-direction: column; justify-content: center; padding: 20px 0; }
.home-heading { display: flex; align-items: center; flex-wrap: wrap; gap: 14px 24px; padding: 0 12px; }
.home-heading__identity { display:grid; gap:6px; }
.home-heading__meta { display:flex; align-items:center; gap:18px; margin-left:auto; color:var(--smart-muted); font:10px var(--font-mono); letter-spacing:.08em; }
.home-heading__signal { display:inline-flex; align-items:center; gap:7px; color:var(--smart-success); }
.home-heading__signal i { width:7px; height:7px; border-radius:50%; background:currentColor; box-shadow:0 0 0 4px color-mix(in srgb,currentColor 13%,transparent), 0 0 16px currentColor; }
.home-heading p { color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .12em; }
.home-heading h1 { margin: 0; color: var(--smart-text); font-size: 18px; font-weight: 500; }
.home-heading h1 span { margin-left: 12px; font-size: 12px; color: var(--smart-muted); }
.home-caption { margin-left: auto; font-size: 11px; color: var(--smart-muted); }
@media (max-width: 767px) { .home-orbital { padding: 18px 0; min-height: calc(100dvh - 100px); } .home-heading { gap: 8px; } .home-heading p { width: 100%; margin: 0; font-size: 9px; } .home-caption { display: none; } .home-heading__meta { width:100%; margin-left:0; justify-content:space-between; } }
</style>
