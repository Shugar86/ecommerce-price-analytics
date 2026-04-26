<#
.SYNOPSIS
    Запуск/управление проектом через Docker Compose на Windows.

.DESCRIPTION
    Скрипт проверяет наличие Docker и Compose, создаёт .env из env.example (если .env отсутствует),
    затем выполняет команду docker compose для текущего проекта.

    Требования:
      - Docker Desktop установлен и запущен
      - PowerShell 5.1+ (или PowerShell 7+)

.EXAMPLE
    .\run.ps1 up

.EXAMPLE
    .\run.ps1 logs -Follow

.EXAMPLE
    .\run.ps1 logs -Service bot -Follow
#>

[CmdletBinding(PositionalBinding = $true)]
param(
    [Parameter(Position = 0)]
    [ValidateSet("up", "down", "stop", "restart", "logs", "ps", "build", "config", "reset-db")]
    [string]$Command = "up",

    [Parameter()]
    [string]$Service = "",

    [Parameter()]
    [switch]$Follow,

    [Parameter()]
    [switch]$Build
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) {
    Write-Host "[INFO] $Message"
}

function Write-Warn([string]$Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Err([string]$Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Команда '$Name' не найдена. Установите Docker Desktop: https://www.docker.com/products/docker-desktop/"
    }
}

function Test-Docker-Running() {
    try {
        docker info *> $null
        return $true
    } catch {
        return $false
    }
}

function Get-ComposeCommand() {
    try {
        docker compose version *> $null
        return @("docker", "compose")
    } catch {
        # fallback для старых установок
        try {
            docker-compose version *> $null
            return @("docker-compose")
        } catch {
            throw "Docker Compose не найден. Обновите Docker Desktop или установите Compose plugin."
        }
    }
}

function Ensure-EnvFile([string]$ProjectRoot) {
    $envPath = Join-Path $ProjectRoot ".env"
    $examplePath = Join-Path $ProjectRoot "env.example"

    if (Test-Path $envPath) {
        return
    }

    if (-not (Test-Path $examplePath)) {
        Write-Warn "Файл 'env.example' не найден. Пропускаю создание '.env'."
        return
    }

    Copy-Item -Path $examplePath -Destination $envPath -Force
    Write-Info "Создан '.env' из 'env.example'. Отредактируйте BOT_TOKEN перед запуском бота."
}

function Warn-If-Token-Placeholder([string]$ProjectRoot) {
    $envPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $envPath)) {
        return
    }

    $content = Get-Content -Path $envPath -ErrorAction Stop
    $tokenLine = $content | Where-Object { $_ -match "^\s*BOT_TOKEN\s*=" } | Select-Object -First 1
    if (-not $tokenLine) {
        Write-Warn "В '.env' нет BOT_TOKEN. Бот может не стартовать."
        return
    }

    if ($tokenLine -match "your_token_here_from_botfather" -or $tokenLine -match "^\s*BOT_TOKEN\s*=\s*$") {
        Write-Warn "BOT_TOKEN не задан (похоже на плейсхолдер). Вставьте токен от @BotFather в '.env'."
    }
}

function Invoke-Compose([string[]]$ComposeCmd, [string[]]$Args) {
    $display = ($ComposeCmd + $Args) -join " "
    Write-Info "Выполняю: $display"

    if ($ComposeCmd.Length -eq 1 -and $ComposeCmd[0] -eq "docker-compose") {
        & docker-compose @Args
    } else {
        & docker compose @Args
    }
}

try {
    $projectRoot = $PSScriptRoot
    Set-Location -Path $projectRoot

    Require-Command "docker"
    if (-not (Test-Docker-Running)) {
        throw "Docker не отвечает. Запустите Docker Desktop и попробуйте снова."
    }

    $composeCmd = Get-ComposeCommand

    $composeFile = Join-Path $projectRoot "docker-compose.yml"
    if (-not (Test-Path $composeFile)) {
        throw "Не найден 'docker-compose.yml' в '$projectRoot'."
    }

    Ensure-EnvFile -ProjectRoot $projectRoot
    Warn-If-Token-Placeholder -ProjectRoot $projectRoot

    switch ($Command) {
        "up" {
            $args = @("up", "-d")
            if ($Build) { $args += @("--build") }
            Invoke-Compose -ComposeCmd $composeCmd -Args $args
            Invoke-Compose -ComposeCmd $composeCmd -Args @("ps")
        }
        "down" {
            Invoke-Compose -ComposeCmd $composeCmd -Args @("down")
        }
        "stop" {
            Invoke-Compose -ComposeCmd $composeCmd -Args @("stop")
        }
        "restart" {
            if ([string]::IsNullOrWhiteSpace($Service)) {
                Invoke-Compose -ComposeCmd $composeCmd -Args @("restart")
            } else {
                Invoke-Compose -ComposeCmd $composeCmd -Args @("restart", $Service)
            }
        }
        "ps" {
            Invoke-Compose -ComposeCmd $composeCmd -Args @("ps")
        }
        "logs" {
            $args = @("logs")
            if ($Follow) { $args += @("-f") }
            if (-not [string]::IsNullOrWhiteSpace($Service)) { $args += @($Service) }
            Invoke-Compose -ComposeCmd $composeCmd -Args $args
        }
        "build" {
            $args = @("build")
            if (-not [string]::IsNullOrWhiteSpace($Service)) { $args += @($Service) }
            Invoke-Compose -ComposeCmd $composeCmd -Args $args
        }
        "config" {
            Invoke-Compose -ComposeCmd $composeCmd -Args @("config")
        }
        "reset-db" {
            Write-Warn "Это удалит volume с данными PostgreSQL (postgres_data)."
            Write-Info "Если вы уверены — выполните: docker compose down -v"
            Write-Info "Я не делаю это автоматически, чтобы не снести данные случайно."
            exit 2
        }
        default {
            throw "Неизвестная команда: $Command"
        }
    }
} catch {
    Write-Err $_.Exception.Message
    exit 1
}


