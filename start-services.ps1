$ErrorActionPreference = 'Stop'

$logDir = Join-Path -Path $PSScriptRoot -ChildPath 'logs'
$configPath = '.\config\sample_healthcare.yaml'

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
        ErrorLogFile = Join-Path -Path $logDir -ChildPath 'data_reader.err.log'
    },
    @{
        Name = 'Data Classifier'
        Port = 5002
        Script = 'data_classifier_service.py'
        LogFile = Join-Path -Path $logDir -ChildPath 'data_classifier.log'
        ErrorLogFile = Join-Path -Path $logDir -ChildPath 'data_classifier.err.log'
    },
    @{
        Name = 'Orchestrator'
        Port = 5000
        Script = 'orchestrator_service.py'
        LogFile = Join-Path -Path $logDir -ChildPath 'orchestrator.log'
        ErrorLogFile = Join-Path -Path $logDir -ChildPath 'orchestrator.err.log'
    }
)

foreach ($service in $services) {
    Write-Host ("Starting {0} Service (port {1})..." -f $service.Name, $service.Port)

    Start-Process `
        -FilePath 'python' `
        -ArgumentList @($service.Script, $service.Port, '--config', $configPath) `
        -WorkingDirectory $PSScriptRoot `
        -WindowStyle Normal `
        -RedirectStandardOutput $service.LogFile `
        -RedirectStandardError $service.ErrorLogFile | Out-Null
}

Write-Host ''
Write-Host 'All services started as separate python processes.'
Write-Host ('Logs available in: {0}' -f $logDir)
Write-Host 'Stdout logs: data_reader.log, data_classifier.log, orchestrator.log'
Write-Host 'Stderr logs: data_reader.err.log, data_classifier.err.log, orchestrator.err.log'
Write-Host ''
Write-Host 'Test with:'
Write-Host '  curl -X POST http://localhost:5000/analyze -H "Content-Type: application/json" -d "{"schema": "public", "config_path": "config/sample_healthcare.yaml"}"'