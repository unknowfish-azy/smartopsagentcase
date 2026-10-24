#!/usr/bin/env bash

# ============================================================
# SmartOpsAgent Linux Monitor Installer
#
# 功能：
#   安装 collect-metrics.sh
#
# 默认安装目录：
#   /opt/smartops-monitor
#
# 使用：
#   sudo ./install-monitor.sh
#
# 可自定义：
#   sudo INSTALL_DIR=/data/smartops-monitor ./install-monitor.sh
# ============================================================

set -Eeuo pipefail


# ------------------------------------------------------------
# 配置
# ------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COLLECTOR_SOURCE="${SCRIPT_DIR}/collect-metrics.sh"

INSTALL_DIR="${INSTALL_DIR:-/opt/smartops-monitor}"

COLLECTOR_TARGET="${INSTALL_DIR}/collect-metrics.sh"


# ------------------------------------------------------------
# 日志
# ------------------------------------------------------------

log() {

    echo "[SmartOps Monitor] $(date '+%Y-%m-%d %H:%M:%S') $*"

}


error() {

    echo "[SmartOps Monitor][ERROR] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2

}


# ------------------------------------------------------------
# 检查 root
# ------------------------------------------------------------

require_root() {

    if [[ "${EUID}" -ne 0 ]]; then

        error "安装脚本需要 root 权限。"

        error "请使用：sudo ./install-monitor.sh"

        exit 1

    fi

}


# ------------------------------------------------------------
# 检查操作系统
# ------------------------------------------------------------

check_os() {

    if [[ ! -f /etc/os-release ]]; then

        error "无法识别 Linux 发行版。"

        exit 1

    fi

    # shellcheck disable=SC1091
    source /etc/os-release

    log "系统：${PRETTY_NAME:-unknown}"

}


# ------------------------------------------------------------
# 检查依赖
# ------------------------------------------------------------

check_dependencies() {

    log "检查系统依赖。"

    local commands=(
        bash
        awk
        df
        free
        hostname
        date
    )

    local command_name

    for command_name in "${commands[@]}"; do

        if ! command -v "${command_name}" >/dev/null 2>&1; then

            error "缺少必要命令：${command_name}"

            exit 1

        fi

    done

    log "系统依赖检查通过。"

}


# ------------------------------------------------------------
# 检查源文件
# ------------------------------------------------------------

check_source_files() {

    if [[ ! -f "${COLLECTOR_SOURCE}" ]]; then

        error "找不到采集脚本：${COLLECTOR_SOURCE}"

        exit 1

    fi

}


# ------------------------------------------------------------
# 创建安装目录
# ------------------------------------------------------------

create_install_directory() {

    log "创建安装目录：${INSTALL_DIR}"

    mkdir -p "${INSTALL_DIR}"

}


# ------------------------------------------------------------
# 安装采集器
# ------------------------------------------------------------

install_collector() {

    log "安装 Metrics Collector。"

    cp \
        "${COLLECTOR_SOURCE}" \
        "${COLLECTOR_TARGET}"

    chmod 755 "${COLLECTOR_TARGET}"

    log "安装完成：${COLLECTOR_TARGET}"

}


# ------------------------------------------------------------
# 创建版本信息
# ------------------------------------------------------------

create_version_file() {

    local version_file="${INSTALL_DIR}/VERSION"

    cat > "${version_file}" <<EOF
SmartOpsAgent Monitor
version=0.1.0
installed_at=$(date '+%Y-%m-%dT%H:%M:%S%z')
EOF

    chmod 644 "${version_file}"

}


# ------------------------------------------------------------
# 执行安装测试
# ------------------------------------------------------------

test_collector() {

    log "测试 Metrics Collector。"

    local output

    output="$(
        "${COLLECTOR_TARGET}"
    )"

    if [[ -z "${output}" ]]; then

        error "采集器没有返回任何数据。"

        exit 1

    fi

    if ! echo "${output}" | grep -q '"cpuUsage"'; then

        error "采集器输出缺少 cpuUsage。"

        exit 1

    fi

    if ! echo "${output}" | grep -q '"memoryUsage"'; then

        error "采集器输出缺少 memoryUsage。"

        exit 1

    fi

    if ! echo "${output}" | grep -q '"diskUsage"'; then

        error "采集器输出缺少 diskUsage。"

        exit 1

    fi

    log "采集器测试通过。"

}


# ------------------------------------------------------------
# 输出安装结果
# ------------------------------------------------------------

show_result() {

    echo
    echo "============================================================"
    echo " SmartOpsAgent Monitor 安装完成"
    echo "============================================================"
    echo "安装目录：${INSTALL_DIR}"
    echo "采集脚本：${COLLECTOR_TARGET}"
    echo "版本文件：${INSTALL_DIR}/VERSION"
    echo "============================================================"
    echo
    echo "手动测试："
    echo
    echo "  ${COLLECTOR_TARGET}"
    echo
}


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

main() {

    log "开始安装 SmartOpsAgent Monitor。"

    require_root

    check_os

    check_dependencies

    check_source_files

    create_install_directory

    install_collector

    create_version_file

    test_collector

    show_result

    log "安装成功。"

}


main "$@"