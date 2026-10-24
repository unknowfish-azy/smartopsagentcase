// Docker engine, images, containers, Dockerfile and troubleshooting reference pack.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: `docker.${id}`,
  domain: 'linux', platform: 'Linux / Docker', service: 'docker',
  type: 'DOCKER OPERATIONS', title, section, summary, content,
  tags: ['Docker', 'Container', ...tags], source: 'User-provided Docker operations manual',
  version: 'Reference pack', risk, executionAllowed: false
})

export const dockerOperationsEntries = [
  entry('architecture', 'Docker、容器与虚拟机架构', '01 / 基础', 'Docker 容器是宿主机上的隔离进程，依赖 namespace、cgroups、containerd 和 runc。',
    '[SRC] Docker Engine 可抽象为 Client -> dockerd -> containerd -> runc -> Linux process。容器共享宿主机内核，镜像携带应用与依赖；虚拟机包含独立 Guest OS。\n[OPS] namespace 解决“能看到什么”的隔离，cgroups 解决“最多使用多少”的限制；LXC、Docker、Containerd、runc 是不同层次或历史阶段，不能混为同一组件。\n[VERIFY] 用 docker version、docker info、systemctl status docker、ctr version 和 runc -V 分层确认环境。',
    ['Docker Engine', 'dockerd', 'namespace', 'cgroups', 'containerd', 'runc', 'VM']),
  entry('install-daemon', 'Docker CE 安装、daemon 与安全边界', '02 / Engine', '安装 Docker CE 后验证 daemon、socket、配置和最小容器运行链。',
    '[SRC] 常见验证：systemctl status/enable docker、docker version、docker info、docker ps、docker run hello-world。默认通信通常通过 /var/run/docker.sock；daemon.json 可能包含 registry-mirrors、insecure-registries 和 hosts。\n[OPS] 0.0.0.0:2375 是未加密远程 API，高风险；docker.sock 挂载给容器也等价于授予很强的 Docker 控制能力。不要因访问失败就关闭 firewalld/SELinux，先收集拒绝证据并配置最小放行。\n[VERIFY] 检查 systemd、socket、监听地址、JSON 格式、daemon 日志和最小 pull/run。',
    ['docker-ce', 'dockerd', 'daemon.json', 'docker.sock', '2375', 'systemd'], 'HIGH'),
  entry('images-registry', 'Docker 镜像、Tag、Registry 与迁移', '03 / Image 与 Registry', '管理 images、pull、tag、save/load、login、push/pull 和 Harbor/云仓库引用。',
    '[SRC] Image 是模板，Repository 是镜像集合，Registry 保存镜像；docker tag 只是增加引用，docker save/load 用于离线迁移，push 前通常要使用 registry/namespace/repository:tag。\n[OPS] 镜像源、Registry 地址、项目权限、TLS/HTTP、平台和凭据必须读取实际环境；latest 不利于复现。不要把密码、Token 或课程镜像加速地址写死。删除镜像前确认引用、运行容器和数据卷。\n[VERIFY] 用 docker images、docker info、docker login、digest、目标 Registry 和 pull/push 结果验证完整生命周期。',
    ['image', 'repository', 'registry', 'Docker Hub', 'Harbor', 'pull', 'push', 'tag', 'save', 'load'], 'APPROVAL_REQUIRED'),
  entry('container-lifecycle', '容器生命周期、logs、inspect、exec 与 attach', '04 / Container', '区分 run、start、stop、rm、logs、inspect、exec、attach 和主进程生命周期。',
    '[SRC] docker run 创建并启动，start 启动已有容器，stop 停止，rm 删除；docker logs 看 stdout/stderr，inspect 看配置和状态，exec 在运行容器中创建新进程，attach 连接已有主进程。hello-world 正常输出后退出不一定是故障。\n[OPS] Container Up 不等于应用健康；Exited 先查 ExitCode、OOMKilled、CMD/ENTRYPOINT、环境和日志。进入运行容器排障优先 docker exec，attach 后 exit 可能使主进程结束。\n[VERIFY] 组合 docker ps -a、logs、inspect、exec、port、curl 和应用健康检查。',
    ['docker run', 'docker ps', 'docker logs', 'docker inspect', 'docker exec', 'docker attach', 'Exited', 'Running']),
  entry('network-volume', 'Docker 端口、网络与 Volume 持久化', '05 / 网络与存储', '用 -p、network、bind mount 和 volume 连接外部访问与持久化数据。',
    '[SRC] -p HOST:CONTAINER 做端口映射，EXPOSE 只声明端口；docker network inspect 查看网络，-v HOST:CONTAINER 做目录/文件挂载。Volume 保证容器删除后数据可保留。\n[OPS] 访问失败沿 Client -> Host port -> mapping -> Container port -> process -> application 检查；挂载会遮挡镜像原有目录内容，需确认 Source、Destination、RW/RO 和权限。不要直接删除 /var/lib/docker。\n[VERIFY] 使用 docker port、ss -lntp、docker inspect、docker exec ip/route/resolv.conf、curl 和宿主机目录对照验证。',
    ['port mapping', 'docker network', 'DNS', 'volume', 'bind mount', 'persistence', 'ip_forward']),
  entry('dockerfile', 'Dockerfile 指令与可复现构建', '06 / Dockerfile', '将镜像构建过程代码化，理解 FROM、RUN、COPY、CMD、ENTRYPOINT、WORKDIR、USER 和多阶段构建。',
    '[SRC] RUN 在 build 阶段执行；CMD 是默认启动命令；ENTRYPOINT 是固定入口；ENTRYPOINT + CMD 可形成可参数化入口；EXPOSE 不等于宿主机开放；COPY 默认优先于 ADD；WORKDIR、ENV、USER、VOLUME 描述运行环境。\n[OPS] 使用固定版本、最小但兼容的基础镜像、合并合理层、依赖优先复制、.dockerignore、非 root 用户和多阶段构建。不要把密码写入 Dockerfile、ENV、镜像层或公开仓库。\n[VERIFY] 通过 docker build、镜像扫描、docker inspect Config、启动命令和业务健康检查验证。',
    ['Dockerfile', 'FROM', 'RUN', 'COPY', 'ADD', 'WORKDIR', 'ENV', 'EXPOSE', 'VOLUME', 'USER', 'CMD', 'ENTRYPOINT', 'multi-stage']),
  entry('resource-governance', 'Docker CPU、内存、IO、FD 与 OOM', '07 / 资源治理', '使用 cgroups 参数和 stats/inspect 观察容器资源边界及异常。',
    '[SRC] -m/--memory、--memory-swap、--memory-reservation、--cpus、--cpu-shares、--cpuset-cpus、device read/write bps/iops、--ulimit 控制资源。docker stats 查看使用量，inspect 查看 HostConfig、Ulimits、RestartPolicy。\n[OPS] CPU 限制常表现为延迟，内存超限可能 OOMKilled，IO 限制表现为吞吐下降，FD 超限表现为文件描述符耗尽。必须结合宿主机 free/top/iostat、dmesg/journalctl -k、/proc/1/limits 和应用日志，不能只看一个指标。\n[VERIFY] 对比 limit、reservation、实际使用、宿主机余量和业务 SLO，验证限流、恢复和告警。',
    ['cgroups', 'memory', 'CPU', 'IO', 'OOM', 'ulimit', 'FD', 'docker stats'], 'APPROVAL_REQUIRED'),
  entry('harbor', 'Harbor 私有仓库与 Compose 生命周期', '08 / Harbor', 'Harbor 是由 Registry、Proxy、Core、数据库等组件组成的仓库平台，需用实际 compose 管理。',
    '[SRC] 典型流程：配置 hostname/HTTP 或 HTTPS -> ./install.sh -> docker compose ps -> docker login -> tag -> push/pull。新版本可能使用 docker compose，旧环境可能使用 docker-compose，应先检测。\n[OPS] 公开/私有项目权限、TLS、insecure-registries 和管理员凭据必须按实际环境确认；0.0.0.0 明文 Registry 和弱密码只适合隔离实验。Harbor 故障优先查看 compose ps、组件日志、端口和磁盘，不要只重启 Docker。\n[VERIFY] 检查 Harbor 主机、DNS/hosts、80/443、Registry、项目权限、镜像 digest、docker compose ps 和业务 pull/push。',
    ['Harbor', 'docker compose', 'docker-compose', 'project', 'insecure-registries', 'registry'], 'HIGH'),
  entry('storage-diagnosis', 'Docker/Harbor 磁盘与 inode 故障', '09 / 存储诊断', '针对 no space left on device 区分容量、inode、缓存、日志、Registry 数据和 LVM。',
    '[SRC] 证据链：df -h -> df -i -> docker system df -> du -xh /var -> lsblk/vgs/lvs；必要时查看 containerd/Harbor 日志。空间不足可能发生在 /var/lib/docker、containerd content 或 Harbor 数据目录。\n[OPS] 不要直接 rm -rf /var/lib/docker、清空 /var 或删除生产 Volume。先区分运行容器、镜像、Volume、Registry 持久数据和临时内容，再选择有计划清理或扩容，并保留回滚。\n[VERIFY] 清理/扩容后复查空间、inode、服务状态、镜像操作和 Harbor/应用业务。',
    ['no space left on device', 'df -h', 'df -i', 'docker system df', 'LVM', 'inode', 'storage'], 'HIGH'),
  entry('troubleshooting', 'Docker 标准故障证据链', '10 / 故障排查', '从 Host、daemon、Image/Registry、Container、Network/Volume、资源到应用协议逐层定位。',
    '[OPS] daemon 不可用查 systemctl/journalctl/socket；镜像失败查 DNS、网络、Registry、认证、Tag、TLS；Exited/重启查 logs、inspect、ExitCode、OOMKilled；Running 但不可用查 port、ss、exec、curl、应用日志；数据丢失查 Mounts；性能异常查 stats、top、free、iostat、FD 和 kernel 日志。\n[VERIFY] 先观察和采集证据，再提出修复；记录 Docker/Containerd 版本、上下文、容器名、镜像 digest、时间和原始错误。高风险 stop/rm/prune、修改 daemon、开放 2375、删除数据和重启服务必须确认目标并审批。',
    ['diagnosis', 'journalctl', 'docker system df', 'ExitCode', 'OOMKilled', 'network', 'volume', 'application'], 'READ_ONLY'),
  entry('automation', 'Docker 自动化运维工作流', '11 / 自动化', '把环境读取、构建、发布、运行、资源观察和验证串成可审计闭环。',
    '[SRC] 标准链路：确认 Docker context/Host -> docker version/info -> Image/Registry -> build/tag/push -> run/volume/network -> logs/inspect/stats -> 应用验证 -> 事件记录。\n[OPS] 参数化 Registry、项目、Tag、端口、Volume 和资源限制；动态凭据使用安全注入；默认只读，批量 stop/rm/prune、Harbor变更、数据库容器和 Docker Socket 挂载需要审批。\n[VERIFY] 在隔离环境先做最小 build/pull/run/exec/stop 流程，记录成功/失败、回滚和审计信息。',
    ['automation', 'Docker context', 'audit', 'rollback', 'least privilege'], 'APPROVAL_REQUIRED')
]

export const dockerOperationsRules = Object.freeze([
  { id: 'DOCKER-001', trigger: 'docker daemon 不可用', sequence: ['context', 'systemd', 'journalctl', 'socket', 'daemon.json', 'containerd'] },
  { id: 'DOCKER-002', trigger: '容器异常', sequence: ['ps', 'inspect', 'logs', 'state/exit code', 'network/volume/resource', 'application verify'] },
  { id: 'DOCKER-003', trigger: '镜像或 Harbor 失败', sequence: ['DNS/network', 'registry/protocol', 'auth/project', 'tag/platform', 'storage'] },
  { id: 'DOCKER-004', trigger: '高风险 Docker 操作', sequence: ['preview target', 'approval', 'backup/rollback', 'execute', 'audit', 'verify'] }
])
