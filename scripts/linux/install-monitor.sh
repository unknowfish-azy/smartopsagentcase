#!/usr/bin/env bash

set -Eeuo pipefail


# ============================================================
# SmartOpsAgent Monitor Installer
# ============================================================


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COLLECTOR="${SCRIPT_DIR}/collect-metrics.sh"

INSTALL_DIR="${INSTALL_DIR:-/opt/smartops-monitor}"

BIN_PATH="${INSTALL_DIR}/collect-metrics.sh"


log() {

    echo "[SmartOps Monitor] $(date '+%Y-%m-%d %H:%M:%S') $*"

}


error() {

    echo "[SmartOps Monitor][ERROR] $*" >&2

}


require_root() {

    if [[ "${EUID}" -ne 0 ]]; then

        error "该安装脚本需要 root 权限"

        error "请使用 sudo 执行"

        exit 1

    fi

}


check_environment() {

    log "检查 Linux 环境"

    command -v bash >/dev/null 2>&1 || {
        error "未找到 bash"
        exit 1
    }

    command -v top >/dev/null 2>&1 || {
        error "未找到 top"
        exit 1
    }

    command -v free >/dev/null 2>&1 || {
        error "未找到 free"
        exit 1
    }

    command -v df >/dev/null 2>&1 || {
        error "未找到 df"
        exit 1
    }

    command -v awk >/dev/null 2>&1 || {
        error "未找到 awk"
        exit 1
    }

}


install_collector() {

    log "创建安装目录"

    mkdir -p "${INSTALL_DIR}"

    if [[ ! -f "${COLLECTOR}" ]]; then

        error "找不到采集脚本：${COLLECTOR}"

        exit 1

    fi

    cp "${COLLECTOR}" "${BIN_PATH}"

    chmod 755 "${BIN_PATH}"

    log "监控采集器安装完成：${BIN_PATH}"

}


test_collector() {

    log "执行采集器测试"

    if "${BIN_PATH}" >/dev/null; then

        log "采集器运行正常"

    else

        error "采集器测试失败"

        exit 1

    fi

}


main() {

    require_root

    check_environment
    install_collector
    test_collector

    log "SmartOpsAgent Monitor 安装完成"

}


main "$@"