# ============================================================
# SmartOpsAgent Windows Development Environment Check
#
# 用途：
#   检查 SmartOpsAgent 本地 Windows 开发环境。
#
# 检查项目：
#   Java
#   Maven
#   Node.js
#   npm
#   Python
#   Git
#   Docker
#
# 同时输出主要版本信息。
# 不修改系统环境变量。
# ============================================================

$ErrorActionPreference = "Continue"

$script:HasError = $false


# ============================================================
# 输出工具
# ============================================================

function Write-CheckOk {
    param (
        [string]$Name,
        [string]$Message
    )

    Write-Host "[OK]      $Name - $Message" -ForegroundColor Green
}


function Write-CheckWarn {
    param (
        [string]$Name,
        [string]$Message
    )

    Write-Host "[WARNING] $Name - $Message" -ForegroundColor Yellow
}


function Write-CheckError {
    param (
        [string]$Name,
        [string]$Message
    )

    Write-Host "[ERROR]   $Name - $Message" -ForegroundColor Red

    $script:HasError = $true
}


# ============================================================
# 检查命令是否存在
# ============================================================

function Test-CommandExists {
    param (
        [Parameter(Mandatory = $true)]
        [string]$CommandName
    )

    $command = Get-Command `
        $CommandName `
        -ErrorAction SilentlyContinue

    return $null -ne $command
}


# ============================================================
# 获取命令版本
# ============================================================

function Get-CommandVersion {
    param (
        [Parameter(Mandatory = $true)]
        [string]$CommandName,

        [string[]]$Arguments = @("--version")
    )

    try {

        $output = & $CommandName @Arguments 2>&1

        if ($null -eq $output) {
            return "未知"
        }

        $text = (
            $output |
            Out-String
        ).Trim()

        if ([string]::IsNullOrWhiteSpace($text)) {
            return "未知"
        }

        return $text.Split(
            [Environment]::NewLine
        )[0]

    }
    catch {

        return "无法读取版本"
    }
}


# ============================================================
# Java 检查
# ============================================================

function Test-Java {

    if (-not (Test-CommandExists "java")) {

        Write-CheckError `
            "Java" `
            "未找到 java 命令"

        return
    }

    $version = Get-CommandVersion `
        "java" `
        @("-version")

    Write-CheckOk `
        "Java" `
        $version


    if ($env:JAVA_HOME) {

        if (Test-Path $env:JAVA_HOME) {

            Write-CheckOk `
                "JAVA_HOME" `
                $env:JAVA_HOME

        }
        else {

            Write-CheckWarn `
                "JAVA_HOME" `
                "目录不存在：$env:JAVA_HOME"
        }

    }
    else {

        Write-CheckWarn `
            "JAVA_HOME" `
            "未设置"

    }
}


# ============================================================
# Maven 检查
# ============================================================

function Test-Maven {

    if (-not (Test-CommandExists "mvn")) {

        Write-CheckError `
            "Maven" `
            "未找到 mvn 命令"

        return
    }

    $version = Get-CommandVersion "mvn"

    Write-CheckOk `
        "Maven" `
        $version
}


# ============================================================
# Node.js
# ============================================================

function Test-Node {

    if (-not (Test-CommandExists "node")) {

        Write-CheckError `
            "Node.js" `
            "未找到 node 命令"

        return
    }

    $version = Get-CommandVersion `
        "node" `
        @("--version")

    Write-CheckOk `
        "Node.js" `
        $version
}


# ============================================================
# npm
# ============================================================

function Test-Npm {

    if (-not (Test-CommandExists "npm")) {

        Write-CheckError `
            "npm" `
            "未找到 npm 命令"

        return
    }

    $version = Get-CommandVersion `
        "npm" `
        @("--version")

    Write-CheckOk `
        "npm" `
        "version $version"
}


# ============================================================
# Python
# ============================================================

function Test-Python {

    if (Test-CommandExists "python") {

        $version = Get-CommandVersion `
            "python" `
            @("--version")

        Write-CheckOk `
            "Python" `
            $version

        return
    }


    if (Test-CommandExists "py") {

        $version = Get-CommandVersion `
            "py" `
            @("--version")

        Write-CheckOk `
            "Python Launcher" `
            $version

        return
    }


    Write-CheckError `
        "Python" `
        "未找到 python 或 py 命令"
}


# ============================================================
# Git
# ============================================================

function Test-Git {

    if (-not (Test-CommandExists "git")) {

        Write-CheckError `
            "Git" `
            "未找到 git 命令"

        return
    }

    $version = Get-CommandVersion "git"

    Write-CheckOk `
        "Git" `
        $version
}


