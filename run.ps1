$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 start.py } else { & python start.py }
exit $LASTEXITCODE
