$ErrorActionPreference = 'Continue'
Get-Process -Name SLDWORKS -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3
Write-Output 'cleanup done'
Get-Process -Name SLDWORKS,python -ErrorAction SilentlyContinue | Select-Object Id,ProcessName
