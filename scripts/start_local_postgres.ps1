[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$WebPort = 8002,

    [string]$LegacyDatabaseName = 'emporium_current',

    [ValidateRange(1024, 65535)]
    [int]$LegacyPostgresPort = 55432
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot 'venv\Scripts\python.exe'
$composeFile = Join-Path $projectRoot 'compose.local.yml'
$dockerEnvFile = Join-Path $projectRoot '.env.docker.local'

function Read-LocalEnvironmentFile {
    param([Parameter(Mandatory)][string]$Path)

    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) {
            continue
        }
        $parts = $trimmed -split '=', 2
        if ($parts.Count -eq 2) {
            $values[$parts[0].Trim()] = $parts[1].Trim()
        }
    }
    return $values
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project Python was not found at $python"
}
if (-not (Test-Path -LiteralPath $dockerEnvFile)) {
    throw 'Create .env.docker.local from .env.docker.example and replace both example passwords.'
}

$localEnvironment = Read-LocalEnvironmentFile -Path $dockerEnvFile
$requiredNames = @(
    'LOCAL_POSTGRES_DB',
    'LOCAL_POSTGRES_USER',
    'LOCAL_POSTGRES_PASSWORD',
    'LOCAL_POSTGRES_PORT',
    'LOCAL_REDIS_PASSWORD',
    'LOCAL_REDIS_PORT'
)
foreach ($name in $requiredNames) {
    if (-not $localEnvironment[$name] -or $localEnvironment[$name] -like 'replace-with-*') {
        throw "$name must contain a real local-only value in .env.docker.local."
    }
}

Push-Location $projectRoot
try {
    docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Desktop is not running. Start Docker Desktop and wait for its engine.'
    }

    docker inspect emporium-sandbox-postgres 2>$null | Out-Null
    $usesLegacyPostgres = $LASTEXITCODE -eq 0
    if ($usesLegacyPostgres) {
        docker start emporium-sandbox-postgres | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'The preserved PostgreSQL migration container could not be started.'
        }
    }
    else {
        docker compose --env-file $dockerEnvFile -f $composeFile up -d --wait postgres
        if ($LASTEXITCODE -ne 0) {
            throw 'The local PostgreSQL service could not be started.'
        }
    }

    # Redis contains disposable coordination data, so use the reproducible
    # authenticated Compose service rather than an older unauthenticated container.
    docker compose --env-file $dockerEnvFile -f $composeFile up -d --wait redis
    if ($LASTEXITCODE -ne 0) {
        throw 'The local Redis service could not be started.'
    }

    if ($usesLegacyPostgres) {
        $container = docker inspect emporium-sandbox-postgres | ConvertFrom-Json
        $containerEnvironment = $container[0].Config.Env
        $passwordEntry = $containerEnvironment | Where-Object { $_ -match '^POSTGRES_PASSWORD=' }
        $userEntry = $containerEnvironment | Where-Object { $_ -match '^POSTGRES_USER=' }
        if (-not $passwordEntry -or -not $userEntry) {
            throw 'The preserved PostgreSQL container is missing its local credentials.'
        }
        $postgresPassword = [Uri]::EscapeDataString(($passwordEntry -split '=', 2)[1])
        $postgresUser = [Uri]::EscapeDataString(($userEntry -split '=', 2)[1])
        $postgresDatabase = [Uri]::EscapeDataString($LegacyDatabaseName)
        $postgresPort = $LegacyPostgresPort
    }
    else {
        $postgresPassword = [Uri]::EscapeDataString($localEnvironment['LOCAL_POSTGRES_PASSWORD'])
        $postgresUser = [Uri]::EscapeDataString($localEnvironment['LOCAL_POSTGRES_USER'])
        $postgresDatabase = [Uri]::EscapeDataString($localEnvironment['LOCAL_POSTGRES_DB'])
        $postgresPort = $localEnvironment['LOCAL_POSTGRES_PORT']
    }
    $redisPassword = [Uri]::EscapeDataString($localEnvironment['LOCAL_REDIS_PASSWORD'])
    $redisPort = $localEnvironment['LOCAL_REDIS_PORT']

    $env:DATABASE_URL = (
        "postgresql://${postgresUser}:$postgresPassword" +
        "@127.0.0.1:$postgresPort/$postgresDatabase"
    )
    $env:DATABASE_CONN_MAX_AGE = '0'
    $env:REDIS_URL = "redis://:$redisPassword@127.0.0.1:$redisPort/1"
    $env:ENVIRONMENT = 'development'

    Write-Host 'Applying pending PostgreSQL migrations...' -ForegroundColor Cyan
    & $python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) {
        throw 'Django migrations failed; the website was not started.'
    }

    & $python manage.py check
    if ($LASTEXITCODE -ne 0) {
        throw 'Django system checks failed; the website was not started.'
    }

    Write-Host 'PostgreSQL and Redis are ready.' -ForegroundColor Green
    Write-Host "Open http://127.0.0.1:$WebPort/ and keep this terminal running."
    & $python manage.py runserver "127.0.0.1:$WebPort" --noreload
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
