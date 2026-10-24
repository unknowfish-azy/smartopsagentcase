// Linux Storage Engineering v1.0. Reference cards only; commands require human approval.
export const linuxStorageNodes = [
  {
    id: 'LINUX-STORAGE-001', title: '磁盘生命周期：从块设备到挂载点', category: '07 存储管理', level: 'Junior',
    concept: 'Linux 存储通常经过物理磁盘、分区、文件系统、挂载点和应用使用五层。设备存在不代表已经可用。',
    architecture: 'Physical Disk → Partition → Filesystem → Mount Point → Application',
    commands: [
      { command: 'lsblk -f', purpose: '查看块设备、文件系统、UUID 和挂载点', risk: 'READ_ONLY', parameters: '仅检查已确认主机；输出可能包含内部拓扑信息。' },
      { command: 'fdisk -l', purpose: '查看分区表和容量', risk: 'READ_ONLY', parameters: '只读检查；不要在未确认设备时进入交互式 fdisk。' },
      { command: 'df -Th', purpose: '查看文件系统类型和容量使用', risk: 'READ_ONLY', parameters: '结合 df -i 检查 inode。' }
    ],
    scenario: '磁盘容量告警时，先区分设备、分区、文件系统和挂载点，避免把未挂载磁盘误判为应用故障。',
    diagnosis: ['确认目标主机和影响范围', '用 lsblk -f、df -Th、df -i 建立只读基线', '确认挂载点与应用数据路径一致', '再规划分区或文件系统变更'],
    risk: 'fdisk、mkfs、mount 都可能影响生产数据；未经设备、备份和回滚确认禁止执行写操作。',
    experience: '设备名可能随启动顺序变化，持久化挂载优先使用 UUID，并在变更后验证。',
    verification: '记录变更前后容量、文件系统、挂载点和业务读写结果。',
    relatedIds: ['LINUX-STORAGE-002', 'LINUX-STORAGE-003'], tags: ['disk', 'block device', 'filesystem', 'mount', 'lsblk', 'df']
  },
  {
    id: 'LINUX-STORAGE-002', title: '分区、文件系统与 fstab 安全流程', category: '07 存储管理', level: 'Middle',
    concept: '分区定义边界，mkfs 创建文件系统，mount 建立访问路径，fstab 负责启动时持久化挂载。每一步都可能改变数据可见性。',
    architecture: '裸磁盘 → fdisk/分区工具 → mkfs → mkdir → mount → UUID/fstab',
    commands: [
      { command: 'partprobe /dev/sdb', purpose: '让内核重新读取已确认的分区表', risk: 'CHANGE', parameters: '仅在分区变更已批准且设备无活动写入时使用。' },
      { command: 'mkfs.ext4 /dev/sdb1', purpose: '在指定分区创建 ext4 文件系统', risk: 'CRITICAL', parameters: '会破坏目标分区原有数据；执行前必须二次确认设备和备份。' },
      { command: 'mount -a', purpose: '验证 fstab 中的挂载配置', risk: 'VALIDATION', parameters: '修改 fstab 后重启前必须执行并检查返回值。' }
    ],
    scenario: '服务器因 fstab 配置错误进入维护模式，恢复时从 root 环境检查配置并用 mount -a 验证。',
    diagnosis: ['确认启动失败的挂载点和错误日志', '检查 fstab 中 UUID、类型、路径和选项', '修正后执行 mount -a，不直接重启碰运气', '验证 df -Th、应用路径和业务读写'],
    risk: '错误 fstab 可能阻断启动；mkfs 和错误设备操作可能造成不可逆数据丢失。',
    experience: '生产环境不要依赖 /dev/sdX 持久挂载；修改 fstab 必须保留备份和恢复入口。',
    verification: 'mount -a 返回成功，目标目录可访问，重启演练或维护窗口验证启动链路。',
    relatedIds: ['LINUX-STORAGE-001', 'LINUX-STORAGE-004'], tags: ['partition', 'mkfs', 'mount', 'fstab', 'UUID', 'boot failed']
  },
  {
    id: 'LINUX-STORAGE-003', title: 'LVM：PV、VG、LV 与扩容路径', category: '07 存储管理', level: 'Senior',
    concept: 'LVM 将物理卷 PV 聚合为卷组 VG，再从 VG 分配逻辑卷 LV；扩容必须分别确认块设备、LV 和文件系统三个层次。',
    architecture: 'Disk/Partition → PV → VG → LV → Filesystem → Mount',
    commands: [
      { command: 'pvs; vgs; lvs', purpose: '只读查看 LVM 层级和剩余空间', risk: 'READ_ONLY', parameters: '输出可能包含生产拓扑，记录时脱敏。' },
      { command: 'pvcreate /dev/sdd && vgextend vg1 /dev/sdd', purpose: '将已确认新盘加入卷组', risk: 'CHANGE', parameters: '必须核对设备序列号，禁止把已有数据盘当新盘。' },
      { command: 'lvextend -r -L +200M /dev/vg1/lv1', purpose: '扩展 LV 并尝试同步扩展文件系统', risk: 'CHANGE', parameters: '先确认文件系统支持在线扩容、备份和回滚。' }
    ],
    scenario: '容量不足时先判断 VG 是否有空闲 PE；没有空闲空间再规划新盘、PV、VG 扩容，然后扩展 LV 和文件系统。',
    diagnosis: ['检查 df -Th 与 lvs/vgs 的层级容量', '判断是文件系统满、LV 满还是 VG 无空闲', '确认文件系统类型与在线扩容能力', '变更后分别验证 pvs/vgs/lvs、df 和业务写入'],
    risk: 'LVM 命令作用于错误设备会造成数据损坏；扩容不是自动修复应用容量或 inode 问题。',
    experience: '扩容前保留 lvs、vgs、df 基线；不要把“命令成功”当作业务恢复证据。',
    verification: '块层、LV 层、文件系统层和应用层容量均与预期一致。',
    relatedIds: ['LINUX-STORAGE-001', 'LINUX-STORAGE-002'], tags: ['LVM', 'PV', 'VG', 'LV', 'PE', 'lvextend', 'resize2fs']
  },
  {
    id: 'LINUX-STORAGE-004', title: 'Swap 与内存压力诊断', category: '07 存储管理', level: 'Middle',
    concept: 'Swap 是虚拟内存的一部分，可缓冲内存压力但不能替代 RAM。Swap 活跃、OOM 和延迟升高需要结合进程与内存证据判断。',
    architecture: 'RAM + Swap → Virtual Memory → Process Memory Pressure',
    commands: [
      { command: 'free -h', purpose: '查看 RAM、缓存和 Swap 使用', risk: 'READ_ONLY', parameters: '结合时间序列和应用指标，不以单次快照下结论。' },
      { command: 'swapon --show', purpose: '查看已启用的 Swap 设备或文件', risk: 'READ_ONLY', parameters: '确认目标主机和权限。' },
      { command: 'vmstat 1 5', purpose: '观察内存回收、swap in/out 和运行队列', risk: 'READ_ONLY', parameters: '采样期间注意输出敏感信息。' }
    ],
    scenario: '服务延迟升高或出现 OOM 时，先判断是工作集增长、内存泄漏、容器限制还是 Swap 抖动。',
    diagnosis: ['确认 OOM 时间线和受影响进程', '采集 free、vmstat、进程 RSS 与容器 limits', '区分 Swap 使用量与 swap in/out 活跃度', '修复后验证 OOM、延迟和节点余量'],
    risk: '盲目关闭 Swap 或调高 swappiness 可能放大内存压力；增加 Swap 不等于解决泄漏。',
    experience: 'Swap 是缓冲和证据，不是容量规划的替代品；调整前记录当前内存曲线。',
    verification: '恢复后持续观察内存、Swap I/O、应用延迟和 OOM 事件。',
    relatedIds: ['LINUX-STORAGE-001', 'LINUX-STORAGE-005'], tags: ['swap', 'memory', 'OOM', 'free -h', 'vmstat', 'swappiness']
  },
  {
    id: 'LINUX-STORAGE-005', title: 'df 与 du 不一致：删除但仍打开的文件', category: '08 存储故障案例', level: 'Senior',
    concept: 'df 统计文件系统已分配块，du 统计目录树可见文件；文件删除后若仍被进程打开，空间仍被占用但 du 看不到。',
    architecture: 'Process FD → deleted inode → blocks remain allocated → df high / du normal',
    commands: [
      { command: 'df -h; df -i', purpose: '确认容量和 inode 是否耗尽', risk: 'READ_ONLY', parameters: '固定文件系统和挂载点后采样。' },
      { command: 'lsof +L1', purpose: '定位链接数为零但仍打开的文件', risk: 'READ_ONLY', parameters: '输出可能包含路径和进程信息，需脱敏。' },
      { command: 'ls -l /proc/<PID>/fd', purpose: '核对进程 FD 与 deleted 文件', risk: 'READ_ONLY', parameters: 'PID 必须是已确认进程。' }
    ],
    scenario: 'df 显示 100% 而 du 总量正常，常见原因是日志已删除但进程仍持有 FD。',
    diagnosis: ['确认挂载点、容量和 inode 指标', '对比 du -x 与 df，排除挂载点遮蔽', '用 lsof +L1 找到持有 deleted 文件的进程', '评估优雅重载/重启并验证空间回收'],
    risk: '直接 kill 或重启可能中断业务；不要用 rm -rf 盲目清理未知路径。',
    experience: 'df/du 不一致首先查 deleted-open 文件和挂载点，而不是立即扩容。',
    verification: '回收后 df 下降、业务日志恢复、FD 数量稳定且无新的 deleted-open 文件。',
    relatedIds: ['LINUX-FD-001', 'LINUX-FD-002', 'LINUX-STORAGE-001'], tags: ['disk full', 'df', 'du', 'lsof', 'deleted', 'open file', 'inode']
  }
]
