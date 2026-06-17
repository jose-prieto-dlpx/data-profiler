$ErrorActionPreference = 'Stop'

$logDir = Join-Path -Path $PSScriptRoot -ChildPath 'logs'

if (-not (Test-Path -Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

Write-Host 'Starting Distributed Data Classification Pipeline...'
Write-Host ''

$services = @(
    @{
        Name = 'Data Reader'
        Port = 5001
        Script = 'data_reader_service.py'
        LogFile = Join-Path -Path $logDir -ChildPath 'data_reader.log'
    },
    @{
        Name = 'Data Classifier'
        Port = 5002
        Script = 'data_classifier_service.py'
        LogFile = Join-Path -Path $logDir -ChildPath 'data_classifier.log'
    },
    @{
        Name = 'Orchestrator'
        Port = 5000
        Script = 'orchestrator_service.py'
        LogFile = Join-Path -Path $logDir -ChildPath 'orchestrator.log'
    }
)

foreach ($service in $services) {
    Write-Host ("Starting {0} Service (port {1})..." -f $service.Name, $service.Port)

    $command = "Set-Location -LiteralPath '$PSScriptRoot'; python $($service.Script) $($service.Port) > '$($service.LogFile)' 2>&1"
    Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoExit', '-Command', $command -WindowStyle Normal | Out-Null
}

Write-Host ''
Write-Host 'All services started in separate windows.'
Write-Host ('Logs available in: {0}' -f $logDir)
Write-Host ''
Write-Host 'Test with:'
Write-Host '  curl -X POST http://localhost:5000/analyze -H "Content-Type: application/json" -d "{"schema": "public"}"'