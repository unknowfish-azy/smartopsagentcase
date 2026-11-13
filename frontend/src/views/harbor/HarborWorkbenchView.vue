<template>
  <article class="harbor-workbench">
    <header class="workbench-header">
      <div>
        <p class="eyebrow">HARBOR / REGISTRY OPERATIONS</p>
        <h1>Harbor 工作台</h1>
        <p class="lede">项目、镜像仓库与 Containerd 接入状态集中查看。所有读取结果来自已配置的真实 Harbor。</p>
      </div>
      <div class="status-badge"><span class="status-dot"></span><strong>READ ONLY / 只读</strong><small>不会执行推送、删除或权限变更</small></div>
    </header>

    <section class="registry-panel" aria-label="Harbor 项目与仓库">
      <HarborBrowser />
    </section>

    <section class="knowledge-strip" aria-label="Harbor 运维说明">
      <header><span>OPERATIONS NOTES</span><small>点击卡片，在悬浮窗查看详细步骤与报错原因</small></header>
      <div class="note-grid">
        <button v-for="note in notes" :key="note.id" type="button" class="note-card" @click="openNote(note)">
          <span class="note-kicker">{{ note.kicker }}</span><strong>{{ note.title }}</strong><small>{{ note.summary }}</small><i>查看说明 ↗</i>
        </button>
      </div>
    </section>

    <Teleport to="body">
      <div v-if="activeNote" class="note-modal" role="presentation" @click.self="closeNote">
        <section class="note-dialog" role="dialog" aria-modal="true" :aria-label="activeNote.title">
          <button class="modal-close" type="button" aria-label="关闭说明" title="关闭说明" @click="closeNote">×</button>
          <p class="eyebrow">{{ activeNote.kicker }}</p><h2>{{ activeNote.title }}</h2>
          <div class="note-content"><p v-for="(paragraph, index) in activeNote.details" :key="index">{{ paragraph }}</p></div>
        </section>
      </div>
    </Teleport>
  </article>
</template>

<script setup>
import { ref } from 'vue'
import HarborBrowser from '../../components/operations/HarborBrowser.vue'

const activeNote = ref(null)
const notes = [
  { id: 'containerd', kicker: 'CONTAINERD', title: 'Containerd 拉取 Harbor 镜像', summary: 'hosts.toml、CA、namespace 与 imagePullSecret', details: ['操作步骤：在节点确认 systemctl is-active containerd、ctr version 和 ctr namespaces list。', '配置路径：推荐 /etc/containerd/certs.d/<registry>/hosts.toml，填写 HTTPS 地址、CA 和 pull/resolve capability。修改后重启 containerd，再用 ctr -n k8s.io images list 验证。', '常见报错：x509 certificate signed by unknown authority 表示 CA 未安装；401/403 表示项目或 robot 账号权限不足；看不到镜像时先确认 namespace，不要直接判断 Harbor 没有镜像。'] },
  { id: 'tls', kicker: 'TLS / AUTH', title: 'Harbor 连接与证书排查', summary: '健康接口、TLS、账号权限和网络证据', details: ['先访问 /api/v2.0/health，区分 DNS、网络、TLS 和认证问题。后端只读账号至少需要项目读取权限。', '证书检查：核对证书 SAN 是否包含 Harbor 域名、节点时间是否准确、客户端是否安装签发 CA。禁止用关闭 TLS 校验掩盖证书问题。', '401/403 是服务已到达但凭据或授权不满足；超时则继续检查路由、防火墙、代理和 Harbor 入口负载均衡。'] },
  { id: 'project', kicker: 'PROJECT / REPOSITORY', title: '项目与仓库治理', summary: '项目可见性、仓库命名和镜像证据', details: ['项目列表显示 Harbor API 返回的真实项目；仓库列表显示仓库名称与制品数量，不生成示例数据。', '排查镜像不存在：确认项目名、仓库路径、tag/digest、架构平台和账号范围。生产部署优先使用不可变 digest。', '删除、推送、复制、扫描策略和权限变更不在只读工作台执行，需进入独立审批流程并保留审计记录。'] },
  { id: 'install', kicker: 'INSTALLATION', title: 'Harbor 安装验证', summary: 'Linux、Docker Compose、harbor.yml 与回滚边界', details: ['安装前确认 Linux、Docker Engine、Compose plugin、磁盘、DNS、时间同步和 HTTPS 证书。使用官方安装包并校验 SHA256。', '配置 harbor.yml 的 hostname、HTTPS certificate/private_key 和 data_volume；安装后执行 docker compose ps 与 curl --fail https://<host>/api/v2.0/health。', '升级前备份 Harbor 数据卷和配置；不要在生产环境直接复用课程中的默认密码、HTTP 地址或 insecure registry 配置。'] }
]
function openNote(note) { activeNote.value = note }
function closeNote() { activeNote.value = null }
</script>

