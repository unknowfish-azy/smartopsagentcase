#!/usr/bin/env bash

set -Eeuo pipefail

# ============================================================
# SmartOpsAgent Deployment Script
#
# 用途：
#   Linux 服务器部署 SmartOpsAgent
#
# 流程：
#   1. 检查部署环境
#   2. 备份当前版本
#   3. 部署新版本
#   4. 启动 Docker 服务
#   5. 执行健康检查
#   6. 清理旧备份
#
# 使用：
#   chmod +x deploy.sh
#   ./deploy.sh
#
# 可通过环境变量覆盖默认路径：
#   APP_DIR=/opt/smartops ./deploy.sh
# ============================================================


APP_NAME="${APP_NAME:-smartops-agent}"

APP_DIR="${APP_DIR:-/opt/smartops}"

BACKUP_DIR="${BACKUP_DIR:-/opt/smartops-backups}"

RELEASE_DIR="${RELEASE_DIR:-${APP_DIR}/release}"

COMPOSE_FILE="${COMPOSE_FILE:-${APP_DIR}/docker-compose.yml}"

HEALTH_URL="${HEALTH_URL:-http://127.0.0.1/health}"

MAX_HEALTH_RETRIES="${MAX_HEALTH_RETRIES:-30}"

HEALTH_INTERVAL="${HEALTH_INTERVAL:-2}"

TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"

BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"


# ============================================================
# 日志
# ============================================================

log() {
    echo "[SmartOps][$(date '+%Y-%m-%d %H:%M:%S')] $*"
}


error() {
    echo "[SmartOps][ERROR][$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2
}


# ============================================================
# 错误处理
# ============================================================

on_error() {
    local exit_code=$?

    error "部署过程中发生错误，退出码：${exit_code}"

    error "如果当前版本不可用，请执行："

    error "  cd ${APP_DIR}"

    error "  rollback.sh"

    exit "${exit_code}"
}

trap on_error ERR


# ============================================================
# 检查命令
# ============================================================

require_command() {

    local command_name="$1"

    if ! command -v "${command_name}" >/dev/null 2>&1; then

        error "未找到必要命令：${command_name}"

        exit 1

    fi
}


# ============================================================
# 检查环境
# ============================================================

check_environment() {

    log "检查部署环境"

    require_command docker

    require_command curl

    require_command cp

    require_command mkdir

    require_command find

    if ! docker compose version >/dev/null 2>&1; then

        error "当前 Docker 未提供 docker compose 命令"

        error "请安装 Docker Compose Plugin"

        exit 1

    fi

    mkdir -p "${APP_DIR}"

    mkdir -p "${BACKUP_DIR}"

    log "APP_DIR=${APP_DIR}"

    log "BACKUP_DIR=${BACKUP_DIR}"

    log "RELEASE_DIR=${RELEASE_DIR}"

    log "COMPOSE_FILE=${COMPOSE_FILE}"

    log "HEALTH_URL=${HEALTH_URL}"
}


# ============================================================
# 检查部署文件
# ============================================================

check_deployment_files() {

    log "检查部署文件"

    if [[ ! -d "${RELEASE_DIR}" ]]; then

        error "Release 目录不存在：${RELEASE_DIR}"

        exit 1

    fi

    if [[ ! -f "${COMPOSE_FILE}" ]]; then

        log "未发现 Docker Compose 文件：${COMPOSE_FILE}"

        log "本次只执行 release 部署"

        return 0

    fi

    log "Docker Compose 文件检查通过"
}


# ============================================================
# 备份当前版本
# ============================================================

backup_current_release() {

    if [[ ! -d "${RELEASE_DIR}" ]]; then

        log "当前没有旧版本，跳过备份"

        return 0

    fi

    log "备份当前版本"

    mkdir -p "${BACKUP_PATH}"

    cp -a \
        "${RELEASE_DIR}" \
        "${BACKUP_PATH}/release"

    log "当前版本已经备份到：${BACKUP_PATH}"
}


# ============================================================
# 部署 Release
# ============================================================

deploy_release() {

    log "开始部署 Release"

    # 当前脚本假设 release 目录已经准备完成。
    #
    # 如果以后使用：
    #
    #   Git
    #   Docker Registry
    #   CI/CD
    #   Jenkins
    #
    # 可以在这里增加下载/拉取新版本代码的步骤。

    if [[ ! -d "${RELEASE_DIR}" ]]; then

        error "Release 目录不存在"

        exit 1

    fi

    log "Release 已准备：${RELEASE_DIR}"
}


# ============================================================
# 启动 Docker 服务
# ============================================================

start_services() {

    if [[ ! -f "${COMPOSE_FILE}" ]]; then

        log "没有 Docker Compose 文件，跳过 Docker 服务启动"

        return 0

    fi

    log "启动 Docker 服务"

    cd "${APP_DIR}"

    docker compose \
        -f "${COMPOSE_FILE}" \
        up -d \
        --remove-orphans

    log "Docker 服务启动命令执行完成"
}


# ============================================================
# 显示服务状态
# ============================================================

show_service_status() {

    if [[ ! -f "${COMPOSE_FILE}" ]]; then

        return 0

    fi

    cd "${APP_DIR}"

    log "当前 Docker 服务状态"

    docker compose \
        -f "${COMPOSE_FILE}" \
        ps
}


# ============================================================
# 健康检查
# ============================================================

health_check() {

    log "开始健康检查"

    local retry=0

    while (( retry < MAX_HEALTH_RETRIES )); do

        if curl \
            --silent \
            --show-error \
            --fail \
            --max-time 5 \
            "${HEALTH_URL}" \
            >/dev/null 2>&1; then

            log "健康检查成功"

            return 0

        fi

        retry=$((retry + 1))

        log "健康检查失败，第 ${retry}/${MAX_HEALTH_RETRIES} 次重试"

        sleep "${HEALTH_INTERVAL}"

    done

    error "健康检查失败"

    return 1
}


# ============================================================
# 清理旧备份
# ============================================================

cleanup_old_backups() {

    log "清理 7 天以前的备份"

    find "${BACKUP_DIR}" \
        -mindepth 1 \
        -maxdepth 1 \
        -type d \
        -mtime +7 \
        -print \
        -exec rm -rf {} \;

    log "旧备份清理完成"
}


# ============================================================
# 输出部署结果
# ============================================================

show_result() {

    echo
    echo "============================================================"
    echo " SmartOpsAgent 部署完成"
    echo "============================================================"
    echo "应用名称：${APP_NAME}"
    echo "应用目录：${APP_DIR}"
    echo "Release：${RELEASE_DIR}"
    echo "备份目录：${BACKUP_DIR}"
    echo "健康检查：${HEALTH_URL}"
    echo "============================================================"
    echo
}


# ============================================================
# 主流程
# ============================================================

main() {

    log "开始部署 ${APP_NAME}"

    check_environment

    check_deployment_files

    backup_current_release

    deploy_release

    start_services

    show_service_status

    health_check

    cleanup_old_backups

    show_result

    log "部署成功"
}


main "$@"