# ============================================================
# Docker
# ============================================================

function Test-Docker {

    if (-not (Test-CommandExists "docker")) {

        Write-CheckError `
            "Docker" `
            "未找到 docker 命令"

        return
    }

    $version = Get-CommandVersion "docker"

    Write-CheckOk `
        "Docker" `
        $version


    try {

        docker info *> $null

        if ($LASTEXITCODE -eq 0) {

            Write-CheckOk `
                "Docker Engine" `
                "Docker Engine 正常运行"

        }
        else {

            Write-CheckWarn `
                "Docker Engine" `
                "Docker 命令存在，但 Docker Engine 未正常运行"
        }

    }
    catch {

        Write-CheckWarn `
            "Docker Engine" `
            "无法检查 Docker Engine 状态"
    }


    if (Test-CommandExists "docker") {

        try {

            $composeVersion = (
                docker compose version 2>&1
            )

            if (($LASTEXITCODE -eq 0) -and $composeVersion) {

                Write-CheckOk `
                    "Docker Compose" `
                    $composeVersion

            }
            else {

                Write-CheckWarn `
                    "Docker Compose" `
                    "docker compose 不可用"
            }

        }
        catch {

            Write-CheckWarn `
                "Docker Compose" `
                "无法读取 Docker Compose 版本"
        }
    }
}


# ============================================================
# 项目目录检查
# ============================================================

function Test-ProjectDirectories {

    $scriptRoot = Split-Path `
        -Parent `
        $PSScriptRoot

    $projectRoot = Split-Path `
        -Parent `
        $scriptRoot


    Write-Host ""
    Write-Host "--------------------------------------------"
    Write-Host "Project Directory"
    Write-Host "--------------------------------------------"


    Write-Host "Project Root : $projectRoot"


    $requiredDirectories = @(
        "backend",
        "frontend",
        "ai-service",
        "agent",
        "knowledge",
        "deploy"
    )


    foreach ($directory in $requiredDirectories) {

        $path = Join-Path `
            $projectRoot `
            $directory

        if (Test-Path -Path $path -PathType Container) {

            Write-CheckOk `
                $directory `
                $path

        }
        else {

            Write-CheckWarn `
                $directory `
                "目录不存在：$path"
        }
    }
}


# ============================================================
# 环境变量
# ============================================================

function Show-EnvironmentVariables {

    Write-Host ""
    Write-Host "--------------------------------------------"
    Write-Host "Environment Variables"
    Write-Host "--------------------------------------------"


    if ($env:JAVA_HOME) {

        Write-Host "JAVA_HOME    : $env:JAVA_HOME"

    }
    else {

        Write-Host "JAVA_HOME    : <not set>"
    }


    if ($env:NODE_PATH) {

        Write-Host "NODE_PATH    : $env:NODE_PATH"

    }
    else {

        Write-Host "NODE_PATH    : <not set>"
    }


    if ($env:PYTHONPATH) {

        Write-Host "PYTHONPATH   : $env:PYTHONPATH"

    }
    else {

        Write-Host "PYTHONPATH   : <not set>"
    }


    if ($env:VITE_API_BASE_URL) {

        Write-Host `
            "VITE_API_BASE_URL : $env:VITE_API_BASE_URL"

    }
    else {

        Write-Host `
            "VITE_API_BASE_URL : <not set>"
    }
}


# ============================================================
# 开始检查
# ============================================================

Write-Host ""
Write-Host "============================================"
Write-Host " SmartOpsAgent Environment Check"
Write-Host "============================================"
Write-Host ""


Write-Host "PowerShell : $($PSVersionTable.PSVersion)"

Write-Host "OS         : $([System.Environment]::OSVersion.Version)"

Write-Host ""


# ============================================================
# 工具检查
# ============================================================

Write-Host "--------------------------------------------"
Write-Host "Development Tools"
Write-Host "--------------------------------------------"


Test-Java

Test-Maven

Test-Node

Test-Npm

Test-Python

Test-Git

Test-Docker


# ============================================================
# 项目目录
# ============================================================

Test-ProjectDirectories


# ============================================================
# 环境变量
# ============================================================

Show-EnvironmentVariables


# ============================================================
# Final Result
# ============================================================

Write-Host ""
Write-Host "============================================"


if ($script:HasError) {

    Write-Host `
        "[FAILED] 开发环境检查未通过。" `
        -ForegroundColor Red

    Write-Host ""

    Write-Host `
        "请根据上面的 ERROR 项目修复环境。"

    exit 1
}


Write-Host `
    "[SUCCESS] SmartOpsAgent 开发环境检查通过。" `
    -ForegroundColor Green

Write-Host ""

exit 0
