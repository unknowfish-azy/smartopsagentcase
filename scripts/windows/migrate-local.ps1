# [已废弃] 后端 schema 已由 Flyway 接管（启动时按 db/migration 版本执行并记录
# flyway_schema_history），本脚本仅保留用于 Flyway 接入前的历史库手工兜底，
# 新环境不要再执行；需要补建/升级请直接启动后端或运行 mvn flyway:migrate。
param(
    [string]$MysqlBin = 'C:\Program Files\MySQL\MySQL Server 8.0\bin',
    [string]$Database = 'smartops'
)

$ErrorActionPreference = 'Stop'
if ($Database -notmatch '^[A-Za-z0-9_]+$') { throw 'Invalid database name' }
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$mysql = Join-Path $MysqlBin 'mysql.exe'
$dump = Join-Path $MysqlBin 'mysqldump.exe'
$versions = @('V20261002__operations_and_accounts', 'V002__admin_foundation', 'V003__registration_policy', 'V004__assistant_preference', 'V005__admin_mfa', 'V006__team_workspace', 'V007__chat_attachments')
$config = @{}
Get-Content -LiteralPath (Join-Path $root '.env') -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $config[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'") }
}
$username = if ($env:MYSQL_USERNAME) { $env:MYSQL_USERNAME } else { $config['MYSQL_USERNAME'] }
$password = if ($env:MYSQL_PASSWORD) { $env:MYSQL_PASSWORD } else { $config['MYSQL_PASSWORD'] }
if (!$username -or !$password) { throw 'Configure MYSQL_USERNAME and MYSQL_PASSWORD before migration' }
$arguments = @('--host=127.0.0.1', '--port=3306', "--user=$username", '--default-character-set=utf8mb4')
$previousPassword = $env:MYSQL_PWD
try {
    $env:MYSQL_PWD = $password
    $backupDirectory = Join-Path $root '.runtime\backups'
    [System.IO.Directory]::CreateDirectory($backupDirectory) | Out-Null
    $backup = Join-Path $backupDirectory "$Database-$(Get-Date -Format 'yyyyMMdd-HHmmss-fff').sql"
    & $dump @arguments --single-transaction --routines --triggers --events --no-tablespaces --set-gtid-purged=OFF "--result-file=$backup" $Database
    if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $backup) -or (Get-Item -LiteralPath $backup).Length -eq 0) { throw 'Database backup failed; migration was not started' }
    Write-Output "Backup completed: $backup"
    & $mysql @arguments "--database=$Database" --execute='CREATE TABLE IF NOT EXISTS smartops_schema_migration (version VARCHAR(96) PRIMARY KEY, checksum VARCHAR(64) NOT NULL, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot initialize migration ledger' }
    foreach ($version in $versions) {
        $migration = Join-Path $root "backend\src\main\resources\db\migration\$version.sql"
        $hash = (Get-FileHash -LiteralPath $migration -Algorithm SHA256).Hash.ToLowerInvariant()
        $existing = & $mysql @arguments "--database=$Database" --batch --skip-column-names "--execute=SELECT checksum FROM smartops_schema_migration WHERE version='$version'"
        if ($LASTEXITCODE -ne 0) { throw 'Cannot read migration ledger' }
        if ($existing) {
            if ($existing.Trim() -ne $hash) { throw 'Applied migration checksum differs; refusing to overwrite history' }
            Write-Output "Migration $version already applied with matching checksum"
            continue
        }
        $sourcePath = $migration.Replace('\', '/')
        & $mysql @arguments "--database=$Database" "--execute=source $sourcePath"
        if ($LASTEXITCODE -ne 0) { throw 'Migration failed; retain the backup and inspect the error before retrying' }
        & $mysql @arguments "--database=$Database" "--execute=INSERT INTO smartops_schema_migration(version,checksum) VALUES('$version','$hash')"
        if ($LASTEXITCODE -ne 0) { throw 'Migration ran but could not be recorded' }
        Write-Output "Migration applied: $version"
    }
} finally { $env:MYSQL_PWD = $previousPassword }
