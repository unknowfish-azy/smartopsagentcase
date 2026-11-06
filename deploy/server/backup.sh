#!/usr/bin/env bash
# OPS-13：备份数据库、附件、知识 manifest、审计与密钥，并生成可复核清单。
#
# 只做"产生备份 + 生成清单"；异机副本是否真的可恢复，必须由隔离恢复演练验证，
# 复制成功不等于可恢复。恢复集合与演练记录通过后端 /api/backups 登记。
#
# 必需环境变量：
#   BACKUP_ROOT           本地备份根目录（建议独立磁盘或持久卷挂载点）
#   MYSQL_HOST MYSQL_USER MYSQL_DATABASE   数据库连接（密码走 MYSQL_PASSWORD，不落命令行）
#   ATTACHMENTS_DIR       附件目录（可恢复的目录备份；持久卷需另行快照）
#   AUDIT_DIR             审计导出目录
#   KEYS_DIR              密钥目录（备份到受控位置，umask 077）
#   KNOWLEDGE_MANIFEST_FILE 知识库 manifest 文件
#   SET_NAME              恢复集合名称（与后端登记一致）
# 可选：
#   MYSQL_PORT（默认 3306）、BACKUP_STAMP、RETENTION_DAYS（默认 14）、
#   OFFSITE_TARGET（rsync 可写的异机目标，例如 user@host:/backup/smartops）
set -euo pipefail
umask 077

require() {
  if [ -z "${!1:-}" ]; then
    echo "缺少环境变量 $1" >&2
    exit 2
  fi
}

for name in BACKUP_ROOT MYSQL_HOST MYSQL_USER MYSQL_DATABASE \
            ATTACHMENTS_DIR AUDIT_DIR KEYS_DIR KNOWLEDGE_MANIFEST_FILE SET_NAME; do
  require "$name"
done
if ! command -v mysqldump >/dev/null 2>&1; then
  echo "找不到 mysqldump，无法产生可恢复的数据库备份" >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "找不到 python3，无法生成备份清单" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_TOOL="$SCRIPT_DIR/../../scripts/backup/build_manifest.py"
STAMP="${BACKUP_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
DEST="$BACKUP_ROOT/$STAMP"
mkdir -p "$DEST"

echo "开始备份 $SET_NAME -> $DEST" >&2

# 一致性快照：单事务 + 不锁表；密码通过 MYSQL_PWD 传递，不出现在进程参数里。
MYSQL_PWD="${MYSQL_PASSWORD:-}" mysqldump \
  --single-transaction --quick --routines --triggers --events \
  --host="$MYSQL_HOST" --port="${MYSQL_PORT:-3306}" --user="$MYSQL_USER" \
  "$MYSQL_DATABASE" | gzip > "$DEST/database.sql.gz"

tar -czf "$DEST/attachments.tar.gz" -C "$ATTACHMENTS_DIR" .
tar -czf "$DEST/audit.tar.gz" -C "$AUDIT_DIR" .
tar -czf "$DEST/keys.tar.gz" -C "$KEYS_DIR" .
cp "$KNOWLEDGE_MANIFEST_FILE" "$DEST/knowledge.json"

# 清单对实际备份产物取 sha256：异机复制/落盘损坏都能在演练时发现。
python3 "$MANIFEST_TOOL" --set "$SET_NAME" --output "$DEST/manifest.json" \
  --component "DATABASE=$DEST/database.sql.gz" \
  --component "ATTACHMENTS=$DEST/attachments.tar.gz" \
  --component "KNOWLEDGE_MANIFEST=$DEST/knowledge.json" \
  --component "AUDIT=$DEST/audit.tar.gz" \
  --component "KEYS=$DEST/keys.tar.gz"

if [ -n "${OFFSITE_TARGET:-}" ]; then
  if ! command -v rsync >/dev/null 2>&1; then
    echo "配置了 OFFSITE_TARGET 但找不到 rsync" >&2
    exit 2
  fi
  rsync -a "$DEST/" "$OFFSITE_TARGET/$STAMP/"
  echo "已复制到异机 $OFFSITE_TARGET/$STAMP；该副本仍需通过恢复演练校验" >&2
fi

RETENTION_DAYS="${RETENTION_DAYS:-14}"
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+$RETENTION_DAYS" \
  -print -exec rm -rf -- {} + >&2

echo "备份完成：$DEST（保留 ${RETENTION_DAYS} 天）" >&2
