$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$ollamaBinary = Join-Path $projectPath '.local\ollama\ollama.exe'
if (-not (Test-Path -LiteralPath $ollamaBinary)) {
    $command = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $command) { throw 'Install Ollama from https://ollama.com/download/windows first.' }
    $ollamaBinary = $command.Source
}
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MODELS = Join-Path $projectPath '.local\models'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_CONTEXT_LENGTH = '8192'
New-Item -ItemType Directory -Force (Join-Path $projectPath '.local') | Out-Null
try {
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
    Write-Host 'An Ollama server is already running; using that server and its model store.'
} catch {
    $process = Start-Process -FilePath $ollamaBinary -ArgumentList 'serve' -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $projectPath '.local\ollama.out.log') `
        -RedirectStandardError (Join-Path $projectPath '.local\ollama.err.log')
    $process.Id | Set-Content -LiteralPath (Join-Path $projectPath '.local\ollama.pid')
    Start-Sleep -Seconds 3
}
& $ollamaBinary pull qwen3:4b
if ($LASTEXITCODE -ne 0) { throw 'Model download failed. Check the Ollama log and connection.' }
Write-Host 'Local model ready. Run run_windows.bat to start the web app.'
