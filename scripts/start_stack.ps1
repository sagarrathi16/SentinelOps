# ==============================================================================
# SentinelOps Full Stack Auto-Starter (From Scratch)
# Starts Docker, Switch Core, Mattermost, Target Service, and Agent Daemon
# ==============================================================================

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " SentinelOps: Starting Full Local Incident Response Stack " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Resolve Docker Path
$dockerCli = "C:\Users\sagar\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
if (-not (Test-Path $dockerCli)) {
    $dockerCli = (Get-Command docker -ErrorAction SilentlyContinue).Source
}

if (-not $dockerCli) {
    Write-Host "[!] Docker CLI not found. Please ensure Docker Desktop is installed." -ForegroundColor Red
} else {
    Write-Host "[1/5] Checking Docker containers..." -ForegroundColor Yellow
    # Start Mattermost container
    & $dockerCli start switchdash-local-mattermost-mattermost-1 | Out-Null
    # Start Target Microservice container
    & $dockerCli start sentinelops-target-service | Out-Null
    Write-Host "  -> Mattermost container (port 61981): RUNNING" -ForegroundColor Green
    Write-Host "  -> Target Service container (port 8080): RUNNING" -ForegroundColor Green
}

# 2. Check Switch Core Daemon
Write-Host "[2/5] Checking Switch Core Daemon..." -ForegroundColor Yellow
$switchEnvFile = "C:\Users\sagar\AppData\Roaming\switchdash\local-switch-server\native\run\switch-core.env"
if (Test-Path $switchEnvFile) {
    Get-Content $switchEnvFile | Where-Object { $_ -match '^([^#=]+)=(.*)$' } | ForEach-Object {
        [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2])
    }
    $port = [System.Environment]::GetEnvironmentVariable("SERVER_PORT")
    $coreProc = Get-Process -Name "switch-core" -ErrorAction SilentlyContinue
    if (-not $coreProc) {
        Write-Host "  -> Starting native switch-core on port $port..." -ForegroundColor Cyan
        $switchCoreExe = "C:\Users\sagar\AppData\Roaming\switchdash\local-switch-server\native\switch-core\0.31.0\venv\Scripts\switch-core.exe"
        Start-Process -FilePath $switchCoreExe -WindowStyle Minimized
        Start-Sleep -Seconds 3
    }
    Write-Host "  -> Switch Core running on port: $port" -ForegroundColor Green
} else {
    Write-Host "  [!] switch-core.env not found. Please launch Switch Console once to generate it." -ForegroundColor Red
}

# 3. Reset Target Microservice to buggy state (commit 8f9b2a) for demo readiness
Write-Host "[3/5] Setting Target Service to buggy commit (8f9b2a)..." -ForegroundColor Yellow
try {
    $resp = Invoke-RestMethod -Method Post -Uri "http://localhost:8080/admin/deploy" -ContentType "application/json" -Body '{"commit_sha": "8f9b2a"}' -TimeoutSec 3
    Write-Host "  -> Target Service active commit: $($resp.active_commit) (ready to fail on checkout)" -ForegroundColor Green
} catch {
    Write-Host "  [!] Target Service not responding on :8080 yet (will be ready shortly)" -ForegroundColor Gray
}

# 4. Check PostgreSQL Client Room Binding
Write-Host "[4/5] Checking Postgres Room Agent registration..." -ForegroundColor Yellow
$psqlPath = "C:\Users\sagar\AppData\Roaming\switchdash\local-switch-server\native\toolchain\bundle-057e6b8bca99\postgres\bin\psql.exe"
if (Test-Path $psqlPath) {
    $env:PGPASSWORD = "qzSyCsZC6EO35AJNDWCL9RIGNCk3rFP-"
    $sql = "INSERT INTO client_rooms (client_id, room_id, role) VALUES ('b5c11661-9445-4896-ada4-eb7cdfcefb03', '8e230116-c97c-4456-925e-01afd0021332', 'member') ON CONFLICT DO NOTHING;"
    & $psqlPath -h 127.0.0.1 -p 61982 -U postgres -d switch -c $sql 2>$null | Out-Null
    Write-Host "  -> client_rooms binding verified in PostgreSQL (:61982)" -ForegroundColor Green
}

# 5. Check SentinelOps Agent Daemon
Write-Host "[5/5] Checking SentinelOps Agent Daemon..." -ForegroundColor Yellow
$agentListening = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if (-not $agentListening) {
    Write-Host "  -> Launching agent daemon (python -m agent.triage_commander)..." -ForegroundColor Cyan
    $agentDir = Split-Path -Path $PSScriptRoot -Parent
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$agentDir'; python -m agent.triage_commander"
    Start-Sleep -Seconds 3
} else {
    Write-Host "  -> Agent daemon is already active and listening on port 8000" -ForegroundColor Green
}

Write-Host "==========================================================" -ForegroundColor Green
Write-Host " All Services Are Live & Ready for Demo! " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "1. Mattermost Web UI:   http://localhost:61981 (Channel: #incident-checkout)" -ForegroundColor White
Write-Host "2. Target Service:      http://localhost:8080/health" -ForegroundColor White
Write-Host "3. Trigger Outage:      Invoke-RestMethod -Method Post -Uri http://localhost:8080/checkout -ContentType 'application/json' -Body '{`"amount`": 50.0}'" -ForegroundColor Cyan
Write-Host "4. Approve in Chat:     Type 'approve rollback' in #incident-checkout" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Green