<style scoped>
.harbor-workbench{max-width:1480px;margin:0 auto;padding:16px 0 48px;color:var(--smart-text)}.workbench-header{display:flex;justify-content:space-between;gap:32px;padding:12px 0 28px;border-bottom:1px solid var(--smart-border)}.eyebrow{margin:0 0 10px;color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.14em}.workbench-header h1{margin:0;font:500 clamp(30px,4vw,54px)/1.05 var(--font-cn)}.lede{max-width:660px;margin:13px 0 0;color:var(--smart-muted);font:13px/1.7 var(--font-cn)}.status-badge{display:grid;align-content:center;gap:7px;min-width:220px;padding-left:18px;border-left:1px solid var(--smart-border);font-family:var(--font-mono)}.status-badge strong{font-size:11px;color:var(--smart-primary-strong)}.status-badge small{color:var(--smart-muted);font:11px var(--font-cn)}.status-dot{width:8px;height:8px;border-radius:50%;background:var(--smart-primary-strong);box-shadow:0 0 12px var(--smart-primary-strong)}.registry-panel{margin-top:24px;border:1px solid var(--smart-border);background:color-mix(in srgb,var(--smart-surface) 85%,transparent)}.knowledge-strip{margin-top:24px}.knowledge-strip>header{display:flex;align-items:baseline;justify-content:space-between;gap:16px;margin-bottom:12px}.knowledge-strip>header span{color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.13em}.knowledge-strip>header small{color:var(--smart-muted);font:11px var(--font-cn)}.note-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.note-card{display:grid;gap:8px;min-height:142px;padding:15px;text-align:left;border:1px solid var(--smart-border);background:transparent;color:var(--smart-text);cursor:pointer;transition:border-color .18s,transform .18s,background .18s}.note-card:hover{border-color:var(--smart-primary-strong);background:color-mix(in srgb,var(--smart-primary-strong) 7%,transparent);transform:translateY(-2px)}.note-kicker{color:var(--smart-primary-strong);font:9px var(--font-mono);letter-spacing:.12em}.note-card strong{font:600 14px var(--font-cn)}.note-card small{color:var(--smart-muted);font:11px/1.6 var(--font-cn)}.note-card i{margin-top:auto;color:var(--smart-primary-strong);font:11px var(--font-cn);font-style:normal}.note-modal{position:fixed;z-index:1000;inset:0;display:grid;place-items:center;padding:24px;background:rgba(2,6,10,.72)}.note-dialog{position:relative;width:min(720px,100%);max-height:min(78vh,720px);overflow:auto;padding:30px 34px 34px;border:1px solid var(--smart-border-strong);background:var(--smart-surface);box-shadow:0 24px 80px rgba(0,0,0,.42)}.note-dialog h2{margin:0 0 22px;font:600 24px var(--font-cn)}.modal-close{position:absolute;top:12px;right:12px;width:34px;height:34px;padding:0;border:1px solid var(--smart-border);background:transparent;color:var(--smart-muted);font:24px/1 var(--font-cn);cursor:pointer}.modal-close:hover{color:var(--smart-primary-strong);border-color:var(--smart-primary-strong)}.note-content{display:grid;gap:14px}.note-content p{margin:0;color:var(--smart-muted);font:14px/1.85 var(--font-cn)}@media(max-width:900px){.note-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.workbench-header{display:block}.status-badge{margin-top:20px;padding:14px 0 0;border-top:1px solid var(--smart-border);border-left:0}}@media(max-width:560px){.note-grid{grid-template-columns:1fr}.knowledge-strip>header{align-items:flex-start;flex-direction:column}.note-dialog{padding:26px 20px 24px}}
</style>
