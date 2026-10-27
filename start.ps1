# Start the local dashboard from any working directory.
$ErrorActionPreference = 'Stop'
$appEntry = Join-Path $PSScriptRoot 'app/frontend.py'
& python $appEntry @args
exit $LASTEXITCODE